#!/usr/bin/env python3
"""Propose the curator's knowledge/ changes as a pull request to Petra's own repository.

    python3 scripts/propose_knowledge.py --run-dir RUN_DIR --body RUN_DIR/knowledge_pr.md
    python3 scripts/propose_knowledge.py --run-dir RUN_DIR --body RUN_DIR/knowledge_pr.md --dry-run

Only changes under knowledge/ go in. They are applied as a patch onto the current origin/main in a
throwaway worktree, committed on petra/knowledge/<run directory name> and pushed there, never to main;
the pull request targets main and a human merges it. Once it is open, those files are restored in the
checkout, so later runs read knowledge/ as merged, not as proposed; a re-run updates the same branch
and pull request. It pushes with PETRA_REPO_TOKEN when set, else GITHUB_TOKEN: one fine-grained token for
this repository alone (README step 1). The repository is public: added lines or a body that name a
local path, this machine or an internal site stop it, as in scripts/post_queue.py. Without the token,
or on any failure, the changes stay where they are. Standard library and git only.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from post_queue import api, default_repo, leaks, write_token  # noqa: E402

PETRA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = "<!-- petra:knowledge -->"
AUTHOR = ["-c", "user.name=Petra curator", "-c", "user.email=petra-curator@users.noreply.github.com"]


def git(repo: str, *args, check: bool = True, env: dict | None = None) -> str:
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                       env={**os.environ, **(env or {})})
    if check and p.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args[:2]), (p.stderr or p.stdout).strip()[:300]))
    return p.stdout


def changed(petra: str) -> tuple[list, list]:
    """(tracked, untracked) paths under knowledge/ that differ from HEAD."""
    tracked, untracked = [], []
    entries = iter(git(petra, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "knowledge/").split("\0"))
    for e in entries:
        if len(e) <= 3:
            continue
        (untracked if e[:2] == "??" else tracked).append(e[3:])
        if e[0] in "RC":
            tracked.append(next(entries, ""))  # a rename's source: gone from the tree
    return [t for t in tracked if t], untracked


def patch(petra: str, tracked: list, untracked: list) -> str:
    out = git(petra, "diff", "HEAD", "--binary", "--", *tracked) if tracked else ""
    for f in untracked:
        out += git(petra, "diff", "--no-index", "--binary", "--", "/dev/null", f, check=False)
    return out


def added(diff: str) -> str:
    return "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))


def auth_env(token: str) -> dict:
    """The token as an HTTP header in git's environment, never on a command line."""
    basic = base64.b64encode(("x-access-token:%s" % token).encode()).decode()
    return {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + basic}


def commit_branch(petra: str, branch: str, diff: str, title: str, run: str, push_url: str, token: str) -> str:
    """Apply the patch onto origin/main in a throwaway worktree, commit, push the branch; the commit."""
    git(petra, "fetch", "-q", push_url, "+refs/heads/main:refs/remotes/origin/main", env=auth_env(token))
    wt = tempfile.mkdtemp(prefix="petra-knowledge-")
    os.rmdir(wt)
    git(petra, "worktree", "add", "-q", "--detach", wt, "origin/main")
    try:
        git(wt, "checkout", "-q", "-B", branch)
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as f:
            f.write(diff)
        try:
            git(wt, "apply", "--3way", "--index", f.name)
        finally:
            os.unlink(f.name)
        git(wt, *AUTHOR, "commit", "-q", "-m", title, "-m", "From the Petra run %s." % run)
        sha = git(wt, "rev-parse", "HEAD").strip()
        git(wt, "push", "-q", "--force", push_url, "HEAD:refs/heads/%s" % branch, env=auth_env(token))
        return sha
    finally:
        git(petra, "worktree", "remove", "--force", wt, check=False)
        git(petra, "branch", "-D", branch, check=False)


def open_pr(repo: str, branch: str, title: str, body: str, token: str) -> dict:
    owner = repo.split("/")[0]
    text = body.rstrip() + "\n\n" + MARKER + "\n"
    found = api("GET", "/repos/%s/pulls?state=open&head=%s:%s" % (repo, owner, branch), token)
    if found:
        pr = api("PATCH", "/repos/%s/pulls/%d" % (repo, found[0]["number"]), token, {"body": text})
        return {"action": "updated", "url": pr.get("html_url", ""), "number": pr["number"]}
    pr = api("POST", "/repos/%s/pulls" % repo, token, {"title": title, "head": branch, "base": "main", "body": text})
    return {"action": "created", "url": pr.get("html_url", ""), "number": pr["number"]}


def restore(petra: str, tracked: list, untracked: list) -> None:
    """Put knowledge/ back as HEAD has it: the changes now live on the pull request's branch."""
    if tracked:
        git(petra, "checkout", "HEAD", "--", *tracked)
    for f in untracked:
        path = os.path.join(petra, f)
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
        d = os.path.dirname(path)
        while d.startswith(os.path.join(petra, "knowledge") + os.sep) and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
            d = os.path.dirname(d)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Propose the curator's knowledge/ changes as a pull request.")
    ap.add_argument("--run-dir", required=True, help="the run whose curator made the changes")
    ap.add_argument("--body", required=True, help="the pull request's description, e.g. RUN_DIR/knowledge_pr.md")
    ap.add_argument("--title", default="", help="default: knowledge: what <run> learned")
    ap.add_argument("--repo", default="", help="owner/name (default: the origin of this checkout)")
    ap.add_argument("--petra-dir", default=PETRA, help=argparse.SUPPRESS)
    ap.add_argument("--push-url", default="", help=argparse.SUPPRESS)
    ap.add_argument("--dry-run", action="store_true", help="show what would be proposed")
    a = ap.parse_args(argv)
    run = os.path.basename(os.path.normpath(a.run_dir))
    branch, title = "petra/knowledge/%s" % run, a.title or "knowledge: what %s learned" % run
    try:
        tracked, untracked = changed(a.petra_dir)
        if not tracked and not untracked:
            print(json.dumps({"action": "none", "reason": "no changes under knowledge/"}))
            return 0
        diff = patch(a.petra_dir, tracked, untracked)
        body = open(a.body, encoding="utf-8").read()
        bad = leaks(added(diff), socket.gethostname()) + leaks(body, socket.gethostname())
        if bad:
            print("propose_knowledge: not proposed; it names something local or internal:\n  " + "\n  ".join(bad), file=sys.stderr)
            return 3
        files = tracked + untracked
        if a.dry_run:
            print(json.dumps({"dry_run": True, "branch": branch, "title": title, "files": files}, indent=1))
            return 0
        token = write_token()
        repo = a.repo or default_repo()
        later = "Propose them later with:\n  python3 %s --run-dir %s --body %s" % (sys.argv[0], a.run_dir, a.body)
        if not token or not repo:
            print("propose_knowledge: %s; the changes stay in %s/knowledge. %s" % (
                "no GITHUB_TOKEN or PETRA_REPO_TOKEN" if not token else "no GitHub repository", a.petra_dir, later),
                file=sys.stderr)
            return 2
        sha = commit_branch(a.petra_dir, branch, diff, title, run, a.push_url or "https://github.com/%s.git" % repo, token)
        pr = open_pr(repo, branch, title, body, token)
        restore(a.petra_dir, tracked, untracked)
        print(json.dumps({**pr, "branch": branch, "commit": sha, "files": files}, indent=1))
        return 0
    except urllib.error.HTTPError as e:
        print("propose_knowledge: HTTP %d from GitHub%s; the changes stay where they are" % (
            e.code, " (the token cannot write to the repository: a read-only GITHUB_TOKEN? README step 1)"
            if e.code in (401, 403) else ""), file=sys.stderr)
        return 2 if e.code in (401, 403) else 1
    except RuntimeError as e:
        denied = any(k in str(e) for k in ("403", "401", "Authentication failed", "Permission to"))
        print("propose_knowledge: %s; the changes stay where they are%s" % (
            e, " (the token cannot push: a read-only GITHUB_TOKEN? README step 1)" if denied else ""), file=sys.stderr)
        return 4 if "apply" in str(e) else 2 if denied else 1
    except (urllib.error.URLError, OSError, ValueError) as e:
        print("propose_knowledge: %s; the changes stay where they are" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
