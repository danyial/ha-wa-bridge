"""Restart and log-out buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .client import BridgeError
from .entity import WhatsAppEntity
from .runtime import WhatsAppConfigEntry

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WhatsAppConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [WhatsAppButton(entry, "restart"), WhatsAppButton(entry, "logout")]
    )


class WhatsAppButton(WhatsAppEntity, ButtonEntity):
    """Sends `restart` or `logout` to the bridge."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: WhatsAppConfigEntry, command: str) -> None:
        super().__init__(entry, command)
        self._command = command
        # Logging out unlinks the device in WhatsApp and needs a new QR scan;
        # keep that button out of dashboards unless someone enables it.
        self._attr_entity_registry_enabled_default = command != "logout"

    @property
    def available(self) -> bool:
        return self.data.bridge.connected

    async def async_press(self) -> None:
        try:
            await self.data.bridge.request({"type": self._command})
        except BridgeError as err:
            raise HomeAssistantError(f"WhatsApp: {err}") from err
