"""Download Recordings from the browser (links are signed, see Tap.download_url)."""

from __future__ import annotations

from http import HTTPStatus

from aiohttp.hdrs import CONTENT_DISPOSITION
from aiohttp.web import FileResponse, Request, Response

from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .const import DOMAIN


class RecordingDownloadView(HomeAssistantView):
    url = "/api/modbus_tap/recordings/{entry_id}/{name}"
    name = "api:modbus_tap:recording"

    async def get(self, request: Request, entry_id: str, name: str) -> FileResponse | Response:
        hass = request.app[KEY_HASS]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            return Response(status=HTTPStatus.NOT_FOUND)
        path = await hass.async_add_executor_job(entry.runtime_data.library.path_of, name)
        if path is None:
            return Response(status=HTTPStatus.NOT_FOUND)
        return FileResponse(path, headers={CONTENT_DISPOSITION: f'attachment; filename="{name}"'})
