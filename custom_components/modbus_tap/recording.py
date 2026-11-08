"""Recordings: time-stamped logs of decoded Transactions, reference values and notes.

Each Recording is one gzip-compressed JSON Lines file. The format is documented
in docs/recording-format.md; keep the two in step.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .model import Transaction

FORMAT = "modbus-tap-recording"
VERSION = 1
SUFFIX = ".jsonl.gz"


def _now_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class RecordingInfo:
    name: str
    size: int
    modified: float


class Recording:
    """A Recording in progress. Collects lines in memory; the owner writes them out."""

    def __init__(self, path: Path, started: float, max_seconds: float) -> None:
        self.path = path
        self.started = started
        self.max_seconds = max_seconds
        self._lines: list[str] = []

    @property
    def name(self) -> str:
        return self.path.name

    def expired(self, now: float) -> bool:
        return now - self.started >= self.max_seconds

    def header(self, bridge: dict[str, Any], reference_entities: list[str], units: dict[str, Any]) -> None:
        self._add(
            {
                "type": "header",
                "format": FORMAT,
                "version": VERSION,
                "started": _now_iso(self.started),
                "bridge": bridge,
                "reference_entities": reference_entities,
                "units": units,
            }
        )

    def transaction(self, t: float, tx: Transaction) -> None:
        record: dict[str, Any] = {
            "type": "transaction",
            "t": round(t, 3),
            "unit": tx.unit,
            "function": tx.function,
            "table": tx.table.value if tx.table else None,
            "start": tx.start,
            "values": list(tx.values),
            "outcome": tx.outcome.value,
        }
        if tx.exception_code is not None:
            record["exception_code"] = tx.exception_code
        self._add(record)

    def entity(self, t: float, entity_id: str, state: str, attributes: dict[str, Any]) -> None:
        record = {"type": "entity", "t": round(t, 3), "entity_id": entity_id, "state": state}
        for key in ("unit_of_measurement", "device_class", "friendly_name"):
            if key in attributes:
                record[key] = attributes[key]
        self._add(record)

    def note(self, t: float, text: str) -> None:
        self._add({"type": "note", "t": round(t, 3), "text": text})

    def end(self, t: float, reason: str) -> None:
        self._add({"type": "end", "t": round(t, 3), "ended": _now_iso(t), "reason": reason})

    def take(self) -> str:
        """Lines collected since the last call, ready to append to the file."""
        chunk, self._lines = "".join(self._lines), []
        return chunk

    def _add(self, record: dict[str, Any]) -> None:
        self._lines.append(json.dumps(record, separators=(",", ":")) + "\n")


class RecordingLibrary:
    """The Recordings of one Bus on disk. Every method blocks: call from an executor."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def new_path(self, started: float) -> Path:
        stamp = datetime.fromtimestamp(started, UTC).strftime("%Y%m%d-%H%M%S")
        return self.directory / f"recording-{stamp}{SUFFIX}"

    def append(self, path: Path, text: str) -> None:
        if not text:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "at", encoding="utf-8") as file:  # gzip members concatenate cleanly
            file.write(text)

    def recordings(self) -> list[RecordingInfo]:
        if not self.directory.is_dir():
            return []
        found = [
            RecordingInfo(p.name, p.stat().st_size, p.stat().st_mtime) for p in self.directory.glob(f"*{SUFFIX}")
        ]
        return sorted(found, key=lambda info: info.modified, reverse=True)

    def path_of(self, name: str) -> Path | None:
        """The file for `name`, if it is one of ours (no path tricks)."""
        if "/" in name or "\\" in name or not name.endswith(SUFFIX):
            return None
        path = self.directory / name
        return path if path.is_file() else None

    def delete(self, names: list[str]) -> None:
        for name in names:
            if (path := self.path_of(name)) is not None:
                path.unlink()

    def prune(self, keep: int) -> None:
        for info in self.recordings()[keep:]:
            self.delete([info.name])


def read_records(path: Path) -> list[dict[str, Any]]:
    """Load a whole Recording (for tests and tools)."""
    with gzip.open(path, "rt", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]
