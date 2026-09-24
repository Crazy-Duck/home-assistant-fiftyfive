"""Custom types for integration_fiftyfive."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import FiftyfiveApiClient
    from .coordinator import FiftyfiveDataUpdateCoordinator


type FiftyfiveConfigEntry = ConfigEntry[FiftyfiveData]


@dataclass
class FiftyfiveData:
    """Data for the 50five integration."""

    client: FiftyfiveApiClient
    coordinator: FiftyfiveDataUpdateCoordinator
    integration: Integration
    update_state: dict[str, Any] = field(default_factory=dict)
