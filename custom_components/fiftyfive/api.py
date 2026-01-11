"""Sample API Client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fiftyfive import (
    Api,
    CardSearch,
    Channel,
    ClientSearch,
    Market,
    NetworkOverview,
    Overview,
    Start,
    Stop,
)

if TYPE_CHECKING:
    from aiohttp import ClientSession


class FiftyfiveApiClientError(Exception):
    """Exception to indicate a general API error."""


class FiftyfiveApiClientCommunicationError(
    FiftyfiveApiClientError,
):
    """Exception to indicate a communication error."""


class FiftyfiveApiClientAuthenticationError(
    FiftyfiveApiClientError,
):
    """Exception to indicate an authentication error."""


class FiftyfiveApiInvalidCardError(
    FiftyfiveApiClientError,
):
    """Exception to indicate an invalid card error."""


class FiftyfiveApiClient:
    """Sample API Client."""

    def __init__(
        self,
        username: str,
        password: str,
        market: Market,
        session: ClientSession,
    ) -> None:
        """Sample API Client."""
        self._api = Api(
            session=session,
            email=username,
            password=password,
            market=market
        )

    async def async_get_data(self) -> Any:
        """Get data from the API."""
        networks = await self._api.make_requests([NetworkOverview()])
        if not networks:
            msg = "Invalid credentials"
            raise FiftyfiveApiClientAuthenticationError(msg)

        details = await self._api.make_requests([
            Overview(network["IDX"])
            for network in networks[0]
        ])

        return [c|d for c,d in zip(networks[0], details[0], strict=True)]


    async def async_start(self, charger: str, card_id: str) -> Any:
        """Start charge session."""
        clients = await self._api.make_requests([
            ClientSearch(recharge_spot_id=charger, name="")
        ])

        card_lists = await self._api.make_requests([
            CardSearch(recharge_spot_id=charger, customer_id=client["id"])
            for client in clients[0]
        ])

        for i, card_list in enumerate(card_lists):
            if any(card["text"] == card_id for card in card_list):
                return await self._api.make_requests([Start(
                    channel=Channel(recharge_spot_id=charger, channel_id="1"),
                    customer_id=clients[0][i]["id"],
                    card_id=card_id
                )])
        raise FiftyfiveApiInvalidCardError

    async def async_stop(self, charger: str) -> Any:
        """Stop a charge session."""
        return await self._api.make_requests([
            Stop(channel=Channel(recharge_spot_id=charger, channel_id="1"))
        ])

