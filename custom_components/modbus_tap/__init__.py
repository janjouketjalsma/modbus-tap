"""Modbus Tap: passively decode a Modbus RTU bus into Home Assistant sensors."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .hub import SnifferHub

PLATFORMS: list[Platform] = [Platform.SENSOR]

type SnifferConfigEntry = ConfigEntry[SnifferHub]


async def async_setup_entry(hass: HomeAssistant, entry: SnifferConfigEntry) -> bool:
    """Set up a sniffer from a config entry."""
    hub = SnifferHub(entry.data[CONF_HOST], entry.data[CONF_PORT])
    entry.runtime_data = hub

    # Entities subscribe to the hub before it starts receiving data.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_create_background_task(hass, hub.run(), f"modbus_tap {entry.title}")
    entry.async_on_unload(hub.stop)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SnifferConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: SnifferConfigEntry) -> None:
    """Reload so a changed register map takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)
