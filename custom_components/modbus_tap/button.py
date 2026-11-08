"""Buttons to start and stop a Recording from the Bridge device."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TapConfigEntry
from .const import CONF_REFERENCE_ENTITIES, DEFAULT_RECORDING_HOURS
from .entity import TapEntity, bridge_identifier
from .tap import Tap


@dataclass(frozen=True, kw_only=True)
class RecordingButtonDescription(ButtonEntityDescription):
    press: Callable[[Tap], Awaitable[object]]
    available: Callable[[Tap], bool]


BUTTONS = (
    RecordingButtonDescription(
        key="start_recording",
        translation_key="start_recording",
        press=lambda tap: tap.async_start_recording(
            DEFAULT_RECORDING_HOURS, list(tap.entry.options.get(CONF_REFERENCE_ENTITIES, []))
        ),
        available=lambda tap: tap.session is None,
    ),
    RecordingButtonDescription(
        key="stop_recording",
        translation_key="stop_recording",
        press=lambda tap: tap.async_stop_recording(),
        available=lambda tap: tap.session is not None,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: TapConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(RecordingButton(entry.runtime_data, description) for description in BUTTONS)


class RecordingButton(TapEntity, ButtonEntity):
    entity_description: RecordingButtonDescription

    def __init__(self, tap: Tap, description: RecordingButtonDescription) -> None:
        super().__init__(bridge_identifier(tap.entry))
        self.tap = tap
        self.entity_description = description
        self._attr_unique_id = f"{tap.entry.entry_id}_{description.key}"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.tap.listen_status(self._status_changed))

    _was_available: bool | None = None

    @callback
    def _status_changed(self) -> None:
        if self.available != self._was_available:
            self._was_available = self.available
            self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.entity_description.available(self.tap)

    async def async_press(self) -> None:
        await self.entity_description.press(self.tap)
