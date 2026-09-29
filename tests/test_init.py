"""Setup, bridge events and services."""

from __future__ import annotations

import asyncio
import base64

import pytest
import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.whatsapp import client as client_module
from custom_components.whatsapp.const import (
    CONF_HOST,
    CONF_TOKEN,
    DOMAIN,
    EVENT_GROUPS_RECEIVED,
    EVENT_MESSAGE_RECEIVED,
    EVENT_POLL_VOTE_RECEIVED,
    MAX_MEDIA_BYTES,
)

from .conftest import FakeBridge

MESSAGE = {
    "from": "491700000001@c.us",
    "to": "491700000002@c.us",
    "body": "hallo",
    "fromMe": False,
    "isGroup": False,
}


async def _wait_for(hass: HomeAssistant, predicate, attempts: int = 100) -> None:
    """Let the WebSocket reader run until `predicate` holds."""
    for _ in range(attempts):
        await hass.async_block_till_done()
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached")


def _notification(hass: HomeAssistant, notification_id: str) -> dict | None:
    return persistent_notification._async_get_or_create_notifications(hass).get(
        notification_id
    )


async def _call(hass: HomeAssistant, service: str, data: dict, response=False):
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=response
    )


@pytest.mark.parametrize(
    ("frame", "event_type", "expected"),
    [
        ({"type": "message", "data": MESSAGE}, EVENT_MESSAGE_RECEIVED, MESSAGE),
        (
            {"type": "poll_vote", "data": {"voter": "491700000001"}},
            EVENT_POLL_VOTE_RECEIVED,
            {"voter": "491700000001"},
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


async def test_hello_is_stored(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    await _wait_for(hass, lambda: setup_entry.runtime_data.bridge.hello is not None)
    assert setup_entry.runtime_data.bridge.hello["protocol"] == 2


async def test_qr_notification_created_and_dismissed(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    notification_id = f"whatsapp_qr_{setup_entry.entry_id}"

    await bridge.push({"type": "qr", "data": "2@abc,def"})
    await _wait_for(hass, lambda: _notification(hass, notification_id))
    assert "data:image/png;base64," in _notification(hass, notification_id)["message"]

    await bridge.push({"type": "status", "status": "ready"})
    await _wait_for(hass, lambda: _notification(hass, notification_id) is None)


async def test_send_message_returns_result(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    bridge.replies["send_message"] = lambda cmd: (
        "ok",
        {"chat_id": "491700000001@c.us", "message_id": "m1"},
    )
    response = await _call(
        hass, "send_message", {"number": "491700000001", "message": "hi"}, True
    )
    assert response == {"chat_id": "491700000001@c.us", "message_id": "m1"}
    frame = bridge.received[0]
    assert frame["type"] == "send_message"
    assert frame["number"] == "491700000001"
    assert frame["message"] == "hi"
    assert isinstance(frame["id"], int)


async def test_group_name_maps_to_group_name(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await _call(hass, "send_message", {"group": "Familie", "message": "hi"})
    assert bridge.received[0]["group_name"] == "Familie"
    assert "group" not in bridge.received[0]


async def test_bridge_error_raises(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    bridge.replies["send_message"] = lambda cmd: (
        "error",
        "ambiguous_group",
        '2 groups are named "Haus"; use group_id',
    )
    with pytest.raises(HomeAssistantError, match="use group_id"):
        await _call(hass, "send_message", {"group": "Haus", "message": "hi"})


async def test_timeout_raises(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    bridge: FakeBridge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "REQUEST_TIMEOUT", 0.1)
    bridge.replies["send_message"] = lambda cmd: None
    with pytest.raises(HomeAssistantError, match="did not answer"):
        await _call(hass, "send_message", {"number": "49", "message": "hi"})


async def test_not_connected_raises(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await bridge.close_clients()
    await _wait_for(hass, lambda: not setup_entry.runtime_data.bridge.connected)
    with pytest.raises(HomeAssistantError, match="Not connected"):
        await _call(hass, "send_message", {"number": "49", "message": "hi"})


async def test_reconnects(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    bridge: FakeBridge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client_module, "BACKOFF_MIN", 0.01)
    await bridge.close_clients()
    await _wait_for(hass, lambda: not setup_entry.runtime_data.bridge.connected)
    await _wait_for(
        hass, lambda: setup_entry.runtime_data.bridge.connected, attempts=200
    )


async def test_service_schema(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    with pytest.raises(vol.Invalid):
        await _call(hass, "send_message", {"message": "no target"})
    with pytest.raises(vol.Invalid):
        await _call(
            hass, "send_poll", {"number": "49", "message": "?", "options": ["only one"]}
        )


async def test_send_poll(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await _call(
        hass,
        "send_poll",
        {"group_id": "1@g.us", "message": "?", "options": ["a", "b"]},
    )
    frame = bridge.received[0]
    assert frame["options"] == ["a", "b"]
    assert frame["allow_multiple_answers"] is False
    assert frame["group_id"] == "1@g.us"


async def test_send_event_uses_ha_time_zone(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await hass.config.async_set_time_zone("Europe/Berlin")
    await _call(
        hass,
        "send_event",
        {"number": "49", "name": "Grillen", "start_time": "2026-07-01 18:00:00"},
    )
    assert bridge.received[0]["start_time"] == "2026-07-01T18:00:00+02:00"


async def test_get_groups_response_and_event(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    groups = [{"id": "1@g.us", "name": "G"}]
    bridge.replies["get_groups"] = lambda cmd: ("ok", groups)
    events = async_capture_events(hass, EVENT_GROUPS_RECEIVED)
    assert await _call(hass, "get_groups", {}, True) == {"groups": groups}
    await hass.async_block_till_done()
    assert events[0].data == {"groups": groups}


async def test_broadcast_partial_failure_raises(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    bridge.replies["broadcast"] = lambda cmd: (
        "ok",
        {"sent": ["1@g.us"], "failed": [{"target": "Haus", "error": "ambiguous"}]},
    )
    with pytest.raises(HomeAssistantError, match="Haus"):
        await _call(hass, "send_broadcast", {"targets": ["A", "Haus"], "message": "m"})


async def test_media_url(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    bridge.media["cam.jpg"] = (b"\xff\xd8jpeg", {"Content-Type": "image/jpeg"})
    await _call(
        hass,
        "send_message",
        {
            "number": "49",
            "message": "Klingel",
            "media_url": f"http://{bridge.base}/media/cam.jpg?token=abc",
        },
    )
    media = bridge.received[0]["media"]
    assert media["mimetype"] == "image/jpeg"
    assert media["filename"] == "cam.jpg"
    assert base64.b64decode(media["data"]) == b"\xff\xd8jpeg"


async def test_media_url_too_large(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    bridge.media["big.bin"] = (b"x" * (MAX_MEDIA_BYTES + 1), {})
    with pytest.raises(HomeAssistantError, match="larger than"):
        await _call(
            hass,
            "send_message",
            {
                "number": "49",
                "message": "m",
                "media_url": f"http://{bridge.base}/media/big.bin",
            },
        )
    assert bridge.received == []


async def test_media_url_scheme(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    with pytest.raises(vol.Invalid):
        await _call(
            hass,
            "send_message",
            {"number": "49", "message": "m", "media_url": "file:///etc/passwd"},
        )


async def test_media_path_not_allowed(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    with pytest.raises(ServiceValidationError, match="allowlist"):
        await _call(
            hass,
            "send_message",
            {"number": "49", "message": "m", "media_path": "/etc/passwd"},
        )


async def test_entry_without_token_needs_reauth(
    hass: HomeAssistant, bridge: FakeBridge
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: bridge.url})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.unique_id == DOMAIN
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows[0]["context"]["source"] == "reauth"


async def test_rejected_token_starts_reauth(
    hass: HomeAssistant, bridge: FakeBridge
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_HOST: bridge.url, CONF_TOKEN: "stale"},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await _wait_for(
        hass, lambda: hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    )
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flows[0]["context"]["source"] == "reauth"
    assert bridge.rejected == 1
    await hass.config_entries.async_unload(entry.entry_id)


async def test_unload(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert setup_entry.state is ConfigEntryState.NOT_LOADED
    with pytest.raises(ServiceValidationError, match="not loaded"):
        await _call(hass, "send_message", {"number": "49", "message": "hi"})
