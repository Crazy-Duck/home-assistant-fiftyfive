"""Adds config flow for FiftyFive."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_COUNTRY, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from slugify import slugify

from fiftyfive import CustomerType, Market

from .auth import (
    LoginResult,
    async_start_login,
    async_submit_2fa,
    build_base_url,
    extract_cookies,
)
from .const import CONF_2FA_CODE, CONF_COOKIES, CONF_CUST_TYPE, DOMAIN, LOGGER

if TYPE_CHECKING:
    from collections.abc import Mapping


class FiftyfiveFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for FiftyFive."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialise the flow handler state."""
        # State that is carried across the (interactive) 2FA steps.
        self._login_input: dict[str, Any] = {}
        self._base_url: str = ""
        self._session = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial (username/password) step."""
        _errors: dict[str, str] = {}
        if user_input is not None:
            # A fresh session (own cookie jar) is used for the whole login so
            # that the cookies we capture belong exclusively to this account.
            self._session = async_create_clientsession(self.hass)
            self._base_url = build_base_url(
                user_input[CONF_COUNTRY], user_input[CONF_CUST_TYPE]
            )
            self._login_input = user_input

            try:
                result = await async_start_login(
                    self._session,
                    self._base_url,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except Exception:  # noqa: BLE001 - surface any transport error as connection issue
                LOGGER.exception("Error while contacting the 50five portal")
                _errors["base"] = "connection"
            else:
                if result is LoginResult.TWO_FACTOR_REQUIRED:
                    LOGGER.debug("Credentials accepted, 2FA code required")
                    return await self.async_step_2fa()
                if result is LoginResult.OK:
                    # Portal did not ask for 2FA (backwards compatible path).
                    return await self._async_create_or_update_entry()
                LOGGER.warning("Invalid credentials/market.")
                _errors["base"] = "auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=(user_input or self._login_input or {}).get(
                            CONF_USERNAME, vol.UNDEFINED
                        ),
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
                        default=(user_input or self._login_input or {}).get(
                            CONF_COUNTRY, Market.NONE
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[m.value for m in Market], translation_key="country"
                        )
                    ),
                    vol.Required(
                        CONF_CUST_TYPE,
                        default=(user_input or self._login_input or {}).get(
                            CONF_CUST_TYPE, CustomerType.FORMER_SHELL
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[c.value for c in CustomerType],
                            translation_key="customer_type",
                        )
                    ),
                },
            ),
            errors=_errors,
            description_placeholders={
                "docs_url": "https://github.com/Crazy-Duck/home-assistant-fiftyfive"
            },
        )

    async def async_step_2fa(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the e-mailed two-factor code step."""
        _errors: dict[str, str] = {}
        if user_input is not None:
            try:
                accepted = await async_submit_2fa(
                    self._session,
                    self._base_url,
                    user_input[CONF_2FA_CODE],
                )
            except Exception:  # noqa: BLE001
                LOGGER.exception("Error while submitting the 2FA code")
                _errors["base"] = "connection"
            else:
                if accepted:
                    LOGGER.debug("2FA code accepted")
                    return await self._async_create_or_update_entry()
                LOGGER.warning("Invalid 2FA code.")
                _errors["base"] = "invalid_2fa"

        return self.async_show_form(
            step_id="2fa",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_2FA_CODE): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.TEXT,
                        ),
                    ),
                }
            ),
            errors=_errors,
            description_placeholders={
                "username": self._login_input.get(CONF_USERNAME, "")
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle re-authentication when the stored session expires."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        # Pre-fill the known values (from the existing entry) so the user only
        # has to confirm the password and supply a fresh 2FA code.
        self._login_input = dict(entry_data)
        return await self.async_step_user()

    async def _async_create_or_update_entry(
        self,
    ) -> config_entries.ConfigFlowResult:
        """Persist the authenticated session and finish the flow."""
        cookies = extract_cookies(self._session)
        data = {
            **self._login_input,
            CONF_COOKIES: cookies,
        }
        # Do not persist any leftover 2FA code in the entry data.
        data.pop(CONF_2FA_CODE, None)

        unique_id = slugify(self._login_input[CONF_USERNAME])
        await self.async_set_unique_id(unique_id)

        if self._reauth_entry is not None:
            self.hass.config_entries.async_update_entry(
                self._reauth_entry, data=data
            )
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._login_input[CONF_USERNAME],
            data=data,
        )
