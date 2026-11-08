"""Guess what sniffed registers might be, to help write the register map.

These are heuristics, not facts: they only point at registers worth checking.
"""

from __future__ import annotations

from .rtu import RegisterStats

Key = tuple[int, str, int]


def _printable(byte: int) -> bool:
    return 32 <= byte < 127


def is_text(value: int) -> bool:
    hi, lo = value >> 8, value & 0xFF
    return _printable(hi) and (_printable(lo) or lo == 0) and value != 0x2020


def register_hints(stats: RegisterStats) -> list[str]:
    hints: list[str] = []
    v = stats.value
    if stats.updates >= 3 and stats.changes == 0:
        hints.append("constant")
    if stats.changes and stats.decreases == 0 and stats.updates >= 3:
        hints.append("only increases (counter?)")
    if stats.maximum >= 0x8000 and stats.minimum < 0x8000 or v >= 0xF000:
        hints.append("probably signed (int16)")
    if 1950 <= v <= 2600:
        hints.append("mains voltage x0.1 V?")
    if 4900 <= v <= 5100 or 5900 <= v <= 6100:
        hints.append("mains frequency x0.01 Hz?")
    if is_text(v):
        hints.append("ASCII text?")
    if stats.written:
        hints.append("written by the master")
    return hints


def find_strings(registers: dict[Key, RegisterStats], min_len: int = 3) -> list[dict]:
    """Runs of consecutive registers that look like ASCII text."""
    found = []
    for slave, table, addr in sorted(registers):
        prev = (slave, table, addr - 1)
        if prev in registers and is_text(registers[prev].value):
            continue  # not the start of a run
        run = []
        a = addr
        while (slave, table, a) in registers and is_text(registers[(slave, table, a)].value):
            run.append(registers[(slave, table, a)].value)
            a += 1
        if len(run) >= min_len:
            text = b"".join(r.to_bytes(2, "big") for r in run).replace(b"\x00", b"").decode("ascii")
            found.append({"slave": slave, "table": table, "address": addr, "count": len(run), "text": text.strip()})
    return found
