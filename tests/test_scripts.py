"""Repository scripts (version handling)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import bump_version  # noqa: E402
import wwebjs_update  # noqa: E402


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("3.0.0-dev.1", "3.0.0-dev.2"),
        ("3.0.0-dev.9", "3.0.0-dev.10"),
        ("3.0.0-rc", "3.0.0-rc.1"),
        ("3.0.0", "3.0.1"),
    ],
)
def test_next_version(version: str, expected: str) -> None:
    assert bump_version.next_version(version) == expected


def test_next_version_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        bump_version.next_version("v3")


def test_set_version_updates_all_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text('name: "X"\nversion: "1.0.0"\nslug: x\n')
    package = tmp_path / "package.json"
    package.write_text(json.dumps({"name": "x", "version": "1.0.0"}))
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text(
        json.dumps({"version": "1.0.0", "packages": {"": {"version": "1.0.0"}}})
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"domain": "whatsapp", "version": "1.0.0"}))
    for name, path in {
        "CONFIG": config,
        "PACKAGE": package,
        "LOCKFILE": lockfile,
        "MANIFEST": manifest,
    }.items():
        monkeypatch.setattr(bump_version, name, path)

    bump_version.set_version("3.0.0-dev.2")

    assert 'version: "3.0.0-dev.2"' in config.read_text()
    assert json.loads(package.read_text())["version"] == "3.0.0-dev.2"
    assert json.loads(manifest.read_text())["version"] == "3.0.0-dev.2"
    lock = json.loads(lockfile.read_text())
    assert lock["version"] == lock["packages"][""]["version"] == "3.0.0-dev.2"

    with pytest.raises(ValueError):
        bump_version.set_version("latest")


SHA_OLD = "a" * 40
SHA_NEW = "b" * 40


@pytest.mark.parametrize(
    ("version", "commit", "npm_latest", "main_head", "expected"),
    [
        # New npm release beats a commit pin.
        ("1.34.7", SHA_OLD, "1.35.0", SHA_NEW, ("1.35.0", "1.35.0")),
        ("1.34.7", None, "1.35.0", SHA_NEW, ("1.35.0", "1.35.0")),
        # Commit pin follows main.
        (
            "1.34.7",
            SHA_OLD,
            "1.34.7",
            SHA_NEW,
            (wwebjs_update.TARBALL + SHA_NEW, SHA_NEW[:12]),
        ),
        # Up to date.
        ("1.34.7", SHA_OLD, "1.34.7", SHA_OLD, None),
        # A release pin does not chase main.
        ("1.34.7", None, "1.34.7", SHA_NEW, None),
        # Never downgrade.
        ("1.35.0", None, "1.34.7", SHA_NEW, None),
    ],
)
def test_wwebjs_decide(version, commit, npm_latest, main_head, expected) -> None:
    assert wwebjs_update.decide(version, commit, npm_latest, main_head) == expected
