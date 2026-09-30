"""No blocking I/O or CPU work on the event loop (media, MIME types, QR code).

Home Assistant's own detector skips open() and friends in tests, so these
calls are wrapped here and must not run on the event loop thread.
"""

from __future__ import annotations

import asyncio
import builtins
import mimetypes
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
import qrcode
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.whatsapp.const import DOMAIN

from .conftest import FakeBridge


@pytest.fixture
def loop_calls(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> Iterator[list[str]]:
    """Names of watched calls made on the event loop thread."""
    loop_thread = threading.get_ident()  # fixtures run on the loop thread
    seen: list[str] = []

    def watch(name: str, func):
        def wrapper(*args, **kwargs):
            if threading.get_ident() == loop_thread:
                seen.append(name)
            return func(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(builtins, "open", watch("open", builtins.open))
    monkeypatch.setattr(
        mimetypes, "guess_type", watch("mimetypes.guess_type", mimetypes.guess_type)
    )
    monkeypatch.setattr(qrcode, "make", watch("qrcode.make", qrcode.make))
    yield seen


async def test_media_path_reads_in_executor(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    bridge: FakeBridge,
    tmp_path: Path,
    loop_calls: list[str],
) -> None:
    picture = tmp_path / "klingel.jpg"
    await hass.async_add_executor_job(picture.write_bytes, b"\xff\xd8jpeg")
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    await hass.services.async_call(
        DOMAIN,
        "send_message",
        {"number": "49", "message": "m", "media_path": str(picture)},
        blocking=True,
    )
    assert bridge.received[0]["media"]["mimetype"] == "image/jpeg"
    assert loop_calls == []


async def test_media_url_guesses_type_in_executor(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    bridge: FakeBridge,
    loop_calls: list[str],
) -> None:
    # No usable Content-Type: the MIME type is guessed from the file name.
    bridge.media["cam.png"] = (b"\x89PNG", {"Content-Type": ""})
    await hass.services.async_call(
        DOMAIN,
        "send_message",
        {
            "number": "49",
            "message": "m",
            "media_url": f"http://{bridge.base}/media/cam.png",
        },
        blocking=True,
    )
    assert bridge.received[0]["media"]["mimetype"] == "image/png"
    assert loop_calls == []


async def test_qr_code_rendered_in_executor(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    bridge: FakeBridge,
    loop_calls: list[str],
) -> None:
    await bridge.push({"type": "status", "status": "qr"})
    await bridge.push({"type": "qr", "data": "2@abc"})
    for _ in range(100):
        await hass.async_block_till_done()
        if setup_entry.runtime_data.qr_png:
            break
        await asyncio.sleep(0.02)
    assert setup_entry.runtime_data.qr_png
    assert loop_calls == []


async def test_watcher_catches_loop_calls(loop_calls: list[str]) -> None:
    """The fixture itself works: open() on the loop is recorded."""
    with open(__file__, "rb") as file:  # noqa: ASYNC230
        file.read(1)
    assert loop_calls == ["open"]
