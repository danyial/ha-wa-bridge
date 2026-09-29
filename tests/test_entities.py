"""Status, connected, QR code and button entities."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.whatsapp import client as client_module

from .conftest import FakeBridge

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    registry = er.async_get(hass)
    for platform in ("sensor", "binary_sensor", "image", "button"):
        entity_id = registry.async_get_entity_id(
            platform, "whatsapp", f"{entry.entry_id}_{key}"
        )
        if entity_id:
            return entity_id
    raise AssertionError(f"no entity {key}")


async def _state(hass: HomeAssistant, entity_id: str, expected: str) -> None:
    for _ in range(100):
        await hass.async_block_till_done()
        state = hass.states.get(entity_id)
        if state and state.state == expected:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"{entity_id} is {state and state.state}, not {expected}")


async def test_status_and_connected(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    bridge: FakeBridge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = _entity_id(hass, setup_entry, "status")
    connected = _entity_id(hass, setup_entry, "connected")

    await _state(hass, status, "ready")
    await _state(hass, connected, STATE_ON)

    await bridge.push(
        {
            "type": "status",
            "status": "ready",
            "phone": "491700000002",
            "wa_state": "CONNECTED",
        }
    )
    for _ in range(100):
        await hass.async_block_till_done()
        if hass.states.get(status).attributes.get("phone"):
            break
        await asyncio.sleep(0.02)
    attributes = hass.states.get(status).attributes
    assert attributes["phone"] == "491700000002"
    assert attributes["wa_state"] == "CONNECTED"
    assert attributes["bridge_version"] == "t"

    await bridge.push(
        {
            "type": "status",
            "status": "unresponsive",
            "reason": "no answer within 10000 ms",
        }
    )
    await _state(hass, status, "unresponsive")
    await _state(hass, connected, STATE_OFF)
    assert hass.states.get(status).attributes["reason"] == "no answer within 10000 ms"

    # Bridge gone: the integration reports it, whatever the last status was.
    monkeypatch.setattr(client_module, "BACKOFF_MIN", 30)
    await bridge.close_clients()
    await _state(hass, status, "bridge_offline")
    await _state(hass, connected, STATE_OFF)


async def test_qr_code_image(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    bridge: FakeBridge,
    hass_client,
) -> None:
    image = _entity_id(hass, setup_entry, "qr_code")
    await _state(hass, image, STATE_UNAVAILABLE)

    await bridge.push({"type": "status", "status": "qr"})
    await bridge.push({"type": "qr", "data": "2@first"})
    await _state(hass, _entity_id(hass, setup_entry, "status"), "qr")
    for _ in range(100):
        await hass.async_block_till_done()
        if hass.states.get(image).state != STATE_UNAVAILABLE:
            break
        await asyncio.sleep(0.02)
    first = hass.states.get(image).state

    client = await hass_client()
    response = await client.get(hass.states.get(image).attributes["entity_picture"])
    assert response.status == 200
    assert (await response.read()).startswith(PNG_MAGIC)

    # A new code changes the state (timestamp), so the frontend reloads it.
    await asyncio.sleep(0.01)
    await bridge.push({"type": "qr", "data": "2@second"})
    for _ in range(100):
        await hass.async_block_till_done()
        if hass.states.get(image).state != first:
            break
        await asyncio.sleep(0.02)
    assert hass.states.get(image).state != first

    await bridge.push({"type": "status", "status": "authenticated"})
    await _state(hass, image, STATE_UNAVAILABLE)


async def test_restart_button(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    button = _entity_id(hass, setup_entry, "restart")
    await hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True
    )
    frames = await bridge.wait_frame()
    assert frames[0]["type"] == "restart"


async def test_button_error(
    hass: HomeAssistant, setup_entry: MockConfigEntry, bridge: FakeBridge
) -> None:
    bridge.replies["restart"] = lambda cmd: ("error", "internal_error", "boom")
    button = _entity_id(hass, setup_entry, "restart")
    with pytest.raises(HomeAssistantError, match="boom"):
        await hass.services.async_call(
            "button", "press", {"entity_id": button}, blocking=True
        )


async def test_logout_button_disabled_by_default(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    entity = er.async_get(hass).async_get(_entity_id(hass, setup_entry, "logout"))
    assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
