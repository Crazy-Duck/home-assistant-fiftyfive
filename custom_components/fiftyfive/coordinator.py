"""DataUpdateCoordinator for integration_fiftyfive."""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING, Any

from homeassistant.components import persistent_notification
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    FiftyfiveApiClientAuthenticationError,
    FiftyfiveApiClientError,
)
from .const import (
    CHARGING_UPDATE_INTERVAL,
    CONF_COOKIES,
    DEFAULT_UPDATE_INTERVAL,
    FAST_POLL_TIME,
    LOGGER,
)

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
            # The stored session has expired (the portal keeps a session for
            # ~24h after the 2FA step).
            #
            # We deliberately do NOT raise ConfigEntryAuthFailed here.  That
            # would start Home Assistant's reauth flow, which the user does not
            # want: it feels like the integration is "trying to reconnect" and
            # every completed reauth makes the portal email a fresh 2FA code.
            #
            # Instead we raise UpdateFailed.  The entities go "unavailable" with
            # a clear error in the log, and NO new 2FA e-mail is requested.  The
            # user re-authenticates manually (Settings -> Devices & Services ->
            # 50five -> Reconfigure) whenever they choose to, which is the only
            # moment a new 2FA code is sent.
            LOGGER.error(
                "50five session expired: no connection. The integration will "
                "NOT reconnect automatically and will NOT request a new 2FA "
                "code. Reconfigure the 50five integration manually when you "
                "want to supply a fresh 2FA code."
            )
            self._notify_session_expired()
            raise UpdateFailed(
                "50five session expired - manual reconfiguration required "
                "(no automatic reconnect / no new 2FA code requested)"
            ) from exception
        except FiftyfiveApiClientError as exception:
            raise UpdateFailed(exception) from exception
        else:
            # A successful fetch means the session is valid again; clear any
            # lingering "session expired" notification.
            persistent_notification.async_dismiss(
                self.hass, "fiftyfive_session_expired"
            )

            # Persist the freshest session cookies so a restart within the ~24h
            # window reuses a still-valid session instead of the stale cookie
            # captured at setup time.
            self._persist_session_cookies()
            
            # Fetch the account-wide total energy delivered by all chargers.
            # This is a best-effort query; failure must never break polling.
            total_energy = await self.config_entry.runtime_data.client.async_get_total_energy()
            if total_energy is not None:
                # Inject the total into every charger's data dict so the sensor
                # can access it.  All chargers show the same account-wide value.
                for network in networks:
                    network["TOTAL_ENERGY_KWH"] = total_energy
            
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

    def _notify_session_expired(self) -> None:
        """
        Show a persistent notification when the 50five session has expired.

        This gives the user a clear, visible error in the UI without starting
        the reauth flow automatically.  The notification uses a stable id so it
        is only shown once (and replaced, not duplicated, on repeated failures).
        The user dismisses it and reconfigures the integration manually whenever
        they want to enter a new 2FA code.
        """
        persistent_notification.async_create(
            self.hass,
            (
                "The connection with the 50five portal has been lost because "
                "the session (2FA) has expired.\n\n"
                "The integration does **not** reconnect automatically and will "
                "**not** request a new 2FA code by e-mail.\n\n"
                "To restore the connection, reconfigure the integration "
                "manually via **Settings → Devices & Services → 50five → "
                "Reconfigure**. A new 2FA code will be e-mailed only then."
            ),
            title="50five: connection lost (2FA expired)",
            notification_id="fiftyfive_session_expired",
        )

    def _persist_session_cookies(self) -> None:
        """
        Save the current portal session cookies into the config entry.

        The portal may rotate its session cookie during the ~24h it stays
        valid.  Persisting the latest value (only when it actually changed)
        lets Home Assistant reuse a live session after a restart instead of
        falling back to the possibly-stale cookie captured during setup, which
        would otherwise force an unnecessary 2FA re-authentication.
        """
        entry = self.config_entry
        client = entry.runtime_data.client
        try:
            current = client.current_cookies()
        except Exception:  # noqa: BLE001 - never let persistence break polling
            LOGGER.debug("Could not read session cookies", exc_info=True)
            return

        if not current:
            return

        stored = entry.data.get(CONF_COOKIES, {})
        if current == stored:
            return

        self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_COOKIES: current}
        )
        LOGGER.debug("Refreshed stored 50five session cookies")
