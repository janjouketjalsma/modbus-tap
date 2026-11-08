import asyncio

from tap import bridge as bridge_module
from tap.hints import BusProblem, bus_problem, find_strings
from tap.model import Outcome, Table, Transaction
from tap.recording import Recording, RecordingLibrary, read_records
from tap.rtu import RtuDecoder, with_crc
from tap.store import RegisterState


def test_recording_round_trip(tmp_path):
    library = RecordingLibrary(tmp_path)
    path = library.new_path(1_700_000_000.0)
    rec = Recording(path, started=1_700_000_000.0, max_seconds=60)
    rec.header({"host": "h", "port": 1}, ["sensor.pv_power"], {})
    rec.transaction(1_700_000_001.0, Transaction(1, 4, Table.INPUT, 37, (2344,), Outcome.ANSWERED))
    library.append(path, rec.take())
    rec.entity(1_700_000_002.0, "sensor.pv_power", "2100", {"unit_of_measurement": "W", "other": 1})
    rec.note(1_700_000_003.0, "kettle on")
    rec.end(1_700_000_004.0, "stopped")
    library.append(path, rec.take())
    records = read_records(path)
    assert [r["type"] for r in records] == ["header", "transaction", "entity", "note", "end"]
    assert records[2] == {"type": "entity", "t": 1_700_000_002.0, "entity_id": "sensor.pv_power", "state": "2100", "unit_of_measurement": "W"}
    assert rec.expired(1_700_000_060.0)


def test_library_lists_prunes_and_refuses_path_tricks(tmp_path):
    library = RecordingLibrary(tmp_path)
    for t in (1.0, 2.0, 3.0):
        library.append(library.new_path(t * 3600), "{}\n")
    assert len(library.recordings()) == 3
    library.prune(keep=2)
    assert len(library.recordings()) == 2
    assert library.path_of("../secrets.yaml") is None
    library.delete([library.recordings()[0].name])
    assert len(library.recordings()) == 1


def test_bus_problem_rules():
    assert bus_problem(False, 0, 0, 0, None) is None
    assert bus_problem(True, 0, 0, 0, 700) is BusProblem.SILENT
    assert bus_problem(True, 5000, 10, 0, 0) is None
    assert bus_problem(True, 3000, 0, 900, 0) is BusProblem.REVERSED
    assert bus_problem(True, 3000, 0, 30, 0) is BusProblem.UNDECODABLE


def test_find_strings():
    regs = {(1, Table.INPUT, 144 + i): RegisterState(v, 0, v, v) for i, v in enumerate([0x5353, 0x452D, 0x4848])}
    assert find_strings(regs) == [{"unit": 1, "table": "input", "address": 144, "count": 3, "text": "SSE-HH"}]


def test_bridge_listens_and_never_transmits(monkeypatch):
    monkeypatch.setattr(bridge_module, "IDLE_FLUSH", 0.2)

    async def main():
        received = bytearray()
        writers = []

        async def handle(reader, writer):
            writers.append(writer)
            received.extend(await reader.read())
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        heard = []
        listener = bridge_module.BridgeListener("127.0.0.1", port, RtuDecoder(), heard.extend, lambda: None)
        task = asyncio.create_task(listener.run())
        for _ in range(100):
            await asyncio.sleep(0.02)
            if writers:
                break
        request = with_crc(bytes([1, 4, 0, 37, 0, 1]))
        writers[0].write(request + with_crc(bytes([1, 4, 2, 0x09, 0x28])))
        await writers[0].drain()
        for _ in range(100):
            await asyncio.sleep(0.02)
            if heard:
                break
        assert listener.connected
        listener.stop()
        await asyncio.wait_for(task, 3)
        server.close()
        await server.wait_closed()
        assert [tx.values for tx in heard] == [(2344,)]
        assert bytes(received) == b""

    asyncio.run(main())
