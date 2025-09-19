"""Unit tests for transformer functionality."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from data_transformer_core.transformer import Transformer
from data_transformer_core.engine import TransformEngine, TransformationResult
from data_transformer_core.oc_strategies import DirectMappingStrategy, FixedValueStrategy, LookupMappingStrategy
from data_transformer_core.us_fl_strategies import ParseDateStrategy, DetermineBranchStatusStrategy
from oc_pipeline_bus.identifiers import SnapshotId


class TestOCStrategies:
    """Test OpenCorporates universal transformation strategies."""
    
    def test_direct_mapping_strategy(self):
        """Test direct mapping strategy returns value as-is."""
        from data_transformer_core.oc_strategies import DirectMappingConfig
        
        strategy = DirectMappingStrategy(DirectMappingConfig())
        assert strategy.transform("test") == "test"
        assert strategy.transform(123) == 123
        assert strategy.transform(None) is None
    
    def test_fixed_value_strategy(self):
        """Test fixed value strategy returns the fixed value."""
        from data_transformer_core.oc_strategies import FixedValueConfig
        
        strategy = FixedValueStrategy(FixedValueConfig(fixed_value="us_fl"))
        assert strategy.transform("anything") == "us_fl"
    
    def test_lookup_mapping_strategy(self):
        """Test lookup mapping strategy."""
        from data_transformer_core.oc_strategies import LookupMappingConfig
        
        mapping_data = {"ACT": "Active", "INA": "Inactive"}
        strategy = LookupMappingStrategy(LookupMappingConfig(mapping_file="test.json"), mapping_data)
        
        assert strategy.transform("ACT") == "Active"
        assert strategy.transform("INA") == "Inactive"
        assert strategy.transform("UNKNOWN") == "UNKNOWN"
        assert strategy.transform("") is None
        assert strategy.transform(None) is None


class TestUSFLStrategies:
    """Test US Florida specific transformation strategies."""
    
    def test_parse_date_strategy(self):
        """Test FL date parsing strategy."""
        from data_transformer_core.us_fl_strategies import ParseDateConfig
        
        strategy = ParseDateStrategy(ParseDateConfig())
        assert strategy.transform("09012025") == "2025-09-01"
        assert strategy.transform("12312024") == "2024-12-31"
        assert strategy.transform("") is None
        assert strategy.transform("invalid") is None
        assert strategy.transform("1234567") is None  # Too short
    
    def test_determine_branch_status_strategy(self):
        """Test branch status determination strategy."""
        from data_transformer_core.us_fl_strategies import DetermineBranchStatusConfig
        
        strategy = DetermineBranchStatusStrategy(DetermineBranchStatusConfig())
        assert strategy.transform("FOR") == "true"
        assert strategy.transform("FLL") == "true"
        assert strategy.transform("DOM") == "false"
        assert strategy.transform("LLC") is None
        assert strategy.transform("") is None
        assert strategy.transform(None) is None


class TestTransformEngine:
    """Test transform engine class."""
    
    def test_skip_record_blank_name(self):
        """Test that records with blank names are skipped."""
        config = {
            "validation_rules": {
                "skip_conditions": [
                    {"field": "COR_NAME", "operator": "blank"},
                    {"field": "COR_NUMBER", "operator": "blank"}
                ]
            },
            "company": {}
        }
        
        bus = Mock()
        engine = TransformEngine(config, bus)
        
        # Test blank name
        staged_data = {"COR_NAME": "", "COR_NUMBER": "12345"}
        result = engine.transform_record(SnapshotId("ocid:v1:co:test", "bid:v1:us_fl:test"), staged_data)
        
        assert result.success is True
        assert result.skipped is True
        assert "COR_NAME" in result.skip_reason
    
    def test_skip_record_blank_number(self):
        """Test that records with blank numbers are skipped."""
        config = {
            "validation_rules": {
                "skip_conditions": [
                    {"field": "COR_NAME", "operator": "blank"},
                    {"field": "COR_NUMBER", "operator": "blank"}
                ]
            },
            "company": {}
        }
        
        bus = Mock()
        engine = TransformEngine(config, bus)
        
        # Test blank number
        staged_data = {"COR_NAME": "Test Company", "COR_NUMBER": ""}
        result = engine.transform_record(SnapshotId("ocid:v1:co:test", "bid:v1:us_fl:test"), staged_data)
        
        assert result.success is True
        assert result.skipped is True
        assert "COR_NUMBER" in result.skip_reason
    
    def test_transform_record_success(self):
        """Test successful record transformation."""
        config = {
            "validation_rules": {"skip_conditions": []},
            "company": {
                "company_number": {
                    "input_source": "COR_NUMBER",
                    "transformation_logic": "oc.direct_mapping"
                },
                "name": {
                    "input_source": "COR_NAME", 
                    "transformation_logic": "oc.direct_mapping"
                },
                "jurisdiction_code": {
                    "transformation_logic": "oc.fixed_value",
                    "fixed_value": "us_fl"
                }
            }
        }
        
        bus = Mock()
        engine = TransformEngine(config, bus)
        
        staged_data = {
            "COR_NUMBER": "12345",
            "COR_NAME": "Test Company"
        }
        
        result = engine.transform_record(SnapshotId("ocid:v1:co:test", "bid:v1:us_fl:test"), staged_data)
        
        assert result.success is True
        assert result.skipped is False
        assert result.transformed_data is not None
        assert result.transformed_data["company_number"] == "12345"
        assert result.transformed_data["name"] == "Test Company"
        assert result.transformed_data["jurisdiction_code"] == "us_fl"
    
    def test_transform_record_with_mapping_files(self, tmp_path):
        """Test transformation with mapping files."""
        # Create temporary mapping file
        mapping_file = tmp_path / "company_types.json"
        mapping_file.write_text('{"LLC": "Limited Liability Company", "CORP": "Corporation"}')
        
        config = {
            "validation_rules": {"skip_conditions": []},
            "mapping_files": {"company_types": "company_types.json"},
            "company": {
                "company_type": {
                    "input_source": "COR_FILING_TYPE",
                    "transformation_logic": "oc.lookup_mapping_file",
                    "mapping_file": "company_types"
                }
            }
        }
        
        bus = Mock()
        engine = TransformEngine(config, bus)
        
        # Mock the config directory
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["OC_DATA_PIPELINE_CONFIG_DIR"] = temp_dir
            config_dir = Path(temp_dir)
            (config_dir / "transformer" / "enums").mkdir(parents=True, exist_ok=True)
            
            # Copy mapping file to expected location
            mapping_path = config_dir / "transformer" / "enums" / "company_types.json"
            mapping_path.write_text('{"LLC": "Limited Liability Company", "CORP": "Corporation"}')
            
            staged_data = {"COR_FILING_TYPE": "LLC"}
            result = engine.transform_record(SnapshotId("ocid:v1:co:test", "bid:v1:us_fl:test"), staged_data)
            
            assert result.success is True
            assert result.transformed_data["company_type"] == "Limited Liability Company"
    
    def test_transform_record_error_handling(self):
        """Test error handling during transformation."""
        config = {
            "validation_rules": {"skip_conditions": []},
            "company": {
                "test_field": {
                    "input_source": "TEST_FIELD",
                    "transformation_logic": "unknown.strategy"
                }
            }
        }
        
        bus = Mock()
        engine = TransformEngine(config, bus)
        
        staged_data = {"TEST_FIELD": "test_value"}
        result = engine.transform_record(SnapshotId("ocid:v1:co:test", "bid:v1:us_fl:test"), staged_data)
        
        # Should still succeed but with warning logged
        assert result.success is True
        assert result.transformed_data is not None
        # Field should be None due to unknown strategy
        assert result.transformed_data.get("test_field") is None


class TestTransformer:
    """Test transformer service class."""
    
    def test_process_record_added_event_success(self):
        """Test successful processing of record_added event."""
        config = {"company": {}}
        bus = Mock()
        
        # Mock the change event
        mock_change_event = Mock()
        mock_change_event.event = "record_added"
        mock_change_event.stage = "staged"
        mock_change_event.sid.ocid = "ocid:v1:co:test"
        mock_change_event.sid.bid = "bid:v1:us_fl:test"
        
        bus.get_change_event.return_value = mock_change_event
        bus.get_snapshot_json.return_value = {"COR_NUMBER": "12345", "COR_NAME": "Test Company"}
        bus._utcnow_iso.return_value = "2025-01-01T00:00:00Z"
        
        transformer = Transformer(config, bus)
        
        # Mock the engine's transform_record method
        transformer.engine.transform_record = Mock(return_value=TransformationResult(
            success=True,
            transformed_data={"company_number": "12345", "name": "Test Company"}
        ))
        
        transformer.process_record_added_event("us_fl")
        
        # Verify the bus methods were called
        bus.get_change_event.assert_called_once()
        bus.get_snapshot_json.assert_called_once()
        bus.post_snapshot_json.assert_called_once()
    
    def test_process_record_added_event_skipped(self):
        """Test processing of record_added event that gets skipped."""
        config = {"company": {}}
        bus = Mock()
        
        # Mock the change event
        mock_change_event = Mock()
        mock_change_event.event = "record_added"
        mock_change_event.stage = "staged"
        mock_change_event.sid.ocid = "ocid:v1:co:test"
        mock_change_event.sid.bid = "bid:v1:us_fl:test"
        
        bus.get_change_event.return_value = mock_change_event
        bus.get_snapshot_json.return_value = {"COR_NUMBER": "", "COR_NAME": ""}
        
        transformer = Transformer(config, bus)
        
        # Mock the engine's transform_record method to return skipped
        transformer.engine.transform_record = Mock(return_value=TransformationResult(
            success=True,
            skipped=True,
            skip_reason="Field COR_NAME is blank"
        ))
        
        transformer.process_record_added_event("us_fl")
        
        # Verify the bus methods were called
        bus.get_change_event.assert_called_once()
        bus.get_snapshot_json.assert_called_once()
        # Should not call post_snapshot_json for skipped records
        bus.post_snapshot_json.assert_not_called()
    
    def test_process_unexpected_event(self):
        """Test processing of unexpected change event."""
        config = {"company": {}}
        bus = Mock()
        
        # Mock an unexpected change event
        mock_change_event = Mock()
        mock_change_event.event = "bundle_ready"
        mock_change_event.stage = "parsed"
        
        bus.get_change_event.return_value = mock_change_event
        
        transformer = Transformer(config, bus)
        
        transformer.process_record_added_event("us_fl")
        
        # Verify only get_change_event was called
        bus.get_change_event.assert_called_once()
        bus.get_snapshot_json.assert_not_called()
        bus.post_snapshot_json.assert_not_called()