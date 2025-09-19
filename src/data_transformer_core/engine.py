"""Transform engine implementation for converting staged data to legacy ingestion format."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from oc_pipeline_bus.identifiers import SnapshotId
from oc_pipeline_bus.bus import DataPipelineBus
from oc_pipeline_bus.strategy_registry import StrategyFactoryRegistry
from oc_pipeline_bus.strategy_types import TransformationStrategy

from data_transformer_core.strategy_registration import create_strategy_registry

logger = structlog.get_logger(__name__)


@dataclass
class TransformationResult:
    """Result of a transformation operation."""
    
    success: bool
    transformed_data: dict[str, Any] | None = None
    error_message: str | None = None
    skipped: bool = False
    skip_reason: str | None = None


class TransformEngine:
    """Main transform engine class that applies business logic to convert staged data to legacy format."""
    
    def __init__(self, config: dict[str, Any], bus: DataPipelineBus):
        """Initialize transform engine with configuration and pipeline bus."""
        self.config = config
        self.bus = bus
        self.mapping_data: dict[str, dict[str, Any]] = {}
        self.strategy_registry = create_strategy_registry()
        
        # Load mapping files
        self._load_mapping_files()
    
    def _load_mapping_files(self) -> None:
        """Load mapping files from the configuration directory."""
        config_dir = os.getenv("OC_DATA_PIPELINE_CONFIG_DIR")
        if not config_dir:
            logger.warning("No config directory found, skipping mapping file loading")
            return
        
        mapping_files = self.config.get("mapping_files", {})
        for mapping_name, filename in mapping_files.items():
            mapping_path = Path(config_dir) / "transformer" / "enums" / filename
            try:
                with open(mapping_path, "r", encoding="utf-8") as f:
                    self.mapping_data[mapping_name] = json.load(f)
                logger.info("Loaded mapping file", mapping_name=mapping_name, file=filename)
            except FileNotFoundError:
                logger.warning("Mapping file not found", mapping_name=mapping_name, file=filename)
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON in mapping file", mapping_name=mapping_name, file=filename, error=str(e))
    
    def _should_skip_record(self, data: dict[str, Any]) -> tuple[bool, str | None]:
        """Check if record should be skipped based on validation rules."""
        validation_rules = self.config.get("validation_rules", {})
        skip_conditions = validation_rules.get("skip_conditions", [])
        
        for condition in skip_conditions:
            field = condition.get("field")
            operator = condition.get("operator")
            
            if not field or not operator:
                continue
            
            value = data.get(field)
            
            if operator == "blank" and (not value or str(value).strip() == ""):
                return True, f"Field {field} is blank"
        
        return False, None
    
    def _apply_transformation(self, field_config: dict[str, Any], data: dict[str, Any]) -> Any:
        """Apply transformation logic to a field using strategy pattern."""
        transformation_logic = field_config.get("transformation_logic")
        input_source = field_config.get("input_source")
        
        if not transformation_logic:
            return None
        
        # Get input value
        if input_source:
            input_value = data.get(input_source)
        else:
            input_value = None
        
        try:
            # Create strategy instance using the registry
            strategy = self.strategy_registry.create_strategy(
                TransformationStrategy,
                transformation_logic,
                field_config,
                mapping_data=self.mapping_data
            )
            
            # Apply transformation
            if hasattr(strategy, 'transform'):
                return strategy.transform(input_value)
            else:
                logger.warning("Strategy does not have transform method", strategy=transformation_logic)
                return input_value
                
        except Exception as e:
            logger.warning(
                "Failed to apply transformation strategy",
                strategy=transformation_logic,
                error=str(e)
            )
            return input_value
    
    def transform_record(self, snapshot_id: SnapshotId, staged_data: dict[str, Any]) -> TransformationResult:
        """Transform a single staged record to legacy ingestion format."""
        try:
            # Check if record should be skipped
            should_skip, skip_reason = self._should_skip_record(staged_data)
            if should_skip:
                return TransformationResult(
                    success=True,
                    skipped=True,
                    skip_reason=skip_reason
                )
            
            # Apply transformations according to company schema
            transformed_data = {}
            company_schema = self.config.get("company", {})
            
            for field_name, field_config in company_schema.items():
                try:
                    transformed_value = self._apply_transformation(field_config, staged_data)
                    if transformed_value is not None:
                        transformed_data[field_name] = transformed_value
                except Exception as e:
                    logger.warning(
                        "Failed to transform field",
                        field=field_name,
                        error=str(e),
                        ocid=snapshot_id.ocid,
                        bid=snapshot_id.bid
                    )
                    # Continue with other fields
            
            return TransformationResult(
                success=True,
                transformed_data=transformed_data
            )
        
        except Exception as e:
            logger.exception(
                "Failed to transform record",
                ocid=snapshot_id.ocid,
                bid=snapshot_id.bid,
                error=str(e)
            )
            return TransformationResult(
                success=False,
                error_message=str(e)
            )

