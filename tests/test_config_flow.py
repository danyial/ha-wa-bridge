"""Config flow tests."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.hassio import HassioServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.whatsapp.const import CONF_HOST, CONF_TOKEN, DOMAIN

from .conftest import TOKEN, FakeBridge


async def _user_flow(hass: HomeAssistant, data: dict) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


def _discovery(bridge: FakeBridge, token: str = TOKEN) -> HassioServiceInfo:
    host, port = bridge.base.split(":")
    return HassioServiceInfo(
        config={
            "host": host,
            "port": int(port),
            "token": token,
            "addon": "WhatsApp Bridge",
        },
        name="WhatsApp Bridge",
        slug="abcd1234_ha_wa_bridge",
        uuid="1234",
    )


async def test_user_flow_creates_entry(hass: HomeAssistant, bridge: FakeBridge) -> None:
    result = await _user_flow(hass, {CONF_HOST: bridge.url, CONF_TOKEN: TOKEN})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: bridge.url, CONF_TOKEN: TOKEN}
    assert result["result"].unique_id == DOMAIN


async def test_user_flow_invalid_auth(hass: HomeAssistant, bridge: FakeBridge) -> None:
    result = await _user_flow(hass, {CONF_HOST: bridge.url, CONF_TOKEN: "wrong"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert bridge.rejected == 1


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, bridge: FakeBridge
) -> None:
    url = bridge.url
    await bridge.server.close()
    result = await _user_flow(hass, {CONF_HOST: url, CONF_TOKEN: TOKEN})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_single_instance(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_hassio_discovery(hass: HomeAssistant, bridge: FakeBridge) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_HASSIO},
        data=_discovery(bridge),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "hassio_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: bridge.url.rstrip("/"), CONF_TOKEN: TOKEN}


async def test_hassio_discovery_updates_existing_entry(
    hass: HomeAssistant, bridge: FakeBridge
) -> None:
    old = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_HOST: "ws://old-host:3000", CONF_TOKEN: "old"},
    )
    old.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_HASSIO},
        data=_discovery(bridge, token="new"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert old.data == {CONF_HOST: bridge.url.rstrip("/"), CONF_TOKEN: "new"}


async def test_reauth(hass: HomeAssistant, bridge: FakeBridge) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={CONF_HOST: bridge.url, CONF_TOKEN: "old"}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == TOKEN
    await hass.async_block_till_done()  # reload after reauth
    await hass.config_entries.async_unload(entry.entry_id)
