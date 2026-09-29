"""Runtime state of a WhatsApp config entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .client import WhatsAppBridge
from .const import DOMAIN

# Bridge states (wa-bridge lib/status.js) plus the integration's own.
BRIDGE_STATES = [
    "initializing",
    "qr",
    "authenticated",
    "ready",
    "unresponsive",
    "disconnected",
    "auth_failure",
]
BRIDGE_OFFLINE = "bridge_offline"
STATES = [*BRIDGE_STATES, BRIDGE_OFFLINE]


@dataclass
class WhatsAppData:
    """What the entities show; updated from bridge frames."""

    bridge: WhatsAppBridge
    status: dict[str, Any] = field(default_factory=dict)
    qr_png: bytes | None = None
    qr_updated: datetime | None = None

    @property
    def state(self) -> str:
        if not self.bridge.connected:
            return BRIDGE_OFFLINE
        state = self.status.get("status")
        return state if state in BRIDGE_STATES else "initializing"


type WhatsAppConfigEntry = ConfigEntry[WhatsAppData]


def signal_update(entry: ConfigEntry) -> str:
    """Dispatcher signal sent when anything shown by the entities changed."""
    return f"{DOMAIN}_{entry.entry_id}_update"
