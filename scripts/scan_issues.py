#!/usr/bin/env python3
"""Collect open AMD-related issues with the facts triage needs (knowledge/issue_triage.md).

For each issue: kind (user issue, roadmap, tracker, internal), age, reporter association, linked PRs
that cite the issue explicitly (with their state), replies from anyone but the reporter (with
--with-comments), and the projected date of sglang's 60-day inactivity auto-close. It assigns no
priority: that is the triager's judgement.

  scan_issues.py --out issues.json [--md issues.md] [--with-comments] [--no-prs] [--limit N]
  scan_issues.py --issue 38849 --with-comments --out issue.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _github as gh  # noqa: E402

DEFAULT_REPO = "sgl-project/sglang"
TITLE_KEYWORDS = [
    "AMD",
    "ROCm",
    "MI300X OR MI355X OR MI325X OR MI308X OR MI300",
    "aiter OR gfx950 OR gfx942 OR HIP OR mori",
]
MAINTAINER_ASSOC = {"COLLABORATOR", "MEMBER", "OWNER"}
INACTIVE_DAYS = 60

_ROADMAP = re.compile(r"\broadmap\b", re.I)
_TRACKER = re.compile(r"\[failure tracker\]", re.I)
_INTERNAL = re.compile(r"\[aiter-upgrade\]|\[tracking\]|test-first ci|pr readiness|scout status|"
                       r"prs for community review", re.I)


def classify_kind(title: str, labels: list[str]) -> str:
    """user | roadmap | tracker | internal (issue_triage.md §1)."""
    if "ci-failure-tracker" in labels or _TRACKER.search(title):
        return "tracker"
    if _ROADMAP.search(title):
        return "roadmap"
    if _INTERNAL.search(title):
        return "internal"
    return "user"


def cites_issue(text: str, number: int) -> bool:
    """True when a PR title/body refers to the issue explicitly (#N, issue N, or its URL)."""
    return re.search(rf"(#|/issues/|/pull/|\bissue\s+){number}\b", text or "", re.I) is not None


def parse_time(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def projected_auto_close(updated_at: str, days: int = INACTIVE_DAYS) -> str:
    """Date (UTC) of the first daily 00:00 UTC run after updated_at + days."""
    due = parse_time(updated_at) + dt.timedelta(days=days)
    run = due.replace(hour=0, minute=0, second=0, microsecond=0)
    if run < due:
        run += dt.timedelta(days=1)
    return run.date().isoformat()


def reply_status(comments: list[dict], reporter: str) -> dict:
    others = [c for c in comments
              if c.get("user", {}).get("login") not in (reporter, None)
              and not c.get("user", {}).get("login", "").endswith("[bot]")]
    return {
        "replies_from_others": len(others),
        "repliers": sorted({c["user"]["login"] for c in others}),
        "maintainer_replied": any(c.get("author_association") in MAINTAINER_ASSOC for c in others),
        "only_reporter_or_bots": len(comments) > 0 and not others,
    }


def linked_prs(repo: str, number: int) -> list[dict]:
    items = gh.search_issues(f"repo:{repo} is:pr {number} in:title,body", per_page=50, max_pages=1)
    out = []
    for it in items:
        if it.get("number") == number:
            continue
        if not cites_issue((it.get("title") or "") + "\n" + (it.get("body") or ""), number):
            continue
        merged = (it.get("pull_request") or {}).get("merged_at")
        out.append({
            "number": it["number"],
            "title": it.get("title", ""),
            "state": "merged" if merged else it.get("state", ""),
            "author": (it.get("user") or {}).get("login", ""),
            "created_at": it.get("created_at", ""),
            "merged_at": merged or "",
            "updated_at": it.get("updated_at", ""),
        })
    return sorted(out, key=lambda p: p["created_at"])


def summarize(it: dict, now: dt.datetime) -> dict:
    labels = [l["name"] for l in it.get("labels", [])]
    created = it.get("created_at", "")
    return {
        "number": it["number"],
        "title": it.get("title", ""),
        "url": it.get("html_url", ""),
        "kind": classify_kind(it.get("title", ""), labels),
        "labels": labels,
        "reporter": (it.get("user") or {}).get("login", ""),
        "association": it.get("author_association", ""),
        "created_at": created,
        "updated_at": it.get("updated_at", ""),
        "age_days": (now - parse_time(created)).days if created else None,
        "comments": it.get("comments", 0),
        "reactions": (it.get("reactions") or {}).get("total_count", 0),
        "projected_auto_close": projected_auto_close(it["updated_at"]) if it.get("updated_at") else "",
    }


def collect(repo: str, issue: int | None, limit: int | None) -> list[dict]:
    if issue:
        return [gh.get(f"/repos/{repo}/issues/{issue}")]
    seen: dict[int, dict] = {}
    for kw in TITLE_KEYWORDS:
        for it in gh.search_issues(f"repo:{repo} is:issue is:open {kw} in:title"):
            seen.setdefault(it["number"], it)
    items = sorted(seen.values(), key=lambda i: i["number"])
    return items[:limit] if limit else items


def to_markdown(rows: list[dict]) -> str:
    lines = ["| Issue | Age (d) | Reporter | Replies (others) | Linked PRs | Auto-close | Title |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        prs = ", ".join(f"#{p['number']} {p['state']}" for p in r.get("linked_prs", [])) or "none"
        rep = r.get("replies", {}).get("replies_from_others", "?") if "replies" in r else "?"
        lines.append(f"| #{r['number']} | {r['age_days']} | {r['reporter']} ({r['association']}) | {rep} | "
                     f"{prs} | {r['projected_auto_close']} | {r['title'].replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--issue", type=int, help="one issue instead of the keyword search")
    ap.add_argument("--with-comments", action="store_true", help="fetch comments to compute replies (core API)")
    ap.add_argument("--no-prs", action="store_true", help="skip the linked-PR search (one search call per issue)")
    ap.add_argument("--limit", type=int, help="only the first N issues (testing)")
    ap.add_argument("--out", required=True, help="JSON output path")
    ap.add_argument("--md", help="optional Markdown table for user issues")
    a = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    items = collect(a.repo, a.issue, a.limit)
    users, excluded = [], []
    for it in items:
        if "pull_request" in it:
            continue
        row = summarize(it, now)
        if row["kind"] != "user" and not a.issue:
            excluded.append({k: row[k] for k in ("number", "title", "kind")})
            continue
        if not a.no_prs:
            row["linked_prs"] = linked_prs(a.repo, row["number"])
        if a.with_comments and row["comments"]:
            comments = gh.paginate(f"/repos/{a.repo}/issues/{row['number']}/comments")
            row["replies"] = reply_status(comments, row["reporter"])
            row["last_comments"] = [{"author": c["user"]["login"], "association": c.get("author_association", ""),
                                     "created_at": c["created_at"], "body": (c.get("body") or "")[:600]}
                                    for c in comments[-4:]]
        elif a.with_comments:
            row["replies"] = reply_status([], row["reporter"])
        users.append(row)
        print(f"[scan_issues] #{row['number']} {row['kind']} prs={len(row.get('linked_prs', []))}", file=sys.stderr)

    out = {"generated_at": now.isoformat(timespec="seconds"), "repo": a.repo,
           "auto_close_rule": f"open issues untouched for {INACTIVE_DAYS} days are closed by a daily 00:00 UTC job",
           "issues": users, "excluded": excluded}
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    if a.md:
        Path(a.md).write_text(to_markdown(users))
    print(f"[scan_issues] {len(users)} issue(s), {len(excluded)} excluded -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
