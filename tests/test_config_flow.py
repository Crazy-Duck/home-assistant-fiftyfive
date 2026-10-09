"""Tests for the 50five config flow."""

# ruff: noqa: S101, SLF001

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_COUNTRY, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.fiftyfive.api import AuthenticationResult
from custom_components.fiftyfive.config_flow import FiftyfiveFlowHandler
from custom_components.fiftyfive.const import CONF_CUST_TYPE, CONF_SESSION

ENTRY_DATA = {
    CONF_USERNAME: "joris@example.com",
    CONF_PASSWORD: "secret",
    CONF_COUNTRY: "nl",
    CONF_CUST_TYPE: "shell",
    CONF_SESSION: {"cookies": {"PHPSESSID": "old"}},
}


class FakeSession:
    """Minimal config-flow client session."""

    closed = False

    async def close(self) -> None:
        """Close the session."""
        self.closed = True


@pytest.mark.asyncio
async def test_reauth_requests_one_mfa_code_and_updates_existing_entry() -> None:
    """Reauth should update the existing entry without requesting another code."""
    flow = FiftyfiveFlowHandler()
    flow.context = {"source": config_entries.SOURCE_REAUTH}
    flow.hass = MagicMock()
    flow._entry = entry = MagicMock()
    flow._login_input = dict(ENTRY_DATA)
    flow.async_update_reload_and_abort = MagicMock(
        return_value=flow.async_abort(reason="reauth_successful")
    )

    client = MagicMock()
    client.async_authenticate = AsyncMock(
        return_value=AuthenticationResult.MFA_REQUIRED
    )
    client.async_request_mfa_code = AsyncMock(return_value="challenge")
    client.async_complete_mfa = AsyncMock(side_effect=[False, True])
    client.session_state.return_value = {"cookies": {"PHPSESSID": "new"}}

    with (
        patch(
            "custom_components.fiftyfive.config_flow.async_create_clientsession",
            return_value=FakeSession(),
        ),
        patch(
            "custom_components.fiftyfive.config_flow.FiftyfiveApiClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_reauth_confirm({})
        assert result["step_id"] == "mfa"
        client.async_request_mfa_code.assert_awaited_once()

        result = await flow.async_step_mfa({"code": "bad"})
        assert result["step_id"] == "mfa"
        assert result["errors"] == {"base": "invalid_mfa"}
        client.async_request_mfa_code.assert_awaited_once()

        result = await flow.async_step_mfa({"code": "123456"})

    assert result["type"] is FlowResultType.ABORT
    flow.async_update_reload_and_abort.assert_called_once()
    assert flow.async_update_reload_and_abort.call_args.args[0] is entry
    assert flow.async_update_reload_and_abort.call_args.kwargs["data"][
        CONF_SESSION
    ] == {"cookies": {"PHPSESSID": "new"}}


@pytest.mark.asyncio
async def test_password_only_login_creates_entry() -> None:
    """Accounts without MFA should still complete setup in one step."""
    flow = FiftyfiveFlowHandler()
    flow.hass = MagicMock()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()

    client = MagicMock()
    client.async_authenticate = AsyncMock(
        return_value=AuthenticationResult.AUTHENTICATED
    )
    client.session_state.return_value = {"cookies": {"PHPSESSID": "session"}}

    with (
        patch(
            "custom_components.fiftyfive.config_flow.async_create_clientsession",
            return_value=FakeSession(),
        ),
        patch(
            "custom_components.fiftyfive.config_flow.FiftyfiveApiClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_user(
            {
                CONF_USERNAME: "joris@example.com",
                CONF_PASSWORD: "secret",
                CONF_COUNTRY: "nl",
                CONF_CUST_TYPE: "shell",
            }
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SESSION] == {"cookies": {"PHPSESSID": "session"}}
    client.async_request_mfa_code.assert_not_called()
