"""End-to-end test of the hub against a fake bridge (plain asyncio)."""

import asyncio

from msn import hub as hubmod
from msn.rtu import crc16


def frame(*body: int) -> bytes:
    data = bytes(body)
    crc = crc16(data)
    return data + bytes([crc & 0xFF, crc >> 8])


def poll(volts: int) -> bytes:
    req = frame(1, 4, 0, 37, 0, 2)
    rsp = frame(1, 4, 4, volts >> 8, volts & 0xFF, 0x13, 0x87)
    return req + rsp


async def _serve(chunks, drop_after_first=False):
    """Fake bridge: sends chunks to each client; counts bytes it receives."""
    received = bytearray()
    connections = 0

    async def handle(reader, writer):
        nonlocal connections
        connections += 1
        for chunk in chunks:
            writer.write(chunk)
            await writer.drain()
            await asyncio.sleep(0.05)
        if drop_after_first and connections == 1:
            writer.close()
            return
        try:
            while data := await reader.read(100):
                received.extend(data)
        except ConnectionError:
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port, received, lambda: connections


def test_hub_decodes_and_notifies(monkeypatch):
    monkeypatch.setattr(hubmod, "IDLE_FLUSH", 0.3)

    async def main():
        stream = poll(2344) + poll(2350)
        chunks = [stream[i : i + 5] for i in range(0, len(stream), 5)]
        server, port, received, _ = await _serve(chunks)
        hub = hubmod.SnifferHub("127.0.0.1", port)
        new_keys, hits = [], []
        hub.listen_new_keys(new_keys.extend)
        hub.listen_key((1, "input", 37), lambda: hits.append(hub.value((1, "input", 37))))
        task = asyncio.create_task(hub.run())
        for _ in range(100):
            await asyncio.sleep(0.02)
            if len(hits) >= 2:
                break
        assert hub.connected
        hub.stop()
        await asyncio.wait_for(task, 3)
        server.close()
        assert sorted(new_keys) == [(1, "input", 37), (1, "input", 38)]
        assert hits == [2344, 2350]
        assert hub.registers[(1, "input", 37)].changes == 1
        assert hub.values([(1, "input", 37), (1, "input", 38)]) == [2350, 0x1387]
        assert bytes(received) == b""  # the hub never transmits
        assert not hub.connected

    asyncio.run(main())


def test_hub_reconnects(monkeypatch):
    monkeypatch.setattr(hubmod, "IDLE_FLUSH", 0.3)

    async def main():
        server, port, _, conns = await _serve([poll(2300)], drop_after_first=True)
        hub = hubmod.SnifferHub("127.0.0.1", port)
        task = asyncio.create_task(hub.run())
        for _ in range(200):
            await asyncio.sleep(0.02)
            if conns() >= 2:
                break
        hub.stop()
        await asyncio.wait_for(task, 3)
        server.close()
        assert conns() >= 2
        assert hub.value((1, "input", 37)) == 2300

    asyncio.run(main())


def test_hub_survives_unreachable_host(monkeypatch):
    monkeypatch.setattr(hubmod, "CONNECT_TIMEOUT", 0.2)

    async def main():
        hub = hubmod.SnifferHub("127.0.0.1", 1)  # nothing listens on port 1
        task = asyncio.create_task(hub.run())
        await asyncio.sleep(0.3)
        assert not hub.connected
        hub.stop()
        await asyncio.wait_for(task, 3)

    asyncio.run(main())
