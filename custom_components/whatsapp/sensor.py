"""Bridge status sensor."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import WhatsAppEntity
from .runtime import STATES, WhatsAppConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WhatsAppConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([WhatsAppStatusSensor(entry)])


class WhatsAppStatusSensor(WhatsAppEntity, SensorEntity):
    """initializing, qr, ready, unresponsive, ..., bridge_offline."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATES

    def __init__(self, entry: WhatsAppConfigEntry) -> None:
        super().__init__(entry, "status")

    @property
    def native_value(self) -> str:
        return self.data.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self.data.status
        hello = self.data.bridge.hello or {}
        return {
            "phone": status.get("phone"),
            "wa_state": status.get("wa_state"),
            "reason": status.get("reason"),
            "bridge_version": hello.get("bridge_version"),
            "wwebjs_version": hello.get("wwebjs_version"),
        }
