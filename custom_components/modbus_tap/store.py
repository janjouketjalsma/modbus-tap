"""What the Tap knows about each Register, and who wants to hear about changes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .model import RegisterKey, Table, Transaction

MISSED_POLLS = 3
MIN_STALE_SECONDS = 300.0

Listener = Callable[[], None]


@dataclass(slots=True)
class RegisterState:
    """The latest value of one Register and how it has behaved."""

    value: int
    last_seen: float
    minimum: int
    maximum: int
    interval: float | None = None  # learned seconds between updates
    updates: int = 1
    changes: int = 0
    decreases: int = 0
    written: bool = False

    def update(self, value: int, now: float, written: bool) -> None:
        gap = now - self.last_seen
        if gap > 0:
            self.interval = gap if self.interval is None else 0.7 * self.interval + 0.3 * gap
        if value != self.value:
            self.changes += 1
            self.decreases += value < self.value
        self.value = value
        self.last_seen = now
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        self.updates += 1
        self.written = self.written or written

    def fresh(self, now: float) -> bool:
        limit = max(MISSED_POLLS * (self.interval or 0.0), MIN_STALE_SECONDS)
        return now - self.last_seen <= limit


@dataclass
class RegisterStore:
    registers: dict[RegisterKey, RegisterState] = field(default_factory=dict)
    reads: dict[int, set[tuple[Table, int, int]]] = field(default_factory=dict)
    _listeners: dict[RegisterKey, set[Listener]] = field(default_factory=dict)
    _unit_listeners: set[Callable[[int], None]] = field(default_factory=set)
    _fresh: dict[RegisterKey, bool] = field(default_factory=dict)

    @property
    def units(self) -> set[int]:
        return set(self.reads) | {key[0] for key in self.registers}

    def apply(self, transaction: Transaction, now: float) -> None:
        """Record a Transaction; notify listeners of the Registers it touched."""
        if not transaction.updates_registers or transaction.table is None:
            return
        unit = transaction.unit
        is_new_unit = unit not in self.units
        if not transaction.is_write:
            self.reads.setdefault(unit, set()).add((transaction.table, transaction.start, len(transaction.values)))
        touched: list[RegisterKey] = []
        for offset, value in enumerate(transaction.values):
            key = (unit, transaction.table, transaction.start + offset)
            state = self.registers.get(key)
            if state is None:
                self.registers[key] = RegisterState(value, now, value, value, written=transaction.is_write)
            else:
                state.update(value, now, transaction.is_write)
            self._fresh[key] = True
            touched.append(key)
        if is_new_unit:
            for unit_listener in list(self._unit_listeners):
                unit_listener(unit)
        self._notify(touched)

    def values(self, keys: Iterable[RegisterKey], now: float | None = None) -> list[int] | None:
        """Current values of all `keys`, or None if any is unknown (or stale, given `now`)."""
        out = []
        for key in keys:
            state = self.registers.get(key)
            if state is None or (now is not None and not state.fresh(now)):
                return None
            out.append(state.value)
        return out

    def check_stale(self, now: float) -> None:
        """Notify listeners of Registers that just went stale."""
        stale = [key for key, state in self.registers.items() if self._fresh.get(key) and not state.fresh(now)]
        for key in stale:
            self._fresh[key] = False
        self._notify(stale)

    def subscribe(self, keys: Iterable[RegisterKey], listener: Listener) -> Callable[[], None]:
        keys = list(keys)
        for key in keys:
            self._listeners.setdefault(key, set()).add(listener)

        def unsubscribe() -> None:
            for key in keys:
                self._listeners.get(key, set()).discard(listener)

        return unsubscribe

    def on_new_unit(self, listener: Callable[[int], None]) -> Callable[[], None]:
        self._unit_listeners.add(listener)
        return lambda: self._unit_listeners.discard(listener)

    def poll_interval(self, unit: int) -> float | None:
        """Typical seconds between polls of this Unit."""
        intervals = sorted(s.interval for k, s in self.registers.items() if k[0] == unit and s.interval)
        return intervals[len(intervals) // 2] if intervals else None

    def _notify(self, keys: Iterable[RegisterKey]) -> None:
        listeners: set[Listener] = set()
        for key in keys:
            listeners.update(self._listeners.get(key, ()))
        for listener in listeners:
            listener()
