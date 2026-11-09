"""Write log: what the Poller writes, and when it changes (plain Python, no Home Assistant imports).

Pollers tend to write the same values over and over, so identical writes in a
row are collapsed into one run with a count. Both the number of write blocks
and the runs kept per block are capped, so the log stays small however long
it runs: at most MAX_BLOCKS × MAX_RUNS runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import Transaction

MAX_BLOCKS = 100
MAX_RUNS = 50


@dataclass
class Run:
    """The same values written again and again, from `first` to `last` (Unix time)."""

    values: tuple[int, ...]
    outcome: str
    first: float
    last: float
    count: int = 1


@dataclass
class Block:
    """Writes to the same Registers: one Unit, table, start address and length."""

    unit: int
    table: str
    start: int
    length: int
    runs: list[Run] = field(default_factory=list)
    total: int = 0

    @property
    def key(self) -> tuple[int, str, int, int]:
        return (self.unit, self.table, self.start, self.length)

    @property
    def last(self) -> float:
        return self.runs[-1].last

    @property
    def addresses(self) -> str:
        return str(self.start) if self.length == 1 else f"{self.start}-{self.start + self.length - 1}"

    @property
    def distinct_values(self) -> int:
        return len({run.values for run in self.runs})


class WriteLog:
    def __init__(self) -> None:
        self.blocks: dict[tuple[int, str, int, int], Block] = {}

    def add(self, tx: Transaction, now: float) -> None:
        if not tx.is_write or tx.table is None:
            return
        values = tuple(tx.values)
        key = (tx.unit, tx.table.value, tx.start, len(values))
        block = self.blocks.get(key)
        if block is None:
            if len(self.blocks) >= MAX_BLOCKS:
                oldest = min(self.blocks.values(), key=lambda b: b.last)
                del self.blocks[oldest.key]
            block = self.blocks[key] = Block(*key)
        block.total += 1
        run = block.runs[-1] if block.runs else None
        if run is not None and run.values == values and run.outcome == tx.outcome.value:
            run.last, run.count = now, run.count + 1
            return
        block.runs.append(Run(values, tx.outcome.value, now, now))
        del block.runs[:-MAX_RUNS]

    def clear(self) -> None:
        self.blocks.clear()

    def newest_first(self) -> list[Block]:
        return sorted(self.blocks.values(), key=lambda b: b.last, reverse=True)

    # --- storage ------------------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        return {
            "blocks": [
                {
                    "unit": b.unit, "table": b.table, "start": b.start, "length": b.length, "total": b.total,
                    "runs": [[list(r.values), r.outcome, r.first, r.last, r.count] for r in b.runs],
                }
                for b in self.blocks.values()
            ]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> WriteLog:
        log = cls()
        for item in (data or {}).get("blocks", [])[-MAX_BLOCKS:]:
            block = Block(item["unit"], item["table"], item["start"], item["length"], total=item.get("total", 0))
            block.runs = [Run(tuple(v), o, f, l, c) for v, o, f, l, c in item["runs"][-MAX_RUNS:]]
            if block.runs:
                log.blocks[block.key] = block
        return log
