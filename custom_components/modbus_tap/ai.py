"""Ask Home Assistant's AI Task to refine a suggested Register map."""

from __future__ import annotations

import re

import yaml

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .analysis import Analysis, vet
from .register_map import RegisterMapError, parse_yaml

AI_TASK_DOMAIN = "ai_task"
FENCE = re.compile(r"^```[a-z]*\s*|\s*```$", re.MULTILINE)

INSTRUCTIONS = """\
You are helping map the registers of a Modbus device (unit {unit}) for Home Assistant.
Below is a JSON summary of a recording: the registers the device was polled for,
how their values moved, and reference entities (values from another source, such
as the manufacturer's cloud) logged at the same time. Cloud values can lag the bus
by several minutes. "writes_by_the_poller" lists what the poller wrote; those
registers are usually settings, so name them as such if you can tell what they are.
"matches_found_by_correlation" lists registers already matched
to a reference entity by Modbus Tap; keep them unless the data clearly contradicts them.

Return a register map in the Home Assistant Modbus sensor format: a YAML list, and
nothing else. Each entry has name, address, input_type (holding or input), and where
needed data_type (int16, uint16, int32, uint32, string), swap (word), count (for
strings), scale, precision, unit_of_measurement, device_class and state_class.
Use only the scales devices use: 1, 0.1, 0.01, 0.001 or 10 (negative if the sign is
flipped). A register that only roughly follows a reference at some other factor is a
different quantity; leave it out. Don't add `verified`; Modbus Tap adds it where the
recording backs an entry up.
Only include registers you have real evidence for; leave the rest out.
The unit already has these entries, which you should not repeat:
{existing}

Recording summary:
{summary}
"""


def ai_task_entities(hass: HomeAssistant) -> list[str]:
    return hass.states.async_entity_ids(AI_TASK_DOMAIN)


async def async_refine(hass: HomeAssistant, entity_id: str, analysis: Analysis, unit: int, existing: str) -> tuple[str, list[str]]:
    """The AI's proposal as checked YAML, and notes on what was changed. Raises HomeAssistantError on any failure."""
    from homeassistant.components.ai_task import async_generate_data  # noqa: PLC0415 (optional dependency)

    result = await async_generate_data(
        hass,
        task_name="Modbus Tap register map",
        entity_id=entity_id,
        instructions=INSTRUCTIONS.format(unit=unit, existing=existing.strip() or "(none)", summary=analysis.summary(unit)),
    )
    text = FENCE.sub("", str(result.data or "")).strip()
    try:
        parse_yaml(text)
        entries, notes = vet(yaml.safe_load(text) or [], analysis, unit)
        if not entries:
            raise HomeAssistantError(" ".join(notes) or "the AI returned no entries")
    except (RegisterMapError, yaml.YAMLError, AttributeError) as err:
        raise HomeAssistantError(f"the AI's answer isn't a valid register map ({err})") from err
    return yaml.safe_dump(entries, sort_keys=False, allow_unicode=True), notes
