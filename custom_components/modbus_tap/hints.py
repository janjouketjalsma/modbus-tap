"""Rules of thumb that point people at likely causes. Suggestions, not facts."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from .model import RegisterKey, Table
from .store import RegisterState

MIN_BYTES_FOR_VERDICT = 2000


class BusProblem(StrEnum):
    """What the decoder statistics suggest is wrong with the tap."""

    SILENT = "silent"  # connected, nothing heard
    REVERSED = "reversed"  # junk that is mostly zero bytes: A and B likely swapped
    UNDECODABLE = "undecodable"  # junk otherwise: baud rate or framing likely wrong


def bus_problem(connected: bool, bytes_received: int, frames: int, zero_bytes: int, quiet_seconds: float | None) -> BusProblem | None:
    if not connected:
        return None
    if bytes_received == 0:
        return BusProblem.SILENT if (quiet_seconds or 0) > 600 else None
    if bytes_received < MIN_BYTES_FOR_VERDICT or frames > 0:
        return None
    return BusProblem.REVERSED if zero_bytes > bytes_received * 0.15 else BusProblem.UNDECODABLE


def _printable(byte: int) -> bool:
    return 32 <= byte < 127


def is_text(value: int) -> bool:
    hi, lo = value >> 8, value & 0xFF
    return _printable(hi) and (_printable(lo) or lo == 0) and value != 0x2020


def register_hints(state: RegisterState) -> list[str]:
    hints: list[str] = []
    v = state.value
    if state.updates >= 3 and state.changes == 0:
        hints.append("constant")
    if state.changes and state.decreases == 0 and state.updates >= 3:
        hints.append("only increases (counter?)")
    if (state.maximum >= 0x8000 > state.minimum) or v >= 0xF000:
        hints.append("probably signed (int16)")
    if 1950 <= v <= 2600:
        hints.append("mains voltage x0.1 V?")
    if 4900 <= v <= 5100 or 5900 <= v <= 6100:
        hints.append("mains frequency x0.01 Hz?")
    if is_text(v):
        hints.append("ASCII text?")
    if state.written:
        hints.append("written by the Poller")
    return hints


def find_strings(registers: dict[RegisterKey, RegisterState], min_len: int = 3) -> list[dict]:
    """Runs of consecutive Registers that read as ASCII text."""
    found = []
    for unit, table, address in sorted(registers):
        before = (unit, table, address - 1)
        if before in registers and is_text(registers[before].value):
            continue
        run: list[int] = []
        while (key := (unit, table, address + len(run))) in registers and is_text(registers[key].value):
            run.append(registers[key].value)
        if len(run) >= min_len:
            text = b"".join(r.to_bytes(2, "big") for r in run).replace(b"\x00", b"").decode("ascii").strip()
            found.append({"unit": unit, "table": Table(table).value, "address": address, "count": len(run), "text": text})
    return found


def describe(registers: Iterable[tuple[RegisterKey, RegisterState]]) -> list[dict]:
    """Every Register with its statistics and hints, for diagnostics."""
    rows = []
    for (unit, table, address), state in sorted(registers):
        v = state.value
        rows.append(
            {
                "unit": unit,
                "table": Table(table).value,
                "address": address,
                "value": v,
                "signed": v - 0x10000 if v & 0x8000 else v,
                "min": state.minimum,
                "max": state.maximum,
                "changes": state.changes,
                "updates": state.updates,
                "poll_interval": round(state.interval, 1) if state.interval else None,
                "hints": register_hints(state),
            }
        )
    return rows
