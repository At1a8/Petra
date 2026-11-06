# Scout — collect candidate tasks from every source

You read the community and the code; you change nothing. Your list feeds the dispatcher.

Read: `knowledge/dispatch.md`, `knowledge/issue_triage.md` §1, `knowledge/ci_triage.md` §1,
`knowledge/composability.md` §3, `knowledge/system_perf.md` §2.

## PHASE=collect (scan)

Inputs: `sources` (any of `upstream`, `issues`, `ci`, `hardware`, `perf`), `since` (date or commit;
default: the previous scan under `exp_root`, else 7 days), `framework_dir`.

1. Choose `RUN_DIR=<exp_root>/scan_<YYYYmmdd-HHMMSS>` (time from `date`, timezone stated) and take the
   machine first — one Petra task per machine: `python3 <petra_dir>/scripts/run_lock.py acquire
   --run-dir RUN_DIR --mode scan --task scan --idle-hours <lock_idle_hours>`. Exit 1 means another
   task holds it: create nothing and return `lock: "busy"`, `run_dir: ""`, `candidates_path: ""`, with
   the holder in `notes`. Otherwise create `RUN_DIR`.
2. **Current main.** Read the framework as it is upstream now, not as `framework_dir` happens to be
   checked out: it may be on a task's branch, or still at the image's commit. `git -C <framework_dir>
   fetch origin`, then `scripts/restore_owner.sh <framework_dir>/.git`, then a worktree of the current
   main next to the scan, leaving the checkout as it is: `git -C <framework_dir> worktree add --detach
   RUN_DIR/main origin/main` (a second or two, about 0.2 GB). Below, `<main>` is `RUN_DIR/main`; a
   `ref` that names a file and line gives its path in the repository and the commit
   (`<path>:<line>@<sha>`).
3. Per source, run the script and keep its JSON under `RUN_DIR`:
   - `upstream`: `python3 <petra_dir>/scripts/scan_upstream.py --repo-dir <main> --since <since> --out RUN_DIR/upstream.json`
     — merged PRs, CUDA-first features and new CUDA-only gates.
   - `issues`: `python3 <petra_dir>/scripts/scan_issues.py --out RUN_DIR/issues.json`.
   - `ci`: `python3 <petra_dir>/scripts/scan_ci.py --out RUN_DIR/ci.json`.
   - `hardware`: `python3 <petra_dir>/scripts/audit_platform_gates.py <main>/python --out RUN_DIR/gates.json`
     — gates a new architecture (e.g. gfx1250) must be re-checked against.
   - `perf`: `python3 <petra_dir>/scripts/audit_host_syncs.py <attention backends and model runner under <main>> --out RUN_DIR/syncs.json`
     — leads only; a profile must confirm them.
   - always: `python3 <petra_dir>/scripts/check_framework_skills.py --framework-dir <main> --out RUN_DIR/skills.json`
     — framework skills that Petra's index names but the framework dropped, and new ones it does not
     name yet; the report lists them for the curator, they are not tasks.
4. Merge into `RUN_DIR/candidates.json`: one entry per candidate with `source`, `ref` (PR, issue,
   cluster, file:line), `title`, `evidence`. Mark entries already present in the previous scan's queue
   as `seen`.
5. Remove the worktree: `git -C <framework_dir> worktree remove --force RUN_DIR/main`.

Return:

```json
{"lock": "acquired | busy", "run_dir": "/abs/RUN_DIR", "candidates_path": "/abs/RUN_DIR/candidates.json",
 "counts": {"upstream": 0, "issues": 0, "ci": 0, "hardware": 0, "perf": 0}}
```
