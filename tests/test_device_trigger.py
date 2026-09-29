"""Device triggers."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_get_device_automations,
    async_mock_service,
)

from custom_components.whatsapp.const import DOMAIN, EVENT_MESSAGE_RECEIVED

PHONE = "491700000001@c.us"
LID = "987654321098765@lid"


@pytest.fixture
def calls(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "test", "automation")


def _device(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    return device.id


async def _automation(hass: HomeAssistant, device_id: str, extra: dict) -> None:
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: {
                "trigger": {
                    "platform": "device",
                    "domain": DOMAIN,
                    "device_id": device_id,
                    "type": "message_received",
                    **extra,
                },
                "action": {
                    "service": "test.automation",
                    "data": {"body": "{{ trigger.event.data.body }}"},
                },
            }
        },
    )


def _message(device_id: str, **fields) -> dict:
    return {
        "device_id": device_id,
        "fromMe": False,
        "body": "x",
        "sender": LID,
        "sender_phone": PHONE,
        **fields,
    }


async def test_get_triggers(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    device_id = _device(hass, setup_entry)
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_id
    )
    # Entity triggers (button pressed, connected on/off) come from other domains.
    ours = [t["type"] for t in triggers if t["domain"] == DOMAIN]
    assert ours == ["message_received"]


@pytest.mark.parametrize(
    ("sender_filter", "fires"),
    [
        (None, True),
        ("491700000001", True),
        ("+49 170 0000001", True),
        (LID, True),
        ("491700000009", False),
    ],
)
async def test_sender_filter(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    calls: list[ServiceCall],
    sender_filter: str | None,
    fires: bool,
) -> None:
    device_id = _device(hass, setup_entry)
    await _automation(hass, device_id, {"from": sender_filter} if sender_filter else {})
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, _message(device_id))
    await hass.async_block_till_done()
    assert len(calls) == (1 if fires else 0)


async def test_national_number_filter(
    hass: HomeAssistant, setup_entry: MockConfigEntry, calls: list[ServiceCall]
) -> None:
    await hass.config.async_update(country="DE")
    device_id = _device(hass, setup_entry)
    await _automation(hass, device_id, {"from": "0170 0000001"})
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, _message(device_id))
    await hass.async_block_till_done()
    assert len(calls) == 1


async def test_ignores_other_devices_and_own_messages(
    hass: HomeAssistant, setup_entry: MockConfigEntry, calls: list[ServiceCall]
) -> None:
    device_id = _device(hass, setup_entry)
    await _automation(hass, device_id, {})
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, _message("other-device"))
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, _message(device_id, fromMe=True))
    await hass.async_block_till_done()
    assert calls == []


async def test_real_bridge_frame_reaches_device_trigger(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge, calls
) -> None:
    """End to end: frame from the (fake) bridge -> event with device_id -> trigger."""
    device_id = _device(hass, setup_entry)
    await _automation(hass, device_id, {"from": "491700000001"})
    await bridge.push(
        {
            "type": "message",
            "data": {
                "body": "Klingel",
                "fromMe": False,
                "sender": LID,
                "sender_phone": PHONE,
            },
        }
    )
    for _ in range(100):
        await hass.async_block_till_done()
        if calls:
            break
        await asyncio.sleep(0.02)
    assert calls[0].data == {"body": "Klingel"}
