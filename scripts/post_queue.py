#!/usr/bin/env python3
"""Post a scan's daily report as an issue in Petra's own GitHub repository, one issue per UTC day.

    python3 scripts/post_queue.py --body RUN_DIR/daily_report.md --date 2026-11-06
    python3 scripts/post_queue.py --body RUN_DIR/daily_report.md --dry-run   # what it would do
    python3 scripts/post_queue.py --latest     # the newest report issue: date, URL, age, body (read only)

Petra posts only to its own repository. It posts with PETRA_REPO_TOKEN when set, else GITHUB_TOKEN: one
fine-grained token for this repository alone (README step 1), which reads every public repository and
can write to no other, so nothing can reach upstream. A second scan the
same day updates that day's issue; a new day's issue closes the open earlier ones as superseded. The
repository is public, so the body must be too: a body that names a local path, this machine or an
internal site is refused. The repository defaults to the origin of the checkout this script is in.
Standard library only; --latest reads with GITHUB_TOKEN when set.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
MARKER = "<!-- petra:task-queue -->"
LOCAL = re.compile(r"(?<![\w.-])/(?:data\d*|mnt|home|root|workspace|sgl-workspace|apps|shared|nfs_shared1|kmd2|opt|tmp)/"
                   r"|confluence|jira\.", re.I)


def title(date: str) -> str:
    return "Petra daily report %s" % date


def age_hours(stamp: str, now: dt.datetime | None = None) -> float:
    """Hours since a GitHub timestamp (2026-11-09T01:11:40Z)."""
    then = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return round(((now or dt.datetime.now(dt.timezone.utc)) - then).total_seconds() / 3600, 1)


def repo_from_url(url: str) -> str:
    """owner/name of a GitHub remote URL (https or ssh), '' for anything else."""
    m = re.match(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?/?$", url.strip())
    return m.group(1) if m else ""


def default_repo() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        url = subprocess.run(["git", "-C", here, "remote", "get-url", "origin"], capture_output=True, text=True).stdout
    except OSError:
        return ""
    return repo_from_url(url)


def leaks(body: str, host: str = "") -> list:
    """Lines that would make something private public: local paths, this machine, internal sites."""
    out = []
    for n, line in enumerate(body.splitlines(), 1):
        if LOCAL.search(line) or (host and host.lower() in line.lower()):
            out.append("%d: %s" % (n, line.strip()[:160]))
    return out


def queue_issues(items: list) -> list:
    """Petra's queue issues among GitHub issue records (pull requests left out)."""
    return [i for i in items if "pull_request" not in i and MARKER in (i.get("body") or "")]


def plan(open_queues: list, date: str) -> dict:
    """Update today's open issue, or create it and close every other open one."""
    today = [i for i in open_queues if i.get("title") == title(date)]
    if today:
        return {"action": "update", "number": today[0]["number"],
                "close": [i["number"] for i in open_queues if i["number"] != today[0]["number"]]}
    return {"action": "create", "number": None, "close": [i["number"] for i in open_queues]}


def write_token() -> str:
    """The token that posts: PETRA_REPO_TOKEN, else the GITHUB_TOKEN the scan reads with."""
    return os.environ.get("PETRA_REPO_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def api(method: str, path: str, token: str = "", data: dict | None = None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(data).encode() if data else None,
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "petra-post-queue",
                                          **({"Authorization": "Bearer " + token} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def latest(repo: str, token: str = "") -> dict:
    items = queue_issues(api("GET", "/repos/%s/issues?state=all&per_page=50&sort=created&direction=desc" % repo, token))
    if not items:
        return {}
    i = items[0]
    m = re.search(r"(\d{4}-\d{2}-\d{2})", i.get("title", ""))
    updated = i.get("updated_at") or i.get("created_at") or ""
    return {"date": m.group(1) if m else "", "number": i["number"], "url": i.get("html_url", ""),
            "state": i.get("state", ""), "created_at": i.get("created_at", ""), "updated_at": updated,
            "age_hours": age_hours(updated) if updated else None, "body": i.get("body", "")}


def post(repo: str, body: str, date: str, token: str, dry_run: bool = False) -> dict:
    open_queues = queue_issues(api("GET", "/repos/%s/issues?state=open&per_page=100" % repo, token))
    p = plan(open_queues, date)
    text = body.rstrip() + "\n\n" + MARKER + "\n"
    if dry_run:
        return {"dry_run": True, "repo": repo, "title": title(date), **p}
    if p["action"] == "update":
        issue = api("PATCH", "/repos/%s/issues/%d" % (repo, p["number"]), token, {"body": text})
    else:
        issue = api("POST", "/repos/%s/issues" % repo, token, {"title": title(date), "body": text, "labels": ["task-queue"]})
    for n in p["close"]:
        api("POST", "/repos/%s/issues/%d/comments" % (repo, n), token, {"body": "Superseded by #%d." % issue["number"]})
        api("PATCH", "/repos/%s/issues/%d" % (repo, n), token, {"state": "closed", "state_reason": "completed"})
    return {"action": p["action"] + "d", "url": issue.get("html_url", ""), "number": issue["number"], "closed": p["close"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Post a scan's task queue as an issue in Petra's own repository.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--body", help="the issue body, e.g. RUN_DIR/daily_report.md")
    g.add_argument("--latest", action="store_true", help="print the newest report issue and exit")
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"), help="UTC day (default today)")
    ap.add_argument("--repo", default="", help="owner/name (default: the origin of this checkout)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be posted, closed or updated")
    a = ap.parse_args(argv)
    repo = a.repo or default_repo()
    if not repo:
        print("post_queue: no GitHub repository (set --repo owner/name)", file=sys.stderr)
        return 1
    try:
        if a.latest:
            print(json.dumps(latest(repo, os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""), indent=1))
            return 0
        body = open(a.body, encoding="utf-8").read()
        bad = leaks(body, socket.gethostname())
        if bad:
            print("post_queue: not posted; the body names something local or internal:\n  " + "\n  ".join(bad), file=sys.stderr)
            return 3
        token = write_token()
        if not token and not a.dry_run:
            print("post_queue: no GITHUB_TOKEN or PETRA_REPO_TOKEN (README step 1); post later with:\n  python3 %s --body %s --date %s"
                  % (sys.argv[0], a.body, a.date), file=sys.stderr)
            return 2
        print(json.dumps(post(repo, body, a.date, token, a.dry_run), indent=1))
        return 0
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print("post_queue: the token cannot write to %s (HTTP %d; a read-only GITHUB_TOKEN? README step 1); post "
                  "later with:\n  python3 %s --body %s --date %s" % (repo, e.code, sys.argv[0], a.body, a.date), file=sys.stderr)
            return 2
        print("post_queue: %s" % e, file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, ValueError) as e:
        print("post_queue: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
