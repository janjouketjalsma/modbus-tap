import pytest

from msn import regmap

EXAMPLE = """
- name: Grid voltage
  address: 37
  scale: 0.1
  precision: 1
  unit_of_measurement: V
  device_class: voltage
  state_class: measurement
- name: Grid power
  address: 43
  data_type: int16
  unit_of_measurement: W
- name: Model
  address: 144
  data_type: string
  count: 8
- name: Clock year
  table: holding
  address: 2054
"""


def test_parse_example():
    regs = regmap.parse_register_map(EXAMPLE)
    assert [r.name for r in regs] == ["Grid voltage", "Grid power", "Model", "Clock year"]
    assert regs[0].keys == [(1, "input", 37)]
    assert regs[2].span == 8 and regs[2].keys[-1] == (1, "input", 151)
    assert regs[3].table == "holding"


def test_scaling():
    v, p = regmap.parse_register_map(EXAMPLE)[:2]
    assert regmap.scaled_value(v, 2344) == 234.4
    assert regmap.scaled_value(p, -204) == -204
    assert isinstance(regmap.scaled_value(p, -204), int)


@pytest.mark.parametrize(
    "text,msg",
    [
        ("name: x", "list"),
        ("- address: 3", "'name'"),
        ("- name: a", "'address'"),
        ("- name: a\n  address: 1\n  table: foo", "table"),
        ("- name: a\n  address: 1\n  data_type: float", "data_type"),
        ("- name: a\n  address: 1\n  bogus: 2", "unknown key"),
        ("- name: a\n  address: 1\n- name: b\n  address: 1", "twice"),
        ("- name: a\n  address: [", "YAML"),
    ],
)
def test_errors(text, msg):
    with pytest.raises(regmap.RegisterMapError, match=msg):
        regmap.parse_register_map(text)


def test_empty():
    assert regmap.parse_register_map("") == []
    assert regmap.parse_register_map("   \n") == []
