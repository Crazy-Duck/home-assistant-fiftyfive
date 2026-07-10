"""
Check GitHub for newer releases of this integration.

HACS shows updates in its own UI, but not everyone browses HACS regularly.
This module polls the GitHub *Releases* API for the repository that publishes
the integration and:
1. Updates the ``update_state`` dict (powering binary_sensor.fiftyfive_update_available)
2. Creates a persistent notification in HA's notification center when a newer version exists

The notification auto-dismisses when you update to the latest version.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from awesomeversion import AwesomeVersion, AwesomeVersionException
from homeassistant.components import persistent_notification
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    LOGGER,
    UPDATE_LATEST_RELEASE_URL,
    UPDATE_NOTIFICATION_ID,
    UPDATE_RELEASES_URL,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import FiftyfiveConfigEntry

_REQUEST_TIMEOUT = 20


def _normalise(version: str | None) -> str | None:
    """Strip a leading ``v`` (e.g. ``v0.10.2`` -> ``0.10.2``)."""
    if not version:
        return None
    version = version.strip()
    return version[1:] if version[:1].lower() == "v" else version


async def async_check_for_update(
    hass: HomeAssistant,
    entry: FiftyfiveConfigEntry,
) -> None:
    """
    Check GitHub for a newer release and notify the user.

    Updates the ``update_state`` dict (powering the binary sensor) and creates
    a persistent notification in HA's notification center when a newer version
    exists. The notification auto-dismisses when you're on the latest version.

    Best effort: network/parse errors are logged and never propagate, so this
    can be scheduled safely in the background.
    """
    state = entry.runtime_data.update_state
    installed_raw = str(entry.runtime_data.integration.version)
    installed = _normalise(installed_raw)
    state["installed"] = installed
    
    LOGGER.info("50five update check started (installed: %s)", installed)
    
    if installed is None:
        LOGGER.warning("Installed 50five version unknown; skipping update check")
        return

    session = async_get_clientsession(hass)
    try:
        async with session.get(
            UPDATE_LATEST_RELEASE_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=_REQUEST_TIMEOUT,
        ) as response:
            if response.status != 200:  # noqa: PLR2004
                LOGGER.warning(
                    "GitHub release check returned HTTP %s", response.status
                )
                return
            payload = await response.json()
            LOGGER.debug("GitHub API response: %s", payload.get("tag_name"))
    except Exception as err:  # noqa: BLE001 - best effort background task
        LOGGER.warning("Failed to check GitHub for updates: %s", err, exc_info=True)
        return

    latest = _normalise(payload.get("tag_name") or payload.get("name"))
    release_url = payload.get("html_url") or UPDATE_RELEASES_URL
    state["latest"] = latest
    state["release_url"] = release_url
    if latest is None:
        LOGGER.warning("GitHub release payload had no usable version")
        return

    try:
        is_newer = AwesomeVersion(latest) > AwesomeVersion(installed)
    except AwesomeVersionException:
        # Fall back to a simple string compare if the tags are not semver.
        is_newer = latest != installed
        LOGGER.debug("Non-semver version compare: %s vs %s", latest, installed)

    if is_newer:
        LOGGER.info(
            "A new 50five release is available: %s (installed: %s)",
            latest,
            installed,
        )
        try:
            persistent_notification.async_create(
                hass,
                (
                    f"A new version of the **50five** integration is available.\n\n"
                    f"- Installed: `{installed}`\n"
                    f"- Latest: `{latest}`\n\n"
                    f"Update via HACS, or view the release notes "
                    f"[on GitHub]({release_url})."
                ),
                title="50five update available",
                notification_id=UPDATE_NOTIFICATION_ID,
            )
            LOGGER.info("Update notification created (ID: %s)", UPDATE_NOTIFICATION_ID)
        except Exception as err:  # noqa: BLE001
            LOGGER.error(
                "Failed to create update notification: %s", err, exc_info=True
            )
    else:
        LOGGER.info(
            "50five up to date (installed %s, latest %s)", installed, latest
        )
        # Clear any stale notification from a previous (now-installed) update.
        try:
            persistent_notification.async_dismiss(hass, UPDATE_NOTIFICATION_ID)
        except Exception as err:  # noqa: BLE001
            LOGGER.debug("Failed to dismiss notification: %s", err)
