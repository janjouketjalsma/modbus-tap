"""Home Assistant tests; run in CI with pytest-homeassistant-custom-component."""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.util import dt as dt_util

from custom_components.modbus_tap.const import (
    CONF_COMMUNITY_MAP,
    CONF_OVERRIDES,
    CONF_UNITS,
    CONF_WRITE_EVENTS,
    DOMAIN,
    EVENT_WRITE,
)
from custom_components.modbus_tap.rtu import with_crc


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations, socket_enabled):
    yield


def read_pair(unit: int, function: int, start: int, values: list[int]) -> bytes:
    request = with_crc(bytes([unit, function, start >> 8, start & 0xFF, 0, len(values)]))
    payload = b"".join(v.to_bytes(2, "big") for v in values)
    return request + with_crc(bytes([unit, function, len(payload)]) + payload)


MODEL = [0x5353, 0x452D, 0x4848, 0x364B, 0x2D50, 0x312D, 0x4555, 0x2020]  # "SSE-HH6K-P1-EU  "
POLL = read_pair(1, 4, 37, [2344] + [0] * 9 + [65332]) + read_pair(1, 4, 144, MODEL)


class FakeBridge:
    """A TCP server standing in for the Elfin; records anything sent to it."""

    def __init__(self) -> None:
        self.writers: list[asyncio.StreamWriter] = []
        self.received = bytearray()
        self.server: asyncio.Server | None = None

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def _handle(self, reader, writer) -> None:
        self.writers.append(writer)
        self.received.extend(await reader.read())
        writer.close()

    async def send(self, data: bytes) -> None:
        for _ in range(100):
            if self.writers:
                break
            await asyncio.sleep(0.02)
        self.writers[-1].write(data)
        await self.writers[-1].drain()

    async def stop(self) -> None:
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()


async def wait_for(condition, tries: int = 150) -> bool:
    for _ in range(tries):
        if condition():
            return True
        await asyncio.sleep(0.02)
    return False


async def setup_entry(hass: HomeAssistant, port: int, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"127.0.0.1:{port}",
        unique_id=f"127.0.0.1:{port}",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: port},
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_community_map_sensors_devices_and_listen_only(hass: HomeAssistant) -> None:
    bridge = FakeBridge()
    port = await bridge.start()
    units = {"1": {CONF_COMMUNITY_MAP: "sosen_sse_hh6k", CONF_OVERRIDES: "- name: Grid power\n  address: 47\n  input_type: input\n  data_type: int16\n  unit_of_measurement: W\n"}}
    entry = await setup_entry(hass, port, **{CONF_UNITS: units})
    await bridge.send(POLL)

    entities = er.async_get(hass)
    voltage = entities.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_1_input_37_uint16")
    power = entities.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_1_input_47_int16")
    assert voltage and power
    assert await wait_for(lambda: hass.states.get(voltage).state not in ("unknown", "unavailable"))
    assert float(hass.states.get(voltage).state) == pytest.approx(234.4)
    assert int(hass.states.get(power).state) == -204
    assert hass.states.get(voltage).attributes["map_status"] == "guessed"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    devices = dr.async_get(hass)
    unit = devices.async_get_device_by_identifier((DOMAIN, f"{entry.entry_id}_unit_1"), entry.entry_id)
    bridge_device = devices.async_get_device_by_identifier((DOMAIN, f"{entry.entry_id}_bridge"), entry.entry_id)
    assert unit is not None and unit.model == "SSE-HH6K-P1-EU"
    assert unit.via_device_id == bridge_device.id

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await bridge.stop()
    assert bytes(bridge.received) == b""  # ADR 0001: never transmits


async def test_suggests_community_map(hass: HomeAssistant) -> None:
    bridge = FakeBridge()
    entry = await setup_entry(hass, await bridge.start())
    await bridge.send(POLL)
    await asyncio.sleep(0.2)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_suggest_map_1")
    assert issue is not None and issue.is_fixable
    assert await hass.config_entries.async_unload(entry.entry_id)
    await bridge.stop()


async def test_undecodable_bus_raises_a_repair(hass: HomeAssistant) -> None:
    bridge = FakeBridge()
    entry = await setup_entry(hass, await bridge.start())
    await bridge.send(bytes([0x7F, 0xDF, 0xF1, 0xFE, 0xFD]) * 600)
    await asyncio.sleep(0.2)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_undecodable") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await bridge.stop()


async def test_write_events(hass: HomeAssistant) -> None:
    bridge = FakeBridge()
    entry = await setup_entry(hass, await bridge.start(), **{CONF_WRITE_EVENTS: True})
    events = []
    hass.bus.async_listen(EVENT_WRITE, events.append)
    clock = [26, 11, 8, 21, 11, 7]
    payload = b"".join(v.to_bytes(2, "big") for v in clock)
    write = with_crc(bytes([1, 16, 0x08, 0x06, 0, 6, 12]) + payload) + with_crc(bytes([1, 16, 0x08, 0x06, 0, 6]))
    await bridge.send(write)
    assert await wait_for(lambda: events)
    assert events[0].data["outcome"] == "confirmed" and events[0].data["values"] == clock
    assert await hass.config_entries.async_unload(entry.entry_id)
    await bridge.stop()


async def test_recording_with_reference_entity_and_note(hass: HomeAssistant, hass_client) -> None:
    bridge = FakeBridge()
    entry = await setup_entry(hass, await bridge.start())
    hass.states.async_set("sensor.pv_power", "2100", {"unit_of_measurement": "W"})
    response = await hass.services.async_call(
        DOMAIN, "start_recording", {"config_entry": entry.entry_id, "reference_entities": ["sensor.pv_power"]}, blocking=True, return_response=True
    )
    name = response["recording"]
    await bridge.send(POLL)
    await asyncio.sleep(0.2)
    hass.states.async_set("sensor.pv_power", "2200", {"unit_of_measurement": "W"})
    await hass.services.async_call(DOMAIN, "add_note", {"config_entry": entry.entry_id, "text": "kettle on"}, blocking=True)
    await hass.services.async_call(DOMAIN, "stop_recording", {"config_entry": entry.entry_id}, blocking=True)

    tap = entry.runtime_data
    path = tap.library.directory / name
    lines = [json.loads(line) for line in gzip.open(path, "rt") if line.strip()]
    kinds = [line["type"] for line in lines]
    assert kinds[0] == "header" and kinds[-1] == "end"
    assert "transaction" in kinds and "note" in kinds
    assert [line["state"] for line in lines if line["type"] == "entity"] == ["2100", "2200"]

    client = await hass_client()
    download = await client.get(tap.download_url(name))
    assert download.status == 200
    assert gzip.decompress(await download.read()).startswith(b'{"type":"header"')
    missing = await client.get(f"/api/modbus_tap/recordings/{entry.entry_id}/..%2Fsecrets.yaml")
    assert missing.status in (400, 404)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await bridge.stop()


async def test_config_flow_and_reconfigure(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch("custom_components.modbus_tap.config_flow._can_connect", return_value=False):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "192.168.1.120", CONF_PORT: 8899})
    assert result["errors"] == {"base": "cannot_connect"}
    with (
        patch("custom_components.modbus_tap.config_flow._can_connect", return_value=True),
        patch("custom_components.modbus_tap.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "192.168.1.120", CONF_PORT: 8899})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        entry = result["result"]
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "192.168.1.121", CONF_PORT: 8899})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.168.1.121"


async def test_options_unit_map_validates_and_exports(hass: HomeAssistant) -> None:
    bridge = FakeBridge()
    entry = await setup_entry(hass, await bridge.start())
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "pick_unit"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"unit": "1"})
    assert result["step_id"] == "unit_map"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_COMMUNITY_MAP: "none", CONF_OVERRIDES: "- name: x"})
    assert result["errors"] == {CONF_OVERRIDES: "invalid_map"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_COMMUNITY_MAP: "chint_ddsu666", CONF_OVERRIDES: ""})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_UNITS]["1"][CONF_COMMUNITY_MAP] == "chint_ddsu666"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "export"})
    assert result["step_id"] == "export"
    assert "rtuovertcp" in result["description_placeholders"]["yaml"]
    assert await hass.config_entries.async_unload(entry.entry_id)
    await bridge.stop()
