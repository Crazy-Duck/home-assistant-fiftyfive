"""Sample API Client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fiftyfive import (
    Api,
    Block,
    CardSearch,
    Channel,
    ClientSearch,
    Current,
    CustomerType,
    HardReset,
    Market,
    NetworkOverview,
    Overview,
    SoftReset,
    Start,
    Stop,
    Unblock,
    UnlockConnector,
)

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)


def extract_latest_power(graph: Any) -> float | None:
    """
    Extract the most recent live power (kW) from a ``current`` graph response.

    The 50five portal renders its charging-power graph from the dashboard
    ``current`` service instead of the ``MOM_POWER_KW`` field returned by the
    ``overview`` service.  ``MOM_POWER_KW`` is unreliable and frequently reports
    ``0``/``null`` even while a session is active (see upstream issue #27), so
    we derive a value from the same data source the portal itself graphs.

    The ``current`` response looks like::

        {
            "labels": ["03:00", "03:15", ...],
            "datasets": {
                "1":        {"values": [...], "unit": "kW"},
                "1_count":  {"values": [...], "unit": ""}
            }
        }

    We return the most recent non-null value of the kW dataset (the last time
    bin, i.e. "now"), or ``None`` when no usable value is present.
    """
    if not isinstance(graph, dict):
        return None
    datasets = graph.get("datasets")
    if not isinstance(datasets, dict):
        return None

    for key, dataset in datasets.items():
        # The companion "<channel>_count" series holds transaction counts, not
        # power, so skip it and only consider the kW dataset.
        if str(key).endswith("_count"):
            continue
        if not isinstance(dataset, dict) or dataset.get("unit") != "kW":
            continue
        values = dataset.get("values") or []
        for value in reversed(values):
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
    return None


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

    async def async_get_data(self) -> Any:
        """Get data from the API."""
        networks = await self._api.make_requests([NetworkOverview()])
        if not networks:
            msg = "Invalid credentials"
            raise FiftyfiveApiClientAuthenticationError(msg)

        details = await self._api.make_requests(
            [Overview(network["IDX"]) for network in networks[0]]
        )

        merged = [c | d[0] for c, d in zip(networks[0], details, strict=True)]

        # ``MOM_POWER_KW`` (from the overview service) is unreliable and often
        # reports 0/null even while charging.  The portal itself draws its
        # charging-power graph from the dashboard ``current`` service, so we
        # fetch that too and expose the latest value as ``LIVE_POWER_KW`` which
        # the sensor uses as a fallback.  Failures here must never break the
        # regular data update, so they are caught and logged.
        try:
            currents = await self._api.make_requests(
                [
                    Current(recharge_spot_ids=[network["IDX"]], mode=1)
                    for network in merged
                ]
            )
        except Exception:  # noqa: BLE001 - best effort, never break polling
            _LOGGER.debug("Failed to fetch 'current' power graph", exc_info=True)
        else:
            for network, graph in zip(merged, currents, strict=False):
                live_power = extract_latest_power(graph)
                network["LIVE_POWER_KW"] = live_power
                _LOGGER.debug(
                    "Charger %s: MOM_POWER_KW=%s LIVE_POWER_KW=%s STATUS=%s",
                    network.get("IDX"),
                    network.get("MOM_POWER_KW"),
                    live_power,
                    network.get("STATUS"),
                )

        return merged

    async def async_start(self, charger: str, card_id: str) -> Any:
        """Start charge session."""
        clients = await self._api.make_requests(
            [ClientSearch(recharge_spot_id=charger, name="")]
        )

        card_lists = await self._api.make_requests(
            [
                CardSearch(recharge_spot_id=charger, customer_id=client["id"])
                for client in clients[0]
            ]
        )

        for i, card_list in enumerate(card_lists):
            if any(card["text"] == card_id for card in card_list):
                return await self._api.make_requests(
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
        return await self._api.make_requests(
            [Stop(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )

    async def async_soft_reset(self, charger: str) -> Any:
        """Soft reset a charger."""
        return await self._api.make_requests(
            [SoftReset(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )

    async def async_hard_reset(self, charger: str) -> Any:
        """Hard reset a charger."""
        return await self._api.make_requests(
            [HardReset(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )

    async def async_unlock_connector(self, charger: str) -> Any:
        """Unlock the connector from a charger."""
        return await self._api.make_requests(
            [UnlockConnector(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )

    async def async_block(self, charger: str) -> Any:
        """Block a charger."""
        return await self._api.make_requests(
            [Block(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )

    async def async_unblock(self, charger: str) -> Any:
        """Unblock a charger."""
        return await self._api.make_requests(
            [Unblock(channel=Channel(recharge_spot_id=charger, channel_id="1"))]
        )
