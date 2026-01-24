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
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

from .api import FiftyfiveApiClient
from .const import DEFAULT_UPDATE_INTERVAL, DOMAIN, LOGGER
from .coordinator import FiftyfiveDataUpdateCoordinator
from .data import FiftyfiveData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall
    from homeassistant.helpers.typing import ConfigType

    from .data import FiftyfiveConfigEntry

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]


async def async_setup(hass: HomeAssistant, _: ConfigType) -> bool:
    """Set up the integration (global)."""

    async def find_charger_idx(device_id: str) -> str | None:
        """Find charger idx based on device id."""
        device_registry = dr.async_get(hass)

        device = device_registry.async_get(device_id)
        if not device:
            LOGGER.warning("Device %s not found", device_id)
            return None

        identifier = next(iter(device.identifiers), None)
        if not identifier or identifier[0] != DOMAIN:
            LOGGER.warning("Device %s does not belong to %s", device_id, DOMAIN)
            return None

        return identifier[1]

    async def handle_stop_charge_session(call: ServiceCall) -> None:
        """Handle the stop_charge_session service call."""
        device_id = call.data.get("device", None)

        if not device_id:
            LOGGER.error("No device selected for stop_charge_session")
            return

        idx = find_charger_idx(device_id)

        for entry in hass.config_entries.async_entries(DOMAIN):
            networks = entry.runtime_data.coordinator.data
            if any(charger["IDX"] == idx for charger in networks):
                client = entry.runtime_data.client
                LOGGER.info("Stopping charge session on charger %s", idx)
                await client.async_stop(charger=idx)
                break
        else:
            LOGGER.warning("No config entry found for charger %s", idx)

    async def handle_start_charge_session(call: ServiceCall) -> None:
        """Handle the start_charge_session service call."""
        device_id = call.data.get("device", None)
        card_id = call.data.get("card", None)

        if not device_id:
            LOGGER.error("No device selected for start_charge_session")
            return

        if not card_id:
            LOGGER.error("No card selected for start_charge_session")
            return

        idx = find_charger_idx(device_id=device_id)

        for entry in hass.config_entries.async_entries(DOMAIN):
            networks = entry.runtime_data.coordinator.data
            if any(charger["IDX"] == idx for charger in networks):
                client = entry.runtime_data.client
                LOGGER.info("Starting charge session on charger %s", idx)
                await client.async_start(charger=idx, card_id=card_id)
                await entry.runtime_data.coordinator.start_fast_polling()
                break
        else:
            LOGGER.warning("No config entry found for charger %s", idx)

    hass.services.async_register(
        DOMAIN, "start_charge_session", handle_start_charge_session
    )
    hass.services.async_register(
        DOMAIN, "stop_charge_session", handle_stop_charge_session
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
