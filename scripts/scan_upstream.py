#!/usr/bin/env python3
"""List upstream changes that may need AMD follow-up (knowledge/dispatch.md).

Reads a local framework checkout (a full or blobless clone; a treeless clone fetches every blob on
demand and is slow). For each non-merge commit in the range it reports:

  new_cuda_gate       added lines that branch on CUDA (is_cuda(), device capability, "CUDA only" notes)
  cuda_first_feature  a [Feat]/[Perf] change, not AMD work, that adds a CUDA-only dependency (flashinfer,
                      DeepGEMM, FlashMLA, CUTLASS/CuTe, TRT-LLM, DeepEP, .cu/.cuh code) or a CUDA gate,
                      and touches no HIP/ROCm path
  new_model           a change that adds a model file (Day-0 support to check on AMD)

Changes tagged for another platform ([XPU], [NPU], [CPU], ...) are skipped.

  scan_upstream.py --repo-dir ~/sglang --since 2026-10-25 --out upstream.json [--md upstream.md]
  scan_upstream.py --repo-dir ~/sglang --range b057d5b3f1..origin/main --out upstream.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

# `tensor.is_cuda` is True on ROCm too (PyTorch keeps the "cuda" device type), so only platform checks
# count: is_cuda() calls, _is_cuda flags, current_platform.is_cuda(), torch.version.cuda.
GATE_PATTERNS = [
    ("cuda_check", re.compile(r"(?<![.\w])_?is_cuda\b|\.is_cuda\(\)|torch\.version\.cuda")),
    ("nv_capability", re.compile(r"is_sm\d+_supported|is_blackwell|is_hopper|get_device_capability|"
                                 r"get_device_sm\(|\bsm_version\b")),
    ("unsupported_note", re.compile(r"cuda[- ]only|only (?:supported|available) on cuda|"
                                    r"not supported on (?:rocm|hip|amd)|rocm is not supported", re.I)),
    ("hip_excluded", re.compile(r"\bnot\s+_?is_hip\b|\bnot\s+is_hip\(\)")),
]
_AMD_WORDS = re.compile(r"\b(AMD|ROCm|HIP|aiter|gfx\d+|MI3\d\dX?|MI45\dX?|MoRI)\b", re.I)
_HIP_PATH = re.compile(r"(hip|rocm|aiter|amd|gfx)", re.I)
_HIP_LINE = re.compile(r"\b_?is_hip\b|is_hip\(\)|\baiter\b|rocm", re.I)
_CUDA_DEP = re.compile(r"\b(flashinfer|deep_gemm|deepgemm|flash_mla|cutlass|cute|cuda\.bindings|cuda-python|"
                       r"trtllm|tensorrt_llm|deep_ep|nvshmem|cublas\w*|cudnn)\b", re.I)
_CUDA_SRC = re.compile(r"\.(cu|cuh)$")
_MODEL_FILE = re.compile(r"/models?/[^/]+\.py$|/models/dits/[^/]+\.py$")
OTHER_PLATFORMS = {"xpu", "npu", "intel", "ascend", "musa", "cpu", "mps", "metal", "apple", "tpu", "hpu", "habana"}
_TAGS = re.compile(r"^((?:\[[^\]]+\]\s*)+)")
_PR = re.compile(r"\(#(\d+)\)\s*$")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
FEATURE_TAGS = {"feat", "feature", "perf"}


def parse_subject(subject: str) -> dict:
    m = _TAGS.match(subject)
    tags = re.findall(r"\[([^\]]+)\]", m.group(1)) if m else []
    pr = _PR.search(subject)
    lowered = [t.strip().lower() for t in tags]
    if tags:
        is_feature = any(t in FEATURE_TAGS for t in lowered)
    else:
        rest = re.sub(r"^[\w./\- ]+:\s*", "", subject)  # drop a leading "scope: "
        is_feature = bool(re.match(r"(support|add|enable)\b", rest, re.I))
    return {
        "tags": tags,
        "pr": int(pr.group(1)) if pr else None,
        "is_amd": any(t in ("amd", "rocm", "hip") for t in lowered) or bool(_AMD_WORDS.search(subject)),
        "other_platform": any(t in OTHER_PLATFORMS for t in lowered),
        "is_feature": is_feature,
    }


def parse_log(text: str) -> list[dict]:
    """Parse `git log -p --unified=0` output written with --format=%x1e%H%x1f%ad%x1f%an%x1f%s."""
    commits = []
    for rec in text.split("\x1e"):
        if not rec.strip():
            continue
        head, _, diff = rec.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 4:
            continue
        sha, date, author, subject = parts[0], parts[1], parts[2], "\x1f".join(parts[3:])
        files, new_files, gates, cuda_deps = [], [], [], []
        touches_hip = False
        cur, new_line, prev = None, 0, ""
        for line in diff.split("\n"):
            if line.startswith("+++ "):
                cur = line[6:] if line.startswith("+++ b/") else None
                if cur:
                    files.append(cur)
                    touches_hip = touches_hip or bool(_HIP_PATH.search(cur))
                    if prev.startswith("--- /dev/null"):
                        new_files.append(cur)
                    if _CUDA_SRC.search(cur) and not _HIP_PATH.search(cur):
                        cuda_deps.append(cur)
                prev = line
                continue
            prev = line
            h = _HUNK.match(line)
            if h:
                new_line = int(h.group(1))
                continue
            if line.startswith("+") and cur:
                added = line[1:]
                if _HIP_LINE.search(added):
                    touches_hip = True
                m = _CUDA_DEP.search(added)
                if m and not added.lstrip().startswith("#"):
                    cuda_deps.append(m.group(1).lower())
                for kind, pat in GATE_PATTERNS:
                    if pat.search(added):
                        gates.append({"kind": kind, "file": cur, "line": new_line, "text": added.strip()[:200]})
                        break
                new_line += 1
        info = parse_subject(subject)
        commits.append({"sha": sha, "date": date, "author": author, "subject": subject, "files": files,
                        "new_files": new_files, "touches_hip": touches_hip, "gates": gates,
                        "cuda_deps": sorted(set(cuda_deps))[:10], **info})
    return commits


def candidates(commits: list[dict]) -> list[dict]:
    out = []
    for c in commits:
        if c["is_amd"] or c["other_platform"]:
            continue
        kinds = []
        if c["gates"]:
            kinds.append("new_cuda_gate")
        if c["is_feature"] and not c["touches_hip"] and (c["cuda_deps"] or c["gates"]):
            kinds.append("cuda_first_feature")
        if any(_MODEL_FILE.search(f) for f in c["new_files"]):
            kinds.append("new_model")
        if kinds:
            out.append({"sha": c["sha"][:12], "date": c["date"], "pr": c["pr"], "subject": c["subject"],
                        "kinds": kinds, "cuda_deps": c["cuda_deps"], "gates": c["gates"][:10],
                        "new_files": c["new_files"][:10], "files": c["files"][:20]})
    return out


def git_log(repo: Path, rev: list[str], paths: list[str]) -> str:
    cmd = ["git", "-C", str(repo), "log", "--no-merges", "--date=iso-strict",
           "--format=%x1e%H%x1f%ad%x1f%an%x1f%s", "-p", "--unified=0", "--no-color", *rev, "--", *paths]
    return subprocess.run(cmd, check=True, capture_output=True, text=True, errors="replace").stdout


def to_markdown(res: dict) -> str:
    lines = [f"Range `{res['range']}`: {res['commits_scanned']} commits, {len(res['candidates'])} candidates.\n",
             "| Date | PR | Kinds | Subject |", "|---|---|---|---|"]
    for c in res["candidates"]:
        pr = f"#{c['pr']}" if c["pr"] else c["sha"]
        lines.append(f"| {c['date'][:10]} | {pr} | {', '.join(c['kinds'])} | {c['subject'].replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-dir", required=True, type=Path)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--since", help="date (YYYY-MM-DD) or any git --since value")
    g.add_argument("--range", help="revision range, e.g. <last-scan-sha>..origin/main")
    ap.add_argument("--paths", nargs="*", default=["python/"], help="pathspecs to scan (default python/)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md")
    a = ap.parse_args()

    rev = [a.range] if a.range else [f"--since={a.since}"]
    commits = parse_log(git_log(a.repo_dir, rev, a.paths))
    res = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "repo_dir": str(a.repo_dir), "range": a.range or f"since {a.since}",
           "commits_scanned": len(commits), "amd_commits": sum(c["is_amd"] for c in commits),
           "candidates": candidates(commits)}
    Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False))
    if a.md:
        Path(a.md).write_text(to_markdown(res))
    print(f"[scan_upstream] {len(commits)} commits, {len(res['candidates'])} candidates -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
