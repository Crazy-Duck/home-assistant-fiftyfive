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

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.const import UnitOfPower
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER

# Month-abbreviation -> month-number map covering the portal locales the
# integration supports (nl / en / fr).  The portal renders mode=3 labels like
# ``"07-jul. 06:00"`` using the account's locale, so we accept all of them.
_MONTHS: dict[str, int] = {
    # Dutch
    "jan": 1, "feb": 2, "mrt": 3, "apr": 4, "mei": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
    # English (only the ones that differ from the above)
    "mar": 3, "may": 5, "oct": 10,
    # French (only the ones that differ from the above)
    "janv": 1, "fevr": 2, "févr": 2, "mars": 3, "avr": 4, "juin": 6,
    "juil": 7, "aout": 8, "août": 8, "sept": 9, "dec.": 12, "déc": 12,
}

# Matches labels such as "07-jul. 06:00" -> day, month-abbr, hour, minute.
_LABEL_RE = re.compile(
    r"(?P<day>\d{1,2})\s*[-/ ]\s*(?P<mon>[^\W\d_]+)\.?\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})",
    re.UNICODE,
)

def _arithmetic_mean_type() -> object | None:
    """
    Return the recorder ``StatisticMeanType.ARITHMETIC`` value, or ``None``.

    The recorder statistics API changed over time; ``StatisticMeanType`` is
    needed to populate ``mean_type`` (required from HA 2026.11) while still
    running on older cores.  This import is done lazily (inside the function)
    rather than at module top-level: importing ``homeassistant.components.
    recorder`` is heavy (pulls in SQLAlchemy) and doing it while Home Assistant
    imports the integration would block the event loop.
    """
    try:  # pragma: no cover - depends on installed HA version
        from homeassistant.components.recorder.models import StatisticMeanType

        return StatisticMeanType.ARITHMETIC
    except Exception:  # noqa: BLE001 - older HA without StatisticMeanType
        return None


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
    arithmetic_mean = _arithmetic_mean_type()
    if arithmetic_mean is not None:
        metadata["mean_type"] = arithmetic_mean
    return metadata


def _parse_label(label: str, now: datetime) -> datetime | None:
    """
    Parse a portal ``mode=3`` label like ``"07-jul. 06:00"`` into a datetime.

    The label carries day, localized month abbreviation and time but no year,
    so the year is inferred from ``now`` (rolling back a year when the parsed
    month lies in the future, which only happens around New Year).  The result
    is timezone-aware in Home Assistant's local zone, matching the local time
    the portal renders.  Returns ``None`` when the label cannot be parsed.
    """
    match = _LABEL_RE.search(label)
    if not match:
        return None
    mon_key = match.group("mon").lower().rstrip(".")
    month = _MONTHS.get(mon_key)
    if month is None:
        return None
    try:
        day = int(match.group("day"))
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
    except (TypeError, ValueError):
        return None

    year = now.year
    # Handle the year boundary: a month far ahead of "now" belongs to last year.
    if month > now.month + 1:
        year -= 1
    try:
        naive = datetime(year, month, day, hour, minute)
    except ValueError:
        return None
    return naive.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)


def _series_to_statistics(
    series: list[float | None],
    labels: list[str] | None = None,
    include_current_hour: bool = False,
) -> list[dict]:
    """
    Map an hourly power series (oldest -> newest) onto hour-aligned statistics.

    Timestamps come from the portal's own ``mode=3`` labels when available
    (e.g. ``"07-jul. 06:00"``), so each reading lands on its exact hour
    regardless of clock skew or time zone.  When labels are missing or cannot
    be parsed, timestamps fall back to being reconstructed from "now" assuming
    the last bin is the current hour.

    Idle hours (a ``None`` reading) are recorded as ``0`` kW so the power
    history graph stays continuous instead of showing gaps when the car was
    not charging.

    Args:
        series: Hourly power values (kW), oldest to newest.
        labels: Portal labels aligned with ``series`` (oldest to newest).
        include_current_hour: If True, include the incomplete current hour in
            the statistics. Useful for manual backfills so today's data shows
            up immediately; normally False for the hourly background import to
            avoid fighting the recorder's own live compilation.
    """
    if not series:
        return []

    now = dt_util.now()
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    count = len(series)

    # Try to build timestamps from the portal labels first (robust across
    # time zones); fall back to reconstruction from "now" per-bin.
    parsed: list[datetime | None] = []
    if labels and len(labels) == count:
        parsed = [_parse_label(lbl, now) for lbl in labels]
    parsed_ok = any(ts is not None for ts in parsed)

    statistics: list[dict] = []
    for index, value in enumerate(series):
        start: datetime | None = parsed[index] if parsed_ok else None
        if start is None:
            # Fallback: assume hourly bins ending at the current hour.
            start = current_hour - timedelta(hours=(count - 1 - index))
        # Normalize to the top of the hour.
        start = start.replace(minute=0, second=0, microsecond=0)
        # Skip the current (incomplete) hour unless explicitly requested.
        if not include_current_hour and start >= current_hour:
            continue
        # Idle hours -> 0 kW so the graph stays continuous.
        reading = 0.0 if value is None else value
        statistics.append(
            {
                "start": start,
                "mean": reading,
                "min": reading,
                "max": reading,
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
    # Imported lazily (not at module top-level): importing the recorder pulls
    # in SQLAlchemy and is heavy, which would block the event loop while Home
    # Assistant imports the integration.
    from homeassistant.components.recorder.statistics import (
        async_import_statistics,
    )

    client = entry.runtime_data.client
    try:
        history = await client.async_get_power_history()
    except Exception:  # noqa: BLE001 - best effort background task
        LOGGER.warning("Could not fetch 50five power history", exc_info=True)
        return

    if not history:
        LOGGER.info("50five power history import: portal returned no chargers")
        return

    registry = er.async_get(hass)
    imported_count = 0
    for idx, (labels, series) in history.items():
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{idx}_{_POWER_KEY}"
        )
        if entity_id is None:
            LOGGER.warning(
                "No power sensor registered yet for charger %s; "
                "skipping history import",
                idx,
            )
            continue

        statistics = _series_to_statistics(series, labels, include_current_hour)
        if not statistics:
            LOGGER.info(
                "50five power history for charger %s produced no statistics "
                "(series length %d)",
                idx,
                len(series),
            )
            continue

        try:
            async_import_statistics(hass, _build_metadata(entity_id), statistics)
            imported_count += len(statistics)
            LOGGER.info(
                "Imported %d hourly power statistics for %s (%s -> %s)",
                len(statistics),
                entity_id,
                statistics[0]["start"].isoformat(),
                statistics[-1]["start"].isoformat(),
            )
        except Exception:  # noqa: BLE001 - never break the background task
            LOGGER.warning(
                "Failed to import power statistics for %s", entity_id, exc_info=True
            )

    LOGGER.info(
        "50five power history import completed: %d statistics imported%s",
        imported_count,
        " (manual, incl. current hour)" if include_current_hour else "",
    )
