"""ChargerServiceHandler class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant, ServiceCall

    from .api import FiftyfiveApiClient
    from .data import FiftyfiveConfigEntry


class ChargerServiceHandler:
    """Handles all service calls."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass

    async def _find_charger_idx(self, device_id: str) -> str | None:
        """Find charger idx based on device id."""
        device_registry = dr.async_get(self.hass)

        device = device_registry.async_get(device_id)
        if not device:
            LOGGER.warning("Device %s not found", device_id)
            return None

        identifier = next(iter(device.identifiers), None)
        if not identifier or identifier[0] != DOMAIN:
            LOGGER.warning("Device %s does not belong to %s", device_id, DOMAIN)
            return None

        return identifier[1]

    async def _do_action_on_device(self, device_id: str, action: Callable) -> None:
        """."""
        idx = await self._find_charger_idx(device_id)
        if not idx:
            return

        for entry in self.hass.config_entries.async_entries(DOMAIN):
            networks = entry.runtime_data.coordinator.data
            if any(charger["IDX"] == idx for charger in networks):
                client = entry.runtime_data.client
                await action(entry, client, idx)
                break
        else:
            LOGGER.warning("No config entry found for charger %s", idx)

    async def handle_soft_reset(self, call: ServiceCall) -> None:
        """Handle the soft_reset_charger service call."""
        device_id = call.data.get("device", None)

        if not device_id:
            LOGGER.error("No device selected for soft_reset_charger")
            return

        async def action(
            _: FiftyfiveConfigEntry, client: FiftyfiveApiClient, idx: str
        ) -> None:
            LOGGER.info("Soft resetting charger %s", idx)
            await client.async_soft_reset(charger=idx)

        await self._do_action_on_device(device_id=device_id, action=action)

    async def handle_hard_reset(self, call: ServiceCall) -> None:
        """Handle the hard_reset_charger service call."""
        device_id = call.data.get("device", None)

        if not device_id:
            LOGGER.error("No device selected for hard_reset_charger")
            return

        async def action(
            _: FiftyfiveConfigEntry, client: FiftyfiveApiClient, idx: str
        ) -> None:
            LOGGER.info("Hard resetting charger %s", idx)
            await client.async_hard_reset(charger=idx)

        await self._do_action_on_device(device_id=device_id, action=action)

    async def handle_unlock(self, call: ServiceCall) -> None:
        """Handle the unlock_connector service call."""
        device_id = call.data.get("device", None)

        if not device_id:
            LOGGER.error("No device selected for unlock_connector")
            return

        async def action(
            _: FiftyfiveConfigEntry, client: FiftyfiveApiClient, idx: str
        ) -> None:
            LOGGER.info("Unlocking connector from charger %s", idx)
            await client.async_unlock_connector(charger=idx)

        await self._do_action_on_device(device_id=device_id, action=action)

    async def handle_block(self, call: ServiceCall) -> None:
        """Handle the block_charger service call."""
        device_id = call.data.get("device", None)

        if not device_id:
            LOGGER.error("No device selected for block_charger")
            return

        async def action(
            _: FiftyfiveConfigEntry, client: FiftyfiveApiClient, idx: str
        ) -> None:
            LOGGER.info("Blocking charger %s", idx)
            await client.async_block(charger=idx)

        await self._do_action_on_device(device_id=device_id, action=action)

    async def handle_unblock(self, call: ServiceCall) -> None:
        """Handle the unblock_charger service call."""
        device_id = call.data.get("device", None)

        if not device_id:
            LOGGER.error("No device selected for unblock_charger")
            return

        async def action(
            _: FiftyfiveConfigEntry, client: FiftyfiveApiClient, idx: str
        ) -> None:
            LOGGER.info("Unblocking charger %s", idx)
            await client.async_block(charger=idx)

        await self._do_action_on_device(device_id=device_id, action=action)

    async def handle_stop(self, call: ServiceCall) -> None:
        """Handle the stop_charge_session service call."""
        device_id = call.data.get("device", None)

        if not device_id:
            LOGGER.error("No device selected for stop_charge_session")
            return

        async def action(
            _: FiftyfiveConfigEntry, client: FiftyfiveApiClient, idx: str
        ) -> None:
            LOGGER.info("Stopping charge session on charger %s", idx)
            await client.async_stop(charger=idx)

        await self._do_action_on_device(device_id=device_id, action=action)

    async def handle_start(self, call: ServiceCall) -> None:
        """Handle the start_charge_session service call."""
        device_id = call.data.get("device", None)
        card_id = call.data.get("card", None)

        if not device_id:
            LOGGER.error("No device selected for start_charge_session")
            return

        if not card_id:
            LOGGER.error("No card selected for start_charge_session")
            return

        async def action(
            entry: FiftyfiveConfigEntry, client: FiftyfiveApiClient, idx: str
        ) -> None:
            LOGGER.info("Starting charge session on charger %s", idx)
            await client.async_start(charger=idx, card_id=card_id)
            await entry.runtime_data.coordinator.start_fast_polling()

        await self._do_action_on_device(device_id=device_id, action=action)
