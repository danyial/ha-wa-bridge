"""Notify entity: send to the default chat."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import BridgeError
from .const import CONF_DEFAULT_CHAT
from .entity import WhatsAppEntity
from .runtime import WhatsAppConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WhatsAppConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([WhatsAppNotify(entry)])


def format_message(message: str, title: str | None) -> str:
    """WhatsApp has no title; put it in bold on the first line."""
    return f"*{title}*\n{message}" if title else message


class WhatsAppNotify(WhatsAppEntity, NotifyEntity):
    """notify.send_message to the chat set in the integration options."""

    _attr_name = None  # the device name: notify.whatsapp

    def __init__(self, entry: WhatsAppConfigEntry) -> None:
        super().__init__(entry, "notify")

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        chat_id = self._entry.options.get(CONF_DEFAULT_CHAT)
        if not chat_id:
            raise ServiceValidationError(
                "No default chat set; set one in the WhatsApp integration options "
                "or use whatsapp.send_message"
            )
        target = (
            {"group_id": chat_id} if chat_id.endswith("@g.us") else {"number": chat_id}
        )
        try:
            await self.data.bridge.request(
                {
                    "type": "send_message",
                    **target,
                    "message": format_message(message, title),
                }
            )
        except BridgeError as err:
            raise HomeAssistantError(f"WhatsApp: {err}") from err
