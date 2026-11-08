"""Sensors for Modbus Tap."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SnifferConfigEntry
from .const import CONF_RAW_SENSORS, CONF_REGISTER_MAP, DOMAIN
from .hub import RegisterKey, SnifferHub
from .regmap import MappedRegister, RegisterMapError, parse_register_map, scaled_value
from .rtu import decode_value

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SnifferConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    hub = entry.runtime_data
    device = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Modbus Tap {entry.title}",
        manufacturer="Modbus Tap",
        model="Passive Modbus RTU listener",
    )

    try:
        mapped = parse_register_map(entry.options.get(CONF_REGISTER_MAP, ""))
    except RegisterMapError as err:  # stored map should already be valid
        _LOGGER.error("Ignoring invalid register map: %s", err)
        mapped = []

    entities: list[SensorEntity] = [MappedSensor(hub, entry, device, reg) for reg in mapped]
    entities += [
        StatusSensor(hub, entry, device, kind)
        for kind in ("connection", "frames", "discarded", "registers", "last_frame")
    ]
    async_add_entities(entities)

    if entry.options.get(CONF_RAW_SENSORS, True):
        created: set[RegisterKey] = set()

        @callback
        def _new_keys(keys: list[RegisterKey]) -> None:
            fresh = [k for k in keys if k not in created]
            created.update(fresh)
            if fresh:
                async_add_entities(RawSensor(hub, entry, device, key) for key in fresh)

        entry.async_on_unload(hub.listen_new_keys(_new_keys))
        if hub.registers:
            _new_keys(list(hub.registers))


class _SnifferEntity(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: SnifferHub, entry: SnifferConfigEntry, device: DeviceInfo) -> None:
        self.hub = hub
        self._attr_device_info = device
        self._entry_id = entry.entry_id


class MappedSensor(_SnifferEntity):
    """A named, scaled value from the register map."""

    def __init__(self, hub, entry, device, reg: MappedRegister) -> None:
        super().__init__(hub, entry, device)
        self.reg = reg
        self._keys = reg.keys
        self._attr_name = reg.name
        self._attr_unique_id = f"{entry.entry_id}_map_{reg.uid}"
        self._attr_native_unit_of_measurement = reg.unit_of_measurement
        self._attr_icon = reg.icon
        if reg.precision is not None and reg.data_type != "string":
            self._attr_suggested_display_precision = reg.precision
        if reg.device_class:
            try:
                self._attr_device_class = SensorDeviceClass(reg.device_class)
            except ValueError:
                _LOGGER.warning("%s: unknown device_class %s", reg.name, reg.device_class)
        if reg.state_class:
            try:
                self._attr_state_class = SensorStateClass(reg.state_class)
            except ValueError:
                _LOGGER.warning("%s: unknown state_class %s", reg.name, reg.state_class)

    _was_connected: bool | None = None

    async def async_added_to_hass(self) -> None:
        for key in self._keys:
            self.async_on_remove(self.hub.listen_key(key, self.async_write_ha_state))
        self.async_on_remove(self.hub.listen_status(self._status))

    @callback
    def _status(self) -> None:
        # Only the connection state matters here; value changes arrive via listen_key.
        if self.hub.connected != self._was_connected:
            self._was_connected = self.hub.connected
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.hub.connected and self.hub.values(self._keys) is not None

    @property
    def native_value(self) -> Any:
        regs = self.hub.values(self._keys)
        if regs is None:
            return None
        return scaled_value(self.reg, decode_value(self.reg.data_type, regs))


class RawSensor(_SnifferEntity):
    """One raw 16-bit register, created automatically when first seen."""

    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hub, entry, device, key: RegisterKey) -> None:
        super().__init__(hub, entry, device)
        self.key = key
        slave, table, address = key
        self._attr_name = f"Slave {slave} {table} {address}"
        self._attr_unique_id = f"{entry.entry_id}_raw_{slave}_{table}_{address}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.hub.listen_key(self.key, self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self.key in self.hub.registers

    @property
    def native_value(self) -> int | None:
        return self.hub.value(self.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self.hub.registers.get(self.key)
        if stats is None:
            return {}
        v = stats.value
        hi, lo = v >> 8, v & 0xFF
        text = "".join(chr(c) if 32 <= c < 127 else "." for c in (hi, lo))
        return {
            "address_hex": f"0x{self.key[2]:04X}",
            "hex": f"0x{v:04X}",
            "signed": v - 0x10000 if v & 0x8000 else v,
            "ascii": text,
            "min": stats.minimum,
            "max": stats.maximum,
            "changes": stats.changes,
            "decreases": stats.decreases,
            "written_by_master": stats.written,
        }


STATUS_DESCRIPTIONS: dict[str, dict[str, Any]] = {
    "connection": {"name": "Connection", "device_class": SensorDeviceClass.ENUM, "options": ["connected", "disconnected"]},
    "frames": {"name": "Frames decoded", "state_class": SensorStateClass.TOTAL_INCREASING},
    "discarded": {"name": "Bytes discarded", "state_class": SensorStateClass.TOTAL_INCREASING, "unit": "B"},
    "registers": {"name": "Registers seen", "state_class": SensorStateClass.MEASUREMENT},
    "last_frame": {"name": "Last frame", "device_class": SensorDeviceClass.TIMESTAMP},
}


class StatusSensor(_SnifferEntity):
    """Health of the connection and decoder."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub, entry, device, kind: str) -> None:
        super().__init__(hub, entry, device)
        self.kind = kind
        desc = STATUS_DESCRIPTIONS[kind]
        self._attr_name = desc["name"]
        self._attr_unique_id = f"{entry.entry_id}_status_{kind}"
        self._attr_device_class = desc.get("device_class")
        self._attr_state_class = desc.get("state_class")
        self._attr_native_unit_of_measurement = desc.get("unit")
        if "options" in desc:
            self._attr_options = desc["options"]
        self._last: Any = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.hub.listen_status(self._status))

    @callback
    def _status(self) -> None:
        value = self.native_value
        if value != self._last:
            self._last = value
            self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        hub = self.hub
        if self.kind == "connection":
            return "connected" if hub.connected else "disconnected"
        if self.kind == "frames":
            return hub.decoder.frames
        if self.kind == "discarded":
            return hub.decoder.discarded_bytes
        if self.kind == "registers":
            return len(hub.registers)
        if hub.last_frame is None:
            return None
        return datetime.fromtimestamp(hub.last_frame, tz=UTC)
