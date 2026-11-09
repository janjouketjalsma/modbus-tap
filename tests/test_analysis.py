"""Suggesting a Register map from a Recording."""

import math

from tap.analysis import analyse
from tap.register_map import parse_yaml


def _recording(points: int = 40):
    """Unit 1 polls input 0-3 every 10 s; a reference sensor follows two of them."""
    records = [{"type": "header", "reference_entities": ["sensor.pv_power", "sensor.battery_power", "sensor.energy"]}]
    for i in range(points):
        t = 1000.0 + i * 10
        pv = int(1500 + 1200 * math.sin(i / 5))  # watts, raw = W
        battery = int(-800 + 60 * i)  # signed, raw = W / 10... crosses zero
        energy = 120_000 + i * 37  # 32-bit counter, 0.01 kWh
        voltage = 2300 + (i % 3)  # changes, no reference
        values = [
            pv,
            (battery // 10) & 0xFFFF,
            energy >> 16,
            energy & 0xFFFF,
            voltage,
            0x5353,  # "SS", constant
        ]
        records.append({"type": "transaction", "t": t, "unit": 1, "function": 4, "table": "input", "start": 0, "values": values, "outcome": "answered"})
        records.append({"type": "entity", "t": t + 1, "entity_id": "sensor.pv_power", "state": str(pv), "unit_of_measurement": "W", "device_class": "power", "friendly_name": "PV power"})
        records.append({"type": "entity", "t": t + 2, "entity_id": "sensor.battery_power", "state": str(battery // 10 * 10), "unit_of_measurement": "W", "device_class": "power", "friendly_name": "Battery power"})
        records.append({"type": "entity", "t": t + 3, "entity_id": "sensor.energy", "state": f"{energy / 100:.2f}", "unit_of_measurement": "kWh", "device_class": "energy", "friendly_name": "Energy today"})
    records.append({"type": "entity", "t": 9999, "entity_id": "sensor.pv_power", "state": "unavailable"})
    return records


def test_finds_registers_that_follow_reference_entities():
    result = analyse("r.jsonl.gz", _recording())
    by_entity = {m.entity_id: m for m in result.matches[1]}

    pv = by_entity["sensor.pv_power"]
    assert (pv.address, pv.data_type, pv.scale) == (0, "uint16", 1.0)

    battery = by_entity["sensor.battery_power"]
    assert (battery.address, battery.data_type, battery.scale) == (1, "int16", 10.0)

    energy = by_entity["sensor.energy"]
    assert (energy.address, energy.data_type, energy.swap, energy.scale) == (2, "uint32", "none", 0.01)


def test_proposal_is_a_valid_register_map():
    result = analyse("r.jsonl.gz", _recording())
    entries = parse_yaml(result.proposal_yaml(1)).entries
    names = {e.name for e in entries}
    assert names == {"PV power", "Battery power", "Energy today"}
    energy = next(e for e in entries if e.name == "Energy today")
    assert energy.precision == 2
    assert energy.state_class == "total_increasing"
    assert energy.verified


def test_few_reference_values_are_matched_on_value_but_not_verified():
    result = analyse("r.jsonl.gz", _recording(points=4))
    by_entity = {m.entity_id: m for m in result.matches[1]}
    pv = by_entity["sensor.pv_power"]
    assert (pv.address, pv.scale, pv.correlation) == (0, 1.0, None)
    assert all("verified" not in entry for entry in result.proposal(1))


def test_nothing_to_match_without_reference_values():
    records = [r for r in _recording() if r["type"] != "entity"]
    result = analyse("r.jsonl.gz", records)
    assert result.proposal_yaml(1) == ""


def test_summary_is_compact_json_with_text_and_references():
    import json

    result = analyse("r.jsonl.gz", _recording())
    data = json.loads(result.summary(1))
    assert {r["entity_id"] for r in data["reference_entities"]} == {"sensor.pv_power", "sensor.battery_power", "sensor.energy"}
    assert data["constant_registers"] == 2  # the text and the energy high word
    assert any(r["address"] == 4 for r in data["changing_registers"])
    assert len(result.summary(1, limit=1500)) <= 1500 or data["changing_registers"] == []


def test_merge_keeps_comments_when_nothing_is_replaced():
    from tap.register_map import merge_yaml

    existing = "# mine\n- name: A\n  address: 1\n"
    merged = merge_yaml(existing, "- name: B\n  address: 2\n")
    assert merged.startswith("# mine")
    assert [e.name for e in parse_yaml(merged).entries] == ["A", "B"]


def test_merge_replaces_entries_at_the_same_slot():
    from tap.register_map import merge_yaml

    merged = merge_yaml("- name: Old\n  address: 1\n  input_type: input\n- name: Keep\n  address: 2\n", "- name: New\n  address: 1\n  input_type: input\n")
    assert [e.name for e in parse_yaml(merged).entries] == ["Keep", "New"]
    assert merge_yaml("", "- name: B\n  address: 2\n") == "- name: B\n  address: 2\n"
    assert merge_yaml("- name: A\n  address: 1\n", "") == "- name: A\n  address: 1\n"


def test_entries_the_current_map_already_has_right_are_left_out():
    result = analyse("r.jsonl.gz", _recording())
    current = parse_yaml("- name: Solar\n  address: 0\n  input_type: input\n- name: Wrong\n  address: 1\n  input_type: input\n").entries
    assert result.confirmed(1, current) == 1
    names = [e.name for e in parse_yaml(result.proposal_yaml(1, current)).entries]
    assert names == ["Battery power", "Energy today"]  # address 1 had the wrong scale, so it's proposed
