"""Repairs: bus health hints and Community map suggestions."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .community import CommunityMap
from .const import DOMAIN, TAPPING_GUIDE
from .hints import BusProblem


def _bus_issue_id(entry: ConfigEntry, problem: BusProblem) -> str:
    return f"{entry.entry_id}_{problem.value}"


def suggestion_issue_id(entry: ConfigEntry, unit: int) -> str:
    return f"{entry.entry_id}_suggest_map_{unit}"


@callback
def show_bus_problem(hass: HomeAssistant, entry: ConfigEntry, problem: BusProblem | None) -> None:
    """Raise the issue for `problem` and clear the others."""
    for candidate in BusProblem:
        issue_id = _bus_issue_id(entry, candidate)
        if candidate is problem:
            ir.async_create_issue(
                hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=candidate.value,
                translation_placeholders={"title": entry.title},
                learn_more_url=f"{TAPPING_GUIDE}#troubleshooting",
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, issue_id)


@callback
def suggest_map(hass: HomeAssistant, entry: ConfigEntry, unit: int, community_map: CommunityMap) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        suggestion_issue_id(entry, unit),
        data={"entry_id": entry.entry_id, "unit": unit, "map_id": community_map.id},
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="suggest_map",
        translation_placeholders={"unit": str(unit), "map": community_map.name, "title": entry.title},
    )
