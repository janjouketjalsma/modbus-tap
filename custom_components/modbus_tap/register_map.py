"""Register maps in the core Modbus sensor format (ADR 0004), plus Overrides (ADR 0003)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

import yaml

from .model import RegisterKey, Table
from .values import INTEGER_TYPES, DataType, Swap, decode, register_count, scale_value

# Keys that only make sense when Home Assistant polls the Unit itself.
IGNORED_KEYS = frozenset({"scan_interval", "unique_id"})
# Core features that read many values from one block; not built until someone needs them.
UNSUPPORTED_KEYS = frozenset({"structure", "slave_count", "virtual_count"})
TAP_KEYS = frozenset({"documented", "verified", "model"})
CORE_KEYS = frozenset(
    {
        "name", "address", "device_address", "slave", "input_type", "data_type", "count", "swap",
        "scale", "offset", "precision", "nan_value", "min_value", "max_value", "zero_suppress",
        "unit_of_measurement", "device_class", "state_class",
    }
)
SENSOR_TABLES = {"holding": Table.HOLDING, "input": Table.INPUT}


class RegisterMapError(ValueError):
    """A Register map could not be read; the message says where and why."""


@dataclass(frozen=True, slots=True)
class MapEntry:
    """One named value in a Register map."""

    name: str
    address: int
    device_address: int = 1
    table: Table = Table.HOLDING
    data_type: DataType = DataType.INT16
    count: int | None = None
    swap: Swap = Swap.NONE
    scale: float = 1.0
    offset: float = 0.0
    precision: int | None = None
    nan_value: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    zero_suppress: float | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    documented: str | None = None
    verified: str | None = None
    model: bool = False

    @property
    def size(self) -> int:
        return register_count(self.data_type, self.count)

    @property
    def keys(self) -> list[RegisterKey]:
        return [(self.device_address, self.table, self.address + i) for i in range(self.size)]

    @property
    def slot(self) -> RegisterKey:
        """What an Override matches on: Unit address, table and address."""
        return (self.device_address, self.table, self.address)

    @property
    def guessed(self) -> bool:
        return not self.documented and not self.verified

    def value(self, registers: list[int]) -> int | float | str | None:
        raw = decode(self.data_type, registers, self.swap)
        if isinstance(raw, str):
            return raw
        return scale_value(
            raw,
            integer_type=self.data_type in INTEGER_TYPES,
            scale=self.scale,
            offset=self.offset,
            precision=self.precision,
            nan_value=self.nan_value,
            min_value=self.min_value,
            max_value=self.max_value,
            zero_suppress=self.zero_suppress,
        )


@dataclass(frozen=True, slots=True)
class ParsedMap:
    entries: tuple[MapEntry, ...]
    notices: tuple[str, ...]  # things that were accepted but ignored


def parse_yaml(text: str | None) -> ParsedMap:
    """Parse a user's YAML list of core-style sensors."""
    return parse_entries(_load_list(text))


def merge_yaml(existing: str | None, additions: str | None) -> str:
    """Add entries to a user's list; an added entry replaces one at the same slot.

    Kept as text (comments and all) when nothing is replaced.
    """
    old, new = _load_list(existing), _load_list(additions)
    if not new:
        return existing or ""
    replaced = {_parse_entry(item, "entry")[0].slot for item in new}
    kept = [item for item in old if _parse_entry(item, "entry")[0].slot not in replaced]
    if len(kept) == len(old) and not (existing and "sensors:" in existing):
        return f"{existing.rstrip()}\n{additions.strip()}\n" if old else f"{additions.strip()}\n"
    return yaml.safe_dump(kept + new, sort_keys=False, allow_unicode=True)


def _load_list(text: str | None) -> list[Any]:
    if not text or not text.strip():
        return []
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise RegisterMapError(f"YAML error: {err}") from err
    if data is None:
        return []
    if isinstance(data, dict) and "sensors" in data:
        data = data["sensors"]
    if not isinstance(data, list):
        raise RegisterMapError("expected a list of sensors, each starting with '- name:'")
    return data


def parse_entries(items: Iterable[Any]) -> ParsedMap:
    entries: list[MapEntry] = []
    notices: list[str] = []
    seen: set[RegisterKey] = set()
    for index, item in enumerate(items, start=1):
        entry, entry_notices = _parse_entry(item, f"sensor {index}")
        if entry.slot in seen:
            raise RegisterMapError(f"{entry.name}: register {entry.address} is mapped twice")
        seen.add(entry.slot)
        entries.append(entry)
        notices.extend(entry_notices)
    return ParsedMap(tuple(entries), tuple(notices))


def _parse_entry(item: Any, where: str) -> tuple[MapEntry, list[str]]:
    if not isinstance(item, Mapping):
        raise RegisterMapError(f"{where}: expected a mapping like '- name: ...'")
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RegisterMapError(f"{where}: 'name' is required")
    where = f"{name.strip()}"
    keys = set(item)
    if unsupported := keys & UNSUPPORTED_KEYS:
        raise RegisterMapError(f"{where}: {', '.join(sorted(unsupported))} is not supported yet")
    if item.get("data_type") == "custom":
        raise RegisterMapError(f"{where}: data_type custom is not supported yet")
    if unknown := keys - CORE_KEYS - TAP_KEYS - IGNORED_KEYS:
        raise RegisterMapError(f"{where}: unknown key(s) {', '.join(sorted(map(str, unknown)))}")
    if "address" not in item:
        raise RegisterMapError(f"{where}: 'address' is required")
    if "device_address" in item and "slave" in item:
        raise RegisterMapError(f"{where}: use either device_address or slave, not both")

    table = SENSOR_TABLES.get(str(item.get("input_type", "holding")))
    if table is None:
        raise RegisterMapError(f"{where}: input_type must be holding or input")
    data_type = _enum(DataType, item.get("data_type", "int16"), "data_type", where)
    count = _number(item, "count", int, where)
    if data_type is DataType.STRING and not count:
        raise RegisterMapError(f"{where}: a string needs 'count' (registers)")
    entry = MapEntry(
        name=name.strip(),
        address=_address(item, where),
        device_address=_number(item, "device_address", int, where) or _number(item, "slave", int, where) or 1,
        table=table,
        data_type=data_type,
        count=count,
        swap=_enum(Swap, item.get("swap") or "none", "swap", where),
        scale=_number(item, "scale", float, where) or 1.0,
        offset=_number(item, "offset", float, where) or 0.0,
        precision=_number(item, "precision", int, where),
        nan_value=_nan(item, where),
        min_value=_number(item, "min_value", float, where),
        max_value=_number(item, "max_value", float, where),
        zero_suppress=_number(item, "zero_suppress", float, where),
        unit_of_measurement=_text(item, "unit_of_measurement"),
        device_class=_text(item, "device_class"),
        state_class=_text(item, "state_class"),
        documented=_text(item, "documented"),
        verified=_text(item, "verified"),
        model=bool(item.get("model", False)),
    )
    if entry.model and data_type is not DataType.STRING:
        raise RegisterMapError(f"{where}: 'model: true' needs data_type string")
    notices = [f"{where}: {key} is ignored (Modbus Tap only listens)" for key in sorted(keys & IGNORED_KEYS)]
    return entry, notices


def _address(item: Mapping, where: str) -> int:
    address = _number(item, "address", int, where)
    if address is None or not 0 <= address <= 0xFFFF:
        raise RegisterMapError(f"{where}: address must be 0-65535")
    return address


def _number(item: Mapping, key: str, kind: type, where: str) -> Any:
    value = item.get(key)
    if value is None:
        return None
    try:
        return kind(int(value, 0)) if isinstance(value, str) and kind is int else kind(value)
    except (TypeError, ValueError) as err:
        raise RegisterMapError(f"{where}: {key} must be a number") from err


def _nan(item: Mapping, where: str) -> int | None:
    return _number(item, "nan_value", int, where)


def _text(item: Mapping, key: str) -> str | None:
    value = item.get(key)
    return None if value is None else str(value)


def _enum(kind: type, value: Any, key: str, where: str) -> Any:
    try:
        return kind(str(value))
    except ValueError as err:
        allowed = ", ".join(member.value for member in kind)
        raise RegisterMapError(f"{where}: {key} must be one of {allowed}") from err


def apply_overrides(base: Iterable[MapEntry], overrides: Iterable[MapEntry]) -> list[MapEntry]:
    """A Community map with the user's Overrides on top (matched by Unit, table, address)."""
    merged = {entry.slot: entry for entry in base}
    for entry in overrides:
        merged[entry.slot] = entry
    return list(merged.values())


def with_unit(entries: Iterable[MapEntry], unit: int) -> list[MapEntry]:
    """Place a map's entries on a given Unit address."""
    return [replace(entry, device_address=unit) for entry in entries]


def to_core(entry: MapEntry, **extra: Any) -> dict[str, Any]:
    """The entry as a core Modbus sensor config (Tap-only keys left out)."""
    out: dict[str, Any] = {"name": entry.name, "address": entry.address, "device_address": entry.device_address}
    defaults = MapEntry(name="", address=0)
    for key in ("data_type", "count", "swap", "scale", "offset", "precision", "nan_value", "min_value",
                "max_value", "zero_suppress", "unit_of_measurement", "device_class", "state_class"):
        value = getattr(entry, key)
        if value is not None and value != getattr(defaults, key):
            out[key] = value.value if hasattr(value, "value") else value
    out["input_type"] = entry.table.value
    out.update(extra)
    return out
