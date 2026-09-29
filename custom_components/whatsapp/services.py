"""WhatsApp services."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .client import BridgeError, WhatsAppBridge
from .const import DOMAIN, EVENT_GROUPS_RECEIVED
from .media import async_load_media

TARGET = {
    vol.Optional("number"): cv.string,
    vol.Optional("group"): cv.string,
    vol.Optional("group_id"): cv.string,
}
MEDIA = {
    vol.Exclusive("media_url", "media"): cv.url,
    vol.Exclusive("media_path", "media"): cv.string,
}


def _has_target(data: dict[str, Any]) -> dict[str, Any]:
    if not any(data.get(key) for key in ("number", "group", "group_id")):
        raise vol.Invalid("number, group or group_id is required")
    return data


def _datetime(value: Any) -> str:
    """Accept a datetime or string; naive times are in the HA time zone."""
    parsed = cv.datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return parsed.isoformat()


SEND_MESSAGE_SCHEMA = vol.All(
    vol.Schema({**TARGET, **MEDIA, vol.Required("message"): cv.string}),
    _has_target,
)
SEND_BROADCAST_SCHEMA = vol.Schema(
    {
        **MEDIA,
        vol.Required("message"): cv.string,
        vol.Required("targets"): vol.All(
            cv.ensure_list, [cv.string], vol.Length(min=1)
        ),
    }
)
SEND_POLL_SCHEMA = vol.All(
    vol.Schema(
        {
            **TARGET,
            vol.Required("message"): cv.string,
            vol.Required("options"): vol.All(
                cv.ensure_list, [cv.string], vol.Length(min=2, max=12)
            ),
            vol.Optional("allow_multiple_answers", default=False): cv.boolean,
        }
    ),
    _has_target,
)
SEND_EVENT_SCHEMA = vol.All(
    vol.Schema(
        {
            **TARGET,
            vol.Required("name"): cv.string,
            vol.Optional("description"): cv.string,
            vol.Optional("location"): cv.string,
            vol.Required("start_time"): _datetime,
            vol.Optional("end_time"): _datetime,
            vol.Optional("call_type"): vol.In(["video", "voice", "none"]),
        }
    ),
    _has_target,
)
SET_GROUP_SUBJECT_SCHEMA = vol.Schema(
    {vol.Required("group_id"): cv.string, vol.Required("subject"): cv.string}
)
SET_GROUP_PICTURE_SCHEMA = vol.All(
    vol.Schema({vol.Required("group_id"): cv.string, **MEDIA}),
    cv.has_at_least_one_key("media_url", "media_path"),
)


def _bridge(hass: HomeAssistant) -> WhatsAppBridge:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data
    raise ServiceValidationError("The WhatsApp integration is not loaded")


def _target(data: dict[str, Any]) -> dict[str, Any]:
    wire = {
        "number": data.get("number"),
        "group_name": data.get("group"),
        "group_id": data.get("group_id"),
    }
    return {key: value for key, value in wire.items() if value}


async def _request(hass: HomeAssistant, command: dict[str, Any]) -> Any:
    try:
        return await _bridge(hass).request(command)
    except BridgeError as err:
        raise HomeAssistantError(f"WhatsApp: {err}") from err


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services (once, independent of config entries)."""

    async def send_message(call: ServiceCall) -> ServiceResponse:
        media = await async_load_media(
            hass, call.data.get("media_url"), call.data.get("media_path")
        )
        command = {
            "type": "send_message",
            **_target(call.data),
            "message": call.data["message"],
        }
        if media:
            command["media"] = media
        return await _request(hass, command)

    async def send_broadcast(call: ServiceCall) -> ServiceResponse:
        media = await async_load_media(
            hass, call.data.get("media_url"), call.data.get("media_path")
        )
        command = {
            "type": "broadcast",
            "targets": call.data["targets"],
            "message": call.data["message"],
        }
        if media:
            command["media"] = media
        result = await _request(hass, command)
        if result and result.get("failed"):
            failed = ", ".join(
                f"{f['target']} ({f['error']})" for f in result["failed"]
            )
            raise HomeAssistantError(
                f"WhatsApp: sent to {len(result['sent'])} target(s), failed: {failed}"
            )
        return result

    async def send_poll(call: ServiceCall) -> ServiceResponse:
        return await _request(
            hass,
            {
                "type": "send_poll",
                **_target(call.data),
                "message": call.data["message"],
                "options": call.data["options"],
                "allow_multiple_answers": call.data["allow_multiple_answers"],
            },
        )

    async def send_event(call: ServiceCall) -> ServiceResponse:
        command = {"type": "send_event", **_target(call.data)}
        for key in ("name", "description", "location", "start_time", "end_time"):
            if call.data.get(key):
                command[key] = call.data[key]
        if call.data.get("call_type"):
            command["call_type"] = call.data["call_type"]
        return await _request(hass, command)

    async def get_groups(call: ServiceCall) -> ServiceResponse:
        groups = await _request(hass, {"type": "get_groups"})
        # Event kept for automations written against earlier versions.
        hass.bus.async_fire(EVENT_GROUPS_RECEIVED, {"groups": groups})
        return {"groups": groups}

    async def set_group_subject(call: ServiceCall) -> None:
        await _request(
            hass,
            {
                "type": "set_group_subject",
                "group_id": call.data["group_id"],
                "subject": call.data["subject"],
            },
        )

    async def set_group_picture(call: ServiceCall) -> None:
        media = await async_load_media(
            hass, call.data.get("media_url"), call.data.get("media_path")
        )
        await _request(
            hass,
            {
                "type": "set_group_picture",
                "group_id": call.data["group_id"],
                "media": media,
            },
        )

    optional = SupportsResponse.OPTIONAL
    for name, handler, schema, response in (
        ("send_message", send_message, SEND_MESSAGE_SCHEMA, optional),
        ("send_broadcast", send_broadcast, SEND_BROADCAST_SCHEMA, optional),
        ("send_poll", send_poll, SEND_POLL_SCHEMA, optional),
        ("send_event", send_event, SEND_EVENT_SCHEMA, optional),
        ("get_groups", get_groups, vol.Schema({}), optional),
        ("set_group_subject", set_group_subject, SET_GROUP_SUBJECT_SCHEMA, None),
        ("set_group_picture", set_group_picture, SET_GROUP_PICTURE_SCHEMA, None),
    ):
        hass.services.async_register(
            DOMAIN,
            name,
            handler,
            schema=schema,
            supports_response=response or SupportsResponse.NONE,
        )
