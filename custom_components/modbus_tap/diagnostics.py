"""Diagnostics: a full table of sniffed registers with hints.

Download it from the integration page (three dots > Download diagnostics) to
see every register on the bus and which ones might be worth mapping.
Note that it may contain serial numbers read from your devices.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import SnifferConfigEntry
from .hints import find_strings, register_hints


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: SnifferConfigEntry) -> dict[str, Any]:
    hub = entry.runtime_data
    table = []
    for (slave, tbl, addr), stats in sorted(hub.registers.items()):
        v = stats.value
        table.append(
            {
                "slave": slave,
                "table": tbl,
                "address": addr,
                "address_hex": f"0x{addr:04X}",
                "value": v,
                "signed": v - 0x10000 if v & 0x8000 else v,
                "min": stats.minimum,
                "max": stats.maximum,
                "changes": stats.changes,
                "updates": stats.updates,
                "hints": register_hints(stats),
            }
        )
    return {
        "connection": {
            "host": hub.host,
            "port": hub.port,
            "connected": hub.connected,
            "bytes_received": hub.bytes_received,
            "frames": hub.decoder.frames,
            "transactions": hub.decoder.transactions,
            "discarded_bytes": hub.decoder.discarded_bytes,
        },
        "options": dict(entry.options),
        "strings": find_strings(hub.registers),
        "registers": table,
    }
