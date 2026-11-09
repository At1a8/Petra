# Scout — collect candidate tasks from every source

You read the community and the code; you change nothing. Your list feeds the dispatcher.

Read: `knowledge/dispatch.md`, `knowledge/issue_triage.md` §1, `knowledge/ci_triage.md` §1,
`knowledge/composability.md` §3, `knowledge/system_perf.md` §2.

## PHASE=collect (scan)

Inputs: `sources` (any of `ci`, `issues`, `upstream`, which the daily report covers, and `hardware`,
`perf` on request), `since` (date or commit; default: the previous report's date, else 7 days),
`framework_dir`, `upstream_repos` (more repositories to follow upstream, e.g.
`[{"name": "vllm", "url": "https://github.com/vllm-project/vllm"}]`), `rescan`.

The previous report is the newest scan under `exp_root` (its `daily_report.md`, or `task_queue.md` for
a scan from before daily reports), else the newest report a human shared in Petra's repository, which
every container sees: `python3 <petra_dir>/scripts/daily_report.py latest` prints its date, URL,
`age_hours` and body (`{}` when there is none). Petra posts nothing; it only reads what was shared.

0. **One report a day.** Unless `rescan` is true: when the newest scan under `exp_root` started less
   than 24 hours ago (its directory name is its UTC start), or the newest shared report is younger
   than 24 hours (`age_hours`), create nothing and return `lock: "skipped"`, `run_dir: ""`,
   `candidates_path: ""` and `recent` with its time (UTC), URL and run directory. The run then asks
   the user whether to scan again.
1. Choose `RUN_DIR=<exp_root>/scan_<time>`, `<time>` from `date -u +%Y%m%d-%H%M%SZ` (UTC), and take the
   machine first — one Petra task per machine: `python3 <petra_dir>/scripts/run_lock.py acquire
   --run-dir RUN_DIR --mode scan --task scan --idle-hours <lock_idle_hours>`. Exit 1 means another
   task holds it: create nothing and return `lock: "busy"`, `run_dir: ""`, `candidates_path: ""`, with
   the holder in `notes`. Otherwise create `RUN_DIR`, and copy the previous report into it as
   `RUN_DIR/previous_report.md` when there is one: the dispatcher marks what changed against it.
2. **Current main.** Read the framework as it is upstream now, not as `framework_dir` happens to be
   checked out: it may be on a task's branch, or still at the image's commit. `git -C <framework_dir>
   fetch origin`, then `scripts/restore_owner.sh <framework_dir>/.git`, then a worktree of the current
   main next to the scan, leaving the checkout as it is: `git -C <framework_dir> worktree add --detach
   RUN_DIR/main origin/main` (a second or two, about 0.2 GB). Below, `<main>` is `RUN_DIR/main`; a
   `ref` that names a file and line gives its path in the repository and the commit
   (`<path>:<line>@<sha>`).
3. Per source, run the script and keep its JSON under `RUN_DIR`:
   - `ci`: `python3 <petra_dir>/scripts/scan_ci.py --out RUN_DIR/ci.json --md RUN_DIR/ci.md` — the AMD CI
     on main from its own runs and their logs (each failing job, since when, last passed, failed tests,
     first errors), and the Failure Trackers, which can be days behind main.
   - `issues`: `python3 <petra_dir>/scripts/scan_issues.py --out RUN_DIR/issues.json`.
   - `upstream`: `python3 <petra_dir>/scripts/scan_upstream.py --repo-dir <main> --since <since> --out RUN_DIR/upstream.json`
     — merged PRs, CUDA-first features and new CUDA-only gates. For each of `upstream_repos`, keep a
     blobless clone at `/workspace/upstream/<name>` (`git clone --filter=blob:none <url>` when missing,
     else `git fetch origin`), check out `origin/HEAD` detached, and write `RUN_DIR/upstream_<name>.json`
     the same way.
   - `hardware`: `python3 <petra_dir>/scripts/audit_platform_gates.py <main>/python --out RUN_DIR/gates.json`
     — gates a new architecture (e.g. gfx1250) must be re-checked against.
   - `perf`: `python3 <petra_dir>/scripts/audit_host_syncs.py <attention backends and model runner under <main>> --out RUN_DIR/syncs.json`
     — leads only; a profile must confirm them.
   - always: `python3 <petra_dir>/scripts/check_framework_skills.py --framework-dir <main> --out RUN_DIR/skills.json`
     — framework skills that Petra's index names but the framework dropped, and new ones it does not
     name yet; the report lists them for the curator, they are not tasks.
4. Merge into `RUN_DIR/candidates.json`: one entry per candidate with `source`, `ref` (PR, issue,
   cluster, file:line), `title`, `evidence`. Mark entries already present in the previous queue
   as `seen`.
5. Remove the worktree: `git -C <framework_dir> worktree remove --force RUN_DIR/main`.

Return:

```json
{"lock": "acquired | busy | skipped", "run_dir": "/abs/RUN_DIR", "candidates_path": "/abs/RUN_DIR/candidates.json",
 "counts": {"ci": 0, "issues": 0, "upstream": 0, "hardware": 0, "perf": 0},
 "recent": {"at": "<UTC time of the recent report>", "url": "<its issue, or empty>", "run_dir": "<or empty>"}}
```
