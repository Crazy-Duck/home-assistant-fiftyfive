"""FiftyfiveChargerEntity class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    ChildDeviceInfo,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FiftyfiveDataUpdateCoordinator

if TYPE_CHECKING:
    from fiftyfive import schema


class FiftyfiveChargerEntity(CoordinatorEntity[FiftyfiveDataUpdateCoordinator]):
    """Defines a Fiftyfive entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FiftyfiveDataUpdateCoordinator, idx: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.idx = idx

    @staticmethod
    def device_info_from_charger(charger: schema.ChargeStation) -> DeviceInfo:
        """Construct DeviceInfo from ChargeStation."""
        return DeviceInfo(
            identifiers={(DOMAIN, charger.id)},
            connections={(CONNECTION_NETWORK_MAC, charger.id)},
            manufacturer=charger.manufacturer_type.vendor,
            sw_version=charger.software_version,
            name=charger.name or charger.id,
            model=charger.manufacturer_type.model,
        )

    @property
    def charger(self) -> dict:
        """Return the charger entry for this entity from the latest coordinator data."""
        return next(c for c in self.coordinator.data if c.id == self.idx)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info dynamically from the latest data."""
        charger = self.charger
        return FiftyfiveChargerEntity.device_info_from_charger(charger)


class FiftyfiveChannelEntity(CoordinatorEntity[FiftyfiveDataUpdateCoordinator]):
    """Base class for Fiftyfive channel entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FiftyfiveDataUpdateCoordinator,
        charger_idx: str,
        channel_idx: str,
        parent_device_id: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.charger_idx = charger_idx
        self.channel_idx = channel_idx
        self.parent_device_id = parent_device_id

    @property
    def charger(self) -> schema.ChargeStation:
        """Return the parent charge station."""
        return next(
            charger
            for charger in self.coordinator.data
            if charger.id == self.charger_idx
        )

    @property
    def channel(self) -> schema.ChargeStationChannel:
        """Return the channel."""
        return next(
            channel
            for channel in self.charger.channels
            if channel.id == self.channel_idx
        )

    @property
    def device_info(self) -> ChildDeviceInfo:
        """Return child device information."""
        charger = self.charger
        channel = self.channel
        return ChildDeviceInfo(
            identifiers={(DOMAIN, f"{self.charger_idx}_{self.channel_idx}")},
            parent_device_id=self.parent_device_id,
            name=f"{charger.name or charger.id} channel {channel.channel_no}",
        )
