"""Tests for the passive RTU decoder (no Home Assistant needed)."""

import os
import random
from pathlib import Path

import pytest

from msn import rtu


def frame(*body: int) -> bytes:
    data = bytes(body)
    crc = rtu.crc16(data)
    return data + bytes([crc & 0xFF, crc >> 8])


def read_req(slave, func, start, count):
    return frame(slave, func, start >> 8, start & 0xFF, count >> 8, count & 0xFF)


def read_rsp(slave, func, values):
    payload = b"".join(v.to_bytes(2, "big") for v in values)
    return frame(slave, func, len(payload), *payload)


def test_crc_known_value():
    # Request captured on the real bus: read input register 0x0087, count 1.
    assert rtu.crc_ok(bytes.fromhex("0104008700 0181e3".replace(" ", "")))


def test_request_response_pair():
    dec = rtu.RtuStreamDecoder()
    stream = read_req(1, 4, 37, 3) + read_rsp(1, 4, [2344, 0xFFF5, 4999])
    ups = dec.feed(stream)
    assert len(ups) == 1
    up = ups[0]
    assert (up.slave, up.table, up.start, up.values) == (1, "input", 37, [2344, 0xFFF5, 4999])
    assert dec.discarded_bytes == 0


def test_byte_by_byte_feed():
    dec = rtu.RtuStreamDecoder()
    stream = read_req(1, 3, 0, 2) + read_rsp(1, 3, [7, 8])
    ups = []
    for b in stream:
        ups += dec.feed(bytes([b]))
    assert [(u.table, u.values) for u in ups] == [("holding", [7, 8])]


def test_noise_between_frames_is_skipped():
    dec = rtu.RtuStreamDecoder()
    stream = b"\xff\x00\x13" + read_req(1, 4, 1, 1) + read_rsp(1, 4, [5]) + b"\x55"
    ups = dec.feed(stream) + dec.flush()
    assert [u.values for u in ups] == [[5]]
    assert dec.discarded_bytes == 4


def test_write_multiple_is_recorded_as_holding():
    dec = rtu.RtuStreamDecoder()
    vals = [26, 11, 8, 21, 11, 7]
    payload = b"".join(v.to_bytes(2, "big") for v in vals)
    req = frame(1, 16, 0x08, 0x06, 0, 6, len(payload), *payload)
    rsp = frame(1, 16, 0x08, 0x06, 0, 6)
    ups = dec.feed(req + rsp)
    assert len(ups) == 1
    assert ups[0].written and ups[0].start == 0x0806 and ups[0].values == vals


def test_exception_clears_pending():
    dec = rtu.RtuStreamDecoder()
    ups = dec.feed(read_req(1, 3, 0, 1) + frame(1, 0x83, 2) + read_rsp(1, 3, [9]))
    assert ups == []  # orphan response after exception is ignored


def test_response_that_looks_like_request_length():
    # A 1-register read response is 7 bytes; a 3-byte-count response could be
    # mistaken for an 8-byte request. Make sure pairing context wins.
    dec = rtu.RtuStreamDecoder()
    ups = dec.feed(read_req(1, 3, 10, 1) + read_rsp(1, 3, [0x1234]) + read_req(1, 4, 5, 1) + read_rsp(1, 4, [1]))
    assert [(u.table, u.start, u.values) for u in ups] == [("holding", 10, [0x1234]), ("input", 5, [1])]


def test_random_stream_fuzz():
    rng = random.Random(1)
    dec = rtu.RtuStreamDecoder()
    expected = []
    stream = b""
    for _ in range(200):
        func = rng.choice([3, 4])
        start = rng.randrange(0, 3000)
        n = rng.randrange(1, 120)
        vals = [rng.randrange(0, 65536) for _ in range(n)]
        stream += read_req(1, func, start, n) + read_rsp(1, func, vals)
        expected.append((func, start, vals))
    got = []
    i = 0
    while i < len(stream):
        step = rng.randrange(1, 64)
        got += dec.feed(stream[i : i + step])
        i += step
    got += dec.flush()
    assert [(3 if u.table == "holding" else 4, u.start, u.values) for u in got] == expected
    assert dec.discarded_bytes == 0


@pytest.mark.parametrize(
    "dtype,regs,value",
    [
        ("uint16", [65332], 65332),
        ("int16", [65332], -204),
        ("uint32", [1, 2], 65538),
        ("int32", [0xFFFF, 0xFFFE], -2),
        ("uint32_swap", [2, 1], 65538),
        ("string", [0x5353, 0x452D, 0x4848, 0x364B], "SSE-HH6K"),
    ],
)
def test_decode_value(dtype, regs, value):
    assert rtu.decode_value(dtype, regs) == value


CAPTURE = os.environ.get("SNIFFER_CAPTURE")


@pytest.mark.skipif(not CAPTURE, reason="set SNIFFER_CAPTURE to a raw capture file")
def test_real_capture():
    data = Path(CAPTURE).read_bytes()
    dec = rtu.RtuStreamDecoder()
    ups = []
    for i in range(0, len(data), 37):
        ups += dec.feed(data[i : i + 37])
    ups += dec.flush()
    assert dec.frames > 100
    assert dec.discarded_bytes < len(data) * 0.02
    assert any(u.table == "input" and u.start <= 37 < u.start + len(u.values) for u in ups)
