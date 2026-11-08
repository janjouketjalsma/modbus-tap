"""Domain model shared by every part of Modbus Tap (no Home Assistant imports)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class Table(StrEnum):
    """A Unit's register tables, named as in the core Modbus integration."""

    HOLDING = "holding"
    INPUT = "input"
    COIL = "coil"
    DISCRETE = "discrete_input"


class Outcome(StrEnum):
    """How a Transaction ended."""

    ANSWERED = "answered"  # a read with a valid response
    CONFIRMED = "confirmed"  # a Write the Unit echoed back
    REJECTED = "rejected"  # the Unit answered with an exception
    UNANSWERED = "unanswered"  # no response before the next request


@dataclass(frozen=True, slots=True)
class Transaction:
    """One request from the Poller and how the Unit answered it.

    `values` holds what was read, or what the Poller tried to write.
    """

    unit: int
    function: int
    table: Table | None
    start: int
    values: tuple[int, ...]
    outcome: Outcome
    exception_code: int | None = None

    @property
    def is_write(self) -> bool:
        return self.function in WRITE_FUNCTIONS

    @property
    def updates_registers(self) -> bool:
        """Whether the Unit's registers now hold `values`."""
        return self.outcome in (Outcome.ANSWERED, Outcome.CONFIRMED) and bool(self.values)


class Decoder(Protocol):
    """Turns the raw byte stream of a Bus into Transactions.

    Modbus RTU is the only implementation today; this is the seam for others.
    """

    frames: int
    discarded_bytes: int

    def feed(self, data: bytes) -> list[Transaction]:
        """Add received bytes; return Transactions that completed."""

    def flush(self) -> list[Transaction]:
        """The Bus went quiet: resolve whatever is still buffered or pending."""

    def reset(self) -> None:
        """Forget partial data, for example after a reconnect."""


RegisterKey = tuple[int, Table, int]  # (unit address, table, register address)

READ_TABLES = {1: Table.COIL, 2: Table.DISCRETE, 3: Table.HOLDING, 4: Table.INPUT}
WRITE_FUNCTIONS = {5: Table.COIL, 6: Table.HOLDING, 15: Table.COIL, 16: Table.HOLDING}
