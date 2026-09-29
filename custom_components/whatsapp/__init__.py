"""The WhatsApp integration."""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .client import WhatsAppBridge
from .const import (
    CONF_HOST,
    CONF_TOKEN,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    EVENT_POLL_VOTE_RECEIVED,
)
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = []

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type WhatsAppConfigEntry = ConfigEntry[WhatsAppBridge]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the WhatsApp component."""
    async_setup_services(hass)
    return True


def _qr_png_base64(data: str) -> str:
    """Render the pairing QR code (CPU work, run in the executor)."""
    import qrcode  # heavy (Pillow), only needed while pairing

    buffer = io.BytesIO()
    qrcode.make(data).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


async def async_setup_entry(hass: HomeAssistant, entry: WhatsAppConfigEntry) -> bool:
    """Set up WhatsApp from a config entry."""
    if entry.unique_id is None:
        # Entries from before the one-bridge-per-instance unique id.
        hass.config_entries.async_update_entry(entry, unique_id=DOMAIN)

    token = entry.data.get(CONF_TOKEN)
    if not token:
        # Entries from before the bridge required a token.
        raise ConfigEntryAuthFailed("The WhatsApp bridge now requires an access token")

    notification_id = f"whatsapp_qr_{entry.entry_id}"

    async def on_frame(frame: dict[str, Any]) -> None:
        frame_type = frame.get("type")
        if frame_type == "message":
            hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, frame.get("data", {}))
        elif frame_type == "poll_vote":
            hass.bus.async_fire(EVENT_POLL_VOTE_RECEIVED, frame.get("data", {}))
        elif frame_type == "qr":
            png = await hass.async_add_executor_job(_qr_png_base64, frame["data"])
            persistent_notification.async_create(
                hass,
                "Scan this QR code with WhatsApp (Settings → Linked devices) "
                f"to link your account.\n\n![QR Code](data:image/png;base64,{png})",
                "WhatsApp: link your account",
                notification_id,
            )
        elif frame_type == "status":
            _LOGGER.info("WhatsApp bridge status: %s", frame.get("status"))
            if frame.get("status") in ("authenticated", "ready"):
                persistent_notification.async_dismiss(hass, notification_id)

    bridge = WhatsAppBridge(
        hass,
        entry.data[CONF_HOST],
        token,
        on_frame,
        on_auth_failed=lambda: entry.async_start_reauth(hass),
    )
    entry.runtime_data = bridge
    entry.async_create_background_task(hass, bridge.run(), "whatsapp_bridge")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WhatsAppConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.stop()
    return True
