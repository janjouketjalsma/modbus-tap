"""Turn raw registers into values, with the same rules as core Modbus sensors."""

from __future__ import annotations

import math
import struct
from enum import StrEnum


class DataType(StrEnum):
    """Single-value data types of core Modbus sensors."""

    INT16 = "int16"
    INT32 = "int32"
    INT64 = "int64"
    UINT16 = "uint16"
    UINT32 = "uint32"
    UINT64 = "uint64"
    FLOAT16 = "float16"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    STRING = "string"


class Swap(StrEnum):
    """Byte and word order adjustments, as in core Modbus."""

    NONE = "none"
    BYTE = "byte"
    WORD = "word"
    WORD_BYTE = "word_byte"


# struct format character and size in registers
_LAYOUT: dict[DataType, tuple[str, int]] = {
    DataType.INT16: ("h", 1),
    DataType.UINT16: ("H", 1),
    DataType.FLOAT16: ("e", 1),
    DataType.INT32: ("i", 2),
    DataType.UINT32: ("I", 2),
    DataType.FLOAT32: ("f", 2),
    DataType.INT64: ("q", 4),
    DataType.UINT64: ("Q", 4),
    DataType.FLOAT64: ("d", 4),
}

INTEGER_TYPES = frozenset(
    {DataType.INT16, DataType.INT32, DataType.INT64, DataType.UINT16, DataType.UINT32, DataType.UINT64}
)


def register_count(data_type: DataType, count: int | None) -> int:
    """How many registers a value occupies (strings use `count`)."""
    if data_type is DataType.STRING:
        return count or 1
    return _LAYOUT[data_type][1]


def apply_swap(registers: list[int], swap: Swap) -> list[int]:
    regs = list(registers)
    if swap in (Swap.BYTE, Swap.WORD_BYTE):
        regs = [((r & 0xFF) << 8) | (r >> 8) for r in regs]
    if swap in (Swap.WORD, Swap.WORD_BYTE):
        regs.reverse()
    return regs


def decode(data_type: DataType, registers: list[int], swap: Swap = Swap.NONE) -> int | float | str:
    """Decode registers into a raw number or string, before scaling."""
    raw = b"".join(r.to_bytes(2, "big") for r in apply_swap(registers, swap))
    if data_type is DataType.STRING:
        return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
    char, _ = _LAYOUT[data_type]
    return struct.unpack(">" + char, raw)[0]


def scale_value(
    raw: int | float,
    *,
    integer_type: bool,
    scale: float = 1.0,
    offset: float = 0.0,
    precision: int | None = None,
    nan_value: int | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    zero_suppress: float | None = None,
) -> int | float | None:
    """Apply core Modbus post-processing; None means "no valid value"."""
    if nan_value is not None and raw in (nan_value, -nan_value):
        return None
    if isinstance(raw, float) and math.isnan(raw):
        return None
    value = scale * raw + offset
    if min_value is not None and value < min_value:
        value = min_value
    if max_value is not None and value > max_value:
        value = max_value
    if zero_suppress is not None and abs(value) <= zero_suppress:
        value = 0
    digits = precision if precision is not None else (0 if integer_type else 2)
    if digits == 0:
        return round(value)
    return round(float(value), digits)
