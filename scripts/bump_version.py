"""Set the shared version of add-on, bridge and integration.

python scripts/bump_version.py 3.0.0      # explicit
python scripts/bump_version.py --next     # 3.0.0-dev.1 -> 3.0.0-dev.2, 3.0.0 -> 3.0.1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "wa-bridge" / "config.yaml"
PACKAGE = ROOT / "wa-bridge" / "package.json"
LOCKFILE = ROOT / "wa-bridge" / "package-lock.json"
MANIFEST = ROOT / "custom_components" / "whatsapp" / "manifest.json"

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


def current() -> str:
    return json.loads(MANIFEST.read_text())["version"]


def next_version(version: str) -> str:
    match = SEMVER.match(version)
    if not match:
        raise ValueError(f"not a semantic version: {version}")
    major, minor, patch, pre = match.groups()
    if pre:
        parts = pre.split(".")
        if parts[-1].isdigit():
            parts[-1] = str(int(parts[-1]) + 1)
            return f"{major}.{minor}.{patch}-{'.'.join(parts)}"
        return f"{major}.{minor}.{patch}-{pre}.1"
    return f"{major}.{minor}.{int(patch) + 1}"


def set_version(version: str) -> None:
    if not SEMVER.match(version):
        raise ValueError(f"not a semantic version: {version}")
    text = CONFIG.read_text()
    new_text, count = re.subn(
        r"^version: .*$", f'version: "{version}"', text, count=1, flags=re.MULTILINE
    )
    if count != 1:
        raise ValueError("wa-bridge/config.yaml: no version line")
    CONFIG.write_text(new_text)
    for path in (PACKAGE, MANIFEST):
        data = json.loads(path.read_text())
        data["version"] = version
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if LOCKFILE.is_file():
        lock = json.loads(LOCKFILE.read_text())
        lock["version"] = version
        lock["packages"][""]["version"] = version
        LOCKFILE.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("version", nargs="?")
    group.add_argument("--next", action="store_true")
    args = parser.parse_args()
    version = next_version(current()) if args.next else args.version
    set_version(version)
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
