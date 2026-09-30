"""Own messages: option, event filter and "message sent" device trigger."""

from __future__ import annotations

import asyncio

import pytest
import voluptuous as vol
from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_get_device_automations,
    async_mock_service,
)

from custom_components.whatsapp.const import (
    CONF_OWN_MESSAGES,
    DOMAIN,
    EVENT_MESSAGE_RECEIVED,
)
from custom_components.whatsapp.device_trigger import async_validate_trigger_config

from .conftest import FakeBridge

ME = "491700000009@c.us"
OTHER = "491700000001@c.us"

INCOMING = {"from": OTHER, "to": ME, "fromMe": False, "to_self": False, "body": "in"}
SENT = {"from": ME, "to": OTHER, "fromMe": True, "to_self": False, "body": "out"}
NOTE = {"from": ME, "to": "555@lid", "fromMe": True, "to_self": True, "body": "note"}


async def _set_mode(hass: HomeAssistant, entry: MockConfigEntry, mode: str) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_OWN_MESSAGES: mode}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def _connected(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    for _ in range(200):
        await hass.async_block_till_done()
        if (
            entry.state is ConfigEntryState.LOADED
            and entry.runtime_data.bridge.connected
        ):
            return
        await asyncio.sleep(0.02)
    raise AssertionError("not reconnected")


async def test_options_flow_default_and_reload(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    schema = result["data_schema"].schema
    default = next(k for k in schema if k == CONF_OWN_MESSAGES).default()
    assert default == "off"
    bridge_before = setup_entry.runtime_data.bridge
    hass.config_entries.options.async_abort(result["flow_id"])

    await _set_mode(hass, setup_entry, "self")
    assert setup_entry.options == {CONF_OWN_MESSAGES: "self"}
    await _connected(hass, setup_entry)
    assert setup_entry.runtime_data.bridge is not bridge_before, "reloaded"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("off", ["in"]),
        ("self", ["in", "note"]),
        ("all", ["in", "out", "note"]),
    ],
)
async def test_own_messages_filter(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    bridge: FakeBridge,
    mode: str,
    expected: list[str],
) -> None:
    if mode != "off":
        await _set_mode(hass, setup_entry, mode)
        await _connected(hass, setup_entry)
    events = async_capture_events(hass, EVENT_MESSAGE_RECEIVED)
    for message in (INCOMING, SENT, NOTE):
        await bridge.push({"type": "message", "data": message})
    await bridge.push({"type": "message", "data": {**INCOMING, "body": "end"}})
    for _ in range(100):
        await hass.async_block_till_done()
        if events and events[-1].data["body"] == "end":
            break
        await asyncio.sleep(0.02)
    assert [e.data["body"] for e in events][:-1] == expected


def _device(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    return (
        dr.async_get(hass)
        .async_get_device_by_identifier((DOMAIN, entry.entry_id), entry.entry_id)
        .id
    )


async def _types(hass: HomeAssistant, device_id: str) -> list[str]:
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_id
    )
    return [t["type"] for t in triggers if t["domain"] == DOMAIN]


async def test_message_sent_trigger_offered_only_with_option(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    device_id = _device(hass, setup_entry)
    assert await _types(hass, device_id) == ["message_received"]
    await _set_mode(hass, setup_entry, "self")
    assert await _types(hass, device_id) == ["message_received", "message_sent"]


async def test_message_sent_trigger_fires_on_own_messages(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    calls: list[ServiceCall] = async_mock_service(hass, "test", "automation")
    device_id = _device(hass, setup_entry)
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: {
                "trigger": {
                    "platform": "device",
                    "domain": DOMAIN,
                    "device_id": device_id,
                    "type": "message_sent",
                },
                "action": {
                    "service": "test.automation",
                    "data": {"body": "{{ trigger.event.data.body }}"},
                },
            }
        },
    )
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, {**NOTE, "device_id": device_id})
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, {**INCOMING, "device_id": device_id})
    await hass.async_block_till_done()
    assert [c.data["body"] for c in calls] == ["note"]


async def test_sender_filter_only_for_received(hass: HomeAssistant) -> None:
    with pytest.raises(vol.Invalid):
        await async_validate_trigger_config(
            hass,
            {
                "platform": "device",
                "domain": DOMAIN,
                "device_id": "x",
                "type": "message_sent",
                "from": "491700000001",
            },
        )
