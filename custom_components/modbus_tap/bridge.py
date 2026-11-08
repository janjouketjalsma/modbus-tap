"""A read-only connection to the Bridge (ADR 0001: the Tap never transmits)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable

from .model import Decoder, Transaction

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10.0
IDLE_FLUSH = 2.0  # seconds of silence before buffered bytes are resolved
STALE_CONNECTION = 300.0  # reconnect when nothing at all arrives for this long
MAX_RETRY_DELAY = 60.0


class BridgeListener:
    """Keeps a TCP connection to the Bridge open and feeds what it hears to a Decoder."""

    def __init__(
        self,
        host: str,
        port: int,
        decoder: Decoder,
        on_transactions: Callable[[list[Transaction]], None],
        on_status: Callable[[], None],
    ) -> None:
        self.host = host
        self.port = port
        self.decoder = decoder
        self.connected = False
        self.bytes_received = 0
        self.zero_bytes = 0  # many zero bytes in undecodable data hint at swapped A/B
        self.last_data: float | None = None  # monotonic
        self._on_transactions = on_transactions
        self._on_status = on_status
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        delay = 1.0
        warned = False
        while not self._stop.is_set():
            writer = None
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT)
                _LOGGER.info("Listening to %s:%s", self.host, self.port)
                warned, delay = False, 1.0
                self._set_connected(True)
                await self._listen(reader)
            except (OSError, TimeoutError) as err:
                if not warned:
                    _LOGGER.warning("Cannot reach the bridge at %s:%s: %s", self.host, self.port, err)
                    warned = True
            finally:
                if writer is not None:
                    writer.close()
                    with contextlib.suppress(OSError):
                        await writer.wait_closed()
                self._deliver(self.decoder.flush())
                self.decoder.reset()
                self._set_connected(False)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), delay)
            delay = min(delay * 2, MAX_RETRY_DELAY)

    async def _listen(self, reader: asyncio.StreamReader) -> None:
        stopped = asyncio.ensure_future(self._stop.wait())
        last = time.monotonic()
        try:
            while not self._stop.is_set():
                read = asyncio.ensure_future(reader.read(4096))
                done, _ = await asyncio.wait({read, stopped}, timeout=IDLE_FLUSH, return_when=asyncio.FIRST_COMPLETED)
                if read not in done:
                    read.cancel()
                    with contextlib.suppress(asyncio.CancelledError, OSError):
                        await read
                    if self._stop.is_set():
                        return
                    self._deliver(self.decoder.flush())
                    if time.monotonic() - last > STALE_CONNECTION:
                        _LOGGER.info("Nothing heard for %ss, reconnecting", STALE_CONNECTION)
                        return
                    continue
                data = read.result()
                if not data:
                    _LOGGER.info("The bridge closed the connection")
                    return
                last = self.last_data = time.monotonic()
                self.bytes_received += len(data)
                self.zero_bytes += data.count(0)
                self._deliver(self.decoder.feed(data))
        finally:
            stopped.cancel()

    def _deliver(self, transactions: list[Transaction]) -> None:
        if transactions:
            self._on_transactions(transactions)
        self._on_status()

    def _set_connected(self, value: bool) -> None:
        if self.connected != value:
            self.connected = value
            self._on_status()
