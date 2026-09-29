"""Fixtures for WhatsApp tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestServer
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.whatsapp.const import (
    CONF_HOST,
    CONF_TOKEN,
    DOMAIN,
    PROTOCOL_VERSION,
)

TOKEN = "test-token"

Reply = Callable[[dict[str, Any]], tuple[Any, ...] | None]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


class FakeBridge:
    """A scripted stand-in for the wa-bridge WebSocket server.

    Commands with an `id` are answered by `replies[type](cmd)`, which returns
    ("ok", data), ("error", code, message) or None (no answer). Unknown types
    get ("ok", None).
    """

    def __init__(self) -> None:
        self.token = TOKEN
        self.received: list[dict[str, Any]] = []
        self.greeting: list[dict[str, Any]] = [
            {"type": "hello", "protocol": PROTOCOL_VERSION, "bridge_version": "t"},
            {"type": "status", "status": "ready"},
        ]
        self.replies: dict[str, Reply] = {}
        self.media: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.rejected = 0
        self._clients: set[web.WebSocketResponse] = set()
        self._connected = asyncio.Event()
        self._frame = asyncio.Event()
        self.server: TestServer | None = None

    @property
    def base(self) -> str:
        assert self.server is not None
        return f"{self.server.host}:{self.server.port}"

    @property
    def url(self) -> str:
        return f"ws://{self.base}/"

    async def handler(self, request: web.Request) -> web.StreamResponse:
        if request.headers.get("Authorization") != f"Bearer {self.token}":
            self.rejected += 1
            return web.Response(status=401)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._clients.add(ws)
        self._connected.set()
        for frame in self.greeting:
            await ws.send_json(frame)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._command(ws, msg.json())
        finally:
            self._clients.discard(ws)
        return ws

    async def _command(self, ws: web.WebSocketResponse, cmd: dict[str, Any]) -> None:
        self.received.append(cmd)
        self._frame.set()
        if "id" not in cmd:
            return
        reply = self.replies.get(cmd["type"], lambda _: ("ok", None))(cmd)
        if reply is None:
            return
        if reply[0] == "ok":
            await ws.send_json(
                {"type": "result", "id": cmd["id"], "ok": True, "data": reply[1]}
            )
        else:
            await ws.send_json(
                {
                    "type": "result",
                    "id": cmd["id"],
                    "ok": False,
                    "code": reply[1],
                    "error": reply[2],
                }
            )

    async def media_handler(self, request: web.Request) -> web.Response:
        body, headers = self.media[request.match_info["name"]]
        return web.Response(body=body, headers=headers)

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
    app.router.add_get("/media/{name}", fake.media_handler)
    fake.server = TestServer(app, host="127.0.0.1")
    await fake.server.start_server()
    yield fake
    await fake.close_clients()
    await fake.server.close()


@pytest.fixture
def entry(bridge: FakeBridge) -> MockConfigEntry:
    """A config entry pointing at the fake bridge."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="WhatsApp",
        unique_id=DOMAIN,
        data={CONF_HOST: bridge.url, CONF_TOKEN: TOKEN},
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
