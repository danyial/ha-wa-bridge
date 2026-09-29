"""The `platform: whatsapp` trigger."""

from __future__ import annotations

import pytest
from homeassistant.components import automation
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.trigger import async_get_all_descriptions
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.whatsapp.const import EVENT_MESSAGE_RECEIVED

DIRECT = {
    "from": "491700000001@c.us",
    "to": "491700000002@c.us",
    "body": "Tür offen",
    "isGroup": False,
}
GROUP = {
    "from": "120363000000000001@g.us",
    "to": "491700000002@c.us",
    "author": "491700000001@c.us",
    "body": "Hallo Gruppe",
    "isGroup": True,
    "chatName": "Familie",
    "groupId": "120363000000000001@g.us",
}
LID_DIRECT = {
    "from": "987654321098765@lid",
    "to": "491700000002@c.us",
    "body": "Hallo",
    "isGroup": False,
    "sender": "987654321098765@lid",
    "sender_phone": "491700000001@c.us",
    "sender_lid": "987654321098765@lid",
}
LID_GROUP = {
    "from": "120363000000000001@g.us",
    "to": "491700000002@c.us",
    "author": "987654321098765@lid",
    "body": "Hallo",
    "isGroup": True,
    "chatName": "Familie",
    "groupId": "120363000000000001@g.us",
    "sender": "987654321098765@lid",
    "sender_phone": "491700000001:4@c.us",
}
OWN_IN_GROUP = {
    "from": "123456789@lid",
    "to": "120363000000000001@g.us",
    "body": "selbst",
    "fromMe": True,
}


@pytest.fixture
def calls(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "test", "automation")


async def _setup(hass: HomeAssistant, trigger: dict) -> None:
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: {
                "trigger": {"platform": "whatsapp", **trigger},
                "action": {
                    "service": "test.automation",
                    "data": {
                        "from_number": "{{ trigger.from_number }}",
                        "from_group_id": "{{ trigger.from_group_id }}",
                    },
                },
            }
        },
    )


@pytest.mark.parametrize(
    ("trigger", "event", "fires"),
    [
        ({}, DIRECT, True),
        ({"from_number": "491700000001"}, DIRECT, True),
        ({"from_number": "491700000001@c.us"}, DIRECT, True),
        ({"from_number": "491700000009"}, DIRECT, False),
        ({"contains_text": "tür"}, DIRECT, True),
        ({"contains_text": "fenster"}, DIRECT, False),
        ({"equals_text": " TÜR OFFEN "}, DIRECT, True),
        ({"equals_text": "Tür"}, DIRECT, False),
        ({"from_group": "familie"}, GROUP, True),
        ({"from_group": "Familie"}, DIRECT, False),
        ({"from_group_id": "120363000000000001"}, GROUP, True),
        ({"from_group_id": "120363000000000001@g.us"}, GROUP, True),
        ({"from_group_id": "999@g.us"}, GROUP, False),
        # Own group messages carry the group in `to`, not `groupId`.
        ({"from_group_id": "120363000000000001"}, OWN_IN_GROUP, True),
        # 3.0 bridge: LID sender resolved to a number.
        ({"from_number": "491700000001"}, LID_DIRECT, True),
        ({"from_number": "+49 170 0000001"}, LID_DIRECT, True),
        ({"from_number": "987654321098765@lid"}, LID_DIRECT, True),
        ({"from_number": "491700000009"}, LID_DIRECT, False),
        # Group messages: the person is the author (also for 2.x bridges).
        ({"from_number": "491700000001"}, GROUP, True),
        ({"from_number": "491700000001"}, LID_GROUP, True),
    ],
)
async def test_trigger_filters(
    hass: HomeAssistant,
    calls: list[ServiceCall],
    trigger: dict,
    event: dict,
    fires: bool,
) -> None:
    await _setup(hass, trigger)
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, event)
    await hass.async_block_till_done()
    assert len(calls) == (1 if fires else 0)


async def test_trigger_variables(hass: HomeAssistant, calls: list[ServiceCall]) -> None:
    await _setup(hass, {"from_group_id": "120363000000000001"})
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, OWN_IN_GROUP)
    await hass.async_block_till_done()
    assert calls[0].data == {
        "from_number": "123456789@lid",
        "from_group_id": "120363000000000001@g.us",
    }


async def test_trigger_description_loads(
    hass: HomeAssistant, calls: list[ServiceCall]
) -> None:
    """triggers.yaml is valid and describes every trigger option."""
    await _setup(hass, {})
    descriptions = await async_get_all_descriptions(hass)
    fields = descriptions["whatsapp"]["fields"]
    assert set(fields) == {
        "from_number",
        "from_group",
        "from_group_id",
        "contains_text",
        "equals_text",
    }


async def test_national_number_uses_ha_country(
    hass: HomeAssistant, calls: list[ServiceCall]
) -> None:
    await hass.config.async_update(country="DE")
    await _setup(hass, {"from_number": "0170 0000001"})
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, LID_DIRECT)
    await hass.async_block_till_done()
    assert len(calls) == 1


async def test_invalid_number_is_rejected(
    hass: HomeAssistant, calls: list[ServiceCall]
) -> None:
    await hass.config.async_update(country=None)
    await _setup(hass, {"from_number": "0170 0000001"})
    # Invalid config: the automation is not set up and never fires.
    hass.bus.async_fire(EVENT_MESSAGE_RECEIVED, LID_DIRECT)
    await hass.async_block_till_done()
    assert calls == []
    assert hass.states.get("automation.automation_0") is None or (
        hass.states.get("automation.automation_0").state == "unavailable"
    )
