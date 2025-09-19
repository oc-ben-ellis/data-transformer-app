"""Lambda handler for processing transformation messages from data-pipeline-transform queue."""

from __future__ import annotations

import json
import os
from typing import Any

import structlog

from oc_pipeline_bus.bus import DataPipelineBus
from oc_pipeline_bus.identifiers import SnapshotId
from oc_pipeline_bus.config import DataPipelineConfig

from .transformer import Transformer

logger = structlog.get_logger(__name__)


class TransformerLambdaHandler:
    """Lambda handler for transformer service."""
    
    def __init__(self):
        """Initialize the lambda handler."""
        self.bus: DataPipelineBus | None = None
        self.transformer: Transformer | None = None
        self.config: dict[str, Any] | None = None
        self._initialized = False
    
    async def _initialize(self) -> None:
        """Initialize the transformer with configuration and pipeline bus."""
        if self._initialized:
            return
        
        try:
            # Initialize pipeline bus
            self.bus = DataPipelineBus()
            
            # Load YAML configuration
            pipeline_config = DataPipelineConfig()
            self.config = pipeline_config.load_config(
                dict,  # Load as plain dict for transformer
            )
            
            # Initialize transformer
            self.transformer = Transformer(self.config, self.bus)
            
            self._initialized = True
            logger.info("Transformer lambda handler initialized", data_registry_id=data_registry_id)
            
        except Exception as e:
            logger.exception("Failed to initialize transformer lambda handler", error=str(e))
            raise
    
    async def handle_sqs_event(self, event: dict[str, Any], context: Any) -> dict[str, Any]:
        """Handle SQS event containing transformation messages."""
        try:
            await self._initialize()
            
            # Process each record in the SQS event
            results = []
            for record in event.get("Records", []):
                try:
                    result = await self._process_record(record)
                    results.append(result)
                except Exception as e:
                    logger.exception("Failed to process record", record_id=record.get("messageId"), error=str(e))
                    results.append({
                        "recordId": record.get("messageId"),
                        "success": False,
                        "error": str(e)
                    })
            
            # Return results
            successful = sum(1 for r in results if r.get("success", False))
            failed = len(results) - successful
            
            logger.info(
                "Transformation batch completed",
                total=len(results),
                successful=successful,
                failed=failed
            )
            
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "Transformation completed",
                    "total": len(results),
                    "successful": successful,
                    "failed": failed,
                    "results": results
                })
            }
            
        except Exception as e:
            logger.exception("Failed to handle SQS event", error=str(e))
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "error": "Internal server error",
                    "message": str(e)
                })
            }
    
    async def _process_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Process a single SQS record."""
        try:
            # Parse the message body
            message_body = json.loads(record["body"])
            
            # Extract change event information
            change = message_body.get("change", {})
            if not change:
                raise ValueError("No change event found in message")
            
            # Get snapshot ID from the change event
            record_id = change.get("record_id", {})
            if not record_id:
                raise ValueError("No record_id found in change event")
            
            ocid = record_id.get("ocid")
            bid = record_id.get("bid")
            if not ocid or not bid:
                raise ValueError("Invalid record_id: missing ocid or bid")
            
            snapshot_id = SnapshotId(ocid=ocid, bid=bid)
            
            logger.info(
                "Processing transformation",
                ocid=ocid,
                bid=bid,
                stage=change.get("stage")
            )
            
            # Get staged data from pipeline bus
            staged_data = self.bus.get_snapshot_json(snapshot_id, stage="staged")
            
            # Check if already transformed (CDC check)
            try:
                existing_transformed = self.bus.get_snapshot_json(snapshot_id, stage="transformed")
                logger.info("Record already transformed, skipping", ocid=ocid, bid=bid)
                return {
                    "recordId": record.get("messageId"),
                    "success": True,
                    "skipped": True,
                    "reason": "Already transformed"
                }
            except Exception:
                # Not found, proceed with transformation
                pass
            
            # Transform the record
            result = self.transformer.transform_record(snapshot_id, staged_data)
            
            if not result.success:
                raise Exception(f"Transformation failed: {result.error_message}")
            
            if result.skipped:
                logger.info(
                    "Record skipped during transformation",
                    ocid=ocid,
                    bid=bid,
                    reason=result.skip_reason
                )
                return {
                    "recordId": record.get("messageId"),
                    "success": True,
                    "skipped": True,
                    "reason": result.skip_reason
                }
            
            # Store transformed data
            metadata = {
                "transformed_at": self.bus._utcnow_iso(),
                "transformer_version": "1.0",
                "source_stage": "staged"
            }
            
            self.bus.post_snapshot_json(snapshot_id, metadata, result.transformed_data)
            
            logger.info(
                "Record transformed successfully",
                ocid=ocid,
                bid=bid,
                fields_transformed=len(result.transformed_data) if result.transformed_data else 0
            )
            
            return {
                "recordId": record.get("messageId"),
                "success": True,
                "ocid": ocid,
                "bid": bid,
                "fields_transformed": len(result.transformed_data) if result.transformed_data else 0
            }
            
        except Exception as e:
            logger.exception("Failed to process record", record_id=record.get("messageId"), error=str(e))
            return {
                "recordId": record.get("messageId"),
                "success": False,
                "error": str(e)
            }


# Global handler instance
_handler = TransformerLambdaHandler()


async def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler entry point."""
    return await _handler.handle_sqs_event(event, context)
