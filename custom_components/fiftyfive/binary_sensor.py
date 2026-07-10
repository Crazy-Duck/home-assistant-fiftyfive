"""Binary sensor platform for 50five."""

from __future__ import annotations

from typing import TYPE_CHECKING

from awesomeversion import AwesomeVersion, AwesomeVersionException
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, UPDATE_CHECK_INTERVAL

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data import FiftyfiveConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    async_add_entities([FiftyfiveUpdateSensor(entry)])


class FiftyfiveUpdateSensor(BinarySensorEntity):
    """Binary sensor that turns ON when a newer release is available."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.UPDATE

    def __init__(self, entry: FiftyfiveConfigEntry) -> None:
        """Initialize the update sensor."""
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_update_available"
        self._attr_name = "Update available"

    @property
    def is_on(self) -> bool:
        """Return True if a newer version is available."""
        state = self._entry.runtime_data.update_state
        installed = state.get("installed")
        latest = state.get("latest")
        if not installed or not latest:
            return False
        try:
            return AwesomeVersion(latest) > AwesomeVersion(installed)
        except AwesomeVersionException:
            return latest != installed

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return additional attributes."""
        state = self._entry.runtime_data.update_state
        return {
            "installed_version": state.get("installed"),
            "latest_version": state.get("latest"),
            "release_url": state.get("release_url"),
        }

    async def async_added_to_hass(self) -> None:
        """Register update listener when entity is added."""
        # Poll the update state every CHECK_INTERVAL and refresh this sensor.
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._async_refresh_state,
                UPDATE_CHECK_INTERVAL,
            )
        )

    @callback
    def _async_refresh_state(self, _now: object = None) -> None:
        """Refresh state after the background update check runs."""
        self.async_write_ha_state()
