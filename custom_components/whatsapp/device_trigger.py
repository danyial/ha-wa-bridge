import voluptuous as vol
from homeassistant.const import CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import trigger
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, EVENT_MESSAGE_RECEIVED

TRIGGER_TYPES = {"message_received"}

TRIGGER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLATFORM): "device",
        vol.Required(CONF_DOMAIN): DOMAIN,
        vol.Required(CONF_TYPE): "message_received",
        vol.Optional("from_number"): str,
        vol.Optional("from_group"): str,
        vol.Optional("contains_text"): str,
    }
)


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict]:
    """List device triggers for WhatsApp Integration."""
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "message_received",
            "device_id": device_id,
        }
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: trigger.TriggerActionType,
    automation_info: trigger.TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    event_config = {
        trigger.CONF_PLATFORM: "event",
        trigger.CONF_EVENT_TYPE: EVENT_MESSAGE_RECEIVED,
        trigger.CONF_EVENT_DATA: {},
    }

    if "from_number" in config:
        event_config[trigger.CONF_EVENT_DATA]["from"] = config["from_number"]

    # 'contains_text' needs a partial match, which event data matching cannot
    # express, so all filters are checked manually in the listener.

    async def event_listener(event):
        """Handle the event."""
        data = event.data

        # Check from_number
        if "from_number" in config and (
            data.get("from") != config["from_number"]
            and data.get("from") != f"{config['from_number']}@c.us"
        ):
            return

        # Check from_group
        if "from_group" in config:
            if not data.get("isGroup", False):
                return
            if data.get("chatName", "").lower() != config["from_group"].lower():
                return

        # Check contains_text
        if (
            "contains_text" in config
            and config["contains_text"].lower() not in data.get("body", "").lower()
        ):
            return

        await action(event.context)

    return hass.bus.async_listen(EVENT_MESSAGE_RECEIVED, event_listener)
