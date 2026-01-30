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
from homeassistant.loader import async_get_loaded_integration

from .api import FiftyfiveApiClient
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN, LOGGER
from .coordinator import FiftyfiveDataUpdateCoordinator
from .data import FiftyfiveData
from .service_handler import ChargerServiceHandler

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

    from .data import FiftyfiveConfigEntry

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.SENSOR,
]


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

    entry.runtime_data = FiftyfiveData(
        client=FiftyfiveApiClient(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            market=entry.data[CONF_COUNTRY],
            session=async_get_clientsession(hass),
        ),
        integration=async_get_loaded_integration(hass, entry.domain),
        coordinator=coordinator,
    )

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


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
