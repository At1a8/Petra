"""Unit tests for petra/bootstrap.py and scripts/restore_owner.sh: nothing is installed, cloned or
linked outside temporary directories (commands are mocked).

    python3 -m unittest discover -s tests
"""
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from petra import bootstrap as bs  # noqa: E402

OK = SimpleNamespace(returncode=0)


def S(pwd, **env):
    return bs.settings({"PWD": str(pwd), "HOME": str(env.pop("HOME", pwd)), **env})


def make_checkout(root: Path) -> Path:
    (root / ".git").mkdir(parents=True)
    (root / "roles").mkdir()
    (root / "petra.js").write_text("// petra")
    return root


def make_exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class Quiet:
    """Silence stdout and stderr; keep what was written to stderr."""

    def __enter__(self):
        self.err = io.StringIO()
        self._stack = ExitStack()
        self._stack.enter_context(redirect_stdout(io.StringIO()))
        self._stack.enter_context(redirect_stderr(self.err))
        return self

    def __exit__(self, *exc):
        return self._stack.__exit__(*exc)


class VersionAndSettingsTest(unittest.TestCase):
    def test_ver_ge(self):
        self.assertTrue(bs.ver_ge("2.1.206", "2.1.177"))
        self.assertTrue(bs.ver_ge("2.1.177", "2.1.177"))
        self.assertFalse(bs.ver_ge("2.1.99", "2.1.177"))
        self.assertTrue(bs.ver_ge("3.0.0-beta", "2.9.9"))

    def test_claude_version(self):
        self.assertEqual(bs.claude_version(""), "")
        with mock.patch.object(bs, "_out", return_value=(0, "2.1.206 (Claude Code)", "")):
            self.assertEqual(bs.claude_version("/x/claude"), "2.1.206")
        with mock.patch.object(bs, "_out", return_value=(127, "", "not found")):
            self.assertEqual(bs.claude_version("/x/claude"), "")

    def test_settings(self):
        with tempfile.TemporaryDirectory() as d:
            co = make_checkout(Path(d) / "Petra")
            self.assertEqual(S(co, HOME=d)["home"], str(co))
            work = Path(d) / "work"
            work.mkdir()
            self.assertEqual(S(work, HOME=d)["home"], str(work / "Petra"))
            s = bs.settings({"PWD": str(work), "HOME": d, "PETRA_FRAMEWORK_DIR": "~/sglang"}, {"framework_repo": "/r"})
            self.assertEqual((s["framework_dir"], s["framework_repo"]), (os.path.join(d, "sglang"), "/r"))
            self.assertEqual(s["claude_bin_dir"], os.path.join(d, ".local", "bin"))


class HostHomeTest(unittest.TestCase):
    """In the container, the host home that owns the Petra checkout holds Claude Code and the keys."""

    def test_host_claude_and_keys_file(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / "u"
            co = make_checkout(home / "work" / "Petra")
            s = S("/", HOME="/root", PETRA_HOME=str(co))
            self.assertEqual(bs.owner_dirs(s)[:2], [str(home / "work"), str(home)])
            self.assertEqual(bs.host_claude(s), "")
            exe = make_exe(home / ".local" / "bin" / "claude")
            self.assertEqual(bs.host_claude(s), str(exe))
            self.assertEqual(bs.keys_file(s), str(home / ".petra_env"))


class CheckoutTest(unittest.TestCase):
    def test_existing_checkouts_are_kept(self):
        with tempfile.TemporaryDirectory() as d:
            co = make_checkout(Path(d) / "Petra")
            with mock.patch.object(bs, "_run") as run, Quiet():
                self.assertEqual(bs.ensure_checkout(S(co))[0], "kept")
                self.assertEqual(bs.ensure_checkout(S(d, PETRA_HOME=str(co)))[0], "kept")
            run.assert_not_called()

    def test_other_content_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Petra").mkdir()
            (Path(d) / "Petra" / "notes.txt").write_text("mine")
            with mock.patch.object(bs, "_run") as run, Quiet():
                self.assertEqual(bs.ensure_checkout(S(d))[0], "skipped")
            run.assert_not_called()
            self.assertEqual((Path(d) / "Petra" / "notes.txt").read_text(), "mine")

    def test_clone_only_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(bs, "_has", return_value=True), mock.patch.object(bs, "give_back") as back, \
                    mock.patch.object(bs, "_run", return_value=OK) as run, Quiet():
                self.assertEqual(bs.ensure_checkout(S(d, PETRA_REF="main"))[0], "created")
            run.assert_called_once_with(["git", "clone", "--branch", "main", bs.DEFAULT_REPO_URL, str(Path(d) / "Petra")])
            back.assert_called_once_with(str(Path(d) / "Petra"))
            with mock.patch.object(bs, "_has", return_value=False), Quiet():
                self.assertEqual(bs.ensure_checkout(S(d))[0], "failed")


class GiveBackTest(unittest.TestCase):
    def test_root_gives_back_to_the_closest_owner(self):
        with tempfile.TemporaryDirectory() as d:
            new = Path(d) / "a" / "b"
            new.mkdir(parents=True)
            st = os.stat(d)
            with mock.patch.object(bs, "is_root", return_value=True), \
                    mock.patch.object(bs, "_run", return_value=OK) as run, Quiet():
                bs.give_back(str(new))
            run.assert_called_once_with(["chown", "-R", "%d:%d" % (st.st_uid, st.st_gid), str(new)])
            with mock.patch.object(bs, "is_root", return_value=False), mock.patch.object(bs, "_run") as run:
                bs.give_back(str(new))
            run.assert_not_called()

    @unittest.skipIf(os.geteuid() == 0, "checks the non-root path")
    def test_restore_owner_script_does_nothing_without_root(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "f"
            f.write_text("x")
            before = os.stat(f)
            r = subprocess.run(["sh", str(ROOT / "scripts" / "restore_owner.sh"), str(f), str(Path(d) / "missing")])
            self.assertEqual(r.returncode, 0)
            self.assertEqual((os.stat(f).st_uid, os.stat(f).st_gid), (before.st_uid, before.st_gid))

    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_run_docker_script_parses(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(ROOT / "scripts" / "run_docker.sh")]).returncode, 0)


class ClaudeCodeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.s = S(tmp.name)

    def test_link_to_the_host_install(self):
        home = self.tmp / "u"
        co = make_checkout(home / "Petra")
        exe = make_exe(home / ".local" / "bin" / "claude")
        link = self.tmp / "usr-local-bin-claude"
        s = S("/", HOME="/root", PETRA_HOME=str(co))
        with mock.patch.object(bs, "CONTAINER_CLAUDE", str(link)), \
                mock.patch.object(bs.shutil, "which", return_value=None), Quiet():
            self.assertEqual(bs.ensure_claude_link(s)[0], "added")
            self.assertEqual(os.readlink(link), str(exe))
            self.assertEqual(bs.ensure_claude_link(s)[0], "skipped")
        with mock.patch.object(bs.shutil, "which", return_value=str(link)), Quiet():
            self.assertEqual(bs.ensure_claude_link(s)[0], "kept")

    def test_no_link_without_a_host_install(self):
        co = make_checkout(self.tmp / "u" / "Petra")
        link = self.tmp / "usr-local-bin-claude"
        with mock.patch.object(bs, "CONTAINER_CLAUDE", str(link)), \
                mock.patch.object(bs.shutil, "which", return_value=None), Quiet():
            self.assertEqual(bs.ensure_claude_link(S("/", HOME="/root", PETRA_HOME=str(co)))[0], "skipped")
        self.assertFalse(os.path.lexists(link))

    def test_install_off_path_is_found_and_kept(self):
        exe = make_exe(Path(self.s["claude_bin_dir"]) / "claude")
        with mock.patch.object(bs.shutil, "which", return_value=None):
            self.assertEqual(bs.find_claude(self.s), str(exe))
            with mock.patch.object(bs, "claude_version", return_value="2.1.317"), \
                    mock.patch.object(bs, "install_claude") as inst, Quiet():
                self.assertEqual(bs.ensure_claude_code(self.s), ("kept", "2.1.317"))
        inst.assert_not_called()

    def test_old_version_is_updated(self):
        with mock.patch.object(bs, "find_claude", return_value="/x/claude"), \
                mock.patch.object(bs, "claude_version", side_effect=["2.1.100", "2.1.200"]), \
                mock.patch.object(bs, "install_claude") as inst, mock.patch.object(bs, "_run") as run, Quiet():
            self.assertEqual(bs.ensure_claude_code(self.s), ("updated", "2.1.200"))
        run.assert_called_once_with(["/x/claude", "update"])
        inst.assert_not_called()

    def test_update_not_enough_then_install(self):
        with mock.patch.object(bs, "find_claude", return_value="/x/claude"), \
                mock.patch.object(bs, "claude_version", side_effect=["2.1.100", "2.1.100", "2.1.206"]), \
                mock.patch.object(bs, "install_claude", return_value=True) as inst, mock.patch.object(bs, "_run"), Quiet():
            self.assertEqual(bs.ensure_claude_code(self.s), ("installed", "2.1.206"))
        inst.assert_called_once()

    def test_missing_is_installed_or_reported(self):
        with mock.patch.object(bs, "find_claude", side_effect=["", "/x/claude"]), \
                mock.patch.object(bs, "claude_version", side_effect=["", "2.1.206"]), \
                mock.patch.object(bs, "install_claude", return_value=True) as inst, Quiet():
            self.assertEqual(bs.ensure_claude_code(self.s), ("installed", "2.1.206"))
        inst.assert_called_once_with(self.s)
        with mock.patch.object(bs, "find_claude", return_value=""), \
                mock.patch.object(bs, "install_claude", return_value=False), Quiet():
            self.assertEqual(bs.ensure_claude_code(self.s)[0], "failed")

    def test_installers(self):
        with mock.patch.object(bs, "_has", side_effect=lambda c: c == "curl"), \
                mock.patch.object(bs, "_run", return_value=OK) as run, Quiet():
            self.assertTrue(bs.install_claude(self.s))
        self.assertIn("https://claude.ai/install.sh | bash -s latest", run.call_args[0][0])
        self.assertTrue(run.call_args[1].get("shell"))
        with mock.patch.object(bs, "_has", return_value=True), \
                mock.patch.object(bs, "_run", side_effect=[SimpleNamespace(returncode=1), OK]) as run, Quiet():
            self.assertTrue(bs.install_claude(self.s))
        self.assertEqual(run.call_args[0][0], ["npm", "install", "-g", "@anthropic-ai/claude-code"])
        with mock.patch.object(bs, "_has", return_value=False), Quiet():
            self.assertFalse(bs.install_claude(self.s))


class ShellRcTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.s = S(self.home, SHELL="/bin/bash")
        self.rc = self.home / ".bashrc"

    def test_path_skipped_without_a_native_install(self):
        with Quiet():
            self.assertEqual(bs.ensure_path(self.s, path_env="/usr/bin")[0], "skipped")
        self.assertFalse(self.rc.exists())

    def test_path_added_once_and_kept_after(self):
        make_exe(Path(self.s["claude_bin_dir"]) / "claude")
        self.rc.write_text("alias ll='ls -l'\n")
        with Quiet():
            self.assertEqual(bs.ensure_path(self.s, path_env="/usr/bin")[0], "added")
            self.assertEqual(bs.ensure_path(self.s, path_env="/usr/bin")[0], "kept")
            self.assertEqual(bs.ensure_path(self.s, path_env=self.s["claude_bin_dir"])[0], "kept")
        text = self.rc.read_text()
        self.assertTrue(text.startswith("alias ll='ls -l'\n"))
        self.assertEqual(text.count(bs.RC_BEGIN), 1)

    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_path_block_never_duplicates_an_entry(self):
        make_exe(Path(self.s["claude_bin_dir"]) / "claude")
        with Quiet():
            bs.ensure_path(self.s, path_env="/usr/bin")
        out = subprocess.run(["bash", "-c", 'source "$1"; source "$1"; echo "$PATH"', "_", str(self.rc)],
                             env={"PATH": "/usr/bin:/bin", "HOME": str(self.home)}, capture_output=True, text=True).stdout
        self.assertEqual(out.strip().split(":").count(self.s["claude_bin_dir"]), 1)

    def test_existing_path_entry_is_respected(self):
        make_exe(Path(self.s["claude_bin_dir"]) / "claude")
        self.rc.write_text('export PATH="$HOME/.local/bin:$PATH"\n')
        with Quiet():
            self.assertEqual(bs.ensure_path(self.s, path_env="/usr/bin")[0], "kept")
        self.assertEqual(self.rc.read_text(), 'export PATH="$HOME/.local/bin:$PATH"\n')
        self.assertEqual(bs.rc_file(S(self.home, SHELL="/usr/bin/zsh")), str(self.home / ".zshrc"))

    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_container_env_and_keys_added_once(self):
        host = self.home / "u"
        co = make_checkout(host / "Petra")
        make_exe(host / ".local" / "bin" / "claude")
        (host / ".petra_env").write_text("export ANTHROPIC_API_KEY=sk-test\n")
        s = S("/", HOME=str(self.home), SHELL="/bin/bash", PETRA_HOME=str(co))
        with Quiet():
            self.assertEqual(bs.ensure_shell_env(s)[0], "added")
            self.assertEqual(bs.ensure_shell_env(s)[0], "kept")
        self.assertEqual(self.rc.read_text().count(bs.ENV_BEGIN), 1)
        out = subprocess.run(["bash", "-c", 'source "$1"; echo "$PYTHONDONTWRITEBYTECODE $DISABLE_AUTOUPDATER $ANTHROPIC_API_KEY"',
                              "_", str(self.rc)], env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "1 1 sk-test")

    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_an_amd_gateway_key_points_claude_code_at_the_gateway(self):
        host = self.home / "u"
        co = make_checkout(host / "Petra")
        make_exe(host / ".local" / "bin" / "claude")
        (host / ".petra_env").write_text("export LLM_GATEWAY_KEY=k123\n")
        s = S("/", HOME=str(self.home), SHELL="/bin/bash", PETRA_HOME=str(co))
        with Quiet():
            self.assertEqual(bs.ensure_shell_env(s)[0], "added")
        show = 'source "$1"; echo "$ANTHROPIC_BASE_URL|$ANTHROPIC_CUSTOM_HEADERS|$ANTHROPIC_AUTH_TOKEN"'
        out = subprocess.run(["bash", "-c", show, "_", str(self.rc)], env={"PATH": "/usr/bin:/bin"},
                             capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "%s|Ocp-Apim-Subscription-Key: k123|k123" % bs.AMD_GATEWAY_URL)
        out = subprocess.run(["bash", "-c", show, "_", str(self.rc)], capture_output=True, text=True,
                             env={"PATH": "/usr/bin:/bin", "ANTHROPIC_BASE_URL": "https://mine"}).stdout
        self.assertEqual(out.strip(), "https://mine||", "a gateway already chosen is kept")
        (host / ".petra_env").write_text("export ANTHROPIC_API_KEY=sk-test\n")
        out = subprocess.run(["bash", "-c", show, "_", str(self.rc)], env={"PATH": "/usr/bin:/bin"},
                             capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), "||", "without the gateway key nothing changes")
        self.assertTrue(bs.api_configured({"LLM_GATEWAY_KEY": "k"}, str(self.home)))


class ClaudeStateTest(unittest.TestCase):
    """Root's Claude Code state goes to ~/.petra/claude of the checkout's owner, so it outlives the container."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root_home = Path(tmp.name) / "root"
        self.root_home.mkdir()
        self.host = Path(tmp.name) / "u"
        co = make_checkout(self.host / "Petra")
        make_exe(self.host / ".local" / "bin" / "claude")
        self.s = S("/", HOME=str(self.root_home), SHELL="/bin/bash", PETRA_HOME=str(co))
        self.rc = self.root_home / ".bashrc"
        self.state = self.host / ".petra" / "claude"

    def test_state_dir_is_next_to_the_keys(self):
        self.assertEqual(bs.claude_state_dir(self.s), str(self.state))
        with mock.patch.object(bs, "keys_file", return_value=""), Quiet():
            self.assertEqual(bs.claude_state_dir(self.s), "")
            self.assertEqual(bs.ensure_claude_state(self.s, env={})[0], "skipped")
        self.assertFalse(self.rc.exists())

    @unittest.skipUnless(shutil.which("bash"), "needs bash")
    def test_created_once_then_kept(self):
        with mock.patch.object(bs, "give_back") as back, Quiet():
            self.assertEqual(bs.ensure_claude_state(self.s, env={}), ("created", str(self.state)))
            self.assertEqual(bs.ensure_claude_state(self.s, env={})[0], "kept")
        self.assertEqual(back.call_args_list, [mock.call(str(self.state.parent))] * 2)
        self.assertEqual(stat.S_IMODE(os.stat(self.state).st_mode), 0o700)
        self.assertEqual(self.rc.read_text().count(bs.STATE_BEGIN), 1)
        out = subprocess.run(["bash", "-c", 'source "$1"; echo "$CLAUDE_CONFIG_DIR"', "_", str(self.rc)],
                             env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True).stdout
        self.assertEqual(out.strip(), str(self.state))

    def test_new_container_keeps_the_host_state(self):
        self.state.mkdir(parents=True)
        (self.state / ".claude.json").write_text('{"hasCompletedOnboarding": true}')
        with mock.patch.object(bs, "give_back") as back, Quiet():
            self.assertEqual(bs.ensure_claude_state(self.s, env={})[0], "added")
        back.assert_called_once_with(str(self.state.parent))
        self.assertEqual((self.state / ".claude.json").read_text(), '{"hasCompletedOnboarding": true}')

    def test_a_config_dir_already_set_is_used_as_it_is(self):
        with Quiet():
            self.assertEqual(bs.ensure_claude_state(self.s, env={"CLAUDE_CONFIG_DIR": "/elsewhere"}), ("kept", "/elsewhere"))
        self.assertFalse(self.rc.exists() or self.state.exists())

    def test_a_login_kept_there_counts_as_api_access(self):
        self.state.mkdir(parents=True)
        self.assertFalse(bs.api_configured({"CLAUDE_CONFIG_DIR": str(self.state)}, str(self.root_home)))
        (self.state / ".credentials.json").write_text("{}")
        self.assertTrue(bs.api_configured({"CLAUDE_CONFIG_DIR": str(self.state)}, str(self.root_home)))


class GitTrustTest(unittest.TestCase):
    def test_trust_added_once(self):
        s = S(tempfile.gettempdir())
        with mock.patch.object(bs, "_has", return_value=True), mock.patch.object(bs, "_out", return_value=(1, "", "")), \
                mock.patch.object(bs, "_run", return_value=OK) as run, Quiet():
            self.assertEqual(bs.ensure_git_trust(s)[0], "added")
        run.assert_called_once_with(["git", "config", "--global", "--add", "safe.directory", "*"])
        with mock.patch.object(bs, "_has", return_value=True), mock.patch.object(bs, "_out", return_value=(0, "/a\n*", "")), \
                mock.patch.object(bs, "_run") as run, Quiet():
            self.assertEqual(bs.ensure_git_trust(s)[0], "kept")
        run.assert_not_called()


class FrameworkTest(unittest.TestCase):
    def test_skipped_without_a_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(bs.ensure_framework(S(d))[0], "skipped")

    def test_existing_checkout_is_kept_as_it_is(self):
        with tempfile.TemporaryDirectory() as d:
            fw = Path(d) / "sglang"
            (fw / ".git").mkdir(parents=True)
            answers = {"log": (0, "abc123 2026-10-20", ""), "rev-parse": (0, "true", ""),
                       "remote": (0, "git@github.com:sgl-project/sglang.git", "")}
            with mock.patch.object(bs, "_out", side_effect=lambda cmd: answers[cmd[3]]), \
                    mock.patch.object(bs, "_run") as run, Quiet() as q:
                self.assertEqual(bs.ensure_framework(S(d, PETRA_FRAMEWORK_DIR=str(fw)))[0], "kept")
            run.assert_not_called()
            self.assertIn("shallow", q.err.getvalue())
            self.assertNotIn("tracks", q.err.getvalue())

    def test_other_content_is_left_alone(self):
        with tempfile.TemporaryDirectory() as d:
            fw = Path(d) / "sglang"
            fw.mkdir()
            (fw / "notes.txt").write_text("mine")
            with mock.patch.object(bs, "_run") as run, Quiet():
                self.assertEqual(bs.ensure_framework(S(d, PETRA_FRAMEWORK_DIR=str(fw)))[0], "skipped")
            run.assert_not_called()

    def test_missing_is_cloned_blobless_and_given_back(self):
        with tempfile.TemporaryDirectory() as d:
            fw = Path(d) / "src" / "sglang"
            with mock.patch.object(bs, "_has", return_value=True), mock.patch.object(bs, "give_back") as back, \
                    mock.patch.object(bs, "_run", return_value=OK) as run, Quiet():
                self.assertEqual(bs.ensure_framework(S(d, PETRA_FRAMEWORK_DIR=str(fw)))[0], "created")
            run.assert_called_once_with(["git", "clone", "--filter=blob:none", bs.DEFAULT_FRAMEWORK_REPO, str(fw)])
            back.assert_called_once_with(str(fw))


class ReportTest(unittest.TestCase):
    def test_check_environment(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(bs, "_has", return_value=True), mock.patch.object(bs, "in_container", return_value=False), Quiet():
                found = bs.check_environment({"HOME": d, "GITHUB_TOKEN": "x"})
            self.assertTrue(found["git"] and found["github_token"] and found["docker"])
            self.assertFalse(found["api"])
            self.assertIn("sglang", found)
            with mock.patch.object(bs, "_has", return_value=True), mock.patch.object(bs, "in_container", return_value=True), Quiet():
                self.assertNotIn("docker", bs.check_environment({"HOME": d}))
            self.assertTrue(bs.api_configured({"ANTHROPIC_BASE_URL": "u", "ANTHROPIC_CUSTOM_HEADERS": "h"}, d))
            (Path(d) / ".claude").mkdir()
            (Path(d) / ".claude" / ".credentials.json").write_text("{}")
            self.assertTrue(bs.api_configured({}, d))

    def test_next_steps_in_a_new_container(self):
        with tempfile.TemporaryDirectory() as d:
            host = Path(d) / "u"
            co = make_checkout(host / "Petra")
            make_exe(host / ".local" / "bin" / "claude")
            s = bs.settings({"PWD": "/", "HOME": d, "PETRA_HOME": str(co), "PETRA_FRAMEWORK_DIR": str(host / "sglang")})
            with mock.patch.object(bs, "in_container", return_value=True):
                fresh = bs.next_steps(s, {"shell": "added"}, {"api": False}, path_env="/usr/bin")
                (host / ".petra_env").write_text("export ANTHROPIC_API_KEY=x\n")
                with_keys = bs.next_steps(s, {"shell": "added"}, {"api": False}, path_env="/usr/bin")
                ready = bs.next_steps(s, {"shell": "kept"}, {"api": True}, path_env="/usr/bin")
            self.assertIn("source %s" % os.path.join(d, ".bashrc"), fresh)
            self.assertIn("on the host, in %s" % (host / ".petra_env"), fresh)
            self.assertNotIn("ANTHROPIC_API_KEY", with_keys)
            self.assertIn("cd %s && IS_SANDBOX=1 claude --dangerously-skip-permissions" % co, ready)
            self.assertIn("framework_dir=%s, gpu_ids=0\n" % (host / "sglang"), ready + "\n")
            self.assertNotIn("source", ready)
            self.assertNotIn("petra.js", bs.next_steps(s, {}, {"api": True}, path_env="/usr/bin", claude_only=True))
            self.assertIn("in every new container", ready)
            self.assertIn("Yes, I trust this folder", ready)
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": ""}), mock.patch.object(bs, "in_container", return_value=True):
                kept = bs.next_steps(s, {"shell": "kept", "claude-state": "kept"}, {"api": True}, path_env="/usr/bin")
                new_state = bs.next_steps(s, {"shell": "kept", "claude-state": "created"}, {"api": True}, path_env="/usr/bin")
            self.assertIn("once (the answers are kept in %s)" % (host / ".petra" / "claude"), kept)
            self.assertNotIn("source", kept)
            self.assertIn("source", new_state)


class MainTest(unittest.TestCase):
    STEPS = ["ensure_checkout", "ensure_claude_link", "ensure_claude_code", "ensure_path", "ensure_claude_state",
             "ensure_git_trust", "ensure_shell_env", "ensure_framework"]

    def run_main(self, argv, container=False, root=False, failing=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("PETRA_")}
        with ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, env, clear=True))
            m = {n: stack.enter_context(mock.patch.object(bs, n, return_value=("failed" if n == failing else "kept", "")))
                 for n in self.STEPS}
            m["check_environment"] = stack.enter_context(mock.patch.object(bs, "check_environment", return_value={"api": True}))
            stack.enter_context(mock.patch.object(bs, "in_container", return_value=container))
            stack.enter_context(mock.patch.object(bs, "is_root", return_value=root))
            stack.enter_context(Quiet())
            return bs.main(argv), m

    def called(self, m):
        return [n for n in self.STEPS if m[n].called]

    def test_skip(self):
        with mock.patch.dict(os.environ, {"PETRA_SKIP_BOOTSTRAP": "1"}), \
                mock.patch.object(bs, "ensure_claude_code") as ens, Quiet():
            self.assertEqual(bs.main([]), 0)
        ens.assert_not_called()

    def test_steps_follow_where_it_runs(self):
        rc, m = self.run_main(["--framework-dir", "/x/sglang"], container=True, root=True)
        self.assertEqual((rc, self.called(m)), (0, self.STEPS))
        self.assertEqual(m["ensure_framework"].call_args[0][0]["framework_dir"], "/x/sglang")
        self.assertTrue(m["check_environment"].called)
        rc, m = self.run_main([])
        self.assertEqual(self.called(m), ["ensure_checkout", "ensure_claude_code", "ensure_path", "ensure_framework"])
        rc, m = self.run_main(["--claude-only"], container=True, root=True)
        self.assertEqual(self.called(m), ["ensure_claude_link", "ensure_claude_code", "ensure_path", "ensure_claude_state"])
        self.assertFalse(m["check_environment"].called)
        rc, m = self.run_main(["--check"])
        self.assertTrue(m["check_environment"].called and not self.called(m))

    def test_a_failed_step_sets_the_exit_code(self):
        self.assertEqual(self.run_main([], failing="ensure_framework")[0], 1)


if __name__ == "__main__":
    unittest.main()
