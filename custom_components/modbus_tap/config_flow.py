"""Set up a Bus, change its Bridge address, and the Configure menu.

The Configure menu is organised by task: sensors (register maps), recordings,
export, advanced. Each screen says what it found on the bus and what to do next.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import probatio
import yaml

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .ai import AI_TASK_DOMAIN, ai_task_entities, async_refine
from .analysis import MIN_POINTS
from .bridge import CONNECT_TIMEOUT
from .const import (
    ATTR_HOURS,
    CONF_COMMUNITY_MAP,
    CONF_KEEP_RECORDINGS,
    CONF_OVERRIDES,
    CONF_REFERENCE_DEVICES,
    CONF_REFERENCE_ENTITIES,
    CONF_REFERENCE_PATTERNS,
    CONF_UNITS,
    CONF_WRITE_EVENTS,
    DEFAULT_KEEP_RECORDINGS,
    DEFAULT_RECORDING_HOURS,
    DOCS,
    DEFAULT_PORT,
    DOMAIN,
    TAPPING_GUIDE,
)
from .community import suggest
from .export import core_modbus_yaml
from .register_map import RegisterMapError, merge_yaml, parse_yaml, to_core

if TYPE_CHECKING:
    from .tap import Tap

CONF_UNIT = "unit"
CONF_RECORDING = "recording"
CONF_AI_TASK = "ai_task"
CONF_CLEAR = "clear"
WRITES_SHOWN = 20
CHANGES_SHOWN = 15


def _when(timestamp: float) -> str:
    return dt_util.as_local(dt_util.utc_from_timestamp(timestamp)).strftime("%a %d %b %H:%M")


def _values(values: tuple[int, ...], limit: int = 8) -> str:
    shown = ", ".join(str(v) for v in values[:limit])
    return shown + (", …" if len(values) > limit else "")
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


class ModbusTapOptionsFlow(OptionsFlow):
    """Configure: Sensors, Recordings, Export, Advanced."""

    def __init__(self) -> None:
        self._unit: int | None = None
        self._analysis_task: asyncio.Task[None] | None = None
        self._suggestion_result: tuple[str, list[str]] = ("", [])

    @property
    def _tap(self) -> Tap | None:
        return getattr(self.config_entry, "runtime_data", None)

    def _save(self, **changes: Any) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    # --- status lines shown on the screens ------------------------------------

    def _unit_line(self, tap: Tap, unit: int) -> str:
        parts = [f"**Unit {unit}**"]
        if model := tap.models.get(unit):
            parts.append(model)
        settings = self.config_entry.options.get(CONF_UNITS, {}).get(str(unit), {})
        if (map_id := settings.get(CONF_COMMUNITY_MAP)) in tap.community_maps:
            parts.append(f"map: {tap.community_maps[map_id].name}")
        elif match := self._suggestion(tap, unit):
            parts.append(f"suggested map: {match.name}")
        parts.append(f"{len(tap.maps.get(unit, []))} sensors")
        return " · ".join(parts)

    def _suggestion(self, tap: Tap, unit: int):
        return suggest(tap.community_maps.values(), unit, tap.store.values, tap.store.reads.get(unit, set()))

    def _known_units(self) -> list[int]:
        units = {int(u) for u in self.config_entry.options.get(CONF_UNITS, {})}
        if self._tap is not None:
            units |= self._tap.store.units
        return sorted(units)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        tap = self._tap
        if tap is None:
            status = "Modbus Tap isn't running right now; some screens are unavailable."
        else:
            units = ", ".join(f"Unit {u}" for u in sorted(tap.store.units)) or "none yet"
            status = (
                f"Bridge: **{'connected' if tap.listener.connected else 'disconnected'}** · "
                f"units heard: **{units}** · recording: **{tap.session.name if tap.session else 'off'}**"
            )
        return self.async_show_menu(
            step_id="init",
            menu_options=["sensors", "recordings", "writes", "export", "advanced"],
            description_placeholders={"status": status, "docs": DOCS},
        )

    # --- Sensors (register maps) ---------------------------------------------------

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            unit = str(user_input[CONF_UNIT]).strip()
            if unit.isdigit() and 1 <= int(unit) <= 247:
                self._unit = int(unit)
                return await self.async_step_unit_map()
            errors[CONF_UNIT] = "invalid_unit"
        tap = self._tap
        units = self._known_units()
        heard = "\n".join(f"- {self._unit_line(tap, u)}" for u in units) if tap and units else "Nothing heard yet. Check the bridge device's **Frames decoded** sensor."
        options = [selector.SelectOptionDict(value=str(u), label=f"Unit {u}") for u in units] or [
            selector.SelectOptionDict(value="1", label="Unit 1")
        ]
        schema = probatio.Schema(
            {
                probatio.Required(CONF_UNIT, default=options[0]["value"]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="sensors", data_schema=schema, errors=errors, description_placeholders={"heard": heard})

    async def async_step_unit_map(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        unit = self._unit or 1
        units = dict(self.config_entry.options.get(CONF_UNITS, {}))
        current = units.get(str(unit), {})
        errors: dict[str, str] = {}
        error = ""
        if user_input is not None:
            try:
                parse_yaml(user_input.get(CONF_OVERRIDES, ""))
            except RegisterMapError as err:
                errors[CONF_OVERRIDES] = "invalid_map"
                error = str(err)
            else:
                chosen = user_input.get(CONF_COMMUNITY_MAP, NO_MAP)
                units[str(unit)] = {
                    CONF_COMMUNITY_MAP: None if chosen == NO_MAP else chosen,
                    CONF_OVERRIDES: user_input.get(CONF_OVERRIDES, ""),
                }
                return self._save(**{CONF_UNITS: units})

        tap = self._tap
        maps = tap.community_maps if tap else {}
        suggestion = self._suggestion(tap, unit) if tap else None
        options = [selector.SelectOptionDict(value=NO_MAP, label="None: only my own entries")] + [
            selector.SelectOptionDict(
                value=m.id, label=f"{m.manufacturer} {m.name}" + (" (suggested for this unit)" if suggestion and m.id == suggestion.id else "")
            )
            for m in maps.values()
        ]
        default_map = current.get(CONF_COMMUNITY_MAP) or (suggestion.id if suggestion else NO_MAP)
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_COMMUNITY_MAP, default=default_map): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
                ),
                probatio.Optional(CONF_OVERRIDES, description={"suggested_value": current.get(CONF_OVERRIDES, "")}): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(
            step_id="unit_map",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "unit": str(unit),
                "heard": self._heard_summary(tap, unit) if tap else "",
                "maps": "\n".join(f"- {self._map_summary(m)}" for m in maps.values()) or "- none",
                "docs": f"{DOCS}/register-maps.md",
                "error": error,
            },
        )

    @staticmethod
    def _heard_summary(tap: Tap, unit: int) -> str:
        reads = sorted(tap.store.reads.get(unit, set()), key=lambda r: (r[0].value, r[1]))
        if not reads:
            return "Nothing heard from this unit yet."
        blocks = ", ".join(f"{table.value} {start}-{start + count - 1}" for table, start, count in reads[:8])
        more = f" and {len(reads) - 8} more" if len(reads) > 8 else ""
        interval = tap.store.poll_interval(unit)
        every = f", about every {interval:.0f} s" if interval else ""
        model = f" Model: **{tap.models[unit]}**." if unit in tap.models else ""
        return f"The poller reads {blocks}{more}{every}.{model}"

    @staticmethod
    def _map_summary(community_map) -> str:
        entries = community_map.entries
        verified = sum(1 for e in entries if e.verified)
        documented = sum(1 for e in entries if e.documented)
        guessed = sum(1 for e in entries if e.guessed)
        return f"{community_map.manufacturer} {community_map.name}: {len(entries)} sensors ({documented} documented, {verified} verified, {guessed} guessed)"

    # --- Recordings -------------------------------------------------------------------

    async def async_step_recordings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        tap = self._tap
        if tap is None:
            return self.async_abort(reason="not_loaded")
        references = tap.reference_entity_ids()
        state = f"Recording now: **{tap.session.name}**." if tap.session else "Not recording."
        sources = (
            f"{len(references)} reference entities will be logged with each recording."
            if references
            else "No reference sources yet: recordings will only contain bus traffic. Set them under **Reference sources**."
        )
        return self.async_show_menu(
            step_id="recordings",
            menu_options=["recording_control", "recording_sources", "recording_files", "recording_analyse"],
            description_placeholders={"state": state, "sources": sources, "docs": f"{DOCS}/recordings.md"},
        )

    async def async_step_recording_control(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        tap = self._tap
        if tap is None:
            return self.async_abort(reason="not_loaded")
        if tap.session is not None:
            if user_input is not None:
                await tap.async_stop_recording()
                return self.async_abort(reason="recording_stopped")
            return self.async_show_form(
                step_id="recording_control", data_schema=probatio.Schema({}), description_placeholders={"name": tap.session.name, "references": ""}
            )
        references = tap.reference_entity_ids()
        if user_input is not None:
            await tap.async_start_recording(float(user_input[ATTR_HOURS]), references)
            return self.async_abort(reason="recording_started")
        schema = probatio.Schema(
            {
                probatio.Required(ATTR_HOURS, default=DEFAULT_RECORDING_HOURS): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.25, max=DEFAULT_RECORDING_HOURS, step=0.25, unit_of_measurement="h", mode=selector.NumberSelectorMode.BOX)
                )
            }
        )
        listed = ", ".join(f"`{e}`" for e in references[:10]) + (f" and {len(references) - 10} more" if len(references) > 10 else "")
        return self.async_show_form(
            step_id="recording_start",
            data_schema=schema,
            description_placeholders={"references": listed or "none (bus traffic only)"},
            last_step=True,
        )

    async def async_step_recording_start(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_recording_control(user_input)

    async def async_step_recording_sources(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        options = self.config_entry.options
        if user_input is not None:
            return self._save(**{**user_input, CONF_KEEP_RECORDINGS: int(user_input[CONF_KEEP_RECORDINGS])})
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_REFERENCE_DEVICES, default=options.get(CONF_REFERENCE_DEVICES, [])): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(multiple=True)
                ),
                probatio.Optional(CONF_REFERENCE_PATTERNS, default=options.get(CONF_REFERENCE_PATTERNS, [])): selector.TextSelector(
                    selector.TextSelectorConfig(multiple=True)
                ),
                probatio.Optional(CONF_REFERENCE_ENTITIES, default=options.get(CONF_REFERENCE_ENTITIES, [])): selector.EntitySelector(
                    selector.EntitySelectorConfig(multiple=True)
                ),
                probatio.Optional(CONF_KEEP_RECORDINGS, default=options.get(CONF_KEEP_RECORDINGS, DEFAULT_KEEP_RECORDINGS)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=200, mode=selector.NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id="recording_sources", data_schema=schema, description_placeholders={"docs": f"{DOCS}/recordings.md"})

    async def async_step_recording_files(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
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
        return self.async_show_form(step_id="recording_files", data_schema=schema, description_placeholders={"recordings": "\n".join(lines)})

    # --- Suggest a register map from a recording -------------------------------------

    async def async_step_recording_analyse(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        tap = self._tap
        if tap is None:
            return self.async_abort(reason="not_loaded")
        recordings = await tap.async_recordings()
        if not recordings:
            return self.async_abort(reason="no_recordings")
        if user_input is not None:
            self._unit = int(user_input[CONF_UNIT])
            self._analysis_task = self.hass.async_create_task(
                self._async_suggest(user_input[CONF_RECORDING], self._unit, user_input.get(CONF_AI_TASK)),
                eager_start=False,
            )
            return await self.async_step_analysing()
        units = self._known_units() or [1]
        ai_entities = ai_task_entities(self.hass)
        fields: dict[Any, Any] = {
            probatio.Required(CONF_RECORDING, default=recordings[0].name): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[info.name for info in recordings], mode=selector.SelectSelectorMode.DROPDOWN)
            ),
            probatio.Required(CONF_UNIT, default=str(units[0])): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[selector.SelectOptionDict(value=str(u), label=f"Unit {u}") for u in units])
            ),
        }
        if ai_entities:
            fields[probatio.Optional(CONF_AI_TASK)] = selector.EntitySelector(selector.EntitySelectorConfig(domain=AI_TASK_DOMAIN))
        return self.async_show_form(
            step_id="recording_analyse",
            data_schema=probatio.Schema(fields),
            description_placeholders={
                "ai": "" if ai_entities else "Tip: with an AI Task set up in Home Assistant (for example through OpenAI, Google Gemini, Anthropic or Ollama), an AI can refine the suggestion too.",
                "docs": f"{DOCS}/working-out-a-register-map.md",
            },
        )

    async def async_step_analysing(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._analysis_task.done():
            return self.async_show_progress(step_id="analysing", progress_action="analysing", progress_task=self._analysis_task)
        return self.async_show_progress_done(next_step_id="suggestion")

    async def _async_suggest(self, name: str, unit: int, ai_entity: str | None) -> None:
        """Work out the suggestion; the outcome goes to self._suggestion_result for the next screen."""
        tap = self._tap
        assert tap is not None
        current = tap.maps.get(unit, [])
        notes: list[str] = []
        try:
            analysis = await tap.async_analyse(name)
        except (OSError, ValueError) as err:
            self._suggestion_result = ("", [f"Couldn't read {name}: {err}"])
            return
        found = analysis.matches.get(unit, [])
        if found:
            on_values = sum(1 for m in found if m.correlation is None)
            notes.append(f"Matched **{len(found)}** registers to your reference entities" + (f" ({on_values} on a few values only)." if on_values else "."))
        elif not analysis.references:
            notes.append("This recording has no reference values, so there was nothing to match registers against. Set reference sources under **Reference sources and storage** and record again.")
        else:
            notes.append("No register clearly followed any of your reference entities.")
        if confirmed := analysis.confirmed(unit, current):
            notes.append(f"The recording backs up **{confirmed}** entries of the current map; those are left out below.")
        if analysis.references and analysis.reference_points < MIN_POINTS:
            notes.append(
                f"Your reference entities changed only about {analysis.reference_points} times in this recording, so matches rest on a few values and stay unverified. "
                "A recording of a few hours, while the sun and your appliances change things, gives stronger (verified) matches."
            )
        text = analysis.proposal_yaml(unit, current)
        if ai_entity:
            existing = yaml.safe_dump([to_core(e) for e in current], sort_keys=False, allow_unicode=True) if current else ""
            try:
                text = await async_refine(self.hass, ai_entity, analysis, unit, existing)
                notes.append(f"Refined by the AI (`{ai_entity}`). Check its entries before saving: it can be wrong.")
            except HomeAssistantError as err:
                notes.append(f"The AI couldn't help ({err}). Showing Modbus Tap's own matches.")
        self._suggestion_result = (text, notes)

    async def async_step_suggestion(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        unit = self._unit or 1
        text, notes = self._suggestion_result
        errors: dict[str, str] = {}
        error = ""
        if user_input is not None:
            try:
                parse_yaml(user_input.get(CONF_OVERRIDES, ""))
                units = dict(self.config_entry.options.get(CONF_UNITS, {}))
                current = dict(units.get(str(unit), {}))
                current[CONF_OVERRIDES] = merge_yaml(current.get(CONF_OVERRIDES, ""), user_input.get(CONF_OVERRIDES, ""))
                current.setdefault(CONF_COMMUNITY_MAP, None)
            except RegisterMapError as err:
                errors[CONF_OVERRIDES] = "invalid_map"
                error = str(err)
            else:
                units[str(unit)] = current
                return self._save(**{CONF_UNITS: units})
        if not text and user_input is None:
            return self.async_abort(reason="nothing_suggested", description_placeholders={"notes": "\n\n".join(notes)})
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_OVERRIDES, description={"suggested_value": user_input.get(CONF_OVERRIDES) if user_input else text}): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                )
            }
        )
        return self.async_show_form(
            step_id="suggestion",
            data_schema=schema,
            errors=errors,
            description_placeholders={"unit": str(unit), "notes": "\n\n".join(notes), "error": error},
        )

    # --- Writes -----------------------------------------------------------------------

    async def async_step_writes(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        tap = self._tap
        if tap is None:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            if user_input.get(CONF_CLEAR):
                await tap.async_clear_writes()
            return self.async_abort(reason="writes_cleared" if user_input.get(CONF_CLEAR) else "export_done")
        blocks = tap.writes.newest_first()
        if not blocks:
            return self.async_abort(reason="no_writes")
        rows = [
            "| Unit | Registers | Writes | Values seen | Last written |",
            "|---|---|---|---|---|",
            *(
                f"| {b.unit} | {b.table} {b.addresses}{self._names(tap, b)} | {b.total} | {b.distinct_values} | {_when(b.last)} |"
                for b in blocks[:WRITES_SHOWN]
            ),
        ]
        runs = sorted(((b, r) for b in blocks for r in b.runs), key=lambda item: item[1].first, reverse=True)[:CHANGES_SHOWN]
        changes = [
            f"- {_when(r.first)} · unit {b.unit} {b.table} {b.addresses} → `{_values(r.values)}`"
            + (f" ({r.outcome})" if r.outcome != "confirmed" else "")
            + (f", {r.count}× until {_when(r.last)}" if r.count > 1 else "")
            for b, r in runs
        ]
        more = f"\n\nShowing the {WRITES_SHOWN} most recently written of {len(blocks)}." if len(blocks) > WRITES_SHOWN else ""
        return self.async_show_form(
            step_id="writes",
            data_schema=probatio.Schema({probatio.Optional(CONF_CLEAR, default=False): selector.BooleanSelector()}),
            description_placeholders={
                "table": "\n".join(rows) + more,
                "changes": "\n".join(changes),
                "docs": f"{DOCS}/writes.md",
            },
        )

    @staticmethod
    def _names(tap: Tap, block) -> str:
        names = [
            e.name
            for e in tap.maps.get(block.unit, [])
            if e.table.value == block.table and block.start <= e.address < block.start + block.length
        ]
        return f" ({', '.join(names)})" if names else ""

    # --- Export ----------------------------------------------------------------------

    async def async_step_export(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        tap = self._tap
        if tap is None:
            return self.async_abort(reason="not_loaded")
        if user_input is not None:
            return self.async_abort(reason="export_done")
        if not any(tap.maps.values()):
            return self.async_abort(reason="nothing_to_export")
        text = core_modbus_yaml(tap.listener.host, tap.listener.port, tap.maps, {unit: tap.store.poll_interval(unit) for unit in tap.maps})
        return self.async_show_form(
            step_id="export", data_schema=probatio.Schema({}), description_placeholders={"yaml": text, "docs": f"{DOCS}/replacing-your-poller.md"}
        )

    # --- Advanced --------------------------------------------------------------------

    async def async_step_advanced(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(**user_input)
        schema = probatio.Schema(
            {
                probatio.Optional(CONF_WRITE_EVENTS, default=self.config_entry.options.get(CONF_WRITE_EVENTS, False)): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="advanced", data_schema=schema)
