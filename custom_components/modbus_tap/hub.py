"""Listen to a TCP-to-RS485 bridge and keep a table of sniffed registers.

Plain asyncio, no Home Assistant imports, so it can be tested on its own.
The hub only ever reads from the socket: it never transmits on the bus.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from .const import CONNECT_TIMEOUT, IDLE_FLUSH, RECONNECT_MAX_DELAY, STALE_TIMEOUT
from .rtu import RegisterStats, RegisterUpdate, RtuStreamDecoder

_LOGGER = logging.getLogger(__name__)

RegisterKey = tuple[int, str, int]  # (slave, table, address)


class SnifferHub:
    """Owns the TCP connection, the decoder and the register table."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.decoder = RtuStreamDecoder()
        self.registers: dict[RegisterKey, RegisterStats] = {}
        self.connected = False
        self.last_frame: float | None = None  # unix time
        self.bytes_received = 0
        self._key_listeners: dict[RegisterKey, set[Callable[[], None]]] = {}
        self._new_key_listeners: set[Callable[[list[RegisterKey]], None]] = set()
        self._status_listeners: set[Callable[[], None]] = set()
        self._stop = asyncio.Event()

    # --- listener registration (call from the event loop) ---------------

    def listen_key(self, key: RegisterKey, cb: Callable[[], None]) -> Callable[[], None]:
        self._key_listeners.setdefault(key, set()).add(cb)

        def remove() -> None:
            self._key_listeners.get(key, set()).discard(cb)

        return remove

    def listen_new_keys(self, cb: Callable[[list[RegisterKey]], None]) -> Callable[[], None]:
        self._new_key_listeners.add(cb)
        return lambda: self._new_key_listeners.discard(cb)

    def listen_status(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._status_listeners.add(cb)
        return lambda: self._status_listeners.discard(cb)

    # --- main loop -------------------------------------------------------

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        """Connect, read and decode until stop() is called."""
        delay = 1.0
        logged_error = False
        while not self._stop.is_set():
            writer = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
                )
                _LOGGER.info("Connected to %s:%s", self.host, self.port)
                logged_error = False
                delay = 1.0
                self._set_connected(True)
                await self._read_loop(reader)
            except asyncio.CancelledError:
                raise
            except (OSError, TimeoutError) as err:
                if not logged_error:
                    _LOGGER.warning("Connection to %s:%s failed: %s", self.host, self.port, err)
                    logged_error = True
            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except (OSError, asyncio.CancelledError):
                        pass
                self._apply(self.decoder.flush())
                self.decoder.reset()
                self._set_connected(False)
            if self._stop.is_set():
                break
            try:
                await asyncio.wait_for(self._stop.wait(), delay)
            except TimeoutError:
                pass
            delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        last_data = time.monotonic()
        stop_task = asyncio.ensure_future(self._stop.wait())
        try:
            while not self._stop.is_set():
                read_task = asyncio.ensure_future(reader.read(4096))
                done, _ = await asyncio.wait({read_task, stop_task}, timeout=IDLE_FLUSH, return_when=asyncio.FIRST_COMPLETED)
                if read_task not in done:
                    read_task.cancel()
                    try:
                        await read_task
                    except (asyncio.CancelledError, OSError):
                        pass
                    if self._stop.is_set():
                        return
                    # Bus quiet: resolve anything left in the buffer.
                    self._apply(self.decoder.flush())
                    if time.monotonic() - last_data > STALE_TIMEOUT:
                        _LOGGER.info("No data for %ss, reconnecting", STALE_TIMEOUT)
                        return
                    continue
                data = read_task.result()
                if not data:
                    _LOGGER.info("Connection closed by %s:%s", self.host, self.port)
                    return
                last_data = time.monotonic()
                self.bytes_received += len(data)
                self._apply(self.decoder.feed(data))
        finally:
            stop_task.cancel()

    # --- state updates ---------------------------------------------------

    def _set_connected(self, value: bool) -> None:
        if self.connected != value:
            self.connected = value
            self._notify_status()

    def _notify_status(self) -> None:
        for cb in list(self._status_listeners):
            cb()

    def _apply(self, updates: list[RegisterUpdate]) -> None:
        if not updates:
            return
        new_keys: list[RegisterKey] = []
        touched: set[RegisterKey] = set()
        for up in updates:
            for offset, value in enumerate(up.values):
                key = (up.slave, up.table, up.start + offset)
                stats = self.registers.get(key)
                if stats is None:
                    self.registers[key] = RegisterStats(value, value, value, written=up.written)
                    new_keys.append(key)
                else:
                    stats.update(value, up.written)
                touched.add(key)
        self.last_frame = time.time()
        if new_keys:
            for cb in list(self._new_key_listeners):
                cb(new_keys)
        callbacks: set[Callable[[], None]] = set()
        for key in touched:
            callbacks.update(self._key_listeners.get(key, ()))
        for cb in callbacks:
            cb()
        self._notify_status()

    def value(self, key: RegisterKey) -> int | None:
        stats = self.registers.get(key)
        return None if stats is None else stats.value

    def values(self, keys: list[RegisterKey]) -> list[int] | None:
        out = []
        for key in keys:
            stats = self.registers.get(key)
            if stats is None:
                return None
            out.append(stats.value)
        return out
