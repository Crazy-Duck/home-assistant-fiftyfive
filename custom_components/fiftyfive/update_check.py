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
    UPDATE_TAGS_URL,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import FiftyfiveConfigEntry

_REQUEST_TIMEOUT = 20
_GITHUB_HEADERS = {"Accept": "application/vnd.github+json"}


def _normalise(version: str | None) -> str | None:
    """Strip a leading ``v`` (e.g. ``v0.10.2`` -> ``0.10.2``)."""
    if not version:
        return None
    version = version.strip()
    return version[1:] if version[:1].lower() == "v" else version


def _is_newer(candidate: str, installed: str) -> bool:
    """Return True when ``candidate`` is a newer version than ``installed``."""
    try:
        return AwesomeVersion(candidate) > AwesomeVersion(installed)
    except AwesomeVersionException:
        # Fall back to a simple string compare if the tags are not semver.
        LOGGER.debug("Non-semver version compare: %s vs %s", candidate, installed)
        return candidate != installed


async def _fetch_latest_release(hass: HomeAssistant) -> tuple[str | None, str | None]:
    """
    Return ``(version, release_url)`` from the GitHub *releases/latest* API.

    Returns ``(None, None)`` on any error (logged as a warning).  Draft and
    pre-releases are excluded by this GitHub endpoint by design.
    """
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            UPDATE_LATEST_RELEASE_URL,
            headers=_GITHUB_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        ) as response:
            if response.status == 404:  # noqa: PLR2004 - no releases published yet
                LOGGER.debug("No published GitHub release found (404)")
                return None, None
            if response.status != 200:  # noqa: PLR2004
                LOGGER.warning(
                    "GitHub release check returned HTTP %s", response.status
                )
                return None, None
            payload = await response.json()
    except Exception as err:  # noqa: BLE001 - best effort background task
        LOGGER.warning("Failed to fetch GitHub release: %s", err, exc_info=True)
        return None, None

    version = _normalise(payload.get("tag_name") or payload.get("name"))
    release_url = payload.get("html_url") or UPDATE_RELEASES_URL
    return version, release_url


async def _fetch_latest_tag(hass: HomeAssistant) -> str | None:
    """
    Return the highest semver version from the GitHub *tags* API.

    Used as a fallback so a freshly pushed version *tag* is detected even when
    no formal GitHub Release exists for it yet.  Returns ``None`` on any error.
    """
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            UPDATE_TAGS_URL,
            headers=_GITHUB_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        ) as response:
            if response.status != 200:  # noqa: PLR2004
                LOGGER.warning("GitHub tags check returned HTTP %s", response.status)
                return None
            payload = await response.json()
    except Exception as err:  # noqa: BLE001 - best effort background task
        LOGGER.warning("Failed to fetch GitHub tags: %s", err, exc_info=True)
        return None

    if not isinstance(payload, list):
        return None
    best: str | None = None
    for tag in payload:
        version = _normalise(tag.get("name")) if isinstance(tag, dict) else None
        if version is None:
            continue
        if best is None or _is_newer(version, best):
            best = version
    return best


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

    # 1) Prefer a formal GitHub Release (has proper release notes + URL).
    release_version, release_url = await _fetch_latest_release(hass)
    # 2) Also look at raw tags, so a freshly pushed version *tag* is detected
    #    even before/without a formal Release being published.
    tag_version = await _fetch_latest_tag(hass)

    # Pick whichever source reports the highest version.
    latest = release_version
    if tag_version is not None and (
        latest is None or _is_newer(tag_version, latest)
    ):
        latest = tag_version
        # A tag ahead of the latest release has no release page yet; point the
        # user at the releases/tags overview instead.
        if release_version is None or _is_newer(tag_version, release_version):
            release_url = UPDATE_RELEASES_URL

    if not release_url:
        release_url = UPDATE_RELEASES_URL

    state["latest"] = latest
    state["release_url"] = release_url
    LOGGER.info(
        "50five update check: release=%s tag=%s -> latest=%s",
        release_version,
        tag_version,
        latest,
    )
    if latest is None:
        LOGGER.warning("Could not determine latest 50five version from GitHub")
        return

    if _is_newer(latest, installed):
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
