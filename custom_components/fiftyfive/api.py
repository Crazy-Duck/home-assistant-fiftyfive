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
    TotalUsage,
    Unblock,
    UnlockConnector,
)

from .auth import extract_cookies_for_url

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
    dataset = _power_dataset(graph)
    if dataset is None:
        return None
    for value in reversed(dataset.get("values") or []):
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _power_dataset(graph: Any) -> dict | None:
    """Return the kW ``values`` dataset from a ``current`` graph response."""
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
        if isinstance(dataset, dict) and dataset.get("unit") == "kW":
            return dataset
    return None


def extract_power_series(graph: Any) -> list[float | None]:
    """
    Return the full kW power series (oldest -> newest) from a ``current`` graph.

    Used to backfill Home Assistant's long-term statistics with the charging
    power history that the portal itself graphs.  ``None`` is kept for bins
    without a reading so the caller can decide how to handle gaps.
    """
    dataset = _power_dataset(graph)
    if dataset is None:
        return []
    series: list[float | None] = []
    for value in dataset.get("values") or []:
        if value is None:
            series.append(None)
            continue
        try:
            series.append(float(value))
        except (TypeError, ValueError):
            series.append(None)
    return series


def extract_power_labels(graph: Any) -> list[str]:
    """
    Return the label list (oldest -> newest) from a ``current`` graph response.

    For ``mode=3`` the portal labels carry the real per-hour timestamp in the
    account's local time, e.g. ``"07-jul. 06:00"``.  The statistics importer
    parses these so each reading is placed on its exact hour instead of being
    reconstructed from "now" (which is fragile across time zones and clock
    skew).
    """
    if not isinstance(graph, dict):
        return []
    labels = graph.get("labels")
    if not isinstance(labels, list):
        return []
    return [str(label) for label in labels]


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

    @property
    def base_url(self) -> str:
        """Return the portal base URL this client talks to."""
        return self._api.url

    def current_cookies(self) -> dict[str, str]:
        """
        Return the current portal session cookies as ``{name: value}``.

        Used to persist the freshest session cookies (which the portal may
        rotate over the life of the ~24h session) back into the config entry so
        that a Home Assistant restart reuses a still-valid session instead of
        the possibly-stale cookie captured during initial setup.
        """
        return extract_cookies_for_url(self._api.session, self._api.url)

    async def async_get_data(self) -> Any:
        """Get data from the API."""
        networks = await self._api.make_requests([NetworkOverview()])
        # When the session has expired (or was never authenticated) the portal
        # answers the API with an empty ``[]`` instead of the usual
        # ``[[ {charger}, ... ]]`` payload.  Treat that as an authentication
        # failure so the coordinator can raise ``ConfigEntryAuthFailed`` and
        # Home Assistant starts the re-authentication flow (the user then
        # supplies a fresh e-mailed 2FA code).  We deliberately only test the
        # outer list: a genuinely charger-less (but authenticated) account
        # returns ``[[]]`` and must not be forced into a reauth loop.
        if not networks:
            msg = "Session expired or invalid credentials"
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

    async def async_get_power_history(
        self,
    ) -> dict[str, tuple[list[str], list[float | None]]]:
        """
        Fetch the hourly charging-power history for every charger.

        Uses the dashboard ``current`` service in ``mode=3`` which returns an
        hourly kW time-series covering roughly the last three days (this is the
        deepest power history the portal exposes).  The result maps each
        charger IDX to a ``(labels, values)`` tuple ordered oldest -> newest.

        The ``labels`` carry the portal's own timestamps (e.g. ``"07-jul.
        04:00"``); the caller uses them to place each reading on the correct
        hour instead of guessing from "now", which avoids gaps/misalignment.
        """
        networks = await self._api.make_requests([NetworkOverview()])
        if not networks:
            msg = "Invalid credentials"
            raise FiftyfiveApiClientAuthenticationError(msg)

        idxs = [network["IDX"] for network in networks[0]]
        graphs = await self._api.make_requests(
            [Current(recharge_spot_ids=[idx], mode=3) for idx in idxs]
        )
        history: dict[str, tuple[list[str], list[float | None]]] = {}
        for idx, graph in zip(idxs, graphs, strict=False):
            history[idx] = (extract_power_labels(graph), extract_power_series(graph))
        return history

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

    async def async_get_total_energy(self) -> float | None:
        """
        Fetch the total energy delivered by all recharge spots.

        This queries the portal's ``totalUsage`` service with
        ``mode="rechargeSpot"``, which returns the lifetime total energy
        delivered across all chargers linked to the account.  The response is
        a dict like ``{"number": "4,159", "unit": "MWh"}`` (European comma
        formatting). We parse and normalize to kWh.

        Returns ``None`` on failure; failures are logged but never break
        regular polling.
        """
        try:
            result = await self._api.make_requests([TotalUsage(mode="rechargeSpot")])
            # result is a list [response_for_totalUsage]; we want the first
            data = result[0] if result else {}
            if not isinstance(data, dict):
                _LOGGER.debug("totalUsage returned unexpected type: %s", type(data))
                return None

            number_str = data.get("number", "")
            unit = data.get("unit", "kWh")

            # Parse European-formatted number (remove commas/dots as thousand sep)
            cleaned = number_str.replace(",", "").replace(".", "")
            value = float(cleaned)

            # Normalize to kWh
            if unit == "MWh":
                value *= 1000
            elif unit == "GWh":
                value *= 1_000_000

            return value
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to fetch total energy", exc_info=True)
            return None
