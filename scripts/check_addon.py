"""Offline sanity check of the add-on config (wa-bridge/config.yaml).

The official add-on linter runs as a GitHub Action; this covers the
rules that matter here, without network access.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ADDON = ROOT / "wa-bridge"
REQUIRED = ("name", "version", "slug", "description", "arch")
SUPPORTED_ARCH = {"amd64", "aarch64"}


def main() -> int:
    errors: list[str] = []
    config = yaml.safe_load((ADDON / "config.yaml").read_text())

    errors.extend(
        f"config.yaml: '{key}' missing" for key in REQUIRED if key not in config
    )
    if unknown := set(config.get("arch", [])) - SUPPORTED_ARCH:
        # Warn only: dropping armv7 is part of the image rework.
        print(f"WARNING: arch not supported by Home Assistant: {sorted(unknown)}")

    options = config.get("options") or {}
    schema = config.get("schema") or {}
    if missing := set(options) - set(schema):
        errors.append(f"options without schema: {sorted(missing)}")
    if extra := {
        k for k in set(schema) - set(options) if not str(schema[k]).endswith("?")
    }:
        errors.append(f"required schema keys without default option: {sorted(extra)}")

    if "image" not in config and not (ADDON / "Dockerfile").is_file():
        errors.append("neither 'image' nor a Dockerfile")

    for name in ("repository.yaml",):
        if not (ROOT / name).is_file():
            errors.append(f"{name} missing")

    for error in errors:
        print(f"ERROR: {error}")
    print("add-on config ok" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
