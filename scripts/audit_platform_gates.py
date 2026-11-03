#!/usr/bin/env python3
"""Audit platform gates in a framework source tree (knowledge/dispatch.md §4–5).

Categories:
  cuda_gate         a branch on CUDA (_is_cuda, is_cuda(), current_platform.is_cuda(), torch.version.cuda;
                    not tensor.is_cuda, which is True on ROCm)
  hip_excluded      a path switched off on HIP (`not _is_hip`, `not _use_aiter`)
  unsupported_note  "CUDA only" / "not supported on ROCm" in code or messages
  arch_gate         a check naming one AMD architecture (gfx942, gfx950, is_gfx95_supported, ...)
  capability_check  device-capability comparisons; gfx1250 reports a major version of 12, so checks
                    written for NV generations (e.g. `major >= 10`) can pick a CUDA path on MI45x
  wave32            device code assuming 32 lanes (0xffffffff shuffle masks, warpSize == 32)

  audit_platform_gates.py <sglang>/python/sglang/srt --out gates.json [--md gates.md] [--device]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

PY_RULES = [
    ("hip_excluded", re.compile(r"\bnot\s+_?is_hip\b|\bnot\s+is_hip\(\)|\bnot\s+_use_aiter\b")),
    ("unsupported_note", re.compile(r"cuda[- ]only|only (?:supported|available) on (?:cuda|nvidia)|"
                                    r"not supported on (?:rocm|hip|amd)|rocm is not supported|"
                                    r"unsupported on (?:rocm|hip)", re.I)),
    ("capability_check", re.compile(r"get_device_capability\(|\bmajor\s*(?:>=|>|==)\s*\d+|"
                                    r"\bsm_version\s*(?:>=|>|==)\s*\d+|capability\[0\]\s*(?:>=|>|==)")),
    ("arch_gate", re.compile(r"\bgfx(?:9\d\d|1[0-2]\d\d)\b|is_gfx9\d+\w*|_is_gfx9\d+\w*|is_gfx95_supported")),
    # `tensor.is_cuda` is True on ROCm too, so only platform checks count.
    ("cuda_gate", re.compile(r"(?<![.\w])_?is_cuda\b|\.is_cuda\(\)|torch\.version\.cuda")),
]
DEVICE_RULES = [
    ("wave32", re.compile(r"__(?:shfl(?:_xor|_down|_up)?|ballot|any|all)_sync\(\s*0xffffffff[uU]?\b|"
                          r"\bwarpSize\s*==\s*32\b|\b(?:WARP_SIZE|kWarpSize|warp_size)\s*=\s*32\b")),
]
PY_EXT = {".py"}
DEVICE_EXT = {".cu", ".cuh", ".hip", ".h", ".hpp", ".cpp", ".cc"}
_MAJOR_VALUE = re.compile(r"(?:major|sm_version|capability\[0\])\s*(?:>=|>|==)\s*(\d+)")
# Device files whose path says they are built for NVIDIA only; a wave32 assumption there is harmless.
_CUDA_ONLY_PATH = re.compile(r"cutlass|cute|sm\d{2,3}|hopper|blackwell|flashinfer|nvfp4|trtllm|deep_?gemm", re.I)


def scan_text(path: str, text: str, rules) -> list[dict]:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        for cat, pat in rules:
            if pat.search(s):
                e = {"category": cat, "file": path, "line": i, "text": s[:200]}
                if cat == "capability_check":
                    m = _MAJOR_VALUE.search(s)
                    if m and 9 <= int(m.group(1)) <= 12:
                        e["note"] = "true on gfx1250 (major 12)?"
                elif cat == "wave32":
                    e["note"] = ("NVIDIA-only file?" if _CUDA_ONLY_PATH.search(path)
                                 else "built for HIP? check wave64")
                out.append(e)
                break
    return out


def scan(paths: list[Path], device: bool) -> list[dict]:
    exts = PY_EXT | (DEVICE_EXT if device else set())
    entries = []
    for root in paths:
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.suffix in exts)
        for f in files:
            if f.suffix not in exts:
                continue
            try:
                text = f.read_text(errors="replace")
            except OSError:
                continue
            rules = PY_RULES if f.suffix in PY_EXT else DEVICE_RULES
            entries.extend(scan_text(str(f), text, rules))
    return entries


def summarize(entries: list[dict], top: int) -> dict:
    counts = collections.Counter(e["category"] for e in entries)
    by_file: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for e in entries:
        by_file[e["category"]][e["file"]] += 1
    return {"counts": dict(counts),
            "top_files": {c: by_file[c].most_common(top) for c in by_file}}


def to_markdown(res: dict) -> str:
    lines = ["| Category | Count | Top files |", "|---|---|---|"]
    for cat, n in sorted(res["summary"]["counts"].items(), key=lambda x: -x[1]):
        tops = "; ".join(f"{Path(f).name} ({k})" for f, k in res["summary"]["top_files"].get(cat, [])[:5])
        lines.append(f"| {cat} | {n} | {tops} |")
    cap = [e for e in res["entries"] if e["category"] == "capability_check" and e.get("note")]
    if cap:
        lines += ["", "Capability checks that may be true on gfx1250:", ""]
        lines += [f"- `{e['file']}:{e['line']}` `{e['text']}`" for e in cap[:50]]
    wave = [e for e in res["entries"] if e["category"] == "wave32" and e.get("note", "").startswith("built for HIP")]
    if wave:
        lines += ["", "Wave32 assumptions in device code that may be built for HIP:", ""]
        lines += [f"- `{e['file']}:{e['line']}` `{e['text']}`" for e in wave[:50]]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--device", action="store_true", help="also scan device code (.cu/.cuh/.hip/...)")
    ap.add_argument("--top", type=int, default=10, help="top files per category in the summary")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md")
    a = ap.parse_args()

    entries = scan(a.paths, a.device)
    res = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "paths": [str(p) for p in a.paths], "summary": summarize(entries, a.top), "entries": entries}
    Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False))
    if a.md:
        Path(a.md).write_text(to_markdown(res))
    print(f"[audit_platform_gates] {json.dumps(res['summary']['counts'])} -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
