"""A running Recording, wired into Home Assistant (reference entities, disk writes)."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .model import Transaction
from .recording import Recording, RecordingLibrary


class RecordingSession:
    """Collects bus traffic, reference values and notes into one Recording."""

    def __init__(self, hass: HomeAssistant, library: RecordingLibrary, recording: Recording, reference_entities: list[str]) -> None:
        self.hass = hass
        self.library = library
        self.recording = recording
        self.reference_entities = reference_entities
        self._unsubscribe = None

    @property
    def name(self) -> str:
        return self.recording.name

    @callback
    def start(self, bridge: dict[str, Any], units: dict[str, Any]) -> None:
        self.recording.header(bridge, self.reference_entities, units)
        now = time.time()
        for entity_id in self.reference_entities:
            if (state := self.hass.states.get(entity_id)) is not None:
                self.recording.entity(now, entity_id, state.state, dict(state.attributes))
        if self.reference_entities:
            self._unsubscribe = async_track_state_change_event(self.hass, self.reference_entities, self._state_changed)

    @callback
    def _state_changed(self, event: Event[EventStateChangedData]) -> None:
        if (state := event.data["new_state"]) is not None:
            self.recording.entity(time.time(), state.entity_id, state.state, dict(state.attributes))

    @callback
    def transaction(self, now: float, transaction: Transaction) -> None:
        self.recording.transaction(now, transaction)

    @callback
    def note(self, text: str) -> None:
        self.recording.note(time.time(), text)

    async def async_flush(self) -> None:
        await self.hass.async_add_executor_job(self.library.append, self.recording.path, self.recording.take())

    async def async_finish(self, reason: str, keep: int) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self.recording.end(time.time(), reason)
        await self.async_flush()
        await self.hass.async_add_executor_job(self.library.prune, keep)
