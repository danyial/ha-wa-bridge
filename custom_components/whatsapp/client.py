"""WebSocket client for the wa-bridge add-on."""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import PROTOCOL_VERSION

_LOGGER = logging.getLogger(__name__)

HEARTBEAT = 30
REQUEST_TIMEOUT = 60
BACKOFF_MIN = 1
BACKOFF_MAX = 60


class BridgeError(Exception):
    """A command failed on the bridge or the bridge is unreachable."""

    def __init__(self, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.code = code


class BridgeAuthError(BridgeError):
    """The bridge rejected the token."""

    def __init__(self) -> None:
        super().__init__("The bridge rejected the access token", "invalid_auth")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def async_probe(hass: HomeAssistant, url: str, token: str) -> dict[str, Any]:
    """Connect once and return the bridge's hello frame (config flow check)."""
    session = async_get_clientsession(hass)
    try:
        async with (
            asyncio.timeout(10),
            session.ws_connect(url, headers=auth_headers(token)) as ws,
        ):
            while True:
                frame = await ws.receive_json()
                if frame.get("type") == "hello":
                    return frame
    except aiohttp.WSServerHandshakeError as err:
        if err.status == 401:
            raise BridgeAuthError from err
        raise BridgeError(
            f"Handshake failed: HTTP {err.status}", "cannot_connect"
        ) from err
    except (TimeoutError, aiohttp.ClientError, ValueError) as err:
        raise BridgeError(str(err) or "no answer", "cannot_connect") from err


class WhatsAppBridge:
    """Keeps a WebSocket connection to the bridge and correlates commands."""

    def __init__(
        self,
        hass: HomeAssistant,
        url: str,
        token: str,
        on_frame: Callable[[dict[str, Any]], Awaitable[None]],
        on_auth_failed: Callable[[], None],
    ) -> None:
        self.hass = hass
        self.url = url
        self._token = token
        self._on_frame = on_frame
        self._on_auth_failed = on_auth_failed
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._running = False
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self.hello: dict[str, Any] | None = None

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def run(self) -> None:
        """Connect and reconnect until stopped; returns on auth failure."""
        self._running = True
        session = async_get_clientsession(self.hass)
        backoff = BACKOFF_MIN
        while self._running:
            try:
                async with session.ws_connect(
                    self.url, headers=auth_headers(self._token), heartbeat=HEARTBEAT
                ) as ws:
                    self._ws = ws
                    backoff = BACKOFF_MIN
                    _LOGGER.info("Connected to WhatsApp bridge at %s", self.url)
                    await self._read(ws)
            except aiohttp.WSServerHandshakeError as err:
                if err.status == 401:
                    _LOGGER.error("The WhatsApp bridge rejected the access token")
                    self._running = False
                    self._on_auth_failed()
                    return
                _LOGGER.warning("WhatsApp bridge handshake failed: HTTP %s", err.status)
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.warning("WhatsApp bridge not reachable: %s", err)
            finally:
                self._ws = None
                self._fail_pending(
                    BridgeError("Connection to the bridge lost", "disconnected")
                )
            if self._running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)

    async def _read(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type is not aiohttp.WSMsgType.TEXT:
                continue
            try:
                frame = msg.json()
            except ValueError:
                _LOGGER.warning("Ignoring invalid frame from the bridge")
                continue
            if not isinstance(frame, dict):
                continue
            if frame.get("type") == "result":
                self._resolve(frame)
                continue
            if frame.get("type") == "hello":
                self._check_hello(frame)
            try:
                await self._on_frame(frame)
            except Exception:
                _LOGGER.exception("Error handling bridge frame %s", frame.get("type"))

    def _check_hello(self, frame: dict[str, Any]) -> None:
        self.hello = frame
        if frame.get("protocol") != PROTOCOL_VERSION:
            _LOGGER.warning(
                "WhatsApp bridge speaks protocol %s, this integration %s; "
                "update the add-on and the integration to the same version",
                frame.get("protocol"),
                PROTOCOL_VERSION,
            )

    def _resolve(self, frame: dict[str, Any]) -> None:
        future = self._pending.pop(frame.get("id"), None)
        if future is None or future.done():
            return
        if frame.get("ok"):
            future.set_result(frame.get("data"))
        else:
            future.set_exception(
                BridgeError(
                    frame.get("error") or "unknown error", frame.get("code") or "error"
                )
            )

    def _fail_pending(self, err: BridgeError) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(err)
        self._pending.clear()

    async def request(self, command: dict[str, Any]) -> Any:
        """Send a command and wait for its result."""
        ws = self._ws
        if ws is None or ws.closed:
            raise BridgeError("Not connected to the WhatsApp bridge", "disconnected")
        request_id = next(self._ids)
        future: asyncio.Future[Any] = self.hass.loop.create_future()
        self._pending[request_id] = future
        try:
            await ws.send_json({**command, "id": request_id})
            async with asyncio.timeout(REQUEST_TIMEOUT):
                return await future
        except TimeoutError as err:
            raise BridgeError("The bridge did not answer in time", "timeout") from err
        finally:
            self._pending.pop(request_id, None)

    async def stop(self) -> None:
        self._running = False
        if self._ws is not None:
            await self._ws.close()
        self._fail_pending(BridgeError("Integration unloaded", "disconnected"))
