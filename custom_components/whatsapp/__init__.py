"""The WhatsApp integration."""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .client import WhatsAppBridge
from .const import (
    CONF_HOST,
    CONF_OWN_MESSAGES,
    CONF_TOKEN,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
    EVENT_POLL_VOTE_RECEIVED,
    OWN_MESSAGES_ALL,
    OWN_MESSAGES_OFF,
    OWN_MESSAGES_SELF,
)
from .runtime import WhatsAppConfigEntry, WhatsAppData, signal_update
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.SENSOR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the WhatsApp component."""
    async_setup_services(hass)
    return True


def _qr_png(data: str) -> bytes:
    """Render the pairing QR code (CPU work, run in the executor)."""
    import qrcode  # heavy (Pillow), only needed while pairing

    buffer = io.BytesIO()
    qrcode.make(data).save(buffer, format="PNG")
    return buffer.getvalue()


def _wanted(entry: WhatsAppConfigEntry, message: dict[str, Any]) -> bool:
    """Apply the "own messages" option; messages from others always pass."""
    if not message.get("fromMe"):
        return True
    mode = entry.options.get(CONF_OWN_MESSAGES, OWN_MESSAGES_OFF)
    if mode == OWN_MESSAGES_ALL:
        return True
    return mode == OWN_MESSAGES_SELF and bool(message.get("to_self"))


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

    @callback
    def updated() -> None:
        async_dispatcher_send(hass, signal_update(entry))

    @callback
    def device_id() -> str | None:
        device = dr.async_get(hass).async_get_device_by_identifier(
            (DOMAIN, entry.entry_id), entry.entry_id
        )
        return device.id if device else None

    async def on_frame(frame: dict[str, Any]) -> None:
        data = entry.runtime_data
        frame_type = frame.get("type")
        if frame_type in ("message", "poll_vote"):
            payload = frame.get("data", {})
            if frame_type == "message" and not _wanted(entry, payload):
                return
            # device_id lets device triggers tell bridges apart.
            payload = {**payload, "device_id": device_id()}
            hass.bus.async_fire(
                EVENT_MESSAGE_RECEIVED
                if frame_type == "message"
                else EVENT_POLL_VOTE_RECEIVED,
                payload,
            )
        elif frame_type == "qr":
            data.qr_png = await hass.async_add_executor_job(_qr_png, frame["data"])
            data.qr_updated = dt_util.utcnow()
            png = base64.b64encode(data.qr_png).decode()
            persistent_notification.async_create(
                hass,
                "Scan this QR code with WhatsApp (Settings → Linked devices) "
                "to link your account. It is also shown by the QR code entity."
                f"\n\n![QR Code](data:image/png;base64,{png})",
                "WhatsApp: link your account",
                notification_id,
            )
            updated()
        elif frame_type == "status":
            previous = data.status.get("status")
            data.status = {k: v for k, v in frame.items() if k != "type"}
            status = data.status.get("status")
            if status != previous:
                _LOGGER.info("WhatsApp bridge status: %s", status)
            if status != "qr":
                data.qr_png = None
                persistent_notification.async_dismiss(hass, notification_id)
            updated()
        elif frame_type == "hello":
            updated()

    bridge = WhatsAppBridge(
        hass,
        entry.data[CONF_HOST],
        token,
        on_frame,
        on_auth_failed=lambda: entry.async_start_reauth(hass),
        on_connection=lambda connected: updated(),
    )
    entry.runtime_data = WhatsAppData(bridge=bridge)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_create_background_task(hass, bridge.run(), "whatsapp_bridge")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WhatsAppConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.bridge.stop()
    return unloaded
