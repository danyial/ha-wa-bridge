"""Propose a whatsapp-web.js update as a merge request.

Run by a scheduled GitLab CI job. Decision:

1. A newer npm release than the pinned version -> pin that release.
2. Otherwise, if the pin is a commit of wwebjs/whatsapp-web.js main and main
   moved on -> pin the new main head (WhatsApp Web breakage is usually fixed
   on main weeks before a release).
3. Otherwise nothing to do.

With an update it creates the branch deps/whatsapp-web.js-<ref>, updates
package.json and package-lock.json, bumps the shared version, pushes and
opens a merge request with glab. An existing branch of the same name means
the update was already proposed; the script then does nothing.

Needs: git, npm, glab; GITLAB_TOKEN (project access token, api +
write_repository) and GITLAB_HOST in the environment. `--dry-run` only
prints the decision and needs neither token nor glab.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIDGE = ROOT / "wa-bridge"
PACKAGE = "whatsapp-web.js"
REPO = "https://github.com/wwebjs/whatsapp-web.js"
TARBALL = "https://codeload.github.com/wwebjs/whatsapp-web.js/tar.gz/"


def run(*cmd: str, cwd: Path = ROOT, env: dict | None = None) -> str:
    result = subprocess.run(
        cmd, cwd=cwd, env=env, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def release_tuple(version: str) -> tuple[int, ...]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    if not match:
        raise ValueError(f"not a release version: {version}")
    return tuple(int(part) for part in match.groups())


def pinned() -> tuple[str, str | None]:
    """Return (installed version, pinned commit or None)."""
    spec = json.loads((BRIDGE / "package.json").read_text())["dependencies"][PACKAGE]
    lock = json.loads((BRIDGE / "package-lock.json").read_text())
    version = lock["packages"][f"node_modules/{PACKAGE}"]["version"]
    commit = spec.removeprefix(TARBALL) if spec.startswith(TARBALL) else None
    return version, commit


def decide(
    version: str, commit: str | None, npm_latest: str, main_head: str
) -> tuple[str, str] | None:
    """Return (npm spec, short ref for the branch name) or None."""
    if release_tuple(npm_latest) > release_tuple(version):
        return npm_latest, npm_latest
    if commit and main_head != commit:
        return TARBALL + main_head, main_head[:12]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    version, commit = pinned()
    npm_latest = run("npm", "view", PACKAGE, "version")
    main_head = run("git", "ls-remote", REPO, "refs/heads/main").split()[0]
    print(f"pinned {version} ({commit or 'npm release'}); npm latest {npm_latest}")
    print(f"main head {main_head}")

    target = decide(version, commit, npm_latest, main_head)
    if target is None:
        print("up to date")
        return 0
    spec, ref = target
    branch = f"deps/whatsapp-web.js-{ref}"
    print(f"update -> {spec} on {branch}")
    if args.dry_run:
        return 0

    if run("git", "ls-remote", "--heads", "origin", branch):
        print(f"{branch} already exists, update was proposed before")
        return 0

    run("git", "switch", "-c", branch)
    run(
        "npm",
        "install",
        "--package-lock-only",
        "--ignore-scripts",
        "--save-exact",
        f"{PACKAGE}@{spec}",
        cwd=BRIDGE,
    )
    new_version = run(sys.executable, "scripts/bump_version.py", "--next")
    run("git", "add", "wa-bridge", "custom_components/whatsapp/manifest.json")
    run("git", "commit", "-m", f"build(deps): whatsapp-web.js {ref}")
    run("git", "push", "origin", f"HEAD:refs/heads/{branch}")

    compare = f"{REPO}/compare/{commit or 'v' + version}...{spec.removeprefix(TARBALL)}"
    description = (
        f"Automatic update of whatsapp-web.js: `{version}` "
        f"({commit or 'npm'}) -> `{spec.removeprefix(TARBALL)}`.\n\n"
        f"Changes: {compare}\n\n"
        f"Version bumped to `{new_version}`. The image build job in this "
        "pipeline only proves that the add-on builds; check pairing, receiving "
        "and sending on a real session before merging."
    )
    run(
        "glab",
        "mr",
        "create",
        "--source-branch",
        branch,
        "--target-branch",
        os.environ.get("CI_DEFAULT_BRANCH", "main"),
        "--title",
        f"build(deps): whatsapp-web.js {ref}",
        "--description",
        description,
        "--label",
        "dependencies",
        "--yes",
    )
    print("merge request created")
    return 0


if __name__ == "__main__":
    sys.exit(main())
