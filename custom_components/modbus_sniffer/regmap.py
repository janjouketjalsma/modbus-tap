"""Register map: turns user YAML into named, scaled sensor definitions.

Pure Python (no Home Assistant imports) so it can be unit tested.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from .rtu import DATA_TYPES, TABLE_COILS, TABLE_DISCRETE, TABLE_HOLDING, TABLE_INPUT, register_span

TABLE_ALIASES = {
    "input": TABLE_INPUT,
    "input_register": TABLE_INPUT,
    "4": TABLE_INPUT,
    "holding": TABLE_HOLDING,
    "holding_register": TABLE_HOLDING,
    "3": TABLE_HOLDING,
    "coil": TABLE_COILS,
    "1": TABLE_COILS,
    "discrete": TABLE_DISCRETE,
    "discrete_input": TABLE_DISCRETE,
    "2": TABLE_DISCRETE,
}

ALLOWED_KEYS = {
    "name",
    "slave",
    "table",
    "address",
    "data_type",
    "count",
    "scale",
    "offset",
    "precision",
    "unit_of_measurement",
    "device_class",
    "state_class",
    "icon",
}


class RegisterMapError(ValueError):
    """The register map could not be parsed."""


@dataclass(frozen=True, slots=True)
class MappedRegister:
    """One named value built from one or more registers."""

    name: str
    slave: int
    table: str
    address: int
    data_type: str = "uint16"
    count: int = 1
    scale: float = 1.0
    offset: float = 0.0
    precision: int | None = None
    unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    icon: str | None = None

    @property
    def span(self) -> int:
        return register_span(self.data_type, self.count)

    @property
    def keys(self) -> list[tuple[int, str, int]]:
        return [(self.slave, self.table, self.address + i) for i in range(self.span)]

    @property
    def uid(self) -> str:
        return f"{self.slave}_{self.table}_{self.address}_{self.data_type}"


def _num(item: dict, key: str, kind, default, where: str):
    if key not in item or item[key] is None:
        return default
    try:
        return kind(item[key])
    except (TypeError, ValueError) as err:
        raise RegisterMapError(f"{where}: '{key}' must be a number") from err


def parse_register_map(text: str | None) -> list[MappedRegister]:
    """Parse and validate the YAML register map."""
    if not text or not text.strip():
        return []
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise RegisterMapError(f"YAML error: {err}") from err
    if data is None:
        return []
    if not isinstance(data, list):
        raise RegisterMapError("the map must be a list of entries (each starting with '- ')")

    result: list[MappedRegister] = []
    seen: set[str] = set()
    for idx, item in enumerate(data, start=1):
        where = f"entry {idx}"
        if not isinstance(item, dict):
            raise RegisterMapError(f"{where}: must be a mapping like '- name: ...'")
        unknown = set(item) - ALLOWED_KEYS
        if unknown:
            raise RegisterMapError(f"{where}: unknown key(s) {', '.join(sorted(map(str, unknown)))}")
        name = item.get("name")
        if not name or not isinstance(name, str):
            raise RegisterMapError(f"{where}: 'name' is required")
        where = f"entry {idx} ({name})"
        if "address" not in item:
            raise RegisterMapError(f"{where}: 'address' is required")
        address = _num(item, "address", int, None, where)
        if not 0 <= address <= 0xFFFF:
            raise RegisterMapError(f"{where}: address out of range")
        table = TABLE_ALIASES.get(str(item.get("table", "input")).lower())
        if table is None:
            raise RegisterMapError(f"{where}: table must be input, holding, coil or discrete")
        data_type = str(item.get("data_type", "uint16")).lower()
        if data_type not in DATA_TYPES:
            raise RegisterMapError(f"{where}: data_type must be one of {', '.join(DATA_TYPES)}")
        count = _num(item, "count", int, 1, where)
        if data_type == "string" and not 1 <= count <= 64:
            raise RegisterMapError(f"{where}: string 'count' must be 1-64 registers")
        slave = _num(item, "slave", int, 1, where)
        if not 0 <= slave <= 247:
            raise RegisterMapError(f"{where}: slave must be 0-247")
        precision = _num(item, "precision", int, None, where)
        reg = MappedRegister(
            name=name.strip(),
            slave=slave,
            table=table,
            address=address,
            data_type=data_type,
            count=count if data_type == "string" else 1,
            scale=_num(item, "scale", float, 1.0, where),
            offset=_num(item, "offset", float, 0.0, where),
            precision=precision,
            unit_of_measurement=item.get("unit_of_measurement"),
            device_class=item.get("device_class"),
            state_class=item.get("state_class"),
            icon=item.get("icon"),
        )
        if reg.uid in seen:
            raise RegisterMapError(f"{where}: the same register and data_type is mapped twice")
        seen.add(reg.uid)
        result.append(reg)
    return result


def scaled_value(reg: MappedRegister, raw):
    """Apply scale, offset and precision to a decoded value."""
    if isinstance(raw, str):
        return raw
    value = raw * reg.scale + reg.offset
    if reg.precision is not None:
        value = round(value, reg.precision)
        if reg.precision == 0:
            value = int(value)
    elif reg.scale == 1.0 and reg.offset == 0.0:
        value = int(raw)
    return value
