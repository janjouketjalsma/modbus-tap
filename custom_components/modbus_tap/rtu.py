"""Modbus RTU decoder for a passively heard byte stream."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum, auto

from .model import READ_TABLES, WRITE_FUNCTIONS, Outcome, Table, Transaction

MAX_FRAME = 256
BROADCAST = 0


def crc16(data: bytes) -> int:
    """Modbus CRC16."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def with_crc(body: bytes) -> bytes:
    """Append the CRC to a frame body (handy for tests and tools)."""
    crc = crc16(body)
    return body + bytes((crc & 0xFF, crc >> 8))


class _Kind(Enum):
    REQUEST = auto()
    RESPONSE = auto()
    EXCEPTION = auto()


@dataclass(frozen=True, slots=True)
class _Frame:
    kind: _Kind
    raw: bytes

    @property
    def unit(self) -> int:
        return self.raw[0]

    @property
    def function(self) -> int:
        return self.raw[1] & 0x7F


def _word(raw: bytes, offset: int) -> int:
    return int.from_bytes(raw[offset : offset + 2], "big")


def _words(data: bytes) -> tuple[int, ...]:
    return tuple(_word(data, i) for i in range(0, len(data) - 1, 2))


def _bits(data: bytes, count: int) -> tuple[int, ...]:
    return tuple((data[i // 8] >> (i % 8)) & 1 for i in range(min(count, len(data) * 8)))


def _length_at(buf: bytearray, index: int, extra: int) -> int | None:
    """Frame length given by a byte-count field at `index`, if received yet."""
    return extra + buf[index] if len(buf) > index else None


def _candidates(buf: bytearray, pending: _Frame | None) -> Iterator[tuple[_Kind, int | None]]:
    """Possible (kind, length) of a frame starting at buf[0]; None = need more bytes."""
    unit, func = buf[0], buf[1]
    if unit > 247:
        return
    if func & 0x80:
        yield _Kind.EXCEPTION, 5
        return
    expecting = pending is not None and pending.unit == unit and pending.function == func
    request = response = None
    if func in READ_TABLES:
        request, response = 8, _length_at(buf, 2, 5)
    elif func in (5, 6):
        request = response = 8
    elif func in (15, 16):
        request, response = _length_at(buf, 6, 9), 8
    else:
        return
    if expecting:
        yield _Kind.RESPONSE, response
        yield _Kind.REQUEST, request
    else:
        yield _Kind.REQUEST, request
        yield _Kind.RESPONSE, response


class RtuDecoder:
    """Split a Modbus RTU byte stream into frames and pair them into Transactions."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._pending: _Frame | None = None
        self.frames = 0
        self.discarded_bytes = 0

    def reset(self) -> None:
        self.discarded_bytes += len(self._buf)
        self._buf.clear()
        self._pending = None

    def feed(self, data: bytes) -> list[Transaction]:
        self._buf.extend(data)
        return self._drain(final=False)

    def flush(self) -> list[Transaction]:
        done = self._drain(final=True)
        if self._pending is not None:
            done.append(_unanswered(self._pending))
            self._pending = None
        return done

    def _drain(self, final: bool) -> list[Transaction]:
        done: list[Transaction] = []
        buf = self._buf
        while len(buf) >= 4:
            frame, need_more = self._next_frame()
            if frame is not None:
                del buf[: len(frame.raw)]
                self.frames += 1
                done.extend(self._handle(frame))
            elif need_more and not final:
                break
            else:  # nothing valid starts here: resync one byte later
                del buf[0]
                self.discarded_bytes += 1
        if final and buf:
            self.discarded_bytes += len(buf)
            buf.clear()
        return done

    def _next_frame(self) -> tuple[_Frame | None, bool]:
        buf = self._buf
        need_more = False
        for kind, length in _candidates(buf, self._pending):
            if length is None or length > len(buf):
                need_more = need_more or length is None or length <= MAX_FRAME
                continue
            raw = bytes(buf[:length])
            if crc16(raw[:-2]) == int.from_bytes(raw[-2:], "little"):
                return _Frame(kind, raw), False
        return None, need_more

    def _handle(self, frame: _Frame) -> list[Transaction]:
        done: list[Transaction] = []
        if frame.kind is _Kind.REQUEST:
            if self._pending is not None:
                done.append(_unanswered(self._pending))
            if frame.unit == BROADCAST:
                self._pending = None
                done.append(_unanswered(frame))
            else:
                self._pending = frame
            return done

        request, self._pending = self._pending, None
        if request is None or request.unit != frame.unit or request.function != frame.function:
            return done  # a reply we did not see the question for
        if frame.kind is _Kind.EXCEPTION:
            done.append(_transaction(request, Outcome.REJECTED, exception_code=frame.raw[2]))
        elif (answered := _answered(request, frame)) is not None:
            done.append(answered)
        return done


def _request_parts(request: _Frame) -> tuple[Table | None, int, tuple[int, ...]]:
    """Table, start address and (for writes) the values the Poller sent."""
    raw, func = request.raw, request.function
    start = _word(raw, 2)
    if func == 5:
        return Table.COIL, start, (1 if _word(raw, 4) == 0xFF00 else 0,)
    if func == 6:
        return Table.HOLDING, start, (_word(raw, 4),)
    if func == 15:
        return Table.COIL, start, _bits(raw[7:-2], _word(raw, 4))
    if func == 16:
        return Table.HOLDING, start, _words(raw[7:-2])
    return READ_TABLES.get(func), start, ()


def _transaction(request: _Frame, outcome: Outcome, values: tuple[int, ...] | None = None, exception_code: int | None = None) -> Transaction:
    table, start, sent = _request_parts(request)
    return Transaction(
        unit=request.unit,
        function=request.function,
        table=table,
        start=start,
        values=sent if values is None else values,
        outcome=outcome,
        exception_code=exception_code,
    )


def _unanswered(request: _Frame) -> Transaction:
    return _transaction(request, Outcome.UNANSWERED)


def _answered(request: _Frame, response: _Frame) -> Transaction | None:
    """Pair a request with its normal response; None if they do not fit together."""
    func = request.function
    if func in WRITE_FUNCTIONS:
        echo_matches = response.raw[2:6] == request.raw[2:6]
        return _transaction(request, Outcome.CONFIRMED if echo_matches else Outcome.REJECTED)
    count = _word(request.raw, 4)
    data = response.raw[3:-2]
    if func in (1, 2):
        values = _bits(data, count)
    elif len(data) == 2 * count:
        values = _words(data)
    else:
        return None
    return _transaction(request, Outcome.ANSWERED, values=values)
