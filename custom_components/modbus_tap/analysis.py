"""Suggest a Register map from a Recording (plain Python, no Home Assistant imports).

Matches Registers against the reference values logged in the same Recording:
for every reference entity, find the Register (or pair of Registers) whose value
follows it most closely, and the scale that turns one into the other. The result
is a proposal for the user to review; it is never applied on its own.
"""

from __future__ import annotations

import bisect
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import yaml

from .hints import find_strings, register_hints
from .model import WRITE_FUNCTIONS, Outcome, Table, Transaction
from .register_map import MapEntry, parse_entries
from .store import RegisterState
from .writes import WriteLog

MIN_POINTS = 6
MIN_DISTINCT = 3
MIN_CORRELATION = 0.9
VERIFIED_CORRELATION = 0.97
NICE_SCALES = tuple(10.0**k for k in range(-3, 3))  # 0.001 … 100
LAGS = (0, 60, 120, 180, 240, 300, 420, 600)  # seconds a reference may trail the bus (cloud integrations: often 4–5 minutes)
VALUE_WINDOW = 600.0  # seconds a cloud value may lag behind the bus
_NICE = frozenset(NICE_SCALES) | frozenset(-k for k in NICE_SCALES)

DEVICE_CLASSES = {
    "W": "power", "kW": "power",
    "Wh": "energy", "kWh": "energy",
    "V": "voltage", "mV": "voltage",
    "A": "current", "mA": "current",
    "Hz": "frequency",
    "°C": "temperature",
    "VA": "apparent_power", "kVA": "apparent_power",
    "var": "reactive_power", "kvar": "reactive_power",
}

Key = tuple[int, Table, int]


@dataclass
class Series:
    times: list[float] = field(default_factory=list)
    values: list[float] = field(default_factory=list)

    def add(self, t: float, value: float) -> None:
        self.times.append(t)
        self.values.append(value)

    def at(self, t: float) -> float | None:
        """The latest value at or before `t`."""
        i = bisect.bisect_right(self.times, t) - 1
        return self.values[i] if i >= 0 else None

    def window(self, start: float, end: float) -> list[float]:
        """Values seen between `start` and `end`, plus the one in force at `start`."""
        i = bisect.bisect_left(self.times, start)
        j = bisect.bisect_right(self.times, end)
        return self.values[max(i - 1, 0) : j]

    def mapped(self, fn) -> Series:
        return Series(list(self.times), [fn(v) for v in self.values])


@dataclass
class Reference:
    entity_id: str
    name: str
    unit: str | None
    device_class: str | None
    series: Series


@dataclass(frozen=True)
class Match:
    entity_id: str
    name: str
    unit: int
    table: Table
    address: int
    data_type: str
    swap: str
    scale: float
    correlation: float | None  # None: matched on values, too few for a correlation
    unit_of_measurement: str | None
    device_class: str | None

    def entry(self, recording: str) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "address": self.address, "input_type": self.table.value}
        if self.data_type != "int16":
            out["data_type"] = self.data_type
        if self.swap != "none":
            out["swap"] = self.swap
        if self.scale != 1.0:
            out["scale"] = self.scale
            out["precision"] = max(0, math.ceil(-math.log10(abs(self.scale)) - 1e-9))
        # Units and device classes are copied from the reference entity, which
        # isn't always tidy; keep only what Home Assistant will accept together.
        device_class = DEVICE_CLASSES.get(self.unit_of_measurement or "")
        if device_class:
            out["unit_of_measurement"] = self.unit_of_measurement
            out["device_class"] = device_class
            out["state_class"] = "total_increasing" if device_class == "energy" else "measurement"
        if self.correlation is not None and self.correlation >= VERIFIED_CORRELATION:
            out["verified"] = f"follows {self.entity_id} (r={self.correlation:.2f}) in {recording}"
        return out


@dataclass
class Analysis:
    recording: str
    registers: dict[Key, Series]
    references: dict[str, Reference]
    matches: dict[int, list[Match]]  # per unit
    units: list[int]
    writes: WriteLog = field(default_factory=WriteLog)

    @property
    def reference_points(self) -> int:
        """Typical number of values per changing reference entity (the median)."""
        counts = sorted(len(r.series.values) for r in self.references.values() if not _flat(r.series.values))
        return counts[len(counts) // 2] if counts else 0

    def proposal(self, unit: int) -> list[dict[str, Any]]:
        return [match.entry(self.recording) for match in self.matches.get(unit, [])]

    def proposal_yaml(self, unit: int, current: Iterable[MapEntry] = ()) -> str:
        """Suggested entries, minus those the current map already has right."""
        entries = [e for e in self.proposal(unit) if not _agrees(e, current)]
        return yaml.safe_dump(entries, sort_keys=False, allow_unicode=True) if entries else ""

    def confirmed(self, unit: int, current: Iterable[MapEntry]) -> int:
        """How many entries of the current map the Recording backs up."""
        current = list(current)
        return sum(1 for e in self.proposal(unit) if _agrees(e, current))

    def summary(self, unit: int, limit: int = 40_000) -> str:
        """A compact description of the Recording for an AI assistant."""
        states = _states(self.registers, unit)
        changing = [(key, s) for key, s in states.items() if s.changes]
        registers = [
            {
                "table": key[1].value,
                "address": key[2],
                "min": s.minimum,
                "max": s.maximum,
                "changes": s.changes,
                "samples": _samples(self.registers[key]),
                "hints": register_hints(s),
            }
            for key, s in sorted(changing, key=lambda item: (item[0][1].value, item[0][2]))
        ]
        data = {
            "recording": self.recording,
            "unit": unit,
            "reference_entities": [
                {"entity_id": r.entity_id, "name": r.name, "unit": r.unit, "device_class": r.device_class, "samples": _samples(r.series)}
                for r in self.references.values()
            ],
            "matches_found_by_correlation": [m.__dict__ | {"table": m.table.value} for m in self.matches.get(unit, [])],
            "text_found": find_strings(states),
            "writes_by_the_poller": [
                {"table": b.table, "registers": b.addresses, "times": b.total, "values": [[list(r.values), r.outcome, r.count] for r in b.runs[-10:]]}
                for b in self.writes.newest_first()
                if b.unit == unit
            ],
            "constant_registers": sum(1 for s in states.values() if not s.changes),
            "changing_registers": registers,
        }
        text = json.dumps(data, separators=(",", ":"), default=str)
        while len(text) > limit and data["changing_registers"]:
            data["changing_registers"] = data["changing_registers"][: len(data["changing_registers"]) * 3 // 4]
            text = json.dumps(data, separators=(",", ":"), default=str)
        return text


def _agrees(entry: dict[str, Any], current: Iterable[MapEntry]) -> bool:
    for existing in current:
        if (existing.table.value, existing.address) != (entry["input_type"], entry["address"]):
            continue
        proposed, have = entry.get("data_type", "int16"), existing.data_type.value
        # uint16 only means no negative values were seen, which an int16 entry also fits.
        same_type = proposed == have or (proposed == "uint16" and have == "int16")
        return same_type and existing.swap.value == entry.get("swap", "none") and math.isclose(existing.scale, entry.get("scale", 1.0))
    return False


def analyse(recording: str, records: Iterable[dict[str, Any]]) -> Analysis:
    registers: dict[Key, Series] = {}
    references: dict[str, Reference] = {}
    writes = WriteLog()
    for record in records:
        kind = record.get("type")
        if kind == "transaction" and record.get("function") in WRITE_FUNCTIONS and record.get("table"):
            writes.add(
                Transaction(record["unit"], record["function"], Table(record["table"]), record["start"], tuple(record["values"]), Outcome(record["outcome"])),
                record["t"],
            )
        if kind == "transaction" and record.get("outcome") in ("answered", "confirmed") and record.get("table"):
            table = Table(record["table"])
            for offset, value in enumerate(record["values"]):
                registers.setdefault((record["unit"], table, record["start"] + offset), Series()).add(record["t"], value)
        elif kind == "entity":
            try:
                value = float(record["state"])
            except (TypeError, ValueError):
                continue  # unavailable, unknown, text
            ref = references.get(record["entity_id"])
            if ref is None:
                ref = references[record["entity_id"]] = Reference(
                    record["entity_id"], record.get("friendly_name") or record["entity_id"],
                    record.get("unit_of_measurement"), record.get("device_class"), Series(),
                )
            ref.series.add(record["t"], value)
    units = sorted({key[0] for key in registers})
    matches = {unit: _match_unit(unit, registers, references) for unit in units}
    return Analysis(recording, registers, references, matches, units, writes)


def _match_unit(unit: int, registers: dict[Key, Series], references: dict[str, Reference]) -> list[Match]:
    candidates = list(_interpretations(unit, registers))
    ranked = []
    for ref in references.values():
        if _flat(ref.series.values):
            continue
        if len(ref.series.values) >= MIN_POINTS:
            best = _best_correlation(ref, candidates)
        else:
            best = _best_value_match(ref, candidates)
        if best is not None:
            ranked.append((best, ref))
    taken: set[tuple[Table, int]] = set()
    found: list[Match] = []
    for (rank, table, address, data_type, swap, scale, correlation), ref in sorted(ranked, key=lambda item: item[0][0], reverse=True):
        used = {(table, address + i) for i in range(2 if data_type.endswith("32") else 1)}
        if used & taken:
            continue
        taken |= used
        found.append(Match(ref.entity_id, ref.name, unit, table, address, data_type, swap, scale, correlation, ref.unit, ref.device_class))
    return sorted(found, key=lambda m: (m.table.value, m.address))


def _best_correlation(ref: Reference, candidates):
    """With enough reference values: the Register that rises and falls with it,
    allowing for the reference trailing the bus by one of LAGS."""
    best = None
    for table, address, data_type, swap, series in candidates:
        fit = None
        for lag in LAGS:
            pairs = [(x, y) for t, y in zip(ref.series.times, ref.series.values) if (x := series.at(t - lag)) is not None]
            if len(pairs) < MIN_POINTS:
                continue
            xs, ys = zip(*pairs)
            r = _correlation(xs, ys)
            if r is not None and (fit is None or abs(r) > abs(fit[0]) + 1e-9):
                fit = (r, xs, ys)
        if fit is None or abs(fit[0]) < MIN_CORRELATION:
            continue
        r, xs, ys = fit
        if len(set(xs)) < MIN_DISTINCT:
            continue  # a register flipping between two values "follows" any single spike
        scale = _scale(xs, ys)
        if not is_round_scale(scale):
            continue  # follows the reference, but isn't the same quantity (current against power, say)
        # Equal correlation (a constant high word, say): prefer the reading that
        # needs no offset, as a Register map has a scale but rarely an offset.
        rank = (2, round(abs(r), 3), -round(_origin_error(xs, ys), 2), scale in _NICE, not data_type.endswith("32"))
        if best is None or rank > best[0]:
            best = (rank, table, address, data_type, swap, scale, round(abs(r), 3))
    return best


def _best_value_match(ref: Reference, candidates):
    """With only a few reference values (a cloud integration that updates every
    few minutes, say): the Register that showed each of them, at a round scale,
    shortly before the reference did. Cloud values lag the bus, hence the window."""
    best = None
    points = list(zip(ref.series.times, ref.series.values))
    if len(points) < MIN_DISTINCT:
        return None  # two values that happen to match prove nothing
    for table, address, data_type, swap, series in candidates:
        windows = [sorted(set(series.window(t - VALUE_WINDOW, t + 60))) for t, _ in points]
        if not all(windows):
            continue
        for scale in _NICE:
            error = 0.0
            seen = set()
            for (_, y), window in zip(points, windows):
                hit = _nearest(window, y / scale)
                if hit is None or abs(hit * scale - y) > _tolerance(y):
                    break
                error += abs(hit * scale - y) / _tolerance(y)
                seen.add(hit)
            else:
                if len(seen) < 2:  # a value that never changed proves nothing
                    continue
                rank = (1, -round(error / len(points), 2), not data_type.endswith("32"), abs(scale) <= 1, scale > 0)
                if best is None or rank > best[0]:
                    best = (rank, table, address, data_type, swap, scale, None)
    return best


def _nearest(values: list[float], target: float) -> float | None:
    i = bisect.bisect_left(values, target)
    near = values[max(i - 1, 0) : i + 1]
    return min(near, key=lambda v: abs(v - target)) if near else None


def _tolerance(value: float) -> float:
    """1.5 %, or half the last digit the reference shows, whichever is larger."""
    decimals = len(f"{value:.6f}".rstrip("0").split(".")[1])
    return max(abs(value) * 0.015, 0.5 * 10**-decimals)


def _interpretations(unit: int, registers: dict[Key, Series]):
    """(table, address, data_type, swap, decoded Series) for each changing Register and pair."""
    for (u, table, address), series in registers.items():
        if u != unit:
            continue
        if not _flat(series.values):
            yield table, address, "uint16", "none", series
            if any(v >= 0x8000 for v in series.values):
                yield table, address, "int16", "none", series.mapped(lambda v: _signed(v, 16))
        nxt = registers.get((unit, table, address + 1))
        if nxt is None or (_flat(series.values) and _flat(nxt.values)):
            continue
        for swap, hi, lo in (("none", series, nxt), ("word", nxt, series)):
            combined = _pair(hi, lo)
            yield table, address, "uint32", swap, combined
            if any(v >= 0x80000000 for v in combined.values):
                yield table, address, "int32", swap, combined.mapped(lambda v: _signed(v, 32))


def _pair(hi: Series, lo: Series) -> Series:
    out = Series()
    for t in sorted(set(hi.times) | set(lo.times)):
        if (value := _combine(hi.at(t), lo.at(t))) is not None:
            out.add(t, value)
    return out


def _combine(hi: float | None, lo: float | None) -> float | None:
    return None if hi is None or lo is None else int(hi) * 65536 + int(lo)


def _signed(value: float, bits: int) -> int:
    value = int(value)
    return value - (1 << bits) if value >= 1 << (bits - 1) else value


def _flat(values: list[float]) -> bool:
    return len(set(values)) < 2


def _correlation(xs, ys) -> float | None:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


def _origin_error(xs, ys) -> float:
    """Relative error of the best fit y = k·x (through zero)."""
    sxx = sum(x * x for x in xs)
    syy = sum(y * y for y in ys)
    if sxx == 0 or syy == 0:
        return 1.0
    k = sum(x * y for x, y in zip(xs, ys)) / sxx
    return sum((y - k * x) ** 2 for x, y in zip(xs, ys)) / syy


def _scale(xs, ys) -> float:
    """Least-squares factor y ≈ k·x, snapped to a power of ten when close (or negated)."""
    sxx = sum(x * x for x in xs)
    if sxx == 0:
        return 1.0
    k = sum(x * y for x, y in zip(xs, ys)) / sxx
    for nice in NICE_SCALES:
        for candidate in (nice, -nice):
            if abs(k - candidate) <= 0.15 * nice:
                return candidate
    return float(f"{k:.4g}")


def is_round_scale(scale: float) -> bool:
    """1, 0.1, 0.01, 10 and so on, or minus those: the scales devices actually use."""
    return any(math.isclose(scale, nice) for nice in _NICE)


def vet(entries: list[dict[str, Any]], analysis: Analysis, unit: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Check entries from elsewhere (an AI) against the Recording.

    Entries with a scale no device uses are left out, and `verified` is only kept
    where Modbus Tap's own matching backs it up, with that as the evidence.
    """
    ours = {(m.table.value, m.address): m for m in analysis.matches.get(unit, [])}
    kept, odd, unbacked = [], [], 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        scale = entry.get("scale", 1.0)
        if not isinstance(scale, (int, float)) or not is_round_scale(float(scale)):
            odd.append(f"{entry.get('name', '?')} ({scale})")
            continue
        entry = dict(entry)
        match = ours.get((entry.get("input_type", "holding"), entry.get("address")))
        evidence = match.entry(analysis.recording).get("verified") if match else None
        if evidence and _agrees(match.entry(analysis.recording), _as_entries([entry])):
            entry["verified"] = evidence
        elif entry.pop("verified", None):
            unbacked += 1
        kept.append(entry)
    notes = []
    if odd:
        notes.append(f"Left out {len(odd)} of the AI's entries with a scale no device uses: {', '.join(odd)}. That usually means a register that moves along with the reference without being the same thing.")
    if unbacked:
        notes.append(f"Removed `verified` from {unbacked} of the AI's entries: the recording doesn't back them up.")
    return kept, notes


def _as_entries(items: list[dict[str, Any]]) -> list[MapEntry]:
    return parse_entries(items).entries


def _samples(series: Series, count: int = 12) -> list:
    if len(series.values) <= count:
        return [round(v, 3) for v in series.values]
    step = (len(series.values) - 1) / (count - 1)
    return [round(series.values[round(i * step)], 3) for i in range(count)]


def _states(registers: dict[Key, Series], unit: int) -> dict[Key, RegisterState]:
    states = {}
    for key, series in registers.items():
        if key[0] != unit:
            continue
        values = series.values
        changes = sum(1 for a, b in zip(values, values[1:]) if a != b)
        decreases = sum(1 for a, b in zip(values, values[1:]) if b < a)
        states[key] = RegisterState(
            int(values[-1]), series.times[-1], int(min(values)), int(max(values)),
            updates=len(values), changes=changes, decreases=decreases,
        )
    return states
