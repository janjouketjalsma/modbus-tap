"""Ask Home Assistant's AI Task to refine a suggested Register map."""

from __future__ import annotations

import re

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .analysis import Analysis
from .register_map import RegisterMapError, parse_yaml

AI_TASK_DOMAIN = "ai_task"
FENCE = re.compile(r"^```[a-z]*\s*|\s*```$", re.MULTILINE)

INSTRUCTIONS = """\
You are helping map the registers of a Modbus device (unit {unit}) for Home Assistant.
Below is a JSON summary of a recording: the registers the device was polled for,
how their values moved, and reference entities (values from another source, such
as the manufacturer's cloud) logged at the same time. Cloud values can lag the bus
by several minutes. "matches_found_by_correlation" lists registers already matched
to a reference entity by Modbus Tap; keep them unless the data clearly contradicts them.

Return a register map in the Home Assistant Modbus sensor format: a YAML list, and
nothing else. Each entry has name, address, input_type (holding or input), and where
needed data_type (int16, uint16, int32, uint32, string), swap (word), count (for
strings), scale, precision, unit_of_measurement, device_class and state_class.
Add `verified: "<why>"` only to entries backed by a reference entity.
Only include registers you have real evidence for; leave the rest out.
The unit already has these entries, which you should not repeat:
{existing}

Recording summary:
{summary}
"""


def ai_task_entities(hass: HomeAssistant) -> list[str]:
    return hass.states.async_entity_ids(AI_TASK_DOMAIN)


async def async_refine(hass: HomeAssistant, entity_id: str, analysis: Analysis, unit: int, existing: str) -> str:
    """The AI's proposal as validated YAML. Raises HomeAssistantError on any failure."""
    from homeassistant.components.ai_task import async_generate_data  # noqa: PLC0415 (optional dependency)

    result = await async_generate_data(
        hass,
        task_name="Modbus Tap register map",
        entity_id=entity_id,
        instructions=INSTRUCTIONS.format(unit=unit, existing=existing.strip() or "(none)", summary=analysis.summary(unit)),
    )
    text = FENCE.sub("", str(result.data or "")).strip()
    try:
        if not parse_yaml(text).entries:
            raise HomeAssistantError("the AI returned no entries")
    except RegisterMapError as err:
        raise HomeAssistantError(f"the AI's answer isn't a valid register map ({err})") from err
    return text + "\n"
