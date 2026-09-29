"""Connected binary sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import WhatsAppEntity
from .runtime import WhatsAppConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WhatsAppConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([WhatsAppConnectedSensor(entry)])


class WhatsAppConnectedSensor(WhatsAppEntity, BinarySensorEntity):
    """On when messages can be sent: bridge reachable and WhatsApp ready."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, entry: WhatsAppConfigEntry) -> None:
        super().__init__(entry, "connected")

    @property
    def is_on(self) -> bool:
        return self.data.state == "ready"
