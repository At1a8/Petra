#!/usr/bin/env python3
"""List host-device synchronization candidates in Python sources (knowledge/system_perf.md §2.2).

Static leads only: a profile must confirm that a candidate runs every step and stalls the GPU queue.

  sync        .item() .tolist() .cpu() .numpy() torch.cuda.synchronize() / stream.synchronize()
              on a value that is not obviously host-side
  copy        .to(device) without non_blocking=True; torch.tensor(..., device=...) from host data
  host_side   the same calls on a receiver named like *_cpu / cpu (no device sync; listed with --all)

Each candidate carries its enclosing function and whether that function looks cold (init, capture,
warmup, load, debug) or warm (everything else).

  audit_host_syncs.py <files or dirs> --out syncs.json [--md syncs.md] [--all]
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import re
import sys
from pathlib import Path

SYNC_METHODS = {"item", "tolist", "cpu", "numpy"}
# Cold: runs once (construction, loading, graph capture) or only when debugging. Per-step metadata
# builders such as init_forward_metadata* stay warm; *capture* variants run only at capture time.
COLD_FN = re.compile(
    r"^(__init__|__repr__|__str__|__post_init__)$"
    r"|^_?(init|setup|load|register|warm_?up|profile|dump|debug|validate|verify|check|test)(_(?!forward)|$)"
    r"|capture|cuda_graph_state|build_pool", re.I)
HOST_NAME = re.compile(r"(^|_)cpu($|_)|_cpu\b|\bcpu\b|host|_list$|_py$", re.I)


def _src(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - ast.unparse is total on parsed trees
        return "?"


class Finder(ast.NodeVisitor):
    def __init__(self, path: str):
        self.path = path
        self.stack: list[str] = []
        self.found: list[dict] = []

    def _fn(self) -> str:
        return ".".join(self.stack) or "<module>"

    def _add(self, node: ast.Call, call: str, receiver: str, kind: str):
        fn = self.stack[-1] if self.stack else "<module>"
        self.found.append({
            "file": self.path, "line": node.lineno, "function": self._fn(), "call": call,
            "receiver": receiver[:160], "kind": kind,
            "temperature": "cold" if COLD_FN.search(fn) else "warm",
            "text": _src(node)[:200],
        })

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_Call(self, node: ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute):
            recv = _src(f.value)
            name = f.attr
            if name in SYNC_METHODS and not node.args:
                self._add(node, f".{name}()", recv, "host_side" if HOST_NAME.search(recv) else "sync")
            elif name == "synchronize":
                self._add(node, ".synchronize()", recv, "sync")
            elif name == "to":
                kw = {k.arg: k.value for k in node.keywords if k.arg}
                nb = kw.get("non_blocking")
                non_blocking = isinstance(nb, ast.Constant) and nb.value is True
                targets = [_src(a) for a in node.args] + ([_src(kw["device"])] if "device" in kw else [])
                to_device = any(re.search(r"device|cuda|\bgpu\b", t, re.I) for t in targets)
                if to_device and not non_blocking:
                    self._add(node, ".to(device)", recv, "copy")
            elif name in ("tensor", "as_tensor") and recv == "torch":
                kw = {k.arg: k.value for k in node.keywords if k.arg}
                dev = kw.get("device")
                if dev is not None and not (isinstance(dev, ast.Constant) and dev.value in ("cpu", None)):
                    self._add(node, f"torch.{name}(..., device=)", _src(node.args[0]) if node.args else "", "copy")
        self.generic_visit(node)


def scan_file(path: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(errors="replace"), filename=str(path))
    except (SyntaxError, OSError) as e:
        print(f"[audit_host_syncs] skip {path}: {e}", file=sys.stderr)
        return []
    f = Finder(str(path))
    f.visit(tree)
    return f.found


def scan(paths: list[Path]) -> list[dict]:
    out: list[dict] = []
    for p in paths:
        files = [p] if p.is_file() else sorted(p.rglob("*.py"))
        for f in files:
            out.extend(scan_file(f))
    return out


RANK = {("sync", "warm"): 0, ("copy", "warm"): 1, ("sync", "cold"): 2, ("copy", "cold"): 3,
        ("host_side", "warm"): 4, ("host_side", "cold"): 5}


def to_markdown(rows: list[dict]) -> str:
    lines = ["| Kind | Function | Call | Receiver | Where |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['kind']} ({r['temperature']}) | `{r['function']}` | `{r['call']}` | "
                     f"`{r['receiver'].replace('|', '/')}` | {Path(r['file']).name}:{r['line']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--all", action="store_true", help="include host-side calls and cold functions")
    ap.add_argument("--out", required=True)
    ap.add_argument("--md")
    a = ap.parse_args()

    found = scan(a.paths)
    rows = found if a.all else [r for r in found if r["kind"] != "host_side" and r["temperature"] == "warm"]
    rows.sort(key=lambda r: (RANK[(r["kind"], r["temperature"])], r["file"], r["line"]))
    res = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "paths": [str(p) for p in a.paths], "total_calls": len(found), "candidates": rows}
    Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False))
    if a.md:
        Path(a.md).write_text(to_markdown(rows))
    print(f"[audit_host_syncs] {len(rows)} candidate(s) of {len(found)} calls -> {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
