"""Sensors: mapped Register values per Unit, and the Bridge's health."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TapConfigEntry
from .entity import TapEntity, bridge_identifier, unit_identifier
from .register_map import MapEntry
from .tap import Tap

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: TapConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    tap = entry.runtime_data
    entities: list[SensorEntity] = [BridgeSensor(tap, description) for description in BRIDGE_SENSORS]
    for unit, entries in tap.maps.items():
        entities.extend(MappedSensor(tap, unit, map_entry) for map_entry in entries)
    async_add_entities(entities)


def _enum_or_none(kind: type, value: str | None, name: str) -> Any:
    if value is None:
        return None
    try:
        return kind(value)
    except ValueError:
        _LOGGER.warning("%s: %s is not a valid %s, ignoring it", name, value, kind.__name__)
        return None


class MappedSensor(TapEntity, SensorEntity):
    """One named value from a Unit's Register map."""

    def __init__(self, tap: Tap, unit: int, entry: MapEntry) -> None:
        super().__init__(unit_identifier(tap.entry, unit))
        self.tap = tap
        self.map_entry = entry
        self._attr_name = entry.name
        self._attr_unique_id = f"{tap.entry.entry_id}_{unit}_{entry.table.value}_{entry.address}_{entry.data_type.value}"
        self._attr_native_unit_of_measurement = entry.unit_of_measurement
        self._attr_device_class = _enum_or_none(SensorDeviceClass, entry.device_class, entry.name)
        self._attr_state_class = _enum_or_none(SensorStateClass, entry.state_class, entry.name)
        if entry.precision is not None:
            self._attr_suggested_display_precision = entry.precision

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.tap.store.subscribe(self.map_entry.keys, self.async_write_ha_state))

    def _registers(self) -> list[int] | None:
        return self.tap.store.values(self.map_entry.keys, now=time.time())

    @property
    def available(self) -> bool:
        return self._registers() is not None

    @property
    def native_value(self) -> int | float | str | None:
        registers = self._registers()
        return None if registers is None else self.map_entry.value(registers)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        entry = self.map_entry
        status = "guessed" if entry.guessed else ", ".join(
            label for label, value in (("documented", entry.documented), ("verified", entry.verified)) if value
        )
        attributes: dict[str, Any] = {"register": f"{entry.table.value} {entry.address}", "map_status": status}
        if entry.documented:
            attributes["documented"] = entry.documented
        if entry.verified:
            attributes["verified"] = entry.verified
        return attributes


@dataclass(frozen=True, kw_only=True)
class BridgeSensorDescription(SensorEntityDescription):
    value: Callable[[Tap], Any]


BRIDGE_SENSORS = (
    BridgeSensorDescription(
        key="connection",
        translation_key="connection",
        device_class=SensorDeviceClass.ENUM,
        options=["connected", "disconnected"],
        value=lambda tap: "connected" if tap.listener.connected else "disconnected",
    ),
    BridgeSensorDescription(
        key="frames_decoded",
        translation_key="frames_decoded",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda tap: tap.listener.decoder.frames,
    ),
    BridgeSensorDescription(
        key="bytes_discarded",
        translation_key="bytes_discarded",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda tap: tap.listener.decoder.discarded_bytes,
    ),
    BridgeSensorDescription(
        key="last_transaction",
        translation_key="last_transaction",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda tap: datetime.fromtimestamp(tap.last_transaction, UTC) if tap.last_transaction else None,
    ),
    BridgeSensorDescription(
        key="recording",
        translation_key="recording",
        value=lambda tap: tap.session.name if tap.session else None,
    ),
)


class BridgeSensor(TapEntity, SensorEntity):
    entity_description: BridgeSensorDescription

    def __init__(self, tap: Tap, description: BridgeSensorDescription) -> None:
        super().__init__(bridge_identifier(tap.entry))
        self.tap = tap
        self.entity_description = description
        self._attr_unique_id = f"{tap.entry.entry_id}_{description.key}"
        self._last: Any = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.tap.listen_status(self._status_changed))

    @callback
    def _status_changed(self) -> None:
        value = self.native_value
        if value != self._last:
            self._last = value
            self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.tap)
