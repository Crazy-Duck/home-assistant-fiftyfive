"""Constants for 50five."""

from datetime import timedelta
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "fiftyfive"
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=5)
CHARGING_UPDATE_INTERVAL = timedelta(seconds=5)

FAST_POLL_TIME = 30

CONF_CUST_TYPE = "customer_type"
