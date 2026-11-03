#!/usr/bin/env python3
"""Parse AMD Failure Tracker issues into failure clusters (knowledge/ci_triage.md §1).

The tracker bot keeps its state in an HTML comment `<!-- ci-failure-tracker-state: {...} -->`, keyed by
`test_file::test_function`. Each cluster reports its tests, statuses, the earliest `since` date named
in a status, first/last seen dates and one example error.

  scan_ci.py --out ci.json [--md ci.md]          # all open trackers
  scan_ci.py --tracker 45847 --out ci.json
  scan_ci.py --file body.md --out ci.json         # offline: a saved issue body
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _github as gh  # noqa: E402

DEFAULT_REPO = "sgl-project/sglang"
MARKER = "ci-failure-tracker-state:"
_SINCE = re.compile(r"since (\d{4}-\d\d-\d\d)")
_STATUS_HEAD = re.compile(r"^\s*([a-z][a-z \-]*?)\s*(\(|$)", re.I)


def parse_state(body: str) -> dict:
    """The tracker's entries ({key: entry}); empty when the body has no state block."""
    i = (body or "").find(MARKER)
    if i < 0:
        return {}
    text = body[i + len(MARKER):].lstrip()
    try:
        state, _ = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError:
        return {}
    if isinstance(state, dict) and isinstance(state.get("entries"), dict):
        return state["entries"]
    return state if isinstance(state, dict) else {}


def status_head(status: str) -> str:
    m = _STATUS_HEAD.match(status or "")
    return m.group(1).strip().lower() if m else (status or "").strip().lower()


def aggregate(entries: dict) -> list[dict]:
    clusters: dict[str, dict] = {}
    for key, e in entries.items():
        if not isinstance(e, dict):
            continue
        name = e.get("cluster") or "(no cluster)"
        c = clusters.setdefault(name, {"cluster": name, "tests": [], "statuses": collections.Counter(),
                                       "since": "", "first_seen": "", "last_seen": "", "example_error": "",
                                       "job_urls": []})
        c["tests"].append(key)
        st = e.get("status", "")
        c["statuses"][status_head(st)] += 1
        for d in _SINCE.findall(st):
            c["since"] = min(c["since"] or d, d)
        if e.get("first_seen"):
            c["first_seen"] = min(c["first_seen"] or e["first_seen"], e["first_seen"])
        if e.get("last_seen"):
            c["last_seen"] = max(c["last_seen"] or e["last_seen"], e["last_seen"])
        if not c["example_error"] and e.get("error"):
            c["example_error"] = e["error"][:300]
        if e.get("job_url") and len(c["job_urls"]) < 3:
            c["job_urls"].append(e["job_url"])
    out = []
    for c in clusters.values():
        c["n_tests"] = len(c["tests"])
        c["tests"] = sorted(c["tests"])[:10]
        c["statuses"] = dict(c["statuses"])
        out.append(c)
    return sorted(out, key=lambda c: (-c["n_tests"], c["cluster"]))


def trackers(repo: str, number: int | None) -> list[dict]:
    if number:
        return [gh.get(f"/repos/{repo}/issues/{number}")]
    return gh.search_issues(f'repo:{repo} is:issue is:open "Failure Tracker" in:title', max_pages=2)


def to_markdown(result: dict) -> str:
    lines = []
    for t in result["trackers"]:
        lines.append(f"## #{t['number']} {t['title']} (updated {t['updated_at']}) — "
                     f"{t['n_entries']} tests in {len(t['clusters'])} clusters\n")
        lines.append("| Tests | Statuses | Since | First / last seen | Cluster |")
        lines.append("|---|---|---|---|---|")
        for c in t["clusters"]:
            st = ", ".join(f"{k} {v}" for k, v in c["statuses"].items())
            lines.append(f"| {c['n_tests']} | {st} | {c['since'] or '-'} | {c['first_seen']} / {c['last_seen']} | "
                         f"{c['cluster'].replace('|', '/')} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--tracker", type=int, help="one tracker issue number")
    ap.add_argument("--file", help="parse a saved issue body instead of calling GitHub")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md")
    a = ap.parse_args()

    if a.file:
        issues = [{"number": 0, "title": Path(a.file).name, "updated_at": "", "state": "",
                   "body": Path(a.file).read_text()}]
    else:
        issues = trackers(a.repo, a.tracker)
    result = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "repo": a.repo, "trackers": []}
    for it in issues:
        entries = parse_state(it.get("body") or "")
        clusters = aggregate(entries)
        result["trackers"].append({"number": it.get("number"), "title": it.get("title", ""),
                                   "state": it.get("state", ""), "updated_at": it.get("updated_at", ""),
                                   "n_entries": len(entries), "clusters": clusters})
        print(f"[scan_ci] #{it.get('number')}: {len(entries)} tests, {len(clusters)} clusters", file=sys.stderr)
    Path(a.out).write_text(json.dumps(result, indent=1, ensure_ascii=False))
    if a.md:
        Path(a.md).write_text(to_markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
