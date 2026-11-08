"""Devices and the base entity (ADR 0002: a Bridge device, and one device per Unit).

The devices themselves are registered by the Tap when it starts or hears a new
Unit; entities only point at them.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


def bridge_identifier(entry: ConfigEntry) -> tuple[str, str]:
    return (DOMAIN, f"{entry.entry_id}_bridge")


def unit_identifier(entry: ConfigEntry, unit: int) -> tuple[str, str]:
    return (DOMAIN, f"{entry.entry_id}_unit_{unit}")


class TapEntity(Entity):
    """Entities are pushed from the Bus; nothing polls."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, identifier: tuple[str, str]) -> None:
        self._attr_device_info = DeviceInfo(identifiers={identifier})
