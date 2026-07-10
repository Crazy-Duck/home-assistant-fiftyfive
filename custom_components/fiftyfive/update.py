"""Update platform for 50five.

Exposes a first-class Home Assistant ``update`` entity that shows whether the
integration itself is up to date.  Unlike the binary sensor (which is only
"on" when an update is available), this entity is always visible under the
integration and clearly displays the installed vs. latest version, so the user
can see at a glance that they are running the newest release.

The actual update is performed through HACS, so this entity does not implement
an ``install`` method; it is informational (with a release-notes link).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, UPDATE_CHECK_INTERVAL, UPDATE_RELEASES_URL

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data import FiftyfiveConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the update platform."""
    async_add_entities([FiftyfiveUpdateEntity(entry)])


class FiftyfiveUpdateEntity(UpdateEntity):
    """Update entity reflecting whether the integration is up to date."""

    _attr_has_entity_name = True
    _attr_name = "Integration update"
    # Informational only: updates are installed via HACS, not from here.
    _attr_supported_features = UpdateEntityFeature(0)
    _attr_title = "50five (2FA)"

    def __init__(self, entry: FiftyfiveConfigEntry) -> None:
        """Initialize the update entity."""
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_integration_update"

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed version.

        Prefer the value recorded by the update check, but fall back to the
        integration manifest version so this is known immediately at startup,
        before the first GitHub check has run.
        """
        state = self._entry.runtime_data.update_state
        installed = state.get("installed")
        if installed:
            return installed
        version = self._entry.runtime_data.integration.version
        return str(version) if version else None

    @property
    def latest_version(self) -> str | None:
        """Return the latest available version.

        When the update check has not produced a latest version yet, fall back
        to the installed version so the entity reports "up to date" rather than
        an unknown state.
        """
        state = self._entry.runtime_data.update_state
        return state.get("latest") or state.get("installed")

    @property
    def release_url(self) -> str | None:
        """Return the URL to the release notes."""
        return self._entry.runtime_data.update_state.get("release_url") or (
            UPDATE_RELEASES_URL
        )

    async def async_added_to_hass(self) -> None:
        """Refresh state on the same cadence as the update check."""
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
