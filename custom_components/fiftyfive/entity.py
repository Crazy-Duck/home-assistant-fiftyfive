"""FiftyfiveEntity class."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FiftyfiveDataUpdateCoordinator


class FiftyfiveEntity(CoordinatorEntity[FiftyfiveDataUpdateCoordinator]):
    """Defines a Fiftyfive entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FiftyfiveDataUpdateCoordinator, idx: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.idx = idx

    @property
    def network(self) -> dict:
        """Return the network entry for this entity from the latest coordinator data."""
        return next(n for n in self.coordinator.data if n["IDX"] == self.idx)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info dynamically from the latest data."""
        net = self.network
        return DeviceInfo(
            identifiers={(DOMAIN, self.idx)},
            connections={(CONNECTION_NETWORK_MAC, self.idx)},
            manufacturer="50five",
            sw_version=net["SOFTWARE_VERSION"],
            name=net["NAME"] or self.idx,
            model="EV Charger",
            model_id=net["CONNECTOR"],
        )
