"""Constants for Modbus Tap."""

from typing import Final

DOMAIN: Final = "modbus_tap"

DEFAULT_PORT: Final = 8899

# Options
CONF_UNITS: Final = "units"  # {"<unit address>": {"community_map": id | None, "overrides": yaml}}
CONF_COMMUNITY_MAP: Final = "community_map"
CONF_OVERRIDES: Final = "overrides"
CONF_WRITE_EVENTS: Final = "write_events"
CONF_KEEP_RECORDINGS: Final = "keep_recordings"
CONF_REFERENCE_ENTITIES: Final = "reference_entities"

DEFAULT_KEEP_RECORDINGS: Final = 20
DEFAULT_RECORDING_HOURS: Final = 24.0

# Actions and their fields
SERVICE_START_RECORDING: Final = "start_recording"
SERVICE_STOP_RECORDING: Final = "stop_recording"
SERVICE_ADD_NOTE: Final = "add_note"
ATTR_CONFIG_ENTRY: Final = "config_entry"
ATTR_HOURS: Final = "hours"
ATTR_TEXT: Final = "text"

EVENT_WRITE: Final = "modbus_tap_write"

RECORDINGS_PATH: Final = "modbus_tap/recordings"
DOWNLOAD_URL: Final = "/api/modbus_tap/recordings/{entry_id}/{name}"

DOCS: Final = "https://github.com/janjouketjalsma/modbus-tap/blob/main/docs"
TAPPING_GUIDE: Final = f"{DOCS}/tapping-your-bus.md"
