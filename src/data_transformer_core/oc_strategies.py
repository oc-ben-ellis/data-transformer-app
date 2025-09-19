from dataclasses import dataclass
from typing import Any, Optional
from oc_pipeline_bus.strategy_registry import StrategyFactory, StrategyFactoryRegistry
from oc_pipeline_bus.strategy_types import TransformationStrategy


@dataclass
class DirectMappingConfig:
    """Configuration for direct mapping transformation."""
    pass


@dataclass
class FixedValueConfig:
    """Configuration for fixed value transformation."""
    fixed_value: str


@dataclass
class LookupMappingConfig:
    """Configuration for lookup mapping transformation."""
    mapping_file: str


class DirectMappingStrategy:
    """Direct mapping transformation strategy."""
    
    def __init__(self, config: DirectMappingConfig):
        self.config = config
    
    def transform(self, value: Any) -> Any:
        """Return the value as-is."""
        return value


class FixedValueStrategy:
    """Fixed value transformation strategy."""
    
    def __init__(self, config: FixedValueConfig):
        self.config = config
    
    def transform(self, value: Any) -> str:
        """Return the fixed value."""
        return self.config.fixed_value


class LookupMappingStrategy:
    """Lookup mapping transformation strategy."""
    
    def __init__(self, config: LookupMappingConfig, mapping_data: dict[str, Any]):
        self.config = config
        self.mapping_data = mapping_data
    
    def transform(self, value: Any) -> Optional[str]:
        """Look up value in mapping data."""
        if value is None or value == "":
            return None
        return self.mapping_data.get(str(value).strip(), value)


class DirectMappingFactory(StrategyFactory[TransformationStrategy]):
    """Factory for direct mapping strategy."""
    
    def validate(self, config: dict[str, Any]) -> DirectMappingConfig:
        """Validate and return configuration."""
        return DirectMappingConfig()
    
    def create(self, config: DirectMappingConfig, **kwargs) -> DirectMappingStrategy:
        """Create strategy instance."""
        return DirectMappingStrategy(config)
    
    def get_config_type(self) -> type[DirectMappingConfig]:
        """Return configuration type."""
        return DirectMappingConfig


class FixedValueFactory(StrategyFactory[TransformationStrategy]):
    """Factory for fixed value strategy."""
    
    def validate(self, config: dict[str, Any]) -> FixedValueConfig:
        """Validate and return configuration."""
        if "fixed_value" not in config:
            raise ValueError("fixed_value is required for oc.fixed_value strategy")
        return FixedValueConfig(fixed_value=config["fixed_value"])
    
    def create(self, config: FixedValueConfig, **kwargs) -> FixedValueStrategy:
        """Create strategy instance."""
        return FixedValueStrategy(config)
    
    def get_config_type(self) -> type[FixedValueConfig]:
        """Return configuration type."""
        return FixedValueConfig


class LookupMappingFactory(StrategyFactory[TransformationStrategy]):
    """Factory for lookup mapping strategy."""
    
    def validate(self, config: dict[str, Any]) -> LookupMappingConfig:
        """Validate and return configuration."""
        if "mapping_file" not in config:
            raise ValueError("mapping_file is required for oc.lookup_mapping_file strategy")
        return LookupMappingConfig(mapping_file=config["mapping_file"])
    
    def create(self, config: LookupMappingConfig, **kwargs) -> LookupMappingStrategy:
        """Create strategy instance."""
        mapping_data = kwargs.get("mapping_data", {})
        return LookupMappingStrategy(config, mapping_data)
    
    def get_config_type(self) -> type[LookupMappingConfig]:
        """Return configuration type."""
        return LookupMappingConfig


def register_oc_strategies(registry: StrategyFactoryRegistry) -> None:
    """Register OpenCorporates universal strategies with the registry."""
    registry.register(TransformationStrategy, "oc.direct_mapping", DirectMappingFactory())
    registry.register(TransformationStrategy, "oc.fixed_value", FixedValueFactory())
    registry.register(TransformationStrategy, "oc.lookup_mapping_file", LookupMappingFactory())

