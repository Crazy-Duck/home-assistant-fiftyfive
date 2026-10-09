"""Sample API Client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiohttp import ClientError

from fiftyfive import (
    Api,
    AuthenticationError,
    AuthenticationResult,
    Block,
    CardSearch,
    Channel,
    ClientSearch,
    CustomerType,
    HardReset,
    Market,
    MfaRequiredError,
    NetworkOverview,
    Overview,
    Request,
    SoftReset,
    Start,
    Stop,
    Unblock,
    UnlockConnector,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

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
        customer_type: CustomerType,
        session: ClientSession,
    ) -> None:
        """Sample API Client."""
        self._api = Api(
            session=session,
            email=username,
            password=password,
            market=market,
            customer_type=customer_type,
        )

    async def async_authenticate(self) -> AuthenticationResult:
        """Authenticate without automatically requesting an MFA email."""
        try:
            return await self._api.authenticate()
        except (AuthenticationError, MfaRequiredError) as exception:
            msg = str(exception) or "50five authentication is required"
            raise FiftyfiveApiClientAuthenticationError(msg) from exception
        except (ClientError, TimeoutError) as exception:
            msg = str(exception) or "Could not reach the 50five portal"
            raise FiftyfiveApiClientCommunicationError(msg) from exception

    async def async_request_mfa_code(self) -> str:
        """Request one email MFA code and return its challenge token."""
        try:
            return await self._api.request_mfa_code()
        except (AuthenticationError, MfaRequiredError) as exception:
            msg = str(exception) or "Could not start 50five email verification"
            raise FiftyfiveApiClientAuthenticationError(msg) from exception
        except (ClientError, TimeoutError) as exception:
            msg = str(exception) or "Could not reach the 50five portal"
            raise FiftyfiveApiClientCommunicationError(msg) from exception

    async def async_complete_mfa(self, code: str, challenge: str) -> bool:
        """Complete an email MFA challenge."""
        try:
            return await self._api.complete_mfa(code, challenge)
        except (AuthenticationError, MfaRequiredError) as exception:
            msg = str(exception) or "The 50five verification session expired"
            raise FiftyfiveApiClientAuthenticationError(msg) from exception
        except (ClientError, TimeoutError) as exception:
            msg = str(exception) or "Could not reach the 50five portal"
            raise FiftyfiveApiClientCommunicationError(msg) from exception

    def restore_session(self, state: Mapping[str, Any]) -> None:
        """Restore a previously persisted provider session."""
        self._api.restore_session(state)

    def session_state(self) -> dict[str, Any]:
        """Return serializable provider session state."""
        return self._api.export_session()

    async def _async_make_requests(self, requests: list[Request]) -> Any:
        """Make provider requests and normalize connection/authentication errors."""
        try:
            return await self._api.make_requests(requests)
        except (AuthenticationError, MfaRequiredError) as exception:
            msg = str(exception) or "50five authentication is required"
            raise FiftyfiveApiClientAuthenticationError(msg) from exception
        except (ClientError, TimeoutError) as exception:
            msg = str(exception) or "Could not reach the 50five portal"
            raise FiftyfiveApiClientCommunicationError(msg) from exception

    async def async_get_data(self) -> Any:
        """Get data from the API."""
        networks = await self._async_make_requests([NetworkOverview()])
        if not networks:
            msg = "Invalid credentials"
            raise FiftyfiveApiClientAuthenticationError(msg)

        details = await self._async_make_requests(
            [Overview(network["IDX"]) for network in networks[0]]
        )

        return [c | d[0] for c, d in zip(networks[0], details, strict=True)]

    async def async_start(self, charger: str, card_id: str) -> Any:
        """Start charge session."""
        clients = await self._async_make_requests(
            [ClientSearch(recharge_spot_id=charger, name="")]
        )

        card_lists = await self._async_make_requests(
            [
                CardSearch(recharge_spot_id=charger, customer_id=client["id"])
                for client in clients[0]
            ]
        )

        for i, card_list in enumerate(card_lists):
            if any(card["text"] == card_id for card in card_list):
                return await self._async_make_requests(
                    [
                        Start(
                            channel=Channel(recharge_spot_id=charger, channel_id="1"),
                            customer_id=clients[0][i]["id"],
                            card_id=card_id,
                        )
                    ]
                )
        raise FiftyfiveApiInvalidCardError

    async def async_stop(self, charger: str) -> Any:
        """Stop a charge session."""
        return await self._async_make_requests(
            [Stop(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )

    async def async_soft_reset(self, charger: str) -> Any:
        """Soft reset a charger."""
        return await self._async_make_requests(
            [SoftReset(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )

    async def async_hard_reset(self, charger: str) -> Any:
        """Hard reset a charger."""
        return await self._async_make_requests(
            [HardReset(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )

    async def async_unlock_connector(self, charger: str) -> Any:
        """Unlock the connector from a charger."""
        return await self._async_make_requests(
            [UnlockConnector(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )

    async def async_block(self, charger: str) -> Any:
        """Block a charger."""
        return await self._async_make_requests(
            [Block(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )

    async def async_unblock(self, charger: str) -> Any:
        """Unblock a charger."""
        return await self._async_make_requests(
            [Unblock(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )
