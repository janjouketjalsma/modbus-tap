"""Set up a Bus, change its Bridge address, and configure maps, Recordings and export."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .bridge import CONNECT_TIMEOUT
from .const import (
    CONF_COMMUNITY_MAP,
    CONF_KEEP_RECORDINGS,
    CONF_OVERRIDES,
    CONF_REFERENCE_DEVICES,
    CONF_REFERENCE_ENTITIES,
    CONF_UNITS,
    CONF_WRITE_EVENTS,
    DEFAULT_KEEP_RECORDINGS,
    DEFAULT_PORT,
    DOMAIN,
    TAPPING_GUIDE,
)
from .export import core_modbus_yaml
from .register_map import RegisterMapError, parse_yaml

CONF_UNIT = "unit"
CONF_DELETE = "delete"
NO_MAP = "none"

BRIDGE_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): selector.TextSelector(),
        probatio.Required(CONF_PORT, default=DEFAULT_PORT): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=65535, mode=selector.NumberSelectorMode.BOX)
        ),
    }
)


async def _can_connect(host: str, port: int) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), CONNECT_TIMEOUT)
    except (OSError, TimeoutError):
        return False
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return True


def _bridge(user_input: dict[str, Any]) -> dict[str, Any]:
    return {CONF_HOST: user_input[CONF_HOST].strip(), CONF_PORT: int(user_input[CONF_PORT])}


class ModbusTapConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            bridge = _bridge(user_input)
            await self.async_set_unique_id(f"{bridge[CONF_HOST]}:{bridge[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            if await _can_connect(**bridge):
                return self.async_create_entry(title=f"{bridge[CONF_HOST]}:{bridge[CONF_PORT]}", data=bridge)
            errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(BRIDGE_SCHEMA, user_input),
            errors=errors,
            description_placeholders={"guide": TAPPING_GUIDE},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            bridge = _bridge(user_input)
            unique_id = f"{bridge[CONF_HOST]}:{bridge[CONF_PORT]}"
            other = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, unique_id)
            if other is not None and other.entry_id != entry.entry_id:
                return self.async_abort(reason="already_configured")
            await self.async_set_unique_id(unique_id)
            if await _can_connect(**bridge):
                return self.async_update_reload_and_abort(
                    entry, unique_id=self.unique_id, title=f"{bridge[CONF_HOST]}:{bridge[CONF_PORT]}", data=bridge
                )
            errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(BRIDGE_SCHEMA, user_input or entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> ModbusTapOptionsFlow:
        return ModbusTapOptionsFlow()


class ModbusTapOptionsFlow(OptionsFlowWithReload):
    """Configure → Register maps, Recordings, Export, Settings."""

    def __init__(self) -> None:
        self._unit: int | None = None

    @property
    def _tap(self):
        return getattr(self.config_entry, "runtime_data", None)

    def _known_units(self) -> list[int]:
        units = {int(u) for u in self.config_entry.options.get(CONF_UNITS, {})}
        if self._tap is not None:
            units |= self._tap.store.units
        return sorted(units)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["pick_unit", "recordings", "export", "settings"])

    # --- Register maps -------------------------------------------------------

    async def async_step_pick_unit(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            unit = str(user_input[CONF_UNIT]).strip()
            if unit.isdigit() and 1 <= int(unit) <= 247:
                self._unit = int(unit)
                return await self.async_step_unit_map()
            errors[CONF_UNIT] = "invalid_unit"
        units = [str(u) for u in self._known_units()] or ["1"]
        schema = probatio.Schema(
            {
                probatio.Required(CONF_UNIT, default=units[0]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=units, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="pick_unit", data_schema=schema, errors=errors)

    async def async_step_unit_map(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        unit = self._unit or 1
        units = dict(self.config_entry.options.get(CONF_UNITS, {}))
        current = units.get(str(unit), {})
        errors: dict[str, str] = {}
        placeholders = {"unit": str(unit), "error": ""}
        if user_input is not None:
            try:
                parse_yaml(user_input.get(CONF_OVERRIDES, ""))
            except RegisterMapError as err:
                errors[CONF_OVERRIDES] = "invalid_map"
                placeholders["error"] = str(err)
            else:
                chosen = user_input.get(CONF_COMMUNITY_MAP, NO_MAP)
                units[str(unit)] = {
                    CONF_COMMUNITY_MAP: None if chosen == NO_MAP else chosen,
                    CONF_OVERRIDES: user_input.get(CONF_OVERRIDES, ""),
                }
                return self.async_create_entry(data={**self.config_entry.options, CONF_UNITS: units})

        maps = self._tap.community_maps if self._tap else {}
        options = [selector.SelectOptionDict(value=NO_MAP, label="—")] + [
            selector.SelectOptionDict(value=m.id, label=f"{m.manufacturer} · {m.name}") for m in maps.values()
        ]
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_COMMUNITY_MAP, default=current.get(CONF_COMMUNITY_MAP) or NO_MAP): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
                ),
                probatio.Optional(CONF_OVERRIDES, description={"suggested_value": current.get(CONF_OVERRIDES, "")}): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="unit_map", data_schema=schema, errors=errors, description_placeholders=placeholders)

    # --- Recordings ------------------------------------------------------------

    async def async_step_recordings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        tap = self._tap
        if tap is None:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            await tap.async_delete_recordings(user_input.get(CONF_DELETE, []))
            return self.async_abort(reason="recordings_updated")
        recordings = await tap.async_recordings()
        if not recordings:
            return self.async_abort(reason="no_recordings")
        lines = [
            f"- [{info.name}]({tap.download_url(info.name)}) · "
            f"{datetime.fromtimestamp(info.modified, UTC):%Y-%m-%d %H:%M} UTC · {info.size / 1024:.0f} kB"
            for info in recordings
        ]
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_DELETE, default=[]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[info.name for info in recordings], multiple=True)
                )
            }
        )
        return self.async_show_form(
            step_id="recordings", data_schema=schema, description_placeholders={"recordings": "\n".join(lines)}
        )

    # --- Export ------------------------------------------------------------------

    async def async_step_export(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        tap = self._tap
        if tap is None:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            return self.async_abort(reason="export_done")
        if not any(tap.maps.values()):
            return self.async_abort(reason="nothing_to_export")
        text = core_modbus_yaml(
            tap.listener.host, tap.listener.port, tap.maps, {unit: tap.store.poll_interval(unit) for unit in tap.maps}
        )
        return self.async_show_form(
            step_id="export", data_schema=probatio.Schema({}), description_placeholders={"yaml": text}
        )

    # --- Settings ----------------------------------------------------------------

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        options = self.config_entry.options
        if user_input is not None:
            return self.async_create_entry(data={**options, **user_input, CONF_KEEP_RECORDINGS: int(user_input[CONF_KEEP_RECORDINGS])})
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_WRITE_EVENTS, default=options.get(CONF_WRITE_EVENTS, False)): selector.BooleanSelector(),
                probatio.Optional(
                    CONF_REFERENCE_DEVICES, default=options.get(CONF_REFERENCE_DEVICES, [])
                ): selector.DeviceSelector(selector.DeviceSelectorConfig(multiple=True)),
                probatio.Optional(
                    CONF_REFERENCE_ENTITIES, default=options.get(CONF_REFERENCE_ENTITIES, [])
                ): selector.EntitySelector(selector.EntitySelectorConfig(multiple=True)),
                probatio.Optional(
                    CONF_KEEP_RECORDINGS, default=options.get(CONF_KEEP_RECORDINGS, DEFAULT_KEEP_RECORDINGS)
                ): selector.NumberSelector(selector.NumberSelectorConfig(min=1, max=200, mode=selector.NumberSelectorMode.BOX)),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)
