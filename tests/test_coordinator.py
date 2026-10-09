"""Tests for the 50five coordinator authentication lifecycle."""

# ruff: noqa: ANN001, ANN202, S101, SLF001

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.fiftyfive.api import FiftyfiveApiClientAuthenticationError
from custom_components.fiftyfive.const import CONF_SESSION, DOMAIN, LOGGER
from custom_components.fiftyfive.coordinator import FiftyfiveDataUpdateCoordinator


def _coordinator(client: MagicMock, entry_data: dict):
    entry = SimpleNamespace(
        async_on_unload=MagicMock(),
        data=entry_data,
        runtime_data=SimpleNamespace(client=client),
    )
    hass = MagicMock()

    def update_entry(config_entry, *, data):
        config_entry.data = data

    hass.config_entries.async_update_entry.side_effect = update_entry
    coordinator = FiftyfiveDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        config_entry=entry,
        name=DOMAIN,
    )
    coordinator.fast_polling_until = 0
    return coordinator, entry


@pytest.mark.asyncio
async def test_successful_refresh_persists_rotated_session() -> None:
    """A rotated provider session should be stored without replacing the entry."""
    client = MagicMock()
    client.async_get_data = AsyncMock(return_value=[{"STATUS": "0", "IDX": "charger"}])
    client.session_state.return_value = {"cookies": {"PHPSESSID": "new"}}
    coordinator, entry = _coordinator(
        client,
        {CONF_SESSION: {"cookies": {"PHPSESSID": "old"}}},
    )

    data = await coordinator._async_update_data()

    assert data == [{"STATUS": "0", "IDX": "charger"}]
    assert entry.data[CONF_SESSION] == {"cookies": {"PHPSESSID": "new"}}


@pytest.mark.asyncio
async def test_expired_session_starts_native_reauth() -> None:
    """An MFA-required session should stop polling and start one reauth flow."""
    client = MagicMock()
    client.async_get_data = AsyncMock(side_effect=FiftyfiveApiClientAuthenticationError)
    coordinator, _ = _coordinator(client, {})

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
