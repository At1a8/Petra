# Environment hygiene — host, container, servers, disk

Most framework work runs in a container that bind-mounts the source tree from the host. The container
usually runs as root; the host checkout belongs to a user. That split causes most environment
accidents.

## Git: as root in the container, give the files back

Petra runs git inside the container, as root, on checkouts that belong to a host user.

- Any git write as root (worktree add, fetch, commit, cherry-pick, rebase, `pre-commit install`) leaves
  root-owned files in `.git` (refs, objects, `ORIG_HEAD`, hooks) and in the worktree. The next host-side
  git operation fails with `cannot lock ref ... Permission denied` — and a fast-forward can stop
  **after** updating the working tree and index but **before** moving the branch ref, leaving hundreds
  of staged changes on an old HEAD.
- So after every git write, and before handing over a push command, give them back:
  `<petra_dir>/scripts/restore_owner.sh <run_dir>` — the task's clone and its `.git` live there — plus
  the `.git` of any host checkout you fetched into (each path goes to the owner of its closest ancestor
  that is not root's; nothing happens when not root, or for the image's own checkout).
- Detect leftovers: `find <repo>/.git ! -user "$(stat -c %U <repo>)" | head`.
- An update interrupted by a permission error: restore ownership, finish the ref update
  (`git update-ref refs/heads/<branch> <new> <old>`), then confirm `git status` is clean.
- git refuses a repository another user owns ("dubious ownership"); the container setup trusts the
  mounted checkouts (`safe.directory '*'`). Python runs there with `PYTHONDONTWRITEBYTECODE=1`, so
  imports leave no root-owned `__pycache__` in the checkouts.
- `pre-commit install` inside the container writes a hook that calls the container's interpreter; a
  commit from the host then fails with "`pre-commit` not found". Commit inside the container.
- Do not run git or pre-commit from two places at once on the same checkout; formatters rewrite files
  in place and the two runs interleave.
- Trial merges and lint runs go in a throwaway **worktree** (`git worktree add`), never in the checkout a
  running server imports from; give it back like any other write, remove it with `git worktree remove`,
  then `git worktree prune`.
- Agents usually have no push credentials. Prepare the commit, then hand the user the exact `git push`.

## The code under test

- The image provides the runtime — PyTorch, aiter, sgl-kernel — and its own copy of the framework,
  installed in editable mode from the image's checkout (`/sgl-workspace/sglang` in `rocm/sgl-dev`). A
  plain `python -m sglang.launch_server` runs that copy, never the task's changes.
- That checkout has the whole history and is Petra's default `framework_dir`: `git fetch` brings it the
  current main, without touching its working tree, which stays detached at the image's commit with the
  image's build changes. Each task works in its own clone under `RUN_DIR/wt`, seeded from it with
  `git clone --reference <framework_dir> --dissociate <origin URL>`: a standalone repository on the
  host, so its branch and commits outlive the container, which a worktree of the image's checkout
  would not.
- Run every server, test and benchmark from the worktree under test, first on `PYTHONPATH` (sglang:
  `PYTHONPATH=<worktree>/python`), and check it once per launch script:
  `python -c "import sglang; print(sglang.__file__)"` must print a path inside the worktree. Both arms
  of an A/B run from the worktree: the baseline at the base commit or with the feature off, never the
  image's copy.
- Tasks test the newest sglang: the task's clone starts from the current upstream main and, unless the user
  named an image or a container, the image is the newest daily build for its ROCm and GPU
  (`scripts/latest_image.py`, which `scripts/run_docker.sh` starts from; the `miles` images are for
  reinforcement learning). Compiled packages too old for the worktree fail at import or startup: that is
  an environment failure that names the newer image, not a framework bug to fix.

## Servers

- One launch script with a mode switch and a tag; one log per launch named `<tag>_<timestamp>` with the
  timezone stated (container logs are often UTC, the host may be another zone).
- Poll the health endpoint before using a server; read the effective configuration from the
  `server_args=` log line.
- Know the process name you are looking for: `sglang serve ...` and `python -m sglang.launch_server`
  differ. Probe the health endpoint rather than trusting a `pgrep` miss.
- Killing: `pkill -f` patterns inside `bash -lc "..."` match the shell itself; use `'[s]glang serve'`
  style patterns. Better, record the server's identity at launch (its PID, and whether it leads its
  own process group) and kill from that record: the PID and its descendants (`setsid` workers keep
  VRAM otherwise), the whole group only when the launch proved the group is the server's. Never look
  the group up at kill time: a recycled PID belongs to a stranger, and a teardown that did this once
  TERMed a container's PID 1 (GEAK's `server_teardown.sh` contract).
- Every server, test and benchmark runs with `HIP_VISIBLE_DEVICES=<gpu_ids>`, the set Setup pinned;
  without it, tensor-parallel ranks land on GPUs 0..N-1 whoever is using them.
- Keep one server per GPU set; a previous server still holding the GPUs looks like an out-of-memory bug.
  Stop it only if this run started it (its recorded PID); a GPU busy with anything else is somebody's
  work — wait, or ask Setup for other GPUs, never kill it or reset the GPU (`guardrails.md` §3).
- Running a test that needs a GPU the server occupies: stop the server first.

## Disk and tools

- GPU memory faults leave core dumps (`gpucore.<pid>.gpu`, tens of GB each) in the working directory.
  Check after any fault and delete them once the fault is understood.
- Containers may lack host tools (e.g. `rg`); scripts that run inside the container should use `grep`.
- Generated build outputs (e.g. hipified `*.hip` files from JIT builds) show up as untracked files; never
  `git add -A`.

## Code you edit while a server runs

An editable install imports from the checkout. Edits do not affect a running server's already-imported
modules, but JIT kernels compile from the source files at first use and future launches pick everything
up. Restart servers after edits you intend to test, and record which commit each log ran.
