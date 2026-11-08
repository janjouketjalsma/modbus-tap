import struct

import pytest

from tap.export import core_modbus_yaml
from tap.model import Table
from tap.register_map import MapEntry, RegisterMapError, apply_overrides, parse_yaml, to_core, with_unit
from tap.values import DataType, Swap, decode, scale_value


def regs_of(fmt, value):
    raw = struct.pack(">" + fmt, value)
    return [int.from_bytes(raw[i : i + 2], "big") for i in range(0, len(raw), 2)]


@pytest.mark.parametrize(
    "data_type,fmt,value",
    [
        (DataType.INT16, "h", -204),
        (DataType.UINT16, "H", 65332),
        (DataType.INT32, "i", -70000),
        (DataType.UINT32, "I", 70000),
        (DataType.INT64, "q", -(2**40)),
        (DataType.FLOAT32, "f", 1.5),
        (DataType.FLOAT64, "d", -2.25),
        (DataType.FLOAT16, "e", 0.5),
    ],
)
def test_decode_types(data_type, fmt, value):
    assert decode(data_type, regs_of(fmt, value)) == value


def test_swaps():
    assert decode(DataType.UINT32, [0x0002, 0x0001], Swap.WORD) == 0x00010002
    assert decode(DataType.UINT16, [0x3412], Swap.BYTE) == 0x1234
    assert decode(DataType.UINT32, [0x0200, 0x0100], Swap.WORD_BYTE) == 0x00010002


def test_string():
    assert decode(DataType.STRING, [0x5353, 0x452D, 0x4848, 0x364B, 0x2020]) == "SSE-HH6K"


def test_scaling_follows_core():
    assert scale_value(2344, integer_type=True, scale=0.1, precision=1) == 234.4
    assert scale_value(2344, integer_type=True, scale=0.1) == 234  # core: integers default to precision 0
    assert scale_value(1.23456, integer_type=False) == 1.23  # core: floats default to 2
    assert scale_value(0xFFFF, integer_type=True, nan_value=0xFFFF) is None
    assert scale_value(500, integer_type=True, max_value=100) == 100
    assert scale_value(1, integer_type=True, zero_suppress=2) == 0


CORE_SNIPPET = """
- name: Grid voltage
  address: 37
  input_type: input
  data_type: uint16
  scale: 0.1
  precision: 1
  unit_of_measurement: V
  device_class: voltage
  state_class: measurement
  scan_interval: 10
  documented: "Vendor protocol v1.2, table 3"
- name: Model
  address: 144
  input_type: input
  data_type: string
  count: 8
  model: true
- name: Holding default
  slave: 2
  address: 5
"""


def test_parse_core_snippet():
    parsed = parse_yaml(CORE_SNIPPET)
    volts, model, holding = parsed.entries
    assert volts.table is Table.INPUT and volts.documented and not volts.guessed
    assert model.model and model.size == 8
    assert holding.table is Table.HOLDING and holding.data_type is DataType.INT16 and holding.device_address == 2
    assert any("scan_interval" in notice for notice in parsed.notices)
    assert volts.value([2344]) == 234.4


def test_hub_style_yaml_is_accepted():
    assert len(parse_yaml("sensors:\n  - name: a\n    address: 1\n").entries) == 1


@pytest.mark.parametrize(
    "text,message",
    [
        ("name: x", "list"),
        ("- address: 3", "'name'"),
        ("- name: a", "'address'"),
        ("- name: a\n  address: 1\n  input_type: coil", "input_type"),
        ("- name: a\n  address: 1\n  data_type: custom", "custom"),
        ("- name: a\n  address: 1\n  slave_count: 2", "not supported"),
        ("- name: a\n  address: 1\n  data_type: string", "count"),
        ("- name: a\n  address: 1\n  bogus: 2", "unknown"),
        ("- name: a\n  address: 1\n- name: b\n  address: 1", "twice"),
        ("- name: a\n  address: [", "YAML"),
        ("- name: a\n  address: 1\n  model: true", "string"),
    ],
)
def test_errors(text, message):
    with pytest.raises(RegisterMapError, match=message):
        parse_yaml(text)


def test_overrides_replace_and_add():
    base = [MapEntry("Voltage", 37, table=Table.INPUT, scale=1.0), MapEntry("Freq", 46, table=Table.INPUT)]
    mine = [MapEntry("Grid voltage", 37, table=Table.INPUT, scale=0.1), MapEntry("Extra", 50, table=Table.INPUT)]
    merged = {e.name for e in apply_overrides(base, mine)}
    assert merged == {"Grid voltage", "Freq", "Extra"}


def test_with_unit_and_core_export():
    (entry,) = with_unit([MapEntry("Grid voltage", 37, table=Table.INPUT, scale=0.1, precision=1, documented="x")], 3)
    core = to_core(entry)
    assert core == {"name": "Grid voltage", "address": 37, "device_address": 3, "scale": 0.1, "precision": 1, "input_type": "input"}
    text = core_modbus_yaml("192.168.1.120", 8899, {3: [entry]}, {3: 21.4})
    assert "rtuovertcp" in text and "scan_interval: 21" in text and "documented" not in text
