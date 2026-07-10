"""
Backfill Home Assistant long-term statistics with the charging-power history.

The 50five portal graphs charging power from its dashboard ``current`` service.
That same data can be pushed into Home Assistant's statistics database so that
the power sensor's history/statistics graphs are populated with the recent past
(roughly the last three days, which is as far back as the portal exposes hourly
power).  This is done with :func:`async_import_statistics`, targeting the power
sensor entity itself so the data shows up under that entity's history.

The recorder statistics API changed in HA 2025.10 (``has_mean`` -> ``mean_type``
and a new ``unit_class`` field).  The metadata built here includes both the old
and new fields so the integration keeps working across HA versions.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.const import UnitOfPower
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER

# The recorder statistics API changed over time.  Import the new
# ``StatisticMeanType`` enum when available so we can populate ``mean_type``
# (required from HA 2026.11) while still running on older cores.
try:  # pragma: no cover - depends on installed HA version
    from homeassistant.components.recorder.models import StatisticMeanType

    _ARITHMETIC_MEAN = StatisticMeanType.ARITHMETIC
except Exception:  # noqa: BLE001 - older HA without StatisticMeanType
    _ARITHMETIC_MEAN = None

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import FiftyfiveConfigEntry

# The power sensor's ``SensorEntityDescription.key`` (see sensor.py).  The
# entity's unique id is ``f"{idx}_{key}"``.
_POWER_KEY = "power_draw"


def _build_metadata(entity_id: str) -> dict:
    """Build recorder statistics metadata for the power sensor entity."""
    metadata: dict = {
        # ``has_mean`` is deprecated (removed in HA 2026.11) but kept for older
        # cores; ``mean_type`` is the modern replacement.
        "has_mean": True,
        "has_sum": False,
        "name": None,
        "source": "recorder",
        "statistic_id": entity_id,
        "unit_of_measurement": UnitOfPower.KILO_WATT,
        # No unit conversion needed for imported history.
        "unit_class": None,
    }
    if _ARITHMETIC_MEAN is not None:
        metadata["mean_type"] = _ARITHMETIC_MEAN
    return metadata


def _series_to_statistics(
    series: list[float | None], include_current_hour: bool = False
) -> list[dict]:
    """
    Map an hourly power series (oldest -> newest) onto hour-aligned statistics.

    The ``current`` mode=3 graph is a rolling window of hourly bins whose last
    bin is the current hour.  Timestamps are reconstructed from "now" instead
    of parsing the portal's locale-specific labels.

    Args:
        series: Hourly power values (kW), oldest to newest.
        include_current_hour: If True, include the incomplete current hour in
            the statistics. This is useful for manual imports/backfills to
            ensure today's data is visible, but normally False to avoid
            fighting the recorder's own live compilation.
    """
    if not series:
        return []

    current_hour = dt_util.now().replace(minute=0, second=0, microsecond=0)
    count = len(series)
    statistics: list[dict] = []
    for index, value in enumerate(series):
        start = current_hour - timedelta(hours=(count - 1 - index))
        # Skip the current incomplete hour unless explicitly requested
        if not include_current_hour and start >= current_hour:
            continue
        if value is None:
            continue
        statistics.append(
            {
                "start": start,
                "mean": value,
                "min": value,
                "max": value,
            }
        )
    return statistics


async def async_import_power_history(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
    include_current_hour: bool = False,
) -> None:
    """
    Fetch the portal power history and import it into HA statistics.

    Args:
        hass: Home Assistant instance.
        entry: The 50five config entry.
        include_current_hour: If True, import the incomplete current hour too.
            Normally False for automatic hourly imports (to avoid fighting the
            recorder), but can be True for manual backfills to ensure today's
            data is visible immediately.

    Best effort: any failure is logged and swallowed so it can never break the
    integration setup or polling.
    """
    client = entry.runtime_data.client
    try:
        history = await client.async_get_power_history()
    except Exception:  # noqa: BLE001 - best effort background task
        LOGGER.debug("Could not fetch 50five power history", exc_info=True)
        return

    registry = er.async_get(hass)
    imported_count = 0
    for idx, series in history.items():
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{idx}_{_POWER_KEY}"
        )
        if entity_id is None:
            LOGGER.debug("No power entity registered yet for charger %s", idx)
            continue

        statistics = _series_to_statistics(series, include_current_hour)
        if not statistics:
            continue

        LOGGER.debug(
            "Importing %d hourly power statistics for %s",
            len(statistics),
            entity_id,
        )
        try:
            async_import_statistics(hass, _build_metadata(entity_id), statistics)
            imported_count += len(statistics)
        except Exception:  # noqa: BLE001 - never break the background task
            LOGGER.debug(
                "Failed to import power statistics for %s", entity_id, exc_info=True
            )

    if include_current_hour and imported_count > 0:
        LOGGER.info(
            "Manual power history import completed: %d statistics imported",
            imported_count,
        )
