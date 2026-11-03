"""Unit tests for petra/bootstrap.py: no network, nothing installed (subprocess calls are mocked).

    python3 -m unittest discover -s tests
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from petra import bootstrap as bs  # noqa: E402


def make_checkout(root: Path) -> Path:
    (root / ".git").mkdir(parents=True)
    (root / "roles").mkdir()
    (root / "petra.js").write_text("// petra")
    return root


def quiet():
    return redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO())


class VersionTest(unittest.TestCase):
    def test_ver_ge(self):
        self.assertTrue(bs.ver_ge("2.1.206", "2.1.177"))
        self.assertTrue(bs.ver_ge("2.1.177", "2.1.177"))
        self.assertFalse(bs.ver_ge("2.1.99", "2.1.177"))
        self.assertTrue(bs.ver_ge("3.0.0-beta", "2.9.9"))

    def test_claude_version(self):
        with mock.patch.object(bs, "_has", return_value=False):
            self.assertEqual(bs.claude_version(), "")
        out = SimpleNamespace(stdout="2.1.206 (Claude Code)\n")
        with mock.patch.object(bs, "_has", return_value=True), mock.patch.object(bs.subprocess, "run", return_value=out):
            self.assertEqual(bs.claude_version(), "2.1.206")


class SettingsTest(unittest.TestCase):
    def test_home_in_place_or_under_invocation_dir(self):
        with tempfile.TemporaryDirectory() as d:
            co = make_checkout(Path(d) / "Petra")
            self.assertEqual(bs.settings({"PWD": str(co)})["home"], str(co))
            other = Path(d) / "work"
            other.mkdir()
            self.assertEqual(bs.settings({"PWD": str(other)})["home"], str(other / "Petra"))
            self.assertEqual(bs.settings({"PWD": str(other), "PETRA_HOME": str(Path(d) / "x")})["home"], str(Path(d) / "x"))
            s = bs.settings({"PWD": str(other), "CLAUDE_VERSION": "2.1.206", "PETRA_REF": "dev"})
            self.assertEqual((s["claude_version"], s["ref"], s["repo_url"]), ("2.1.206", "dev", bs.DEFAULT_REPO_URL))


class CloneTest(unittest.TestCase):
    def test_in_place_and_existing(self):
        with tempfile.TemporaryDirectory() as d:
            co = make_checkout(Path(d) / "Petra")
            with mock.patch.object(bs, "_run") as run, quiet()[0]:
                self.assertTrue(bs.clone_repo(bs.settings({"PWD": str(co)})))
                self.assertTrue(bs.clone_repo(bs.settings({"PWD": d, "PETRA_HOME": str(co)})))
                run.assert_not_called()

    def test_non_empty_target_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Petra").mkdir()
            (Path(d) / "Petra" / "notes.txt").write_text("mine")
            with mock.patch.object(bs, "_run") as run, quiet()[1]:
                self.assertFalse(bs.clone_repo(bs.settings({"PWD": d})))
                run.assert_not_called()

    def test_clone(self):
        with tempfile.TemporaryDirectory() as d:
            s = bs.settings({"PWD": d, "PETRA_REF": "main"})
            with mock.patch.object(bs, "_has", return_value=True), \
                    mock.patch.object(bs, "_run", return_value=SimpleNamespace(returncode=0)) as run, quiet()[0]:
                self.assertTrue(bs.clone_repo(s))
            run.assert_called_once_with(["git", "clone", "--branch", "main", bs.DEFAULT_REPO_URL, str(Path(d) / "Petra")])

    def test_no_git(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(bs, "_has", return_value=False), quiet()[1]:
                self.assertFalse(bs.clone_repo(bs.settings({"PWD": d})))


class ClaudeCodeTest(unittest.TestCase):
    def setUp(self):
        self.s = bs.settings({"PWD": tempfile.gettempdir(), "CLAUDE_BIN_DIR": "/nonexistent/bin"})

    def test_present_and_new_enough(self):
        with mock.patch.object(bs, "claude_version", return_value="2.1.206"), \
                mock.patch.object(bs, "install_claude") as inst, mock.patch.object(bs, "_run") as run, quiet()[0]:
            self.assertEqual(bs.ensure_claude_code(self.s), "2.1.206")
        inst.assert_not_called()
        run.assert_not_called()

    def test_old_version_is_updated(self):
        with mock.patch.object(bs, "claude_version", side_effect=["2.1.100", "2.1.200"]), \
                mock.patch.object(bs, "install_claude") as inst, mock.patch.object(bs, "_run") as run, quiet()[0], quiet()[1]:
            self.assertEqual(bs.ensure_claude_code(self.s), "2.1.200")
        run.assert_called_once_with(["claude", "update"])
        inst.assert_not_called()

    def test_update_not_enough_then_install(self):
        with mock.patch.object(bs, "claude_version", side_effect=["2.1.100", "2.1.100", "2.1.206"]), \
                mock.patch.object(bs, "install_claude", return_value=True) as inst, mock.patch.object(bs, "_run"), \
                quiet()[0], quiet()[1]:
            self.assertEqual(bs.ensure_claude_code(self.s), "2.1.206")
        inst.assert_called_once()

    def test_missing_is_installed(self):
        with mock.patch.object(bs, "claude_version", side_effect=["", "2.1.206"]), \
                mock.patch.object(bs, "install_claude", return_value=True) as inst, quiet()[0]:
            self.assertEqual(bs.ensure_claude_code(self.s), "2.1.206")
        inst.assert_called_once_with(self.s)

    def test_native_installer(self):
        with mock.patch.object(bs, "_has", side_effect=lambda c: c == "curl"), \
                mock.patch.object(bs, "_run", return_value=SimpleNamespace(returncode=0)) as run, quiet()[0]:
            self.assertTrue(bs.install_claude(self.s))
        cmd = run.call_args[0][0]
        self.assertIn("https://claude.ai/install.sh | bash -s latest", cmd)
        self.assertTrue(run.call_args[1].get("shell"))

    def test_npm_fallback_and_nothing(self):
        with mock.patch.object(bs, "_has", return_value=True), \
                mock.patch.object(bs, "_run", side_effect=[SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)]) as run, \
                quiet()[0], quiet()[1]:
            self.assertTrue(bs.install_claude(self.s))
        self.assertEqual(run.call_args[0][0], ["npm", "install", "-g", "@anthropic-ai/claude-code"])
        with mock.patch.object(bs, "_has", return_value=False), quiet()[1]:
            self.assertFalse(bs.install_claude(self.s))


class NextStepsAndMainTest(unittest.TestCase):
    def test_next_steps(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "claude").write_text("")
            s = bs.settings({"PWD": d, "PETRA_HOME": "/opt/Petra", "CLAUDE_BIN_DIR": d})
            text = bs.next_steps(s, path_env="/usr/bin")
            self.assertIn("not on your PATH", text)
            self.assertIn("IS_SANDBOX=1 claude --dangerously-skip-permissions", text)
            self.assertIn("use /opt/Petra/petra.js with mode=scan", text)
            self.assertNotIn("not on your PATH", bs.next_steps(s, path_env=d))
            self.assertNotIn("petra.js", bs.next_steps(s, path_env=d, claude_only=True))

    def test_check_environment(self):
        with mock.patch.object(bs, "_has", return_value=True), quiet()[0], quiet()[1]:
            found = bs.check_environment({"GITHUB_TOKEN": "x"})
        self.assertTrue(found["git"] and found["github_token"])
        self.assertNotIn("geak_home", found)

    def test_main_modes(self):
        with mock.patch.dict(os.environ, {"PETRA_SKIP_BOOTSTRAP": "1"}), \
                mock.patch.object(bs, "ensure_claude_code") as ens, quiet()[0]:
            self.assertEqual(bs.main([]), 0)
            ens.assert_not_called()
        env = {k: v for k, v in os.environ.items() if k != "PETRA_SKIP_BOOTSTRAP"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(bs, "clone_repo") as clone, mock.patch.object(bs, "ensure_claude_code") as ens, \
                mock.patch.object(bs, "check_environment") as chk, quiet()[0]:
            bs.main(["--claude-only"])
            clone.assert_not_called()
            ens.assert_called_once()
            chk.assert_not_called()
            bs.main(["--check"])
            chk.assert_called_once()
            bs.main([])
            clone.assert_called_once()
            self.assertEqual(ens.call_count, 2)


if __name__ == "__main__":
    unittest.main()
