"""Base entity for WhatsApp."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .runtime import WhatsAppConfigEntry, WhatsAppData, signal_update


class WhatsAppEntity(Entity):
    """One device per bridge; entities refresh on every bridge update."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: WhatsAppConfigEntry, key: str) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="WhatsApp",
            manufacturer="WhatsApp Web",
            model="wa-bridge (whatsapp-web.js)",
        )

    @property
    def data(self) -> WhatsAppData:
        return self._entry.runtime_data

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._entry), self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
