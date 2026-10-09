"""Config flow for 50five."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_COUNTRY, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from slugify import slugify

from fiftyfive import CustomerType, Market

from .api import (
    AuthenticationResult,
    FiftyfiveApiClient,
    FiftyfiveApiClientError,
)
from .const import CONF_CUST_TYPE, CONF_SESSION, DOMAIN, LOGGER

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from homeassistant.config_entries import ConfigEntry


class FiftyfiveFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the 50five config flow."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize config flow state."""
        self._client: FiftyfiveApiClient | None = None
        self._entry: ConfigEntry | None = None
        self._login_input: dict[str, Any] = {}
        self._mfa_challenge: str | None = None
        self._session: ClientSession | None = None

    @callback
    def async_remove(self) -> None:
        """Close an unfinished login session when the flow is removed."""
        if self._session is not None and not self._session.closed:
            self.hass.async_create_task(
                self._session.close(),
                "close unfinished 50five login session",
            )

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_start_authentication(user_input)
            if result is not None:
                return result
            errors["base"] = "auth"

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(),
            errors=errors,
            description_placeholders={
                "docs_url": "https://github.com/Crazy-Duck/home-assistant-fiftyfive"
            },
        )

    async def async_step_reauth(
        self, entry_data: config_entries.Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Start reauthentication after the provider rejects the session."""
        self._entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        self._login_input = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm reauthentication without replacing the config entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            login_input = {
                **self._login_input,
                CONF_PASSWORD: user_input.get(CONF_PASSWORD)
                or self._login_input[CONF_PASSWORD],
            }
            result = await self._async_start_authentication(login_input)
            if result is not None:
                return result
            errors["base"] = "auth"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self._reauth_schema(),
            errors=errors,
            description_placeholders={"username": self._login_input[CONF_USERNAME]},
        )

    async def async_step_mfa(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Complete an email MFA challenge."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if self._client is None or self._mfa_challenge is None:
                return self.async_abort(reason="mfa_session_expired")

            try:
                authenticated = await self._client.async_complete_mfa(
                    user_input["code"], self._mfa_challenge
                )
            except FiftyfiveApiClientError:
                LOGGER.exception("Unable to submit the 50five MFA code")
                errors["base"] = "connection"
            else:
                if authenticated:
                    return await self._async_finish_authentication()
                errors["base"] = "invalid_mfa"

        return self.async_show_form(
            step_id="mfa",
            data_schema=vol.Schema(
                {
                    vol.Required("code"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={"username": self._login_input[CONF_USERNAME]},
        )

    async def _async_start_authentication(
        self, user_input: dict[str, Any]
    ) -> config_entries.ConfigFlowResult | None:
        """Start authentication without requesting MFA more than once."""
        if self._session is not None:
            await self._session.close()

        self._login_input = user_input
        self._session = async_create_clientsession(self.hass)
        self._client = FiftyfiveApiClient(
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            market=user_input[CONF_COUNTRY],
            customer_type=user_input[CONF_CUST_TYPE],
            session=self._session,
        )

        try:
            result = await self._client.async_authenticate()
        except FiftyfiveApiClientError:
            LOGGER.exception("Unable to authenticate with the 50five portal")
            return self._connection_error_form()

        if result is AuthenticationResult.AUTHENTICATED:
            return await self._async_finish_authentication()
        if result is AuthenticationResult.MFA_REQUIRED:
            try:
                self._mfa_challenge = await self._client.async_request_mfa_code()
            except FiftyfiveApiClientError:
                LOGGER.exception("Unable to request a 50five MFA code")
                return self._connection_error_form()
            return await self.async_step_mfa()

        LOGGER.warning("Invalid 50five credentials or market")
        return None

    async def _async_finish_authentication(
        self,
    ) -> config_entries.ConfigFlowResult:
        """Persist the authenticated session and finish the flow."""
        if self._client is None:
            return self.async_abort(reason="mfa_session_expired")

        session_state = self._client.session_state()
        if self._session is not None:
            await self._session.close()
            self._session = None

        data = {
            **self._login_input,
            CONF_SESSION: session_state,
        }
        if self._entry is not None:
            return self.async_update_reload_and_abort(self._entry, data=data)

        unique_id = slugify(self._login_input[CONF_USERNAME])
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._login_input[CONF_USERNAME],
            data=data,
        )

    def _connection_error_form(self) -> config_entries.ConfigFlowResult:
        """Show the current login form with a connection error."""
        if self._entry is not None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=self._reauth_schema(),
                errors={"base": "connection"},
                description_placeholders={"username": self._login_input[CONF_USERNAME]},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(),
            errors={"base": "connection"},
            description_placeholders={
                "docs_url": "https://github.com/Crazy-Duck/home-assistant-fiftyfive"
            },
        )

    def _user_schema(self) -> vol.Schema:
        """Return the initial login schema."""
        return vol.Schema(
            {
                vol.Required(
                    CONF_USERNAME,
                    default=self._login_input.get(CONF_USERNAME, vol.UNDEFINED),
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.TEXT,
                    ),
                ),
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                    ),
                ),
                vol.Optional(
                    CONF_COUNTRY,
                    default=self._login_input.get(CONF_COUNTRY, Market.NONE),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[m.value for m in Market],
                        translation_key="country",
                    )
                ),
                vol.Required(
                    CONF_CUST_TYPE,
                    default=self._login_input.get(
                        CONF_CUST_TYPE, CustomerType.FORMER_SHELL
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[c.value for c in CustomerType],
                        translation_key="customer_type",
                    )
                ),
            }
        )

    @staticmethod
    def _reauth_schema() -> vol.Schema:
        """Return the reauthentication schema."""
        return vol.Schema(
            {
                vol.Optional(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                    ),
                ),
            }
        )
