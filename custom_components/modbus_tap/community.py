"""Community maps shipped with Modbus Tap, and suggesting one for a Unit."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from .model import Table
from .register_map import MapEntry, RegisterMapError, parse_entries, with_unit
from .values import decode

MAPS_DIR = Path(__file__).parent / "community_maps"


@dataclass(frozen=True, slots=True)
class ReadBlock:
    """A block of registers the Poller is known to read for this model."""

    table: Table
    start: int
    count: int


@dataclass(frozen=True, slots=True)
class CommunityMap:
    id: str
    name: str
    manufacturer: str
    entries: tuple[MapEntry, ...]
    model_text: re.Pattern[str] | None = None
    reads: tuple[ReadBlock, ...] = ()

    def for_unit(self, unit: int) -> list[MapEntry]:
        return with_unit(self.entries, unit)

    @property
    def model_entry(self) -> MapEntry | None:
        return next((entry for entry in self.entries if entry.model), None)


def load_maps(directory: Path = MAPS_DIR) -> dict[str, CommunityMap]:
    """Read every bundled map. Blocking: call from an executor."""
    maps: dict[str, CommunityMap] = {}
    for path in sorted(directory.glob("*.yaml")):
        maps[path.stem] = parse_map(path.stem, path.read_text(encoding="utf-8"))
    return maps


def parse_map(map_id: str, text: str) -> CommunityMap:
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or "sensors" not in data:
        raise RegisterMapError(f"{map_id}: a community map needs 'name', 'manufacturer' and 'sensors'")
    match = data.get("match") or {}
    pattern = match.get("model_text")
    return CommunityMap(
        id=map_id,
        name=str(data["name"]),
        manufacturer=str(data["manufacturer"]),
        entries=parse_entries(data["sensors"]).entries,
        model_text=re.compile(pattern) if pattern else None,
        reads=tuple(_read_block(spec) for spec in match.get("reads", ())),
    )


def _read_block(spec: str) -> ReadBlock:
    """'input 1-100' -> ReadBlock(INPUT, 1, 100)."""
    table, span = spec.split()
    first, last = (int(part, 0) for part in span.split("-"))
    return ReadBlock(Table(table), first, last - first + 1)


def suggest(
    maps: Iterable[CommunityMap],
    unit: int,
    registers: Callable[[list[tuple[int, Table, int]]], list[int] | None],
    reads: set[tuple[Table, int, int]],
) -> CommunityMap | None:
    """The first map whose model text or read pattern fits what was heard from `unit`."""
    for community_map in maps:
        if _model_matches(community_map, unit, registers) or _reads_match(community_map, reads):
            return community_map
    return None


def _model_matches(community_map: CommunityMap, unit: int, registers: Callable) -> bool:
    entry = community_map.model_entry
    if community_map.model_text is None or entry is None:
        return False
    on_unit = with_unit([entry], unit)[0]
    values = registers(on_unit.keys)
    if values is None:
        return False
    return bool(community_map.model_text.search(str(decode(entry.data_type, values, entry.swap))))


def _reads_match(community_map: CommunityMap, reads: set[tuple[Table, int, int]]) -> bool:
    return bool(community_map.reads) and all((b.table, b.start, b.count) in reads for b in community_map.reads)
