"""Load media for outgoing messages from a URL or a local path."""

from __future__ import annotations

import base64
import mimetypes
import os
from typing import Any
from urllib.parse import unquote, urlparse

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import MAX_MEDIA_BYTES, MEDIA_FETCH_TIMEOUT


def _guess_type(name: str) -> str | None:
    # The first call reads the system MIME database from disk.
    return mimetypes.guess_type(name)[0]


def _read_file(path: str) -> bytes:
    if os.path.getsize(path) > MAX_MEDIA_BYTES:
        raise ServiceValidationError(f"{path} is larger than {MAX_MEDIA_BYTES} bytes")
    with open(path, "rb") as file:
        return file.read()


async def _fetch(hass: HomeAssistant, url: str) -> tuple[bytes, str | None]:
    # Any http(s) URL is allowed on purpose: cameras and other LAN devices are
    # the main use case. Only an admin can write automations that call this.
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=MEDIA_FETCH_TIMEOUT)
        ) as response:
            response.raise_for_status()
            if (response.content_length or 0) > MAX_MEDIA_BYTES:
                raise HomeAssistantError(
                    f"{url} is larger than {MAX_MEDIA_BYTES} bytes"
                )
            content = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_MEDIA_BYTES:
                    raise HomeAssistantError(
                        f"{url} is larger than {MAX_MEDIA_BYTES} bytes"
                    )
            mimetype = response.headers.get("Content-Type", "").split(";")[0].strip()
            return bytes(content), mimetype or None
    except (aiohttp.ClientError, TimeoutError) as err:
        raise HomeAssistantError(f"Could not download {url}: {err}") from err


async def async_load_media(
    hass: HomeAssistant, media_url: str | None, media_path: str | None
) -> dict[str, Any] | None:
    """Return the bridge's media payload, or None if neither is given."""
    if media_url:
        parsed = urlparse(media_url)
        if parsed.scheme not in ("http", "https"):
            raise ServiceValidationError("media_url must be an http(s) URL")
        content, mimetype = await _fetch(hass, media_url)
        filename = os.path.basename(unquote(parsed.path)) or "media"
    elif media_path:
        if not hass.config.is_allowed_path(media_path):
            raise ServiceValidationError(
                f"{media_path} is not in allowlist_external_dirs"
            )
        try:
            content = await hass.async_add_executor_job(_read_file, media_path)
        except OSError as err:
            raise HomeAssistantError(f"Could not read {media_path}: {err}") from err
        mimetype = None
        filename = os.path.basename(media_path)
    else:
        return None
    if not mimetype:
        mimetype = await hass.async_add_executor_job(_guess_type, filename)
    return {
        "mimetype": mimetype or "application/octet-stream",
        "data": base64.b64encode(content).decode(),
        "filename": filename,
    }
