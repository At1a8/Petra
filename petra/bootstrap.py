"""Petra bootstrap: get a Petra checkout and the Claude Code CLI its workflow runs inside.

`pip install git+https://github.com/At1a8/Petra` (or `pip install .` inside a checkout) runs this
during the wheel build, following GEAK's installer:

  1. clone the Petra repository to $PETRA_HOME (skipped when installing from inside a checkout);
  2. install the Claude Code CLI (native installer, npm as a fallback), or update one older than the
     version whose Workflow tool Petra needs;
  3. check what Petra uses on the box (detect only);
  4. print the next steps.

Every step is best-effort: a failure warns and never aborts the install. Run it again at any time:

  python3 -m petra.bootstrap                 # all steps
  python3 -m petra.bootstrap --claude-only   # only install or update Claude Code
  python3 -m petra.bootstrap --check         # only the environment check

Environment:
  PETRA_HOME            where the checkout goes (default: ./Petra under the directory you run from,
                        or that directory itself when it is a Petra checkout)
  PETRA_REPO_URL        repository to clone (default: https://github.com/At1a8/Petra.git)
  PETRA_REF             branch or tag to clone (default: the repository's default branch)
  CLAUDE_VERSION        native-installer target (default: latest)
  CLAUDE_BIN_DIR        where the CLI lands (default: ~/.local/bin)
  PETRA_SKIP_BOOTSTRAP  set to skip everything (CI, image builds)

Imported at build time, so standard library only.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

CLAUDE_MIN_VERSION = "2.1.177"  # first Claude Code with the dynamic Workflow tool petra.js runs in
DEFAULT_REPO_URL = "https://github.com/At1a8/Petra.git"
INSTALL_DOCS = "https://code.claude.com/docs/en/setup"


def _styles(stream) -> tuple[str, str]:
    return ("\033[1;32m", "\033[0m") if getattr(stream, "isatty", lambda: False)() else ("", "")


def log(msg: str) -> None:
    print("[petra-bootstrap] %s" % msg, flush=True)


def warn(msg: str) -> None:
    print("[petra-bootstrap WARN] %s" % msg, file=sys.stderr, flush=True)


def _has(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd, shell: bool = False):
    log(cmd if shell else " ".join(cmd))
    return subprocess.run(cmd, shell=shell)


def _invocation_dir(env) -> str:
    """The directory the user ran pip from. During `pip install git+...` the process cwd is a
    temporary build tree, but the shell's PWD still names the user's directory."""
    pwd = env.get("PWD", "")
    if pwd and os.path.isdir(pwd):
        return os.path.abspath(pwd)
    return os.getcwd()


def is_petra_checkout(path: str) -> bool:
    return (os.path.isdir(os.path.join(path, ".git"))
            and os.path.isfile(os.path.join(path, "petra.js"))
            and os.path.isdir(os.path.join(path, "roles")))


def settings(env=None) -> dict:
    env = os.environ if env is None else env
    inv = _invocation_dir(env)
    home = env.get("PETRA_HOME") or (inv if is_petra_checkout(inv) else os.path.join(inv, "Petra"))
    return {
        "invocation_dir": inv,
        "home": os.path.abspath(os.path.expanduser(home)),
        "repo_url": env.get("PETRA_REPO_URL") or DEFAULT_REPO_URL,
        "ref": env.get("PETRA_REF") or "",
        "claude_version": env.get("CLAUDE_VERSION") or "latest",
        "claude_bin_dir": os.path.abspath(os.path.expanduser(
            env.get("CLAUDE_BIN_DIR") or os.path.join("~", ".local", "bin"))),
    }


def _ver_tuple(s: str) -> tuple:
    out = []
    for part in s.split("."):
        m = re.match(r"\d+", part)
        out.append(int(m.group(0)) if m else 0)
    return tuple(out)


def ver_ge(a: str, b: str) -> bool:
    return _ver_tuple(a) >= _ver_tuple(b)


def claude_version() -> str:
    """Leading semver of `claude --version` (e.g. '2.1.206 (Claude Code)'), '' when absent."""
    if not _has("claude"):
        return ""
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout
    except Exception:
        return ""
    m = re.search(r"\d+\.\d+\.\d+", out or "")
    return m.group(0) if m else ""


# --- 1. the checkout ---------------------------------------------------------

def clone_repo(s: dict) -> bool:
    home = s["home"]
    if home == s["invocation_dir"] and is_petra_checkout(home):
        log("inside a Petra checkout at %s; using it in place" % home)
        return True
    if is_petra_checkout(home):
        log("Petra checkout already at %s; leaving it as it is" % home)
        return True
    if os.path.isdir(home) and os.listdir(home):
        warn("%s exists and is not empty; leaving it untouched. Set PETRA_HOME to another path." % home)
        return False
    if not _has("git"):
        warn("git not found; cannot clone Petra to %s" % home)
        return False
    os.makedirs(os.path.dirname(home) or ".", exist_ok=True)
    cmd = ["git", "clone"] + (["--branch", s["ref"]] if s["ref"] else []) + [s["repo_url"], home]
    if _run(cmd).returncode == 0:
        log("Petra cloned to %s" % home)
        return True
    warn("git clone failed; check the network and your access to %s" % s["repo_url"])
    return False


# --- 2. Claude Code --------------------------------------------------------------

def install_claude(s: dict) -> bool:
    if _has("curl"):
        # The native installer downloads a large binary silently; minutes without output on a slow
        # link are a slow download, not a hang.
        log("installing Claude Code (%s) with the native installer" % s["claude_version"])
        cmd = "curl -fsSL --connect-timeout 20 https://claude.ai/install.sh | bash -s %s" % s["claude_version"]
        if _run(cmd, shell=True).returncode == 0:
            return True
        warn("native installer failed")
    if _has("npm"):
        warn("falling back to npm: npm install -g @anthropic-ai/claude-code")
        if _run(["npm", "install", "-g", "@anthropic-ai/claude-code"]).returncode == 0:
            return True
    warn("could not install Claude Code (need curl or npm, and network access). Manual setup: %s"
         % INSTALL_DOCS)
    return False


def ensure_claude_code(s: dict) -> str:
    """Make sure a Claude Code >= CLAUDE_MIN_VERSION is installed; return the version found after."""
    cur = claude_version()
    if cur and ver_ge(cur, CLAUDE_MIN_VERSION):
        log("Claude Code %s present (>= %s)" % (cur, CLAUDE_MIN_VERSION))
        return cur
    if cur:
        warn("Claude Code %s is older than %s; updating" % (cur, CLAUDE_MIN_VERSION))
        _run(["claude", "update"])
        cur = claude_version()
        if cur and ver_ge(cur, CLAUDE_MIN_VERSION):
            log("Claude Code updated to %s" % cur)
            return cur
    else:
        log("Claude Code CLI not found")
    install_claude(s)
    cur = claude_version()
    if not cur:
        bin_claude = os.path.join(s["claude_bin_dir"], "claude")
        if os.path.isfile(bin_claude):
            log("Claude Code installed at %s (not on PATH yet)" % bin_claude)
        else:
            warn("claude not found after the install; see %s" % INSTALL_DOCS)
    elif not ver_ge(cur, CLAUDE_MIN_VERSION):
        warn("Claude Code %s is still older than %s; run `claude update` or set CLAUDE_VERSION"
             % (cur, CLAUDE_MIN_VERSION))
    return cur


# --- 3. environment (detect only) ------------------------------------------------

def check_environment(env=None) -> dict:
    env = os.environ if env is None else env
    found = {}
    checks = [
        ("git", _has("git"), "git is required: Petra works in a worktree of the framework checkout"),
        ("docker", _has("docker"), "docker not found: Petra runs framework servers in ROCm containers"),
        ("rocm", _has("rocminfo") or _has("rocm-smi"), "ROCm not detected (rocminfo / rocm-smi): GPU work needs AMD Instinct GPUs with ROCm"),
        ("node", _has("node"), "Node.js not found: needed only for tests/dry_run.mjs and for running petra.js outside Claude Code"),
        ("github_token", bool(env.get("GITHUB_TOKEN") or env.get("GH_TOKEN")), "no GITHUB_TOKEN / GH_TOKEN: scan scripts fall back to 10 search requests per minute"),
    ]
    log("checking what Petra uses (detect only)")
    for name, ok, hint in checks:
        found[name] = ok
        if ok:
            log("  %-12s ok" % name)
        else:
            warn("  %-12s %s" % (name, hint))
    return found


# --- 4. next steps ---------------------------------------------------------------

def next_steps(s: dict, path_env: str | None = None, claude_only: bool = False) -> str:
    c_on, c_off = _styles(sys.stdout)
    path_env = os.environ.get("PATH", "") if path_env is None else path_env
    lines = []
    on_path = any(os.path.abspath(p) == s["claude_bin_dir"] for p in path_env.split(os.pathsep) if p)
    if not on_path and os.path.isfile(os.path.join(s["claude_bin_dir"], "claude")):
        lines += ["NOTE: Claude Code is in %s, which is not on your PATH. Add it (~/.zshrc for zsh):" % s["claude_bin_dir"],
                  "    %secho 'export PATH=\"%s:$PATH\"' >> ~/.bashrc && source ~/.bashrc%s" % (c_on, s["claude_bin_dir"], c_off),
                  ""]
    lines += [
        "Next steps:",
        "",
        "1) Give Claude Code API access (pick ONE, and persist it in ~/.bashrc):",
        "   a. Anthropic API:        %sexport ANTHROPIC_API_KEY=sk-ant-...%s" % (c_on, c_off),
        "   b. a gateway or proxy:   %sexport ANTHROPIC_BASE_URL=https://your-gateway%s" % (c_on, c_off),
        "                            %sexport ANTHROPIC_AUTH_TOKEN=your-token%s" % (c_on, c_off),
        "      a gateway that wants its own header:",
        "                            %sexport ANTHROPIC_CUSTOM_HEADERS=\"Header-Name: <key>\"%s" % (c_on, c_off),
        "   c. interactive login:    %sclaude%s   then /login" % (c_on, c_off),
    ]
    if not claude_only:
        lines += [
            "",
            "2) Launch Claude Code with permissions auto-approved, from the Petra checkout:",
            "     %scd %s%s" % (c_on, s["home"], c_off),
            "     %sIS_SANDBOX=1 claude --dangerously-skip-permissions%s" % (c_on, c_off),
            "",
            "3) Start a task, for example:",
            "     use %s/petra.js with mode=scan, petra_dir=%s, framework_dir=/path/to/sglang" % (s["home"], s["home"]),
        ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m petra.bootstrap",
                                 description="Set up Petra: checkout, Claude Code CLI, environment check.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--claude-only", action="store_true", help="only install or update Claude Code")
    g.add_argument("--check", action="store_true", help="only check the environment")
    a = ap.parse_args([] if argv is None else argv)

    if os.environ.get("PETRA_SKIP_BOOTSTRAP"):
        log("PETRA_SKIP_BOOTSTRAP set; skipping")
        return 0
    s = settings()
    if a.check:
        check_environment()
        return 0
    if not a.claude_only:
        log("PETRA_HOME=%s" % s["home"])
        clone_repo(s)
    ensure_claude_code(s)
    if not a.claude_only:
        check_environment()
    print("\n[petra-bootstrap] done.\n\n" + next_steps(s, claude_only=a.claude_only), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
