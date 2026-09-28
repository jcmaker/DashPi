#!/usr/bin/env python3
"""Pick the landing APK release from GitHub's releases JSON on stdin.

The Pages workflow downloads that tag only after apksigner accepts it.
Creation order does not matter: the highest app-vMAJOR.MINOR.PATCH wins.
"""

from __future__ import annotations

import json
import re
import sys


_TAG = re.compile(r"^app-v(\d+)\.(\d+)\.(\d+)$")
_APK_NAME = "DashPi.apk"


def releases_from_payload(payload: object) -> list | None:
    """Accept one releases page, or the outer array from `gh api --paginate --slurp`."""
    if not isinstance(payload, list):
        return None
    if payload and all(isinstance(page, list) for page in payload):
        flat: list = []
        for page in payload:
            flat.extend(page)
        return flat
    return payload


def select_landing_apk(releases: list[dict]) -> str | None:
    """Return the highest stable app-v tag that ships DashPi.apk."""
    best_tag: str | None = None
    best_version: tuple[int, int, int] | None = None
    for release in releases:
        if not isinstance(release, dict):
            continue
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str):
            continue
        match = _TAG.fullmatch(tag)
        if match is None:
            continue
        assets = release.get("assets") or []
        if not isinstance(assets, list):
            continue
        if not any(isinstance(asset, dict) and asset.get("name") == _APK_NAME for asset in assets):
            continue
        version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if best_version is None or version > best_version:
            best_version = version
            best_tag = tag
    return best_tag


def main() -> int:
    try:
        releases = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"::error::release list is not JSON ({exc})", file=sys.stderr)
        return 1
    releases = releases_from_payload(releases)
    if releases is None:
        print("::error::release list must be a JSON array", file=sys.stderr)
        return 1
    tag = select_landing_apk(releases)
    if tag is None:
        print("::error::no stable app-v* release with DashPi.apk to serve", file=sys.stderr)
        return 1
    print(tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
