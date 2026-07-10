"""
Custom integration to integrate 50five with Home Assistant.

For more details about this integration, please refer to
https://github.com/Crazy-Duck/home-assistant-fiftyfive
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_COUNTRY, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.loader import async_get_loaded_integration

from fiftyfive import CustomerType

from .api import FiftyfiveApiClient
from .auth import build_base_url, seed_cookies
from .const import (
    CONF_COOKIES,
    CONF_CUST_TYPE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    STATISTICS_IMPORT_INTERVAL,
    UPDATE_CHECK_INTERVAL,
)
from .coordinator import FiftyfiveDataUpdateCoordinator
from .data import FiftyfiveData
from .service_handler import ChargerServiceHandler
from .statistics import async_import_power_history
from .update_check import async_check_for_update

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

    from .data import FiftyfiveConfigEntry

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
]


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    if config_entry.version == 1:
        LOGGER.debug(
            "Migrating config from version %s",
            config_entry.version,
        )
        new_data = {**config_entry.data}
        new_data[CONF_CUST_TYPE] = CustomerType.FORMER_SHELL

        hass.config_entries.async_update_entry(config_entry, data=new_data, version=2)
        LOGGER.debug(
            "Migrating to config version %s successful",
            config_entry.version,
        )
    return True


async def async_setup(hass: HomeAssistant, _: ConfigType) -> bool:
    """Set up the integration (global)."""
    handler = ChargerServiceHandler(hass=hass)

    hass.services.async_register(DOMAIN, "start_charge_session", handler.handle_start)
    hass.services.async_register(DOMAIN, "stop_charge_session", handler.handle_stop)
    hass.services.async_register(
        DOMAIN, "soft_reset_charger", handler.handle_soft_reset
    )
    hass.services.async_register(
        DOMAIN, "hard_reset_charger", handler.handle_hard_reset
    )
    hass.services.async_register(DOMAIN, "unlock_connector", handler.handle_unlock)
    hass.services.async_register(DOMAIN, "block_charger", handler.handle_block)
    hass.services.async_register(DOMAIN, "unblock_charger", handler.handle_unblock)
    hass.services.async_register(
        DOMAIN, "import_power_history", handler.handle_import_power_history
    )
    hass.services.async_register(
        DOMAIN, "check_for_update", handler.handle_check_for_update
    )

    return True


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    coordinator = FiftyfiveDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        update_interval=DEFAULT_UPDATE_INTERVAL,
    )
    # Brittle but less mess than overriding __init__
    coordinator.fast_polling_until = 0

    session = async_get_clientsession(hass)

    # Reuse the session cookies captured during (2FA) setup so that regular
    # polling does not trigger a new login -- a new login would require a fresh
    # e-mailed 2FA code which cannot be obtained unattended. When the stored
    # session eventually expires the coordinator raises UpdateFailed (entities
    # go unavailable + a notification is shown); it does NOT reconnect or
    # request a new 2FA code automatically -- the user reconfigures manually.
    seed_cookies(
        session,
        build_base_url(entry.data[CONF_COUNTRY], entry.data[CONF_CUST_TYPE]),
        entry.data.get(CONF_COOKIES, {}),
    )

    entry.runtime_data = FiftyfiveData(
        client=FiftyfiveApiClient(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            market=entry.data[CONF_COUNTRY],
            customer_type=entry.data[CONF_CUST_TYPE],
            session=session,
        ),
        integration=async_get_loaded_integration(hass, entry.domain),
        coordinator=coordinator,
        update_state={},
    )

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _async_setup_power_history(hass, entry)
    _async_setup_update_check(hass, entry)

    return True


def _async_setup_power_history(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
) -> None:
    """
    Backfill the power sensor history from the portal, then refresh hourly.

    The sensor entities are registered by the time this runs, so their
    statistics can be imported.  The work happens in a background task so it
    never blocks setup, and is repeated on an interval to keep the rolling
    window filled.
    """

    async def _import(_now: object = None) -> None:
        await async_import_power_history(hass, entry)

    entry.async_create_background_task(
        hass, _import(), name="fiftyfive_power_history_initial"
    )
    entry.async_on_unload(
        async_track_time_interval(hass, _import, STATISTICS_IMPORT_INTERVAL)
    )


def _async_setup_update_check(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
) -> None:
    """Check GitHub for a newer release now and then daily."""

    async def _check(_now: object = None) -> None:
        await async_check_for_update(hass, entry)

    entry.async_create_background_task(
        hass, _check(), name="fiftyfive_update_check_initial"
    )
    entry.async_on_unload(
        async_track_time_interval(hass, _check, UPDATE_CHECK_INTERVAL)
    )


async def async_unload_entry(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
