"""Constants for the Modbus Sniffer integration."""

DOMAIN = "modbus_sniffer"

DEFAULT_PORT = 8899

CONF_RAW_SENSORS = "raw_sensors"
CONF_REGISTER_MAP = "register_map"

# Decode buffered bytes when the bus has been quiet this long (seconds).
IDLE_FLUSH = 2.0
# Reconnect when nothing at all has been received for this long (seconds).
STALE_TIMEOUT = 300
CONNECT_TIMEOUT = 10
RECONNECT_MAX_DELAY = 60
