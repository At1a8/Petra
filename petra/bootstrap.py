"""Petra bootstrap: set up Petra where it runs; safe to run again at any time.

Petra runs inside a ROCm container as root, the way GEAK does. Claude Code is installed once on the
host and the checkouts stay there; the container (scripts/run_docker.sh) mounts /home at the same path
and is recreated on every start, so run this in every new container (README step 3).

Every step checks first, keeps what is already there and installs or creates only what is missing.
Nothing is deleted, overwritten or re-cloned: a step that could only proceed by changing existing
state warns and leaves it alone.

  checkout      clone Petra to $PETRA_HOME, unless run inside a checkout or one is already there
  claude-in     (container) link the host's Claude Code onto PATH instead of installing another
  claude        install the Claude Code CLI if it is still missing; update one older than petra.js needs
  path          put the CLI's directory on PATH for new shells (one marked block in ~/.bashrc)
  claude-state  (root in a container) keep Claude Code's state on the host, in ~/.petra/claude next to
                the keys (CLAUDE_CONFIG_DIR): first-start answers and a /login outlive the container
  git           (root in a container) trust the mounted checkouts, which belong to another user
  shell         (root in a container) no __pycache__ in the checkouts, no Claude Code self-update, the
                keys kept on the host in ~/.petra_env, and with LLM_GATEWAY_KEY Claude Code on the AMD LLM
                gateway
  framework     the image's /sgl-workspace/sglang (whole history) by default; --framework-dir names a host
                checkout instead, cloned with its whole history if missing
  checks        git, docker (host only), ROCm, sglang, Node.js, API access, GitHub token (detect only)

  python3 -B -m petra.bootstrap [--framework-dir DIR]
  python3 -B -m petra.bootstrap --claude-only   # the claude-in, claude, path and claude-state steps
  python3 -B -m petra.bootstrap --check         # the checks

Environment (a flag wins over its variable):
  PETRA_HOME, PETRA_REPO_URL, PETRA_REF       the checkout (default ./Petra, or the one you are in)
  CLAUDE_VERSION, CLAUDE_BIN_DIR              native-installer target (latest), its bin dir (~/.local/bin)
  CLAUDE_CONFIG_DIR                           when set, used as it is instead of ~/.petra/claude
  PETRA_FRAMEWORK_DIR, PETRA_FRAMEWORK_REPO   --framework-dir (default: the image's checkout), --framework-repo
                                              (default: sglang)
  PETRA_SKIP_BOOTSTRAP                        set to skip everything (CI, image builds)

`pip install` runs it while building the wheel. Standard library only.
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
DEFAULT_FRAMEWORK_REPO = "https://github.com/sgl-project/sglang.git"
INSTALL_DOCS = "https://code.claude.com/docs/en/setup"
CONTAINER_CLAUDE = "/usr/local/bin/claude"
KEYS_FILE = ".petra_env"
RC_BEGIN = "# >>> petra: Claude Code CLI on PATH >>>"
RC_END = "# <<< petra: Claude Code CLI on PATH <<<"
ENV_BEGIN = "# >>> petra: root in the container >>>"
ENV_END = "# <<< petra: root in the container <<<"
STATE_DIR = os.path.join(".petra", "claude")
STATE_BEGIN = "# >>> petra: Claude Code state on the host >>>"
STATE_END = "# <<< petra: Claude Code state on the host <<<"
# Root in the container must not leave root-owned __pycache__ in the host's checkouts, and must not
# update the host's Claude Code install (the host updates it).
CONTAINER_ENV = {"PYTHONDONTWRITEBYTECODE": "1", "DISABLE_AUTOUPDATER": "1"}
# The AMD LLM gateway speaks the Anthropic Messages API and authenticates on the
# Ocp-Apim-Subscription-Key header alone; the same key as a bearer token only keeps Claude Code from
# asking for a login, and the gateway ignores it.
AMD_GATEWAY_URL = "https://llm-api.amd.com/Unified"
# sglang images ship a full-history checkout of sglang; tasks clone their own working copy from it.
IMAGE_SGLANG = "/sgl-workspace/sglang"
GATEWAY_ENV = (
    'if [ -n "$LLM_GATEWAY_KEY" ] && [ -z "$ANTHROPIC_BASE_URL" ]; then\n'
    '  export ANTHROPIC_BASE_URL=%s\n'
    '  export ANTHROPIC_CUSTOM_HEADERS="Ocp-Apim-Subscription-Key: $LLM_GATEWAY_KEY"\n'
    '  export ANTHROPIC_AUTH_TOKEN="$LLM_GATEWAY_KEY"\n'
    'fi' % AMD_GATEWAY_URL
)


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


def _out(cmd) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        return 127, "", str(e)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def _expand(path: str, env) -> str:
    if path == "~" or path.startswith("~/"):
        path = (env.get("HOME") or os.path.expanduser("~")) + path[1:]
    return os.path.abspath(path)


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def in_container() -> bool:
    return os.path.exists("/.dockerenv")


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def give_back(path: str) -> None:
    """chown -R what root wrote to the owner of the closest ancestor that is not root's."""
    if not is_root():
        return
    d = os.path.dirname(os.path.abspath(path))
    while True:
        try:
            st = os.stat(d)
        except OSError:
            st = None
        if st and st.st_uid != 0:
            _run(["chown", "-R", "%d:%d" % (st.st_uid, st.st_gid), path])
            return
        parent = os.path.dirname(d)
        if parent == d:
            return
        d = parent


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


def settings(env=None, opts=None) -> dict:
    env = os.environ if env is None else env
    opts = opts or {}
    inv = _invocation_dir(env)
    home = env.get("PETRA_HOME") or (inv if is_petra_checkout(inv) else os.path.join(inv, "Petra"))
    framework_dir = opts.get("framework_dir") or env.get("PETRA_FRAMEWORK_DIR") or ""
    return {
        "invocation_dir": inv,
        "home": _expand(home, env),
        "repo_url": env.get("PETRA_REPO_URL") or DEFAULT_REPO_URL,
        "ref": env.get("PETRA_REF") or "",
        "claude_version": env.get("CLAUDE_VERSION") or "latest",
        "claude_bin_dir": _expand(env.get("CLAUDE_BIN_DIR") or "~/.local/bin", env),
        "user_home": _expand("~", env),
        "shell": env.get("SHELL") or "",
        "framework_dir": _expand(framework_dir, env) if framework_dir else "",
        "framework_repo": opts.get("framework_repo") or env.get("PETRA_FRAMEWORK_REPO") or DEFAULT_FRAMEWORK_REPO,
    }


def owner_dirs(s: dict) -> list:
    """Ancestors of the Petra checkout, closest first, owned by the checkout's owner: in the
    container, the host home that holds that user's Claude Code and keys."""
    try:
        uid = os.stat(s["home"]).st_uid
    except OSError:
        return []
    out, d = [], os.path.dirname(s["home"])
    while d != os.path.dirname(d):
        try:
            if os.stat(d).st_uid == uid:
                out.append(d)
        except OSError:
            pass
        d = os.path.dirname(d)
    return out


def host_claude(s: dict) -> str:
    for d in owner_dirs(s):
        cand = os.path.join(d, ".local", "bin", "claude")
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return ""


def keys_file(s: dict) -> str:
    """~/.petra_env of the checkout's owner: next to their Claude Code, else in the topmost
    directory they own."""
    claude = host_claude(s)
    if claude:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(claude))), KEYS_FILE)
    dirs = owner_dirs(s)
    return os.path.join(dirs[-1], KEYS_FILE) if dirs else ""


def claude_state_dir(s: dict) -> str:
    """Where root in the container keeps Claude Code's state: ~/.petra/claude of the checkout's owner,
    next to the keys. Separate from their own ~/.claude, which root would otherwise take over."""
    keys = keys_file(s)
    return os.path.join(os.path.dirname(keys), STATE_DIR) if keys else ""


def _ver_tuple(s: str) -> tuple:
    out = []
    for part in s.split("."):
        m = re.match(r"\d+", part)
        out.append(int(m.group(0)) if m else 0)
    return tuple(out)


def ver_ge(a: str, b: str) -> bool:
    return _ver_tuple(a) >= _ver_tuple(b)


# --- checkout --------------------------------------------------------------------

def ensure_checkout(s: dict) -> tuple[str, str]:
    home = s["home"]
    if is_petra_checkout(home):
        log("checkout: kept %s" % home)
        return "kept", home
    if os.path.isdir(home) and os.listdir(home):
        warn("checkout: %s exists and is not a Petra checkout; left untouched (set PETRA_HOME)" % home)
        return "skipped", "%s is not empty" % home
    if not _has("git"):
        warn("checkout: git not found; cannot clone Petra to %s" % home)
        return "failed", "no git"
    os.makedirs(os.path.dirname(home) or ".", exist_ok=True)
    cmd = ["git", "clone"] + (["--branch", s["ref"]] if s["ref"] else []) + [s["repo_url"], home]
    if _run(cmd).returncode == 0:
        give_back(home)
        log("checkout: cloned to %s" % home)
        return "created", home
    warn("checkout: git clone failed; check the network and your access to %s" % s["repo_url"])
    return "failed", "git clone"


# --- Claude Code -----------------------------------------------------------------

def ensure_claude_link(s: dict) -> tuple[str, str]:
    """In the container, call the host's Claude Code (seen through the /home mount) through a link on
    PATH, so it is installed once and the host's updates reach every container."""
    found = shutil.which("claude")
    if found:
        log("claude-in: kept (%s)" % found)
        return "kept", found
    host = host_claude(s)
    if not host:
        warn("claude-in: no Claude Code in the home that owns %s; install it on the host (README step 1)" % s["home"])
        return "skipped", "no host install"
    if os.path.lexists(CONTAINER_CLAUDE):
        warn("claude-in: %s exists but is not on PATH; left as it is" % CONTAINER_CLAUDE)
        return "skipped", "%s exists" % CONTAINER_CLAUDE
    try:
        os.symlink(host, CONTAINER_CLAUDE)
    except OSError as e:
        warn("claude-in: could not link %s (%s)" % (CONTAINER_CLAUDE, e))
        return "failed", CONTAINER_CLAUDE
    log("claude-in: linked %s -> %s" % (CONTAINER_CLAUDE, host))
    return "added", "%s -> %s" % (CONTAINER_CLAUDE, host)


def find_claude(s: dict) -> str:
    """The claude on PATH, else one the native installer left in CLAUDE_BIN_DIR (not on PATH yet)."""
    found = shutil.which("claude")
    if found:
        return found
    cand = os.path.join(s["claude_bin_dir"], "claude")
    return cand if os.path.isfile(cand) and os.access(cand, os.X_OK) else ""


def claude_version(path: str) -> str:
    """Leading semver of `claude --version` (e.g. '2.1.206 (Claude Code)'), '' when absent."""
    if not path:
        return ""
    rc, out, _ = _out([path, "--version"])
    m = re.search(r"\d+\.\d+\.\d+", out)
    return m.group(0) if rc == 0 and m else ""


def install_claude(s: dict) -> bool:
    if _has("curl"):
        # The native installer downloads a large binary silently; minutes without output on a slow
        # link are a slow download, not a hang.
        log("claude: native installer (%s)" % s["claude_version"])
        cmd = "curl -fsSL --connect-timeout 20 https://claude.ai/install.sh | bash -s %s" % s["claude_version"]
        if _run(cmd, shell=True).returncode == 0:
            return True
        warn("claude: native installer failed")
    if _has("npm"):
        warn("claude: falling back to npm install -g @anthropic-ai/claude-code")
        if _run(["npm", "install", "-g", "@anthropic-ai/claude-code"]).returncode == 0:
            return True
    warn("claude: could not install Claude Code (need curl or npm, and network access). Manual setup: %s"
         % INSTALL_DOCS)
    return False


def ensure_claude_code(s: dict) -> tuple[str, str]:
    path = find_claude(s)
    cur = claude_version(path)
    if cur and ver_ge(cur, CLAUDE_MIN_VERSION):
        log("claude: kept %s (%s)" % (cur, path))
        return "kept", cur
    if cur:
        warn("claude: %s is older than %s; updating it" % (cur, CLAUDE_MIN_VERSION))
        _run([path, "update"])
        cur = claude_version(find_claude(s))
        if cur and ver_ge(cur, CLAUDE_MIN_VERSION):
            log("claude: updated to %s" % cur)
            return "updated", cur
    else:
        log("claude: not found; installing")
    install_claude(s)
    cur = claude_version(find_claude(s))
    if cur and ver_ge(cur, CLAUDE_MIN_VERSION):
        log("claude: installed %s" % cur)
        return "installed", cur
    if cur:
        warn("claude: %s is still older than %s; run `claude update` or set CLAUDE_VERSION"
             % (cur, CLAUDE_MIN_VERSION))
    else:
        warn("claude: not found after the install; see %s" % INSTALL_DOCS)
    return "failed", cur


# --- shell rc files --------------------------------------------------------------

def rc_file(s: dict) -> str:
    return os.path.join(s["user_home"], ".zshrc" if os.path.basename(s["shell"]) == "zsh" else ".bashrc")


def _append(rc: str, block: str) -> bool:
    try:
        with open(rc, "a", encoding="utf-8") as f:
            f.write(block)
        return True
    except OSError as e:
        warn("could not append to %s (%s)" % (rc, e))
        return False


def _on_path(d: str, path_env: str) -> bool:
    return any(os.path.abspath(p) == d for p in path_env.split(os.pathsep) if p)


def ensure_path(s: dict, path_env: str | None = None) -> tuple[str, str]:
    d = s["claude_bin_dir"]
    path_env = os.environ.get("PATH", "") if path_env is None else path_env
    if not os.path.isfile(os.path.join(d, "claude")):
        return "skipped", "claude is not in %s" % d
    if _on_path(d, path_env):
        log("path: kept (%s is on PATH)" % d)
        return "kept", d
    rc = rc_file(s)
    text = _read(rc)
    names = {d}
    if d.startswith(s["user_home"] + os.sep):
        rel = d[len(s["user_home"]):]
        names |= {"$HOME" + rel, "${HOME}" + rel, "~" + rel}
    if RC_BEGIN in text or any(n in text for n in names):
        log("path: kept (%s already puts %s on PATH)" % (rc, d))
        return "kept", rc
    block = '\n%s\ncase ":$PATH:" in *":%s:"*) ;; *) export PATH="%s:$PATH" ;; esac\n%s\n' % (RC_BEGIN, d, d, RC_END)
    if not _append(rc, block):
        return "failed", rc
    log("path: added %s to %s" % (d, rc))
    return "added", rc


def ensure_shell_env(s: dict) -> tuple[str, str]:
    rc = rc_file(s)
    if ENV_BEGIN in _read(rc):
        log("shell: kept (%s)" % rc)
        return "kept", rc
    lines = ["export %s=%s" % kv for kv in CONTAINER_ENV.items()]
    keys = keys_file(s)
    if keys:
        lines.append('[ -r "%s" ] && . "%s"' % (keys, keys))
    lines.append(GATEWAY_ENV)
    if not _append(rc, "\n%s\n%s\n%s\n" % (ENV_BEGIN, "\n".join(lines), ENV_END)):
        return "failed", rc
    log("shell: added %s%s to %s" % (", ".join(CONTAINER_ENV), " and %s" % keys if keys else "", rc))
    return "added", rc


def ensure_claude_state(s: dict, env=None) -> tuple[str, str]:
    """Root's home goes with the container, and with it every answer Claude Code asked for at its first
    start (the API key, the folder trust, bypass permissions) and any /login. Keep them on the host."""
    env = os.environ if env is None else env
    if env.get("CLAUDE_CONFIG_DIR"):
        log("claude-state: kept (CLAUDE_CONFIG_DIR=%s)" % env["CLAUDE_CONFIG_DIR"])
        return "kept", env["CLAUDE_CONFIG_DIR"]
    d = claude_state_dir(s)
    if not d:
        warn("claude-state: no home owned by the owner of %s; Claude Code's state stays in the container" % s["home"])
        return "skipped", "no host home"
    created = not os.path.isdir(d)
    if created:
        try:
            os.makedirs(d, mode=0o700)
        except OSError as e:
            warn("claude-state: could not create %s (%s)" % (d, e))
            return "failed", d
    give_back(os.path.dirname(d))  # what Claude Code wrote there as root stays manageable from the host
    rc = rc_file(s)
    if STATE_BEGIN in _read(rc):
        log("claude-state: kept (%s)" % rc)
        return ("created" if created else "kept"), d
    if not _append(rc, '\n%s\nexport CLAUDE_CONFIG_DIR="%s"\n%s\n' % (STATE_BEGIN, d, STATE_END)):
        return "failed", rc
    log("claude-state: Claude Code keeps its state in %s (CLAUDE_CONFIG_DIR, in %s)" % (d, rc))
    return ("created" if created else "added"), d


# --- git, as root in a container -------------------------------------------------

def ensure_git_trust(s: dict) -> tuple[str, str]:
    """git refuses repositories owned by another user; in the container every mounted checkout is."""
    if not _has("git"):
        return "skipped", "no git"
    _, out, _ = _out(["git", "config", "--global", "--get-all", "safe.directory"])
    if "*" in out.splitlines():
        log("git: kept (safe.directory '*')")
        return "kept", "safe.directory '*'"
    if _run(["git", "config", "--global", "--add", "safe.directory", "*"]).returncode == 0:
        return "added", "safe.directory '*'"
    warn("git: could not set safe.directory")
    return "failed", "git config"


# --- framework checkout ----------------------------------------------------------

def _repo_key(url: str) -> str:
    u = re.sub(r"\.git$", "", url.strip().rstrip("/"))
    u = re.sub(r"^(?:ssh://)?git@([^:/]+)[:/]", r"https://\1/", u)
    return u.lower()


def image_checkout() -> str:
    """The sglang image's own checkout, Petra's default framework source, when this is such an image."""
    return IMAGE_SGLANG if os.path.isdir(os.path.join(IMAGE_SGLANG, ".git")) else ""


def ensure_framework(s: dict) -> tuple[str, str]:
    d = s["framework_dir"] or image_checkout()
    if not d:
        return "skipped", "no --framework-dir and no image checkout"
    if os.path.exists(os.path.join(d, ".git")):
        _, head, _ = _out(["git", "-C", d, "log", "-1", "--format=%h %cs"])
        _, shallow, _ = _out(["git", "-C", d, "rev-parse", "--is-shallow-repository"])
        _, origin, _ = _out(["git", "-C", d, "remote", "get-url", "origin"])
        log("framework: kept %s (%s)%s" % (d, head or "no commits",
                                          "; the image's checkout, Petra's default" if d == IMAGE_SGLANG else ""))
        if shallow == "true":
            warn("framework: %s is a shallow clone; ci bisects and the upstream scan need its history. "
                 "It is left as it is (`git -C %s fetch --unshallow` would deepen it)" % (d, d))
        if origin and _repo_key(origin) != _repo_key(s["framework_repo"]):
            warn("framework: %s tracks %s, not %s; kept as it is" % (d, origin, s["framework_repo"]))
        return "kept", d
    if os.path.isdir(d) and os.listdir(d):
        warn("framework: %s exists and is not a git checkout; left untouched" % d)
        return "skipped", "%s is not a git checkout" % d
    if not _has("git"):
        warn("framework: git not found; cannot clone to %s" % d)
        return "failed", "no git"
    os.makedirs(os.path.dirname(d) or ".", exist_ok=True)
    # Blobless: the whole commit history for bisects and the upstream scan, file contents on demand.
    if _run(["git", "clone", "--filter=blob:none", s["framework_repo"], d]).returncode == 0:
        give_back(d)
        log("framework: cloned %s to %s" % (s["framework_repo"], d))
        return "created", d
    warn("framework: git clone of %s failed" % s["framework_repo"])
    return "failed", "git clone"


# --- checks (detect only) --------------------------------------------------------

def api_configured(env, user_home: str) -> bool:
    config_dir = env.get("CLAUDE_CONFIG_DIR") or os.path.join(user_home, ".claude")
    return bool(env.get("LLM_GATEWAY_KEY") or env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_AUTH_TOKEN")
                or (env.get("ANTHROPIC_BASE_URL") and env.get("ANTHROPIC_CUSTOM_HEADERS"))
                or os.path.isfile(os.path.join(config_dir, ".credentials.json")))


def _importable(module: str) -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def keys_defined(path: str) -> set:
    """Names a keys file sets to a real value; a value still in <angle brackets> is the README's
    placeholder and does not count. Values are never read into the report."""
    names = set()
    for line in _read(path).splitlines() if path else ():
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_]\w*)=(.*)$", line)
        value = m.group(2).strip().strip("'\"") if m else ""
        if value and not value.startswith("<"):
            names.add(m.group(1))
    return names


def check_environment(env=None, keys_path: str = "") -> dict:
    """keys_path: ~/.petra_env, which new shells load; what it sets counts before this shell has it."""
    env = dict(os.environ if env is None else env)
    for name in keys_defined(keys_path):
        env.setdefault(name, "set in %s" % keys_path)
    checks = [("git", _has("git"), "git is required: Petra works in a worktree of the framework checkout")]
    if not in_container():
        checks.append(("docker", _has("docker"), "docker not found: scripts/run_docker.sh starts Petra's container"))
    checks += [
        ("rocm", _has("rocminfo") or _has("rocm-smi"), "ROCm not detected (rocminfo / rocm-smi): GPU work needs AMD Instinct GPUs with ROCm"),
        ("sglang", _importable("sglang"), "sglang is not importable here: run Petra where the framework is installed (the container)"),
        ("node", _has("node"), "Node.js not found: needed only for tests/dry_run.mjs and for running petra.js outside Claude Code"),
        ("api", api_configured(env, _expand("~", env)), "no Claude Code API access in this shell (see the next steps)"),
        ("github_token", bool(env.get("GITHUB_TOKEN") or env.get("GH_TOKEN")),
         "no GITHUB_TOKEN: GitHub then allows 60 requests an hour and 10 searches a minute per IP, so scans "
         "crawl and can stop partway; add a read-only token to ~/.petra_env (README step 1)"),
    ]
    found = {}
    log("checks (detect only):")
    for name, ok, hint in checks:
        found[name] = ok
        if ok:
            log("  %-12s ok" % name)
        else:
            warn("  %-12s %s" % (name, hint))
    return found


# --- report ----------------------------------------------------------------------

def summary(results: list) -> str:
    rows = ["  %-12s %-10s %s" % r for r in results]
    return "summary (safe to re-run: what is already there is kept):\n" + "\n".join(rows)


def next_steps(s: dict, statuses: dict, found: dict | None = None, path_env: str | None = None,
               claude_only: bool = False) -> str:
    c_on, c_off = _styles(sys.stdout)
    hl = lambda t: "%s%s%s" % (c_on, t, c_off)  # noqa: E731
    path_env = os.environ.get("PATH", "") if path_env is None else path_env
    steps = []
    d = s["claude_bin_dir"]
    reload_rc = statuses.get("shell") == "added" or statuses.get("claude-state") in ("added", "created") or (
        os.path.isfile(os.path.join(d, "claude")) and not _on_path(d, path_env) and statuses.get("path") in ("added", "kept"))
    if reload_rc:
        steps.append(["Load the new settings into this shell (new shells have them):", hl("source %s" % rc_file(s))])
    state = ""
    if statuses.get("claude-state") in ("added", "created", "kept"):
        state = os.environ.get("CLAUDE_CONFIG_DIR") or claude_state_dir(s)
    keys = keys_file(s) if in_container() else ""
    api = (found or {}).get("api")
    if api is None:
        api = api_configured(os.environ, s["user_home"])
    if not api and not (keys and os.path.isfile(keys)):
        where = ("on the host, in %s (only you can read it; every container loads it):" % keys) if keys \
            else "(pick one; keep it in %s):" % rc_file(s)
        steps.append([
            "Give Claude Code API access %s" % where,
            "a. AMD LLM gateway:     " + hl("export LLM_GATEWAY_KEY=<your key>") + "   (%s)" % AMD_GATEWAY_URL,
            "b. Anthropic API:       " + hl("export ANTHROPIC_API_KEY=sk-ant-..."),
            "c. another gateway:     " + hl("export ANTHROPIC_BASE_URL=https://your-gateway"),
            "                        " + hl("export ANTHROPIC_AUTH_TOKEN=your-token"),
            "   (a gateway that wants its own header: " + hl('export ANTHROPIC_CUSTOM_HEADERS="Header-Name: <key>"') + ")",
            "d. interactive login:   " + hl("claude") + "   then /login"
            + ("  (kept in %s)" % state if state else "  (lost with the container)" if keys else ""),
        ])
    if not claude_only:
        if s["framework_dir"]:
            fw = ", framework_dir=%s" % s["framework_dir"]
        else:
            fw = "" if image_checkout() else ", framework_dir=/path/to/sglang"
        start = ["Start Claude Code from the checkout, permissions auto-approved (README step 4):",
                 hl("cd %s && IS_SANDBOX=1 claude --dangerously-skip-permissions" % s["home"])]
        if in_container():
            start += ["The first start asks a few questions %s; answer these, the defaults would stop you:"
                      % ("once (the answers are kept in %s)" % state if state else "in every new container"),
                      "  use the API key from your environment?  " + hl("Yes") + "   (asked only for an Anthropic API key)",
                      "  trust this folder?                      " + hl("Yes, I trust this folder"),
                      "  Bypass Permissions mode                 " + hl("Yes, I accept")]
        steps.append(start)
        elsewhere = "" if in_container() else ", container=<container>"
        steps.append(["Give it a task, e.g. collect and rank tasks, or take one issue:",
                      "use %s/petra.js with mode=scan, petra_dir=%s%s" % (s["home"], s["home"], fw),
                      "use %s/petra.js with mode=issue, task=<issue URL>, petra_dir=%s%s, gpu_ids=0%s"
                      % (s["home"], s["home"], fw, elsewhere)])
    lines = ["Next steps:"]
    for i, (head, *body) in enumerate(steps, 1):
        lines.append("%d) %s" % (i, head))
        lines += ["     " + b for b in body]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -B -m petra.bootstrap",
                                 description="Set up Petra where it runs (README step 3). "
                                             "Safe to re-run: what is already there is kept.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--claude-only", action="store_true", help="only the Claude Code and PATH steps")
    g.add_argument("--check", action="store_true", help="only the environment checks")
    ap.add_argument("--framework-dir", help="framework checkout for tasks; cloned only if missing (PETRA_FRAMEWORK_DIR)")
    ap.add_argument("--framework-repo", help="repository to clone it from (default: sglang; PETRA_FRAMEWORK_REPO)")
    a = ap.parse_args([] if argv is None else argv)

    if os.environ.get("PETRA_SKIP_BOOTSTRAP"):
        log("PETRA_SKIP_BOOTSTRAP set; skipping")
        return 0
    s = settings(opts={"framework_dir": a.framework_dir, "framework_repo": a.framework_repo})
    container = in_container()
    keys = keys_file(s) if container else ""
    if a.check:
        check_environment(keys_path=keys)
        return 0
    steps = [] if a.claude_only else [("checkout", ensure_checkout)]
    if container:
        steps.append(("claude-in", ensure_claude_link))
    steps += [("claude", ensure_claude_code), ("path", ensure_path)]
    if container and is_root():
        steps.append(("claude-state", ensure_claude_state))
    if not a.claude_only:
        if container and is_root():
            steps += [("git", ensure_git_trust), ("shell", ensure_shell_env)]
        steps.append(("framework", ensure_framework))
    results = [(name,) + step(s) for name, step in steps]
    statuses = {step: status for step, status, _ in results}
    state = {step: detail for step, _, detail in results}.get("claude-state")
    if state and statuses.get("claude-state") in ("added", "created", "kept"):
        os.environ.setdefault("CLAUDE_CONFIG_DIR", state)  # this run's checks see a login kept there
    found = None if a.claude_only else check_environment(keys_path=keys)
    print("\n[petra-bootstrap] %s\n\n%s" % (summary(results), next_steps(s, statuses, found, claude_only=a.claude_only)),
          flush=True)
    return 1 if "failed" in statuses.values() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
