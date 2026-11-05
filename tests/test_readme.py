"""README.md and README.zh-CN.md stay in step: each links to the other, every link to a heading lands
on one, and both show the same commands and the same names in their tables. Offline.

    python3 -m unittest discover -s tests
"""
import re
import unicodedata
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN = (ROOT / "README.md").read_text(encoding="utf-8")
ZH = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
FENCE = re.compile(r"^```.*?^```", re.M | re.S)


def prose(text):
    return FENCE.sub("", text)


def slug(heading):
    """GitHub's anchor for a heading (github-slugger): lower case, punctuation dropped, spaces to hyphens."""
    def keep(c):
        cat = unicodedata.category(c)
        return c in " -" or cat[0] in "LMN" or cat == "Pc"
    return "".join(c for c in heading.strip().lower() if keep(c)).replace(" ", "-")


def anchors(text):
    seen, out = {}, set()
    for heading in re.findall(r"^#{1,6} (.+)$", prose(text), re.M):
        s = slug(heading)
        n = seen.get(s, 0)
        out.add(s if n == 0 else "%s-%d" % (s, n))
        seen[s] = n + 1
    return out


def commands(text):
    """Every line of every bash block; comments are left out, the translation translates them."""
    out = []
    for block in re.findall(r"^```bash\n(.*?)^```", text, re.M | re.S):
        for line in block.splitlines():
            line = re.sub(r"\s+#.*$", "", line).rstrip()
            if line and not line.lstrip().startswith("#"):
                out.append(line)
    return out


def table_names(text):
    """Names in backticks in the first column of every table row."""
    names = set()
    for row in re.findall(r"^\|(.*)$", prose(text), re.M):
        names |= set(re.findall(r"`([^`]+)`", row.split("|")[0]))
    return names


class ReadmeTest(unittest.TestCase):
    def test_each_links_to_the_other(self):
        self.assertIn("[简体中文](README.zh-CN.md)", EN)
        self.assertIn("[English](README.md)", ZH)

    def test_links_to_headings_land_on_one(self):
        for name, text in (("README.md", EN), ("README.zh-CN.md", ZH)):
            targets = set(re.findall(r"\]\(#([^)]+)\)", prose(text)))
            self.assertTrue(targets, name)
            self.assertEqual(targets - anchors(text), set(), name)

    def test_same_commands(self):
        self.assertTrue(commands(EN))
        self.assertEqual(commands(EN), commands(ZH))

    def test_same_names_in_the_tables(self):
        self.assertGreater(len(table_names(EN)), 50)
        self.assertEqual(table_names(EN) ^ table_names(ZH), set())


if __name__ == "__main__":
    unittest.main()
