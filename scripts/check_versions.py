"""Fail if the add-on, bridge and integration versions disagree.

The add-on and the integration speak one WebSocket protocol and are
released together, so they share one version number.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def addon_version() -> str:
    text = (ROOT / "wa-bridge" / "config.yaml").read_text()
    match = re.search(r'^version:\s*"?([^"\s]+)"?\s*$', text, re.MULTILINE)
    if not match:
        raise SystemExit("wa-bridge/config.yaml: no version")
    return match.group(1)


def main() -> int:
    versions = {
        "wa-bridge/config.yaml": addon_version(),
        "wa-bridge/package.json": json.loads(
            (ROOT / "wa-bridge" / "package.json").read_text()
        )["version"],
        "custom_components/whatsapp/manifest.json": json.loads(
            (ROOT / "custom_components" / "whatsapp" / "manifest.json").read_text()
        )["version"],
    }
    for path, version in versions.items():
        print(f"{version:<16} {path}")
    if len(set(versions.values())) != 1:
        print("ERROR: versions differ")
        return 1
    print("versions ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
