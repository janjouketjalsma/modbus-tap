"""Download Recordings from the browser (links are signed, see Tap.download_url).

The view checks authentication itself instead of leaving it to Home Assistant,
so an expired link gets a page that says what happened and where to get a
fresh one, rather than a bare "401: Unauthorized".
"""

from __future__ import annotations

from http import HTTPStatus

from aiohttp.hdrs import CONTENT_DISPOSITION
from aiohttp.web import FileResponse, Request, Response

from homeassistant.components.http import KEY_AUTHENTICATED, KEY_HASS, HomeAssistantView

from .const import DOMAIN

EXPIRED_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Link expired · Modbus Tap</title>
<style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem;line-height:1.5;color:#1c1c1c;background:#fff}
@media (prefers-color-scheme:dark){body{color:#e1e1e1;background:#111}a{color:#6ab0ff}}</style></head>
<body><h1>This download link has expired</h1>
<p>Download links for recordings work for 24 hours, and stop working when Home Assistant restarts.
The recording itself is still there.</p>
<p>For a fresh link: <a href="/config/integrations/integration/modbus_tap">Modbus Tap</a> → <b>Configure</b> →
<b>Recordings</b> → <b>Download or delete recordings</b>.</p></body></html>"""


class RecordingDownloadView(HomeAssistantView):
    url = "/api/modbus_tap/recordings/{entry_id}/{name}"
    name = "api:modbus_tap:recording"
    requires_auth = False  # checked below, to explain expired links

    async def get(self, request: Request, entry_id: str, name: str) -> FileResponse | Response:
        if not request.get(KEY_AUTHENTICATED, False):
            return Response(status=HTTPStatus.FORBIDDEN, text=EXPIRED_PAGE, content_type="text/html")
        hass = request.app[KEY_HASS]
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
            return Response(status=HTTPStatus.NOT_FOUND)
        path = await hass.async_add_executor_job(entry.runtime_data.library.path_of, name)
        if path is None:
            return Response(status=HTTPStatus.NOT_FOUND)
        return FileResponse(path, headers={CONTENT_DISPOSITION: f'attachment; filename="{name}"'})
