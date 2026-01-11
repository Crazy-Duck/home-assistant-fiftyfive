"""Constants for 50five."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "50five"
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=5)
CHARGING_UPDATE_INTERVAL = timedelta(seconds=5)

FAST_POLL_TIME = 30
