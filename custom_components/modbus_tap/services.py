"""Actions: start and stop Recordings, and add notes to them."""

from __future__ import annotations

import probatio

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CONFIG_ENTRY,
    ATTR_HOURS,
    ATTR_TEXT,
    CONF_REFERENCE_DEVICES,
    CONF_REFERENCE_ENTITIES,
    CONF_REFERENCE_PATTERNS,
    DEFAULT_RECORDING_HOURS,
    DOMAIN,
    SERVICE_ADD_NOTE,
    SERVICE_START_RECORDING,
    SERVICE_STOP_RECORDING,
)
from .tap import Tap

ENTRY_SCHEMA = probatio.Schema({probatio.Required(ATTR_CONFIG_ENTRY): cv.string})
START_SCHEMA = ENTRY_SCHEMA.extend(
    {
        probatio.Optional(ATTR_HOURS, default=DEFAULT_RECORDING_HOURS): probatio.All(
            probatio.Coerce(float), probatio.Range(min=0.05, max=DEFAULT_RECORDING_HOURS)
        ),
        probatio.Optional(CONF_REFERENCE_ENTITIES): cv.entity_ids,
        probatio.Optional(CONF_REFERENCE_DEVICES): probatio.All(cv.ensure_list, [cv.string]),
        probatio.Optional(CONF_REFERENCE_PATTERNS): probatio.All(cv.ensure_list, [cv.string]),
    }
)
NOTE_SCHEMA = ENTRY_SCHEMA.extend({probatio.Required(ATTR_TEXT): cv.string})


def _tap(hass: HomeAssistant, call: ServiceCall) -> Tap:
    entry = hass.config_entries.async_get_entry(call.data[ATTR_CONFIG_ENTRY])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="entry_not_loaded")
    return entry.runtime_data


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def start(call: ServiceCall) -> dict:
        tap = _tap(hass, call)
        if tap.session is not None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="already_recording")
        references = tap.reference_entity_ids(
            call.data.get(CONF_REFERENCE_ENTITIES), call.data.get(CONF_REFERENCE_DEVICES), call.data.get(CONF_REFERENCE_PATTERNS)
        )
        name = await tap.async_start_recording(call.data[ATTR_HOURS], references)
        return {"recording": name}

    async def stop(call: ServiceCall) -> dict:
        name = await _tap(hass, call).async_stop_recording()
        if name is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_recording")
        return {"recording": name}

    async def note(call: ServiceCall) -> None:
        if not _tap(hass, call).add_note(call.data[ATTR_TEXT]):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_recording")

    hass.services.async_register(DOMAIN, SERVICE_START_RECORDING, start, START_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_STOP_RECORDING, stop, ENTRY_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_ADD_NOTE, note, NOTE_SCHEMA)
