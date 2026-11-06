"""Rules Claude Code's Workflow tool enforces on petra.js and the agents it runs (Claude Code 2.1.317):

- meta must be a pure literal: the tool reads it without running the script and rejects any expression
  there ("meta must be a pure literal: non-literal node type in meta: ...");
- a subagent's Write of a file named like a report (/^(REPORT|SUMMARY|FINDINGS|ANALYSIS).*\\.md$/i) is
  refused ("Subagents should return findings as text, not write report files"), so no artifact an
  agent writes may be named that way.

    python3 -m unittest discover -s tests
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "petra.js").read_text(encoding="utf-8")
START = "export const meta = "
TOKEN = re.compile(r"""\s+|//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\$])*`"""
                   r"""|-?\d+(?:\.\d+)?|[A-Za-z_$][\w$]*|[{}\[\]:,]|.""", re.S)
SUBAGENT_REPORT = re.compile(r"^(REPORT|SUMMARY|FINDINGS|ANALYSIS).*\.md$", re.I)


def meta_tokens(src: str) -> list:
    """The tokens of the meta object, comments and spaces left out."""
    depth, out = 0, []
    for m in TOKEN.finditer(src, src.index(START) + len(START)):
        t = m.group(0)
        if t.isspace() or t.startswith(("//", "/*")):
            continue
        out.append(t)
        if t in ("{", "["):
            depth += 1
        elif t in ("}", "]"):
            depth -= 1
            if depth == 0:
                return out
    raise AssertionError("meta does not close")


def literal(tokens: list, i: int) -> bool:
    t = tokens[i]
    return (t in ("{", "}", "[", "]", ":", ",") or t[0] in "'\"" or (t[0] == "`" and "${" not in t)
            or re.fullmatch(r"-?\d+(?:\.\d+)?|true|false|null", t) is not None
            or (re.fullmatch(r"[A-Za-z_$][\w$]*", t) is not None and i + 1 < len(tokens) and tokens[i + 1] == ":"))


def artifact_names() -> set:
    """Markdown files agents are told to write under RUN_DIR, and the templates they copy."""
    names = {p.name for p in ROOT.glob("templates/*.md")}
    for p in [ROOT / "petra.js", *ROOT.glob("roles/*.md"), *ROOT.glob("knowledge/*.md")]:
        names |= set(re.findall(r"RUN_DIR/(?:[\w.<>-]+/)*([\w.<>-]+\.md)\b", p.read_text(encoding="utf-8")))
    return names


class WorkflowMetaTest(unittest.TestCase):
    def test_meta_is_a_pure_literal(self):
        tokens = meta_tokens(SRC)
        self.assertEqual([t for i, t in enumerate(tokens) if not literal(tokens, i)], [],
                         "meta must be a pure literal: Claude Code's Workflow tool rejects expressions there")

    def test_the_check_sees_expressions(self):
        for bad in ("{a: 'x' + 'y'}", "{a: NAME}", "{a: `x${y}`}", "{a: f()}"):
            tokens = meta_tokens(START + bad + ";")
            self.assertTrue([t for i, t in enumerate(tokens) if not literal(tokens, i)], bad)


class ArtifactNamesTest(unittest.TestCase):
    def test_no_artifact_is_named_like_a_subagent_report(self):
        names = artifact_names()
        self.assertTrue({"run_report.md", "validation_report.md", "task_queue.md"} <= names, sorted(names))
        self.assertEqual(sorted(n for n in names if SUBAGENT_REPORT.match(n)), [],
                         "Claude Code refuses a subagent's Write of these names")

    def test_the_rule_is_claude_codes(self):
        self.assertTrue(SUBAGENT_REPORT.match("report.md") and SUBAGENT_REPORT.match("Summary_final.md"))
        self.assertFalse(SUBAGENT_REPORT.match("run_report.md") or SUBAGENT_REPORT.match("perf_analysis.md"))


if __name__ == "__main__":
    unittest.main()
