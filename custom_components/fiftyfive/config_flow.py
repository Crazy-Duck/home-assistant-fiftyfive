"""Adds config flow for Blueprint."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_COUNTRY, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from slugify import slugify

from fiftyfive import Api, Market, NetworkOverview

from .const import DOMAIN, LOGGER


class FiftyfiveFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Blueprint."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _errors = {}
        if user_input is not None:
            if not await self._test_credentials(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                market=user_input[CONF_COUNTRY],
            ):
                LOGGER.warning("Invalid credentials/market.")
                _errors["base"] = "auth"
            else:
                await self.async_set_unique_id(
                    unique_id=slugify(user_input[CONF_USERNAME])
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=(user_input or {}).get(CONF_USERNAME, vol.UNDEFINED),
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
                    vol.Required(CONF_COUNTRY): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[m.value for m in Market]
                        )
                    )
                },
            ),
            errors=_errors,
        )

    async def _test_credentials(
        self, username: str, password: str, market: Market
    ) -> Any:
        """Validate credentials."""
        client = Api(
            session=async_create_clientsession(self.hass),
            email=username,
            password=password,
            market=market,
        )
        return await client.make_requests([NetworkOverview()])
