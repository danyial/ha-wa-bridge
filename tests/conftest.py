"""Fixtures for WhatsApp tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestServer
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.whatsapp.const import CONF_HOST, DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


class FakeBridge:
    """A scripted stand-in for the wa-bridge WebSocket server."""

    def __init__(self) -> None:
        self.received: list[dict[str, Any]] = []
        self.hello: dict[str, Any] | None = {"type": "status", "status": "ready"}
        self._clients: set[web.WebSocketResponse] = set()
        self._connected = asyncio.Event()
        self._frame = asyncio.Event()
        self.server: TestServer | None = None

    @property
    def url(self) -> str:
        assert self.server is not None
        return f"ws://{self.server.host}:{self.server.port}/"

    async def handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        self._connected.set()
        if self.hello is not None:
            await ws.send_json(self.hello)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    self.received.append(msg.json())
                    self._frame.set()
        finally:
            self._clients.discard(ws)
        return ws

    async def wait_connected(self) -> None:
        await asyncio.wait_for(self._connected.wait(), 5)

    async def wait_frame(self, count: int = 1) -> list[dict[str, Any]]:
        """Wait until at least `count` frames have arrived from clients."""
        async with asyncio.timeout(5):
            while len(self.received) < count:
                self._frame.clear()
                await self._frame.wait()
        return self.received

    async def push(self, frame: dict[str, Any]) -> None:
        """Send a frame to every connected client (like the bridge's broadcast)."""
        for ws in list(self._clients):
            await ws.send_json(frame)

    async def close_clients(self) -> None:
        for ws in list(self._clients):
            await ws.close()


@pytest.fixture
async def bridge(socket_enabled: None) -> AsyncIterator[FakeBridge]:
    """A running fake bridge on 127.0.0.1 (real sockets, loopback only)."""
    fake = FakeBridge()
    app = web.Application()
    app.router.add_get("/", fake.handler)
    fake.server = TestServer(app, host="127.0.0.1")
    await fake.server.start_server()
    yield fake
    await fake.close_clients()
    await fake.server.close()


@pytest.fixture
def entry(bridge: FakeBridge) -> MockConfigEntry:
    """A config entry pointing at the fake bridge."""
    return MockConfigEntry(
        domain=DOMAIN, title="WhatsApp", data={CONF_HOST: bridge.url}
    )


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant, entry: MockConfigEntry, bridge: FakeBridge
) -> AsyncIterator[MockConfigEntry]:
    """Set up the integration and wait until it is connected to the bridge."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await bridge.wait_connected()
    await hass.async_block_till_done()
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
