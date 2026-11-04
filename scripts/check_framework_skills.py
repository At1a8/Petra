#!/usr/bin/env python3
"""Check Petra's index of the framework's own skills against a framework checkout.

The index (knowledge/frameworks/<framework>/skills.md) names skills that live in the framework's
repository; roles read them from the task worktree. This reports the drift:

  missing    skills the index table names that the checkout does not have
  unindexed  skills the checkout has that the index never mentions

    python3 scripts/check_framework_skills.py --framework-dir /path/to/sglang [--out drift.json] [--md]

Exit code 1 when a named skill is missing. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

SKILL_DIRS = (".agents/skills", ".claude/skills", "python/sglang/multimodal_gen/.agents/skills")
NAME = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`")


def table_names(index_text: str) -> list:
    """Skill names in the Skills column of the index table (the third column)."""
    names = []
    for line in index_text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not line.lstrip().startswith("|") or set(cells[0]) <= {"-", " "}:
            continue
        names += NAME.findall(cells[2])
    return sorted(set(names))


def checkout_skills(framework_dir: str) -> list:
    found = set()
    for rel in SKILL_DIRS:
        root = os.path.join(framework_dir, rel)
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            if os.path.isfile(os.path.join(root, name, "SKILL.md")):
                found.add(name)
    return sorted(found)


def check(index_text: str, framework_dir: str) -> dict:
    named = table_names(index_text)
    present = checkout_skills(framework_dir)
    mentioned = set(NAME.findall(index_text))
    rc = subprocess.run(["git", "-C", framework_dir, "log", "-1", "--format=%h %cs"],
                        capture_output=True, text=True)
    return {
        "framework_dir": os.path.abspath(framework_dir),
        "commit": rc.stdout.strip() if rc.returncode == 0 else "",
        "named": len(named),
        "present": len(present),
        "missing": [n for n in named if n not in present],
        "unindexed": [n for n in present if n not in mentioned],
    }


def to_md(r: dict) -> str:
    lines = ["framework skills at %s (%s): %d named in the index, %d in the checkout"
             % (r["framework_dir"], r["commit"] or "no git", r["named"], r["present"])]
    lines.append("- missing (named, not in the checkout): " + (", ".join(r["missing"]) or "none"))
    lines.append("- unindexed (in the checkout, not in the index): " + (", ".join(r["unindexed"]) or "none"))
    return "\n".join(lines)


def main(argv=None) -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--framework-dir", required=True)
    ap.add_argument("--index", default=os.path.join(here, "knowledge", "frameworks", "sglang", "skills.md"))
    ap.add_argument("--out", help="write the JSON report here")
    ap.add_argument("--md", action="store_true", help="print a short markdown summary instead of JSON")
    a = ap.parse_args(argv)
    with open(a.index, encoding="utf-8") as f:
        report = check(f.read(), a.framework_dir)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    print(to_md(report) if a.md else json.dumps(report, indent=2))
    return 1 if report["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
