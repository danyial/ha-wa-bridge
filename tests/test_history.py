"""Message history services (search_messages, get_messages)."""

from __future__ import annotations

import asyncio

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.whatsapp.const import DOMAIN

from .conftest import FakeBridge

RESULT = {
    "query": "Paket",
    "chat_id": None,
    "messages": [
        {"id": "m1", "body": "Paket ist da", "sender_phone": "491700000001@c.us"}
    ],
}


async def _allow(hass: HomeAssistant, entry: MockConfigEntry, allowed: bool) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"own_messages": "off", "max_age_minutes": 0, "allow_message_history": allowed},
    )
    for _ in range(300):
        await hass.async_block_till_done()
        if (
            entry.state is ConfigEntryState.LOADED
            and entry.runtime_data.bridge.connected
        ):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("not reconnected")


async def _call(hass: HomeAssistant, service: str, data: dict):
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True
    )


async def test_off_by_default(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    with pytest.raises(ServiceValidationError, match="options"):
        await _call(hass, "search_messages", {"query": "Paket"})
    with pytest.raises(ServiceValidationError, match="options"):
        await _call(hass, "get_messages", {"number": "491700000001"})
    assert bridge.received == []


async def test_search_messages(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await _allow(hass, setup_entry, True)
    bridge.replies["search_messages"] = lambda cmd: ("ok", RESULT)
    assert await _call(hass, "search_messages", {"query": "Paket"}) == RESULT
    frame = bridge.received[-1]
    assert frame["type"] == "search_messages"
    assert frame["query"] == "Paket"
    assert frame["limit"] == 20
    assert "number" not in frame


async def test_search_in_one_chat_with_national_number(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await hass.config.async_update(country="DE")
    await _allow(hass, setup_entry, True)
    bridge.replies["search_messages"] = lambda cmd: ("ok", RESULT)
    await _call(
        hass, "search_messages", {"query": "x", "number": "0170 0000001", "limit": 5}
    )
    frame = bridge.received[-1]
    assert frame["number"] == "491700000001@c.us"
    assert frame["limit"] == 5


async def test_get_messages(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await _allow(hass, setup_entry, True)
    reply = {"chat_id": "1@g.us", "chat_name": "Familie", "messages": []}
    bridge.replies["get_messages"] = lambda cmd: ("ok", reply)
    assert await _call(hass, "get_messages", {"group": "Familie", "limit": 3}) == reply
    frame = bridge.received[-1]
    assert frame == {
        **frame,
        "type": "get_messages",
        "group_name": "Familie",
        "limit": 3,
    }


async def test_schema_limits(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    await _allow(hass, setup_entry, True)
    with pytest.raises(vol.Invalid):
        await _call(hass, "search_messages", {"query": "x", "limit": 51})
    with pytest.raises(vol.Invalid):
        await _call(hass, "get_messages", {"limit": 5})
    with pytest.raises(vol.Invalid):
        await _call(hass, "search_messages", {})


async def test_bridge_error(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await _allow(hass, setup_entry, True)
    bridge.replies["search_messages"] = lambda cmd: ("error", "not_ready", "not linked")
    with pytest.raises(HomeAssistantError, match="not linked"):
        await _call(hass, "search_messages", {"query": "x"})


async def test_switching_off_again(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    await _allow(hass, setup_entry, True)
    await _allow(hass, setup_entry, False)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "search_messages", {"query": "x"})


async def test_empty_bridge_answer_gives_empty_result(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await _allow(hass, setup_entry, True)
    bridge.replies["get_messages"] = lambda cmd: ("ok", None)
    assert await _call(hass, "get_messages", {"number": "491700000001"}) == {
        "messages": []
    }
