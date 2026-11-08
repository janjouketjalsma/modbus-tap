"""Passive Modbus RTU stream decoder.

This module has no Home Assistant dependencies so it can be tested on its own.

It takes the raw byte stream seen on an RS485 bus (for example from a
serial-to-WiFi bridge in transparent mode), splits it into Modbus RTU frames
using the CRC, pairs each request with its response and turns the result into
register values.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

TABLE_COILS = "coil"
TABLE_DISCRETE = "discrete"
TABLE_HOLDING = "holding"
TABLE_INPUT = "input"

# Function code -> register table it reads.
READ_FUNCTIONS = {
    1: TABLE_COILS,
    2: TABLE_DISCRETE,
    3: TABLE_HOLDING,
    4: TABLE_INPUT,
}
REGISTER_READS = (3, 4)
BIT_READS = (1, 2)

MAX_FRAME = 256  # Modbus RTU ADU limit


def crc16(data: bytes | bytearray | memoryview) -> int:
    """Return the Modbus CRC16 of data."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def crc_ok(frame: bytes | bytearray | memoryview) -> bool:
    """Check the trailing CRC (little endian) of a complete frame."""
    if len(frame) < 4:
        return False
    crc = crc16(frame[:-2])
    return frame[-2] == crc & 0xFF and frame[-1] == crc >> 8


class FrameKind(str, Enum):
    """What a frame is."""

    REQUEST = "request"
    RESPONSE = "response"
    EXCEPTION = "exception"


@dataclass(slots=True)
class Frame:
    """One decoded Modbus RTU frame."""

    kind: FrameKind
    raw: bytes

    @property
    def slave(self) -> int:
        return self.raw[0]

    @property
    def function(self) -> int:
        return self.raw[1] & 0x7F

    @property
    def payload(self) -> bytes:
        return self.raw[2:-2]


@dataclass(slots=True)
class RegisterUpdate:
    """A batch of register values decoded from one transaction."""

    slave: int
    table: str
    start: int
    values: list[int]
    written: bool = False  # True when the master wrote these values


def _candidates(buf: bytearray, expect_response_for: Frame | None):
    """Yield (kind, length) candidates for a frame at the start of buf.

    A length of None means more bytes are needed to know the length.
    """
    if len(buf) < 2:
        return
    slave, func = buf[0], buf[1]
    if slave > 247:
        return
    if func & 0x80:
        yield FrameKind.EXCEPTION, 5
        return

    want_response = (
        expect_response_for is not None
        and expect_response_for.slave == slave
        and expect_response_for.function == func
    )

    if func in READ_FUNCTIONS:
        resp = (FrameKind.RESPONSE, 5 + buf[2] if len(buf) > 2 else None)
        req = (FrameKind.REQUEST, 8)
        order = (resp, req) if want_response else (req, resp)
        yield from order
    elif func in (5, 6):  # single write: request and response are identical
        yield (FrameKind.RESPONSE if want_response else FrameKind.REQUEST), 8
    elif func in (15, 16):
        req = (FrameKind.REQUEST, 9 + buf[6] if len(buf) > 6 else None)
        resp = (FrameKind.RESPONSE, 8)
        order = (resp, req) if want_response else (req, resp)
        yield from order
    elif func == 23:  # read/write multiple registers
        req = (FrameKind.REQUEST, 13 + buf[10] if len(buf) > 10 else None)
        resp = (FrameKind.RESPONSE, 5 + buf[2] if len(buf) > 2 else None)
        order = (resp, req) if want_response else (req, resp)
        yield from order


class RtuStreamDecoder:
    """Incremental decoder for a sniffed Modbus RTU byte stream."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._pending: Frame | None = None
        self.frames = 0
        self.discarded_bytes = 0
        self.transactions = 0

    def reset(self) -> None:
        """Forget partial data, for example after a reconnect."""
        self.discarded_bytes += len(self._buf)
        self._buf.clear()
        self._pending = None

    def feed(self, data: bytes) -> list[RegisterUpdate]:
        """Add received bytes; return register updates that became complete."""
        self._buf.extend(data)
        return self._drain(final=False)

    def flush(self) -> list[RegisterUpdate]:
        """Resolve buffered data after the bus has been quiet for a while.

        Bytes that cannot start a valid frame are dropped so that a burst of
        noise cannot stall decoding until the next poll.
        """
        return self._drain(final=True)

    def _drain(self, final: bool) -> list[RegisterUpdate]:
        updates: list[RegisterUpdate] = []
        buf = self._buf
        while len(buf) >= 4:
            frame, need_more = self._try_frame()
            if frame is not None:
                del buf[: len(frame.raw)]
                self.frames += 1
                updates.extend(self._handle(frame))
                continue
            if need_more and not final:
                break
            # Nothing valid starts here: drop one byte and resync.
            del buf[0]
            self.discarded_bytes += 1
        if final and buf:
            self.discarded_bytes += len(buf)
            buf.clear()
        return updates

    def _try_frame(self) -> tuple[Frame | None, bool]:
        buf = self._buf
        need_more = False
        for kind, length in _candidates(buf, self._pending):
            if length is None or length > len(buf):
                if length is None or length <= MAX_FRAME:
                    need_more = True
                continue
            if length > MAX_FRAME:
                continue
            chunk = bytes(buf[:length])
            if crc_ok(chunk):
                return Frame(kind, chunk), False
        return None, need_more

    def _handle(self, frame: Frame) -> list[RegisterUpdate]:
        if frame.kind is FrameKind.EXCEPTION:
            self._pending = None
            return []
        if frame.kind is FrameKind.REQUEST:
            self._pending = frame
            return _decode_write_request(frame)

        request, self._pending = self._pending, None
        if request is None:
            return []
        if request.slave != frame.slave or request.function != frame.function:
            return []
        self.transactions += 1
        return _decode_response(request, frame)


def _decode_write_request(frame: Frame) -> list[RegisterUpdate]:
    """Values written by the master are what the slave's registers now hold."""
    raw = frame.raw
    if frame.function == 6:
        addr = int.from_bytes(raw[2:4], "big")
        value = int.from_bytes(raw[4:6], "big")
        return [RegisterUpdate(frame.slave, TABLE_HOLDING, addr, [value], True)]
    if frame.function == 16:
        addr = int.from_bytes(raw[2:4], "big")
        count = int.from_bytes(raw[4:6], "big")
        data = raw[7:-2]
        if len(data) != 2 * count:
            return []
        values = [int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2)]
        return [RegisterUpdate(frame.slave, TABLE_HOLDING, addr, values, True)]
    return []


def _decode_response(request: Frame, response: Frame) -> list[RegisterUpdate]:
    func = request.function
    req = request.raw
    if func in REGISTER_READS:
        start = int.from_bytes(req[2:4], "big")
        count = int.from_bytes(req[4:6], "big")
        data = response.raw[3:-2]
        if response.raw[2] != len(data) or len(data) != 2 * count:
            return []
        values = [int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2)]
        return [RegisterUpdate(request.slave, READ_FUNCTIONS[func], start, values)]
    if func in BIT_READS:
        start = int.from_bytes(req[2:4], "big")
        count = int.from_bytes(req[4:6], "big")
        data = response.raw[3:-2]
        bits = [(data[i // 8] >> (i % 8)) & 1 for i in range(min(count, len(data) * 8))]
        return [RegisterUpdate(request.slave, READ_FUNCTIONS[func], start, bits)]
    if func == 23:
        start = int.from_bytes(req[2:4], "big")
        count = int.from_bytes(req[4:6], "big")
        data = response.raw[3:-2]
        if len(data) != 2 * count:
            return []
        values = [int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2)]
        return [RegisterUpdate(request.slave, TABLE_HOLDING, start, values)]
    return []


# --- value decoding -------------------------------------------------------

DATA_TYPES = {
    "uint16": 1,
    "int16": 1,
    "uint32": 2,
    "int32": 2,
    "uint32_swap": 2,  # low word first
    "int32_swap": 2,
    "string": None,  # length given by `count`
}


def register_span(data_type: str, count: int | None = None) -> int:
    """Number of registers a value of data_type occupies."""
    span = DATA_TYPES[data_type]
    if span is None:
        return max(1, int(count or 1))
    return span


def decode_value(data_type: str, regs: list[int]):
    """Turn raw 16-bit registers into a Python value."""
    if data_type == "uint16":
        return regs[0]
    if data_type == "int16":
        v = regs[0]
        return v - 0x10000 if v & 0x8000 else v
    if data_type in ("uint32", "int32", "uint32_swap", "int32_swap"):
        hi, lo = (regs[1], regs[0]) if data_type.endswith("_swap") else (regs[0], regs[1])
        v = (hi << 16) | lo
        if data_type.startswith("int") and v & 0x80000000:
            v -= 0x100000000
        return v
    if data_type == "string":
        raw = b"".join(r.to_bytes(2, "big") for r in regs)
        return raw.replace(b"\x00", b"").decode("ascii", errors="replace").strip()
    raise ValueError(f"unknown data type {data_type}")


@dataclass
class RegisterStats:
    """Running statistics for one register, used for diagnostics."""

    value: int
    minimum: int
    maximum: int
    changes: int = 0
    decreases: int = 0
    updates: int = 1
    written: bool = False

    def update(self, value: int, written: bool) -> bool:
        changed = value != self.value
        if changed:
            self.changes += 1
            if value < self.value:
                self.decreases += 1
        self.value = value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)
        self.updates += 1
        self.written = self.written or written
        return changed
