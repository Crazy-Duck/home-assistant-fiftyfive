"""
Custom integration to integrate 50five with Home Assistant.

For more details about this integration, please refer to
https://github.com/Crazy-Duck/home-assistant-fiftyfive
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_COUNTRY, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.loader import async_get_loaded_integration

from .api import FiftyfiveApiClient
from .const import (
    CONF_CUST_TYPE,
    CURRENT_VERSION,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
)
from .coordinator import FiftyfiveDataUpdateCoordinator
from .data import FiftyfiveData
from .entity import FiftyfiveChargerEntity
from .service_handler import ChannelServiceHandler, ChargerServiceHandler

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

    from .data import FiftyfiveConfigEntry

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.SENSOR,
]


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    if config_entry.version < CURRENT_VERSION:
        LOGGER.debug(
            "Migrating config from version %s",
            config_entry.version,
        )
        new_data = {**config_entry.data}
        new_data.pop(CONF_CUST_TYPE, None)
        new_data.pop(CONF_COUNTRY, None)

        hass.config_entries.async_update_entry(
            config_entry, data=new_data, version=CURRENT_VERSION
        )
        LOGGER.debug(
            "Migrating to config version %s successful",
            config_entry.version,
        )
    return True


async def async_setup(hass: HomeAssistant, _: ConfigType) -> bool:
    """Set up the integration (global)."""
    h_charger = ChargerServiceHandler(hass=hass)
    h_channel = ChannelServiceHandler(hass=hass)

    hass.services.async_register(DOMAIN, "start_charge_session", h_channel.handle_start)
    hass.services.async_register(DOMAIN, "stop_charge_session", h_channel.handle_stop)
    hass.services.async_register(DOMAIN, "unlock_connector", h_channel.handle_unlock)
    hass.services.async_register(
        DOMAIN, "soft_reset_charger", h_charger.handle_soft_reset
    )
    hass.services.async_register(
        DOMAIN, "hard_reset_charger", h_charger.handle_hard_reset
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

    entry.runtime_data = FiftyfiveData(
        client=FiftyfiveApiClient(
            client=get_async_client(hass),
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        ),
        integration=async_get_loaded_integration(hass, entry.domain),
        coordinator=coordinator,
    )

    await coordinator.async_config_entry_first_refresh()

    # Register the charge station devices here so they're registered before
    # their child entries
    device_registry = dr.async_get(hass)
    for charger in coordinator.data:
        device_registry.async_get_or_create_from_info(
            config_entry_id=entry.entry_id,
            device_info=FiftyfiveChargerEntity.device_info_from_charger(charger),
        )

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
