"""DataUpdateCoordinator for integration_fiftyfive."""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    FiftyfiveApiClientAuthenticationError,
    FiftyfiveApiClientError,
)
from .const import CHARGING_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, FAST_POLL_TIME

if TYPE_CHECKING:
    from .data import FiftyfiveConfigEntry


class FiftyfiveDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    config_entry: FiftyfiveConfigEntry

    async def start_fast_polling(self) -> None:
        """Start polling at increased rate."""
        self.fast_polling_until = monotonic() + FAST_POLL_TIME
        await self.async_request_refresh()

    async def _async_update_data(self) -> Any:
        """Update data via library."""
        try:
            networks = await self.config_entry.runtime_data.client.async_get_data()
        except FiftyfiveApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except FiftyfiveApiClientError as exception:
            raise UpdateFailed(exception) from exception
        else:
            charging = any(int(n["STATUS"] or "0") > 0 for n in networks)
            interval = CHARGING_UPDATE_INTERVAL if charging else DEFAULT_UPDATE_INTERVAL

            # During fast polling we disregard charger status
            # This allows us to do a short time of fast polling after a session start
            if monotonic() < self.fast_polling_until:
                self.fast_polling_until -= 1
                if self.update_interval != CHARGING_UPDATE_INTERVAL:
                    self.update_interval = CHARGING_UPDATE_INTERVAL
            elif self.update_interval != interval:
                self.update_interval = interval
            return networks
