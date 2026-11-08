"""Export a Bus's Register maps as core Modbus YAML, for replacing the Poller."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import yaml

from .register_map import MapEntry, to_core

DEFAULT_SCAN_INTERVAL = 30


def core_modbus_yaml(
    host: str,
    port: int,
    maps: Mapping[int, Sequence[MapEntry]],
    poll_intervals: Mapping[int, float | None],
) -> str:
    """A ready-to-paste `modbus:` block polling the same Units through the same Bridge."""
    sensors = []
    for unit in sorted(maps):
        interval = poll_intervals.get(unit)
        scan = max(1, round(interval)) if interval else DEFAULT_SCAN_INTERVAL
        sensors.extend(to_core(entry, scan_interval=scan) for entry in maps[unit])
    hub = {"name": "modbus_tap_export", "type": "rtuovertcp", "host": host, "port": port, "sensors": sensors}
    return yaml.safe_dump({"modbus": [hub]}, sort_keys=False, allow_unicode=True)
