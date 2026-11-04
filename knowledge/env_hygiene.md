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
  `<petra_dir>/scripts/restore_owner.sh <framework_dir>/.git <worktree> <run_dir>` (each path goes to
  the owner of its closest ancestor that is not root's; nothing happens when not root).
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
- Keep one server per GPU set; a previous server still holding the GPUs looks like an out-of-memory bug.
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
