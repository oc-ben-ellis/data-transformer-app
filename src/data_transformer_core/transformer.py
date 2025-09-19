"""Transformer service class for processing record transformation events."""

from __future__ import annotations

from typing import Any

import structlog

from oc_pipeline_bus.bus import DataPipelineBus
from oc_pipeline_bus.identifiers import SnapshotId

from data_transformer_core.engine import TransformEngine

logger = structlog.get_logger(__name__)


class Transformer:
    """Transformer service class that handles record transformation events."""
    
    def __init__(self, config: dict[str, Any], bus: DataPipelineBus):
        """Initialize transformer with configuration and pipeline bus."""
        self.config = config
        self.bus = bus
        self.engine = TransformEngine(config, bus)
    
    def process_record_added_event(self, data_registry_id: str) -> None:
        """Process a record_added event from the staged stage."""
        # Get change event from environment (set by orchestration)
        change_event = self.bus.get_change_event()
        
        if change_event.event == "record_added" and change_event.stage == "staged":
            # Process the record transformation
            snapshot_id = SnapshotId(
                ocid=change_event.sid.ocid,
                bid=change_event.sid.bid
            )
            
            # Get staged data
            staged_data = self.bus.get_snapshot_json(snapshot_id, stage="staged")
            
            # Transform the record
            result = self.engine.transform_record(snapshot_id, staged_data)
            
            if result.success and not result.skipped:
                # Store transformed data
                metadata = {
                    "transformed_at": self.bus._utcnow_iso(),
                    "transformer_version": "1.0",
                    "source_stage": "staged"
                }
                
                self.bus.post_snapshot_json(snapshot_id, metadata, result.transformed_data)
                
                logger.info(
                    "TRANSFORM_OPERATION_COMPLETED",
                    data_registry_id=data_registry_id,
                    ocid=snapshot_id.ocid,
                    bid=snapshot_id.bid,
                    fields_transformed=len(result.transformed_data) if result.transformed_data else 0,
                )
            elif result.skipped:
                logger.info(
                    "TRANSFORM_OPERATION_SKIPPED",
                    data_registry_id=data_registry_id,
                    ocid=snapshot_id.ocid,
                    bid=snapshot_id.bid,
                    reason=result.skip_reason,
                )
            else:
                logger.error(
                    "TRANSFORM_OPERATION_FAILED",
                    data_registry_id=data_registry_id,
                    ocid=snapshot_id.ocid,
                    bid=snapshot_id.bid,
                    error=result.error_message,
                )
                raise Exception(f"Transformation failed: {result.error_message}")
        else:
            logger.warning(
                "UNEXPECTED_CHANGE_EVENT",
                data_registry_id=data_registry_id,
                event=change_event.event,
                stage=change_event.stage,
            )

