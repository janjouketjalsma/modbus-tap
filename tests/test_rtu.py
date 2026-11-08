import os
import random
from pathlib import Path

import pytest

from tap.model import Outcome, Table
from tap.rtu import RtuDecoder, with_crc


def read_request(unit, function, start, count):
    return with_crc(bytes([unit, function, start >> 8, start & 0xFF, count >> 8, count & 0xFF]))


def read_response(unit, function, values):
    payload = b"".join(v.to_bytes(2, "big") for v in values)
    return with_crc(bytes([unit, function, len(payload)]) + payload)


def write_multiple(unit, start, values):
    payload = b"".join(v.to_bytes(2, "big") for v in values)
    return with_crc(bytes([unit, 16, start >> 8, start & 0xFF, 0, len(values), len(payload)]) + payload)


def write_echo(unit, start, count):
    return with_crc(bytes([unit, 16, start >> 8, start & 0xFF, 0, count]))


def test_read_is_answered():
    (tx,) = RtuDecoder().feed(read_request(1, 4, 37, 2) + read_response(1, 4, [2344, 0xFFF5]))
    assert (tx.unit, tx.table, tx.start, tx.values, tx.outcome) == (1, Table.INPUT, 37, (2344, 0xFFF5), Outcome.ANSWERED)
    assert tx.updates_registers


def test_byte_by_byte():
    decoder = RtuDecoder()
    done = []
    for byte in read_request(1, 3, 0, 1) + read_response(1, 3, [7]):
        done += decoder.feed(bytes([byte]))
    assert [tx.values for tx in done] == [(7,)]


def test_confirmed_write():
    clock = [26, 11, 8, 21, 11, 7]
    (tx,) = RtuDecoder().feed(write_multiple(1, 2054, clock) + write_echo(1, 2054, 6))
    assert tx.outcome is Outcome.CONFIRMED and tx.is_write and tx.values == tuple(clock)
    assert tx.updates_registers


def test_rejected_write_does_not_update():
    exception = with_crc(bytes([1, 0x90, 2]))
    (tx,) = RtuDecoder().feed(write_multiple(1, 10, [5]) + exception)
    assert tx.outcome is Outcome.REJECTED and tx.exception_code == 2
    assert not tx.updates_registers


def test_unanswered_when_next_request_arrives():
    done = RtuDecoder().feed(write_multiple(1, 10, [5]) + read_request(1, 3, 0, 1) + read_response(1, 3, [1]))
    assert [tx.outcome for tx in done] == [Outcome.UNANSWERED, Outcome.ANSWERED]


def test_unanswered_on_flush():
    decoder = RtuDecoder()
    assert decoder.feed(read_request(1, 3, 0, 1)) == []
    (tx,) = decoder.flush()
    assert tx.outcome is Outcome.UNANSWERED


def test_broadcast_write_is_unanswered_by_design():
    (tx,) = RtuDecoder().feed(write_multiple(0, 10, [5]))
    assert tx.unit == 0 and tx.outcome is Outcome.UNANSWERED


def test_single_register_write_echo():
    request = with_crc(bytes([1, 6, 0, 5, 0x12, 0x34]))
    (tx,) = RtuDecoder().feed(request + request)
    assert tx.outcome is Outcome.CONFIRMED and tx.values == (0x1234,) and tx.start == 5


def test_coil_reads():
    request = read_request(1, 1, 0, 10)
    response = with_crc(bytes([1, 1, 2, 0b00000101, 0b00000010]))
    (tx,) = RtuDecoder().feed(request + response)
    assert tx.table is Table.COIL and tx.values == (1, 0, 1, 0, 0, 0, 0, 0, 0, 1)


def test_noise_is_skipped():
    decoder = RtuDecoder()
    done = decoder.feed(b"\xff\x00\x13" + read_request(1, 4, 1, 1) + read_response(1, 4, [5]) + b"\x55")
    done += decoder.flush()
    assert [tx.values for tx in done] == [(5,)]
    assert decoder.discarded_bytes == 4


def test_fuzz_random_chunking():
    rng = random.Random(7)
    stream, expected = b"", []
    for _ in range(300):
        function, start, n = rng.choice([3, 4]), rng.randrange(3000), rng.randrange(1, 120)
        values = [rng.randrange(65536) for _ in range(n)]
        stream += read_request(1, function, start, n) + read_response(1, function, values)
        expected.append((start, tuple(values)))
    decoder, done, i = RtuDecoder(), [], 0
    while i < len(stream):
        step = rng.randrange(1, 64)
        done += decoder.feed(stream[i : i + step])
        i += step
    done += decoder.flush()
    assert [(tx.start, tx.values) for tx in done] == expected
    assert decoder.discarded_bytes == 0


CAPTURE = os.environ.get("MODBUS_TAP_CAPTURE")


@pytest.mark.skipif(not CAPTURE, reason="set MODBUS_TAP_CAPTURE to a raw capture file")
def test_real_capture():
    data = Path(CAPTURE).read_bytes()
    decoder, done = RtuDecoder(), []
    for i in range(0, len(data), 37):
        done += decoder.feed(data[i : i + 37])
    done += decoder.flush()
    assert decoder.frames > 100
    assert any(tx.outcome is Outcome.CONFIRMED for tx in done)
    assert any(tx.table is Table.INPUT and tx.start <= 37 < tx.start + len(tx.values) for tx in done)
