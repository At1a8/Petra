#!/usr/bin/env python3
"""Print the newest daily sglang image on Docker Hub, e.g. rocm/sgl-dev:v0.5.23-rocm10-mi35x-20261103.

Tasks test the newest sglang unless the user names an image or a container: scripts/run_docker.sh
starts from this image, and the director compares the image a run uses with it.

    python3 scripts/latest_image.py                          # ROCm 10, MI35x (the default)
    python3 scripts/latest_image.py --variant rocm10-mi30x   # another GPU or ROCm

Only the daily sglang builds count (v<version>-<variant>-<YYYYMMDD>); the miles images in the same
repository are for reinforcement learning and are skipped. Prints nothing and exits 1 when Docker Hub
cannot be read or has no such tag. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

REPO = "rocm/sgl-dev"
VARIANT = "rocm10-mi35x"
API = "https://hub.docker.com/v2/repositories/%s/tags?page_size=100&ordering=last_updated&name=%s"


def daily_key(name: str, variant: str):
    """Sort key of a daily sglang tag for the variant (date, version), None for any other tag."""
    m = re.fullmatch(r"v(\d+(?:\.\d+)*)[0-9a-z.]*-%s-(\d{8})" % re.escape(variant), name)
    if not m:
        return None
    return m.group(2), tuple(int(x) for x in m.group(1).split("."))


def pick(results: list, variant: str) -> str:
    """The newest daily tag among Docker Hub tag records ({"name", "last_updated"}), '' if none."""
    best, best_key = "", None
    for t in results:
        key = daily_key(t.get("name", ""), variant)
        if key is None:
            continue
        key = key + (t.get("last_updated") or "",)
        if best_key is None or key > best_key:
            best, best_key = t["name"], key
    return best


def fetch(repo: str, variant: str, timeout: float, pages: int = 2) -> list:
    url = API % (repo, urllib.parse.quote(variant))
    results = []
    for _ in range(pages):
        with urllib.request.urlopen(url, timeout=timeout) as r:
            page = json.load(r)
        results += page.get("results") or []
        url = page.get("next")
        if not url:
            break
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Print the newest daily sglang image on Docker Hub.")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--variant", default=VARIANT, help="ROCm and GPU part of the tag (default %(default)s)")
    ap.add_argument("--timeout", type=float, default=20, help="seconds per request (default %(default)s)")
    a = ap.parse_args(argv)
    try:
        tag = pick(fetch(a.repo, a.variant, a.timeout), a.variant)
    except (OSError, ValueError) as e:
        print("latest_image: cannot read the %s tags on Docker Hub (%s)" % (a.repo, e), file=sys.stderr)
        return 1
    if not tag:
        print("latest_image: no daily %s tag for %s" % (a.repo, a.variant), file=sys.stderr)
        return 1
    print("%s:%s" % (a.repo, tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
