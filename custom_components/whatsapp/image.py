"""QR code for linking the WhatsApp account."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import WhatsAppEntity
from .runtime import WhatsAppConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WhatsAppConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([WhatsAppQrImage(hass, entry)])


class WhatsAppQrImage(WhatsAppEntity, ImageEntity):
    """Available only while the bridge waits for the QR code to be scanned."""

    _attr_content_type = "image/png"

    def __init__(self, hass: HomeAssistant, entry: WhatsAppConfigEntry) -> None:
        WhatsAppEntity.__init__(self, entry, "qr_code")
        ImageEntity.__init__(self, hass)

    @property
    def available(self) -> bool:
        return self.data.state == "qr" and self.data.qr_png is not None

    @property
    def image_last_updated(self) -> datetime | None:
        # A new timestamp makes the frontend fetch the new code.
        return self.data.qr_updated

    async def async_image(self) -> bytes | None:
        return self.data.qr_png
