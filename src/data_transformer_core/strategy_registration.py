"""Strategy registration for the transformer service.

This module provides a centralized way to register all strategy factories
with the StrategyFactoryRegistry, enabling YAML-based configuration loading.
"""

from oc_pipeline_bus.strategy_registry import StrategyFactoryRegistry

from data_transformer_core.oc_strategies import register_oc_strategies
from data_transformer_core.us_fl_strategies import register_us_fl_strategies


def create_strategy_registry() -> StrategyFactoryRegistry:
    """Create and register all available strategy factories with a new registry.

    Returns:
        Registry with all strategies registered
    """
    registry = StrategyFactoryRegistry()

    # Register OpenCorporates universal strategies
    register_oc_strategies(registry)
    
    # Register US-FL specific strategies
    register_us_fl_strategies(registry)

    return registry
