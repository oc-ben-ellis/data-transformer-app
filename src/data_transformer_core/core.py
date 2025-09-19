"""Core framework components and base classes.

This module provides the fundamental building blocks of the OC transformer framework,
including the base DataRegistrytransformerConfig and configuration creation utilities.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Imports used only for type checking to avoid runtime import side effects
    from collections.abc import Mapping  # noqa: I001
    from oc_pipeline_bus.config import Annotated, strategy

# Import pipeline-bus config types
from oc_pipeline_bus.identifiers import Bid






@dataclass
class DataRegistryServiceConfig:
    """YAML-based service configuration using strategy factory registry."""

    # Add your service-specific configuration fields here
    config_id: str = ""
    # Protocol configurations for resolving relative configs

