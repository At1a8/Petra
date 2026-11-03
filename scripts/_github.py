"""Minimal GitHub REST client for Petra's scan scripts (standard library only).

A token from GITHUB_TOKEN or GH_TOKEN raises the limits (search 30/min, core 5000/h); without one,
search allows 10 requests per minute and core 60 per hour per IP, and the IP may be shared.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"


def _token() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def search_pause() -> float:
    return 2.2 if _token() else 6.5


def request(url: str, retries: int = 6) -> object:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "petra-scan"}
    tok = _token()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < retries - 1:
                wait = 15 * (attempt + 1)
                retry_after = e.headers.get("Retry-After")
                reset = e.headers.get("X-RateLimit-Reset")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                elif reset and reset.isdigit() and e.headers.get("X-RateLimit-Remaining") == "0":
                    wait = int(reset) - int(time.time()) + 1
                wait = max(1, min(wait, 120))
                print(f"[github] HTTP {e.code}, waiting {wait}s (attempt {attempt + 1}/{retries})", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"unreachable: {url}")


def get(path: str, params: dict | None = None) -> object:
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return request(url)


def paginate(path: str, params: dict | None = None, max_pages: int = 20) -> list:
    out: list = []
    p = dict(params or {})
    p.setdefault("per_page", 100)
    for page in range(1, max_pages + 1):
        p["page"] = page
        items = get(path, p)
        if not isinstance(items, list):
            break
        out.extend(items)
        if len(items) < p["per_page"]:
            break
    return out


def search_issues(query: str, per_page: int = 100, max_pages: int = 10) -> list:
    """All items of an issue/PR search (GitHub caps search results at 1000)."""
    out: list = []
    for page in range(1, max_pages + 1):
        d = get("/search/issues", {"q": query, "per_page": per_page, "page": page})
        items = d.get("items", []) if isinstance(d, dict) else []
        out.extend(items)
        total = d.get("total_count", 0) if isinstance(d, dict) else 0
        time.sleep(search_pause())
        if not items or page * per_page >= total:
            break
    return out
