"""Config and options flow for Modbus Tap."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_RAW_SENSORS, CONF_REGISTER_MAP, CONNECT_TIMEOUT, DEFAULT_PORT, DOMAIN
from .regmap import RegisterMapError, parse_register_map

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
    }
)


async def _can_connect(host: str, port: int) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), CONNECT_TIMEOUT)
    except (OSError, TimeoutError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return True


class ModbusSnifferConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the bridge's address."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]
            self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})
            if await _can_connect(host, port):
                return self.async_create_entry(
                    title=f"{host}:{port}",
                    data={CONF_HOST: host, CONF_PORT: port},
                    options={CONF_RAW_SENSORS: True, CONF_REGISTER_MAP: ""},
                )
            errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return ModbusSnifferOptionsFlow()


class ModbusSnifferOptionsFlow(OptionsFlow):
    """Edit the register map and the raw-sensor setting."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            try:
                parse_register_map(user_input.get(CONF_REGISTER_MAP, ""))
            except RegisterMapError as err:
                errors[CONF_REGISTER_MAP] = "invalid_map"
                placeholders["error"] = str(err)
            else:
                return self.async_create_entry(data=user_input)

        current = user_input or self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_RAW_SENSORS, default=current.get(CONF_RAW_SENSORS, True)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_REGISTER_MAP,
                    description={"suggested_value": current.get(CONF_REGISTER_MAP, "")},
                ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors, description_placeholders=placeholders
        )
