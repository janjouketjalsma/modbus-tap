"""Diagnostics: every Register heard on the Bus, with hints for writing a map.

May include serial numbers read from your devices; check before sharing.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import TapConfigEntry
from .hints import describe, find_strings


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: TapConfigEntry) -> dict[str, Any]:
    tap = entry.runtime_data
    listener = tap.listener
    return {
        "bridge": {
            "host": listener.host,
            "port": listener.port,
            "connected": listener.connected,
            "bytes_received": listener.bytes_received,
            "frames": listener.decoder.frames,
            "bytes_discarded": listener.decoder.discarded_bytes,
        },
        "options": dict(entry.options),
        "units": {
            str(unit): {
                "poll_interval": tap.store.poll_interval(unit),
                "reads": sorted(f"{table.value} {start}-{start + count - 1}" for table, start, count in tap.store.reads.get(unit, set())),
            }
            for unit in sorted(tap.store.units)
        },
        "strings": find_strings(tap.store.registers),
        "registers": describe(tap.store.registers.items()),
        "writes": tap.writes.as_dict(),
    }
