"""Constants for 50five."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "fiftyfive"
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=5)
CHARGING_UPDATE_INTERVAL = timedelta(seconds=5)

FAST_POLL_TIME = 30

CONF_CUST_TYPE = "customer_type"
CONF_2FA_CODE = "auth_code"
CONF_COOKIES = "session_cookies"

# GitHub repository that publishes the releases for this integration.  Used by
# the update checker to notify the user when a newer version is available.
UPDATE_REPO = "pimhofstee/50five-HA-2fa"
UPDATE_LATEST_RELEASE_URL = (
    f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
)
# Tags endpoint is used as a fallback so a freshly pushed version *tag* is
# detected even when no formal GitHub Release has been published for it yet.
UPDATE_TAGS_URL = f"https://api.github.com/repos/{UPDATE_REPO}/tags"
UPDATE_RELEASES_URL = f"https://github.com/{UPDATE_REPO}/releases"
# How often to check GitHub for a newer release.  Kept short so a newly
# published version shows up in the HA notification center within minutes
# instead of up to a day.  GitHub's unauthenticated rate limit is 60 requests
# per hour per IP; at 15-minute intervals (~8 requests/hour incl. the tags
# fallback) we stay comfortably within it.
UPDATE_CHECK_INTERVAL = timedelta(minutes=15)
# How often to re-import the portal power history into HA statistics.  The
# portal exposes a rolling ~3-day hourly window, so an hourly refresh keeps the
# statistics filled without gaps (e.g. after HA downtime).
STATISTICS_IMPORT_INTERVAL = timedelta(hours=1)
