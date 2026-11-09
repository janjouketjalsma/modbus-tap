"""Modbus Tap: listen in on a Modbus RTU bus and turn what goes past into sensors."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.hass_dict import HassKey

from .community import CommunityMap, load_maps
from .const import CONF_UNITS, DOMAIN
from .download import RecordingDownloadView
from .services import async_setup_services
from .tap import Tap

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
COMMUNITY_MAPS: HassKey[dict[str, CommunityMap]] = HassKey(f"{DOMAIN}_community_maps")

type TapConfigEntry = ConfigEntry[Tap]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data[COMMUNITY_MAPS] = await hass.async_add_executor_job(load_maps)
    hass.http.register_view(RecordingDownloadView)
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: TapConfigEntry) -> bool:
    tap = Tap(hass, entry, hass.data[COMMUNITY_MAPS])
    entry.runtime_data = tap
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    tap.start()  # after the platforms, so entities hear the first frames
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: TapConfigEntry) -> None:
    """Reload only when register maps change; other options are read live, so a running recording survives."""
    if dict(entry.options.get(CONF_UNITS, {})) != entry.runtime_data.units_config:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TapConfigEntry) -> bool:
    await entry.runtime_data.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
