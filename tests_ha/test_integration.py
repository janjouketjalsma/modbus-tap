"""Home Assistant tests (run in CI with pytest-homeassistant-custom-component)."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.modbus_tap.const import CONF_RAW_SENSORS, CONF_REGISTER_MAP, DOMAIN
from custom_components.modbus_tap.rtu import crc16

MAP = """
- name: Grid voltage
  address: 37
  scale: 0.1
  precision: 1
  unit_of_measurement: V
  device_class: voltage
  state_class: measurement
- name: Power
  address: 38
  data_type: int16
  unit_of_measurement: W
  device_class: power
"""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def frame(*body: int) -> bytes:
    data = bytes(body)
    crc = crc16(data)
    return data + bytes([crc & 0xFF, crc >> 8])


def poll(volts: int, watts: int) -> bytes:
    w = watts & 0xFFFF
    return frame(1, 4, 0, 37, 0, 2) + frame(1, 4, 4, volts >> 8, volts & 0xFF, w >> 8, w & 0xFF)


async def _wait_for(cond, tries=150):
    for _ in range(tries):
        if cond():
            return True
        await asyncio.sleep(0.02)
    return False


async def test_sensors_from_sniffed_traffic(hass: HomeAssistant) -> None:
    writers = []
    received = bytearray()

    async def handle(reader, writer):
        writers.append(writer)
        try:
            received.extend(await reader.read())  # returns when the client disconnects
        except ConnectionError:
            pass

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"127.0.0.1:{port}",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: port},
        options={CONF_RAW_SENSORS: True, CONF_REGISTER_MAP: MAP},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await _wait_for(lambda: writers)
    writers[0].write(poll(2344, -204))
    await writers[0].drain()

    reg = er.async_get(hass)
    volt_id = reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_map_1_input_37_uint16")
    power_id = reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_map_1_input_38_int16")
    assert volt_id and power_id

    def ready():
        state = hass.states.get(volt_id)
        return state is not None and state.state not in ("unknown", "unavailable")

    assert await _wait_for(ready)
    assert float(hass.states.get(volt_id).state) == pytest.approx(234.4)
    assert hass.states.get(volt_id).attributes["unit_of_measurement"] == "V"
    assert int(hass.states.get(power_id).state) == -204

    # A raw sensor is registered for every sniffed register, disabled by default.
    raw_id = reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_raw_1_input_37")
    assert raw_id is not None
    assert reg.async_get(raw_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION

    writers[0].write(poll(2350, 10))
    await writers[0].drain()
    assert await _wait_for(lambda: hass.states.get(volt_id).state == "235.0")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    server.close()
    await server.wait_closed()
    assert bytes(received) == b""  # the integration never transmits on the bus


async def test_config_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    with patch("custom_components.modbus_tap.config_flow._can_connect", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.1.120", CONF_PORT: 8899}
        )
    assert result["errors"] == {"base": "cannot_connect"}

    with (
        patch("custom_components.modbus_tap.config_flow._can_connect", return_value=True),
        patch("custom_components.modbus_tap.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.1.120", CONF_PORT: 8899}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: "192.168.1.120", CONF_PORT: 8899}


async def test_options_flow_rejects_bad_map(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.168.1.120", CONF_PORT: 8899},
        options={CONF_RAW_SENSORS: True, CONF_REGISTER_MAP: ""},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.modbus_tap.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_RAW_SENSORS: True, CONF_REGISTER_MAP: "- name: x"}
        )
        assert result["errors"] == {CONF_REGISTER_MAP: "invalid_map"}
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_RAW_SENSORS: False, CONF_REGISTER_MAP: MAP}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_REGISTER_MAP] == MAP
