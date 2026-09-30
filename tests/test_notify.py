"""Notify entity and default chat option."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.whatsapp.const import CONF_DEFAULT_CHAT, CONF_OWN_MESSAGES

from .conftest import FakeBridge


def _notify_entity(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    return er.async_get(hass).async_get_entity_id(
        "notify", "whatsapp", f"{entry.entry_id}_notify"
    )


async def _options(hass: HomeAssistant, entry: MockConfigEntry, data: dict) -> dict:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_OWN_MESSAGES: "off", **data}
    )


async def _reconnected(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    for _ in range(300):
        await hass.async_block_till_done()
        if (
            entry.state is ConfigEntryState.LOADED
            and entry.runtime_data.bridge.connected
        ):
            return
        await asyncio.sleep(0.01)
    raise AssertionError("not reconnected")


async def _send(hass: HomeAssistant, entity_id: str, **data) -> None:
    await hass.services.async_call(
        "notify", "send_message", {"entity_id": entity_id, **data}, blocking=True
    )


async def test_entity_is_the_device(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    assert _notify_entity(hass, setup_entry) == "notify.whatsapp"


async def test_without_default_chat(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    with pytest.raises(ServiceValidationError, match="default chat"):
        await _send(hass, "notify.whatsapp", message="hi")
    assert bridge.received == []


async def test_default_chat_number_with_title(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await hass.config.async_update(country="DE")
    result = await _options(hass, setup_entry, {CONF_DEFAULT_CHAT: "0170 0000001"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_entry.options[CONF_DEFAULT_CHAT] == "491700000001@c.us"
    await _reconnected(hass, setup_entry)

    await _send(hass, "notify.whatsapp", message="Tür offen", title="Haus")
    frame = (await bridge.wait_frame())[0]
    assert frame["type"] == "send_message"
    assert frame["number"] == "491700000001@c.us"
    assert frame["message"] == "*Haus*\nTür offen"


async def test_default_chat_group(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await _options(hass, setup_entry, {CONF_DEFAULT_CHAT: "120363000000000001@g.us"})
    await _reconnected(hass, setup_entry)
    await _send(hass, "notify.whatsapp", message="hi")
    frame = (await bridge.wait_frame())[0]
    assert frame["group_id"] == "120363000000000001@g.us"
    assert "number" not in frame


async def test_rejects_own_number_and_invalid(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await bridge.push({"type": "status", "status": "ready", "phone": "491700000009"})
    for _ in range(100):
        await hass.async_block_till_done()
        if setup_entry.runtime_data.status.get("phone"):
            break
        await asyncio.sleep(0.01)

    result = await _options(hass, setup_entry, {CONF_DEFAULT_CHAT: "+49 170 0000009"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_DEFAULT_CHAT: "own_number"}

    await hass.config.async_update(country=None)
    result = await _options(hass, setup_entry, {CONF_DEFAULT_CHAT: "0170 0000001"})
    assert result["errors"] == {CONF_DEFAULT_CHAT: "invalid_chat_id"}
    assert CONF_DEFAULT_CHAT not in setup_entry.options


async def test_clearing_the_default_chat(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    await _options(hass, setup_entry, {CONF_DEFAULT_CHAT: "491700000001"})
    await _reconnected(hass, setup_entry)
    await _options(hass, setup_entry, {CONF_DEFAULT_CHAT: ""})
    assert CONF_DEFAULT_CHAT not in setup_entry.options
    await _reconnected(hass, setup_entry)


async def test_bridge_error(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    await _options(hass, setup_entry, {CONF_DEFAULT_CHAT: "491700000001"})
    await _reconnected(hass, setup_entry)
    bridge.replies["send_message"] = lambda cmd: ("error", "not_ready", "not linked")
    with pytest.raises(HomeAssistantError, match="not linked"):
        await _send(hass, "notify.whatsapp", message="hi")
