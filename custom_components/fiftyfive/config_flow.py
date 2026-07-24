"""Adds config flow for FiftyFive."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_COUNTRY, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from slugify import slugify

from fiftyfive import Api, CustomerType, Market, NetworkOverview

from .const import CONF_CUST_TYPE, DOMAIN, LOGGER


class FiftyfiveFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for FiftyFive."""

    VERSION = 2

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a flow initialized by the user."""
        _errors: dict[str, str] = {}
        if user_input is not None:
            if not await self._test_credentials(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                market=user_input[CONF_COUNTRY],
                customer_type=user_input[CONF_CUST_TYPE],
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
                    vol.Optional(
                        CONF_COUNTRY,
                        default=(user_input or {}).get(CONF_COUNTRY, Market.NONE),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[m.value for m in Market], translation_key="country"
                        )
                    ),
                    vol.Required(
                        CONF_CUST_TYPE,
                        default=(user_input or {}).get(
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

    async def async_step_reauth(
        self, entry_data: config_entries.Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Perform reauthentication upon an API authentication error."""
        self.username = entry_data[CONF_USERNAME]
        self.country = entry_data[CONF_COUNTRY]
        self.customer_type = entry_data[CONF_CUST_TYPE]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm reauthentication dialog."""
        _errors: dict[str, str] = {}
        if not await self._test_credentials(
            username=self.username,
            password=user_input[CONF_PASSWORD],
            market=self.country,
            customer_type=self.customer_type,
        ):
            LOGGER.warning("Invalid credentials/market.")
            _errors["base"] = "auth"
        else:
            await self.async_set_unique_id(unique_id=slugify(user_input[CONF_USERNAME]))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_USERNAME],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        ),
                    ),
                },
            ),
            errors=_errors,
            description_placeholders={
                "docs_url": "https://github.com/Crazy-Duck/home-assistant-fiftyfive"
            },
        )

    async def _test_credentials(
        self, username: str, password: str, market: Market, customer_type: CustomerType
    ) -> Any:
        """Validate credentials."""
        client = Api(
            session=async_create_clientsession(self.hass),
            email=username,
            password=password,
            market=market,
            customer_type=customer_type,
        )
        return await client.make_requests([NetworkOverview()])
