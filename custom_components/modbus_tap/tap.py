"""The running Tap for one Bus: Bridge connection, Register store, Recordings, devices."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.components.http.auth import async_sign_path
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from . import issues
from .bridge import BridgeListener
from .community import CommunityMap, suggest
from .const import (
    CONF_COMMUNITY_MAP,
    CONF_KEEP_RECORDINGS,
    CONF_OVERRIDES,
    CONF_UNITS,
    CONF_WRITE_EVENTS,
    DEFAULT_KEEP_RECORDINGS,
    DOMAIN,
    DOWNLOAD_URL,
    EVENT_WRITE,
    RECORDINGS_PATH,
)
from .entity import bridge_identifier, unit_identifier
from .hints import bus_problem
from .model import Transaction
from .recording import Recording, RecordingInfo, RecordingLibrary
from .register_map import MapEntry, RegisterMapError, apply_overrides, parse_yaml, with_unit
from .rtu import RtuDecoder
from .session import RecordingSession
from .store import RegisterStore
from .values import decode

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(seconds=30)
LINK_LIFETIME = timedelta(hours=1)


def unit_maps(options: Mapping[str, Any], community_maps: Mapping[str, CommunityMap]) -> dict[int, list[MapEntry]]:
    """Each configured Unit's effective Register map: Community map plus Overrides."""
    maps: dict[int, list[MapEntry]] = {}
    for unit_key, settings in options.get(CONF_UNITS, {}).items():
        unit = int(unit_key)
        base_id = settings.get(CONF_COMMUNITY_MAP)
        base = community_maps[base_id].for_unit(unit) if base_id in community_maps else []
        try:
            overrides = with_unit(parse_yaml(settings.get(CONF_OVERRIDES)).entries, unit)
        except RegisterMapError as err:  # saved maps are validated, so this is a safety net
            _LOGGER.error("Unit %s: ignoring invalid overrides: %s", unit, err)
            overrides = []
        maps[unit] = apply_overrides(base, overrides)
    return maps


class Tap:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, community_maps: dict[str, CommunityMap]) -> None:
        self.hass = hass
        self.entry = entry
        self.community_maps = community_maps
        self.maps = unit_maps(entry.options, community_maps)
        self.store = RegisterStore()
        self.listener = BridgeListener(entry.data[CONF_HOST], entry.data[CONF_PORT], RtuDecoder(), self._on_transactions, self._on_status)
        self.library = RecordingLibrary(Path(hass.config.path(RECORDINGS_PATH, entry.entry_id)))
        self.session: RecordingSession | None = None
        self.last_transaction: float | None = None
        self._status_listeners: set[Callable[[], None]] = set()
        self._models: dict[int, str] = {}

    # --- lifecycle ----------------------------------------------------------

    @callback
    def start(self) -> None:
        entry = self.entry
        devices = dr.async_get(self.hass)
        devices.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={bridge_identifier(entry)},
            translation_key="bridge",
            translation_placeholders={"title": entry.title},
        )
        for unit in self.maps:
            self._ensure_unit_device(unit)
        entry.async_on_unload(self.store.on_new_unit(self._ensure_unit_device))
        entry.async_on_unload(async_track_time_interval(self.hass, self._async_tick, TICK))
        entry.async_create_background_task(self.hass, self.listener.run(), f"{DOMAIN} {entry.title}")
        entry.async_on_unload(self.listener.stop)

    async def async_shutdown(self) -> None:
        if self.session is not None:
            await self.async_stop_recording("unloaded")

    # --- bus traffic --------------------------------------------------------

    @callback
    def _on_transactions(self, transactions: list[Transaction]) -> None:
        now = time.time()
        fire_writes = self.entry.options.get(CONF_WRITE_EVENTS, False)
        for tx in transactions:
            self.store.apply(tx, now)
            if self.session is not None:
                self.session.transaction(now, tx)
            if fire_writes and tx.is_write:
                self.hass.bus.async_fire(
                    EVENT_WRITE,
                    {
                        "config_entry_id": self.entry.entry_id,
                        "unit": tx.unit,
                        "table": tx.table.value if tx.table else None,
                        "address": tx.start,
                        "values": list(tx.values),
                        "outcome": tx.outcome.value,
                        "exception_code": tx.exception_code,
                    },
                )
        self.last_transaction = now

    @callback
    def _on_status(self) -> None:
        for listener in list(self._status_listeners):
            listener()

    @callback
    def listen_status(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._status_listeners.add(listener)
        return lambda: self._status_listeners.discard(listener)

    async def _async_tick(self, _now: Any = None) -> None:
        now = time.time()
        self.store.check_stale(now)
        self._update_models()
        self._suggest_maps()
        listener = self.listener
        issues.show_bus_problem(
            self.hass,
            self.entry,
            bus_problem(listener.connected, listener.bytes_received, listener.decoder.frames, listener.zero_bytes, listener.quiet_seconds()),
        )
        if self.session is not None:
            if self.session.recording.expired(now):
                await self.async_stop_recording("time limit reached")
            else:
                await self.session.async_flush()

    # --- devices and suggestions -----------------------------------------------

    @callback
    def _ensure_unit_device(self, unit: int) -> None:
        dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={unit_identifier(self.entry, unit)},
            translation_key="unit",
            translation_placeholders={"address": str(unit)},
            via_device=bridge_identifier(self.entry),
        )

    @callback
    def _update_models(self) -> None:
        devices = dr.async_get(self.hass)
        for unit, entries in self.maps.items():
            entry = next((e for e in entries if e.model), None)
            if entry is None or (registers := self.store.values(entry.keys)) is None:
                continue
            model = str(decode(entry.data_type, registers, entry.swap))
            if model and self._models.get(unit) != model:
                self._models[unit] = model
                if device := devices.async_get_device_by_identifier(unit_identifier(self.entry, unit), self.entry.entry_id):
                    devices.async_update_device(device.id, model=model)

    @callback
    def _suggest_maps(self) -> None:
        configured = self.entry.options.get(CONF_UNITS, {})
        for unit in self.store.units:
            if configured.get(str(unit), {}).get(CONF_COMMUNITY_MAP):
                continue
            match = suggest(self.community_maps.values(), unit, self.store.values, self.store.reads.get(unit, set()))
            if match is not None:
                issues.suggest_map(self.hass, self.entry, unit, match)

    # --- recordings ------------------------------------------------------------

    async def async_start_recording(self, hours: float, reference_entities: list[str]) -> str:
        if self.session is not None:
            return self.session.name
        started = time.time()
        recording = Recording(self.library.new_path(started), started, hours * 3600)
        self.session = RecordingSession(self.hass, self.library, recording, reference_entities)
        bridge = {"host": self.listener.host, "port": self.listener.port}
        units = {str(u): {"community_map": s.get(CONF_COMMUNITY_MAP)} for u, s in self.entry.options.get(CONF_UNITS, {}).items()}
        self.session.start(bridge, units)
        await self.session.async_flush()
        self._on_status()
        return recording.name

    async def async_stop_recording(self, reason: str = "stopped") -> str | None:
        session, self.session = self.session, None
        if session is None:
            return None
        await session.async_finish(reason, self.entry.options.get(CONF_KEEP_RECORDINGS, DEFAULT_KEEP_RECORDINGS))
        self._on_status()
        persistent_notification.async_create(
            self.hass,
            f"Recording **{session.name}** finished ({reason}).\n\n"
            f"[Download it]({self.download_url(session.name)}) (link valid for one hour), or find it later under "
            f"**Settings → Devices & services → Modbus Tap → Configure → Recordings**.",
            title="Modbus Tap recording finished",
            notification_id=f"{DOMAIN}_{self.entry.entry_id}_recording",
        )
        return session.name

    @callback
    def add_note(self, text: str) -> bool:
        if self.session is None:
            return False
        self.session.note(text)
        return True

    async def async_recordings(self) -> list[RecordingInfo]:
        return await self.hass.async_add_executor_job(self.library.recordings)

    async def async_delete_recordings(self, names: list[str]) -> None:
        active = self.session.name if self.session else None
        await self.hass.async_add_executor_job(self.library.delete, [n for n in names if n != active])

    @callback
    def download_url(self, name: str) -> str:
        path = DOWNLOAD_URL.format(entry_id=self.entry.entry_id, name=name)
        return async_sign_path(self.hass, path, LINK_LIFETIME)
