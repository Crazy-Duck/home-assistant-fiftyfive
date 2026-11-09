"""Sample API Client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sgqlc.operation import Operation

from fiftyfive import (
    Api,
    schema,
)

if TYPE_CHECKING:
    from httpx import AsyncClient


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
    """Fiftyfive API Client."""

    def __init__(
        self,
        username: str,
        password: str,
        client: AsyncClient,
    ) -> None:
        """Initialize API Client."""
        self._api = Api(
            client=client,
            email=username,
            password=password,
        )

    async def async_get_data(self) -> list[schema.ChargeStation]:
        """Get data from the API."""
        op = Operation(schema.Query)
        stations = op.get_charge_stations()
        stations.items.id()
        stations.items.name()
        stations.items.reference()
        stations.items.comm_id()
        stations.items.comm_key()
        stations.items.comm_medium()
        stations.items.comm_mode()
        stations.items.comm_status()
        stations.items.comm_version()
        stations.items.cost_center_number()
        stations.items.state()
        stations.items.physical_number()
        stations.items.last_communication_date()
        stations.items.sim_number()
        stations.items.software_version()
        stations.items.manufacturer_type()

        stations.items.channels()
        stations.items.home_charging_compensation()

        data = await self._api.make_request(op)
        if data.get("errors"):
            raise FiftyfiveApiClientError
        return (op + data).get_charge_stations.items

    async def async_start(self, charger: str, channel: str, card_id: str) -> bool:
        """Start charge session."""
        op = Operation(schema.Query)
        cards = op.get_cards()
        cards.items.internal_id()
        cards.items.external_id()

        data = await self._api.make_request(op)
        if data.get("errors"):
            raise FiftyfiveApiInvalidCardError

        card_list = (op + data).get_cards
        card = next((c for c in card_list.items if c.external_id == card_id), None)
        if card is None:
            raise FiftyfiveApiInvalidCardError

        op = Operation(schema.Mutation)
        op.start_transaction(
            charge_station_id=charger,
            channel_id=channel,
            card=card.internal_id,
        )
        data = await self._api.make_request(op)

        if data.get("errors"):
            raise FiftyfiveApiInvalidCardError
        return (op + data).start_transaction

    async def async_stop(self, charger: str, channel: str) -> bool:
        """Stop a charge session."""
        op = Operation(schema.Mutation)
        op.stop_transaction(
            charge_station_id=charger,
            channel_id=channel,
        )
        data = await self._api.make_request(op)

        if data.get("errors"):
            raise FiftyfiveApiClientError
        return (op + data).stop_transaction

    async def async_soft_reset(self, charger: str) -> bool:
        """Soft reset a charger."""
        op = Operation(schema.Mutation)
        op.soft_reset(
            charge_station_id=charger,
        )
        data = await self._api.make_request(op)

        if data.get("errors"):
            raise FiftyfiveApiClientError
        return (op + data).soft_reset

    async def async_hard_reset(self, charger: str) -> bool:
        """Hard reset a charger."""
        op = Operation(schema.Mutation)
        op.hard_reset(
            charge_station_id=charger,
        )
        data = await self._api.make_request(op)

        if data.get("errors"):
            raise FiftyfiveApiClientError
        return (op + data).hard_reset

    async def async_unlock_connector(self, charger: str, channel: str) -> bool:
        """Unlock the connector from a charger."""
        op = Operation(schema.Mutation)
        op.unlock_connector(charge_station_id=charger, channel_id=channel)
        data = await self._api.make_request(op)

        if data.get("errors"):
            raise FiftyfiveApiClientError
        return (op + data).unlock_connector
