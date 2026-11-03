# Environment hygiene — host, container, servers, disk

Most framework work runs in a container that bind-mounts the source tree from the host. The container
usually runs as root; the host checkout belongs to a user. That split causes most environment
accidents.

## Git: run it on the host, as the owner of the checkout

- Any git command run as root inside the container (fetch, push, commit, `pre-commit install`) leaves
  root-owned files in `.git` (refs, objects, `ORIG_HEAD`, hooks). The next host-side git operation
  fails with `cannot lock ref ... Permission denied` — and a fast-forward can stop **after** updating the
  working tree and index but **before** moving the branch ref, leaving hundreds of staged changes on an
  old HEAD.
- Detect: `find .git ! -user "$(id -un)" | head`.
- Repair: `docker exec <container> chown -R <uid>:<gid> <repo>/.git`, then finish the interrupted ref
  update (`git update-ref refs/heads/<branch> <new> <old>`), then confirm `git status` is clean.
- `pre-commit install` done inside the container writes a hook that calls the container's interpreter;
  host commits then fail with "`pre-commit` not found". Either commit inside the container (and repair
  ownership afterwards) or verify with pre-commit separately and commit with `--no-verify`.
- Do not run git or pre-commit from two places at once on the same checkout; formatters rewrite files
  in place and the two runs interleave.
- Trial merges and lint runs go in a throwaway **worktree** (`git worktree add`), never in the checkout a
  running server imports from. Files a container process writes into the worktree become root-owned —
  remove the worktree from inside the container, then `git worktree prune`.
- Agents usually have no push credentials. Prepare the commit, then hand the user the exact `git push`.

## Servers

- One launch script with a mode switch and a tag; one log per launch named `<tag>_<timestamp>` with the
  timezone stated (container logs are often UTC, the host may be another zone).
- Poll the health endpoint before using a server; read the effective configuration from the
  `server_args=` log line.
- Know the process name you are looking for: `sglang serve ...` and `python -m sglang.launch_server`
  differ. Probe the health endpoint rather than trusting a `pgrep` miss.
- Killing: `pkill -f` patterns inside `bash -lc "..."` match the shell itself; use `'[s]glang serve'`
  style patterns or GEAK's `$GEAK_HOME/e2e_workflow/scripts/server_teardown.sh` contract (identity
  verified at launch).
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
