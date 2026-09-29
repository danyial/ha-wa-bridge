"""Setup, bridge events and services."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.whatsapp.const import (
    DOMAIN,
    EVENT_GROUPS_RECEIVED,
    EVENT_MESSAGE_RECEIVED,
    EVENT_POLL_VOTE_RECEIVED,
)

from .conftest import FakeBridge

MESSAGE = {
    "from": "491700000001@c.us",
    "to": "491700000002@c.us",
    "body": "hallo",
    "fromMe": False,
    "isGroup": False,
}


@pytest.mark.parametrize(
    ("frame", "event_type", "expected"),
    [
        ({"type": "message", "data": MESSAGE}, EVENT_MESSAGE_RECEIVED, MESSAGE),
        (
            {"type": "poll_vote", "data": {"voter": "491700000001"}},
            EVENT_POLL_VOTE_RECEIVED,
            {"voter": "491700000001"},
        ),
        (
            {"type": "get_groups_response", "data": [{"id": "1@g.us", "name": "G"}]},
            EVENT_GROUPS_RECEIVED,
            {"groups": [{"id": "1@g.us", "name": "G"}]},
        ),
    ],
)
async def test_bridge_frames_fire_events(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    bridge: FakeBridge,
    frame: dict,
    event_type: str,
    expected: dict,
) -> None:
    events = async_capture_events(hass, event_type)
    await bridge.push(frame)
    await _wait_for(hass, lambda: events)
    assert events[0].data == expected


async def test_qr_notification_created_and_dismissed(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    notification_id = f"whatsapp_qr_{setup_entry.entry_id}"

    await bridge.push({"type": "qr", "data": "2@abc,def"})
    await _wait_for(hass, lambda: _notification(hass, notification_id))
    assert "data:image/png;base64," in _notification(hass, notification_id)["message"]

    await bridge.push({"type": "status", "status": "ready"})
    await _wait_for(hass, lambda: _notification(hass, notification_id) is None)


async def test_send_message_service(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "send_message",
        {"number": "491700000001", "message": "hi"},
        blocking=True,
    )
    frames = await bridge.wait_frame()
    assert frames[0] == {
        "type": "send_message",
        "number": "491700000001",
        "message": "hi",
    }


async def test_send_poll_service(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "send_poll",
        {"group_id": "1@g.us", "message": "?", "options": ["a", "b"]},
        blocking=True,
    )
    frames = await bridge.wait_frame()
    assert frames[0] == {
        "type": "send_poll",
        "group_id": "1@g.us",
        "message": "?",
        "options": ["a", "b"],
        "allow_multiple_answers": False,
    }


async def test_get_groups_service(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await hass.services.async_call(DOMAIN, "get_groups", {}, blocking=True)
    frames = await bridge.wait_frame()
    assert frames[0] == {"type": "get_groups"}


async def test_unload(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert setup_entry.entry_id not in hass.data[DOMAIN]


def _notification(hass: HomeAssistant, notification_id: str) -> dict | None:
    return persistent_notification._async_get_or_create_notifications(hass).get(
        notification_id
    )


async def _wait_for(hass: HomeAssistant, predicate, attempts: int = 50) -> None:
    """Let the WebSocket reader run until `predicate` holds."""
    for _ in range(attempts):
        await hass.async_block_till_done()
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached")
