"""Fix flow for "use this Community map?" suggestions."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant

from . import COMMUNITY_MAPS
from .const import CONF_COMMUNITY_MAP, CONF_OVERRIDES, CONF_UNITS


class UseCommunityMapFlow(RepairsFlow):
    def __init__(self, entry_id: str, unit: int, map_id: str) -> None:
        self.entry_id = entry_id
        self.unit = unit
        self.map_id = map_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if entry is None:
            return self.async_abort(reason="entry_gone")
        if user_input is not None:
            units = dict(entry.options.get(CONF_UNITS, {}))
            current = units.get(str(self.unit), {})
            units[str(self.unit)] = {CONF_COMMUNITY_MAP: self.map_id, CONF_OVERRIDES: current.get(CONF_OVERRIDES, "")}
            self.hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_UNITS: units})  # reloads via the update listener
            return self.async_create_entry(data={})
        maps = self.hass.data.get(COMMUNITY_MAPS, {})
        name = maps[self.map_id].name if self.map_id in maps else self.map_id
        return self.async_show_form(
            step_id="confirm",
            data_schema=probatio.Schema({}),
            description_placeholders={"unit": str(self.unit), "map": name},
        )


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None) -> RepairsFlow:
    assert data is not None
    return UseCommunityMapFlow(str(data["entry_id"]), int(data["unit"]), str(data["map_id"]))
