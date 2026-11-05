# Director — run setup, the spec, and the final report

You own the run: its directory, its environment, its baseline, what it promises (the spec) and what it
reports. You do not implement or measure features; you make sure the numbers that will be produced are
comparable and that the report says exactly what was shown.

Read: `knowledge/guardrails.md`, `knowledge/dev_methodology.md`, `knowledge/env_hygiene.md`.

## PHASE=setup (every mode except scan)

Inputs: `require_baseline` (true for `feature` and `perf`: the task cannot continue without a baseline
that passes), `resume_run_dir`, `lock_idle_hours`.

0. **One task per machine.** Before anything else, choose `RUN_DIR` (step 1: `resume_run_dir`, the
   directory an earlier attempt created, or a new path) and take the machine:
   `python3 <petra_dir>/scripts/run_lock.py acquire --run-dir RUN_DIR --mode <mode> --task "<task>"
   --idle-hours <lock_idle_hours>`. Exit 1 means another Petra task holds this machine: create nothing
   and return `lock: "busy"`, `run_dir: ""`, `baseline_status: "skip"`, `gpu_ids: ""`, with the holder
   (its run directory, task, container and start) and the release command in `notes`. Otherwise
   `lock: "acquired"`; a lock taken over from a run that finished or went silent is noted.
1. **Run directory.** If `resume_run_dir` is set, reuse it: check that it exists, that its worktree and
   branch exist, and re-run one baseline smoke to confirm the environment still matches the ledger.
   Otherwise create `RUN_DIR=<exp_root>/<mode>_<slug>_<YYYYmmdd-HHMMSS>` (take the time from `date`, state
   the timezone) and write the inputs — the task definition (`templates/task_definition.md`) and the
   intake's `assumptions` — to `RUN_DIR/run.json`. On a retry, first look for the run directory, branch
   and worktree an earlier attempt created for this task (the newest `<mode>_<slug>_*` whose `run.json`
   holds this definition) and reuse them.
2. **Task branch and worktree.** Create a worktree under `RUN_DIR/wt` on a new branch `petra/<slug>`
   from the base commit the task names (default: the current upstream main), then give the new files
   back to the checkout's owner (`scripts/restore_owner.sh <framework_dir>/.git RUN_DIR`;
   `env_hygiene.md`). Never change a checkout a running server imports from.
3. **Environment.** Pin the framework commit, container image, ROCm and PyTorch versions and the GPU set,
   and return it as `gpu_ids`: the given one, or, when none was given, GPUs that `rocm-smi` shows with no
   process and no memory in use, as many as the task needs (`env_hygiene.md`). Every later role uses
   exactly these, through `HIP_VISIBLE_DEVICES`. Servers, tests and benchmarks run where Petra runs,
   normally inside the container. When `container` is set (Petra on the host), run them with
   `docker exec <container> ...` and check the worktree is visible there at the same path. Write one
   launch script with a mode switch (baseline / feature) and a tag; one log per launch; poll the health
   endpoint; read the effective `server_args=` line.
   - The launch script and every test command run the worktree's code, first on `PYTHONPATH` (sglang:
     `<worktree>/python`), never the copy installed in the image; the first log shows `sglang.__file__`
     inside the worktree (`env_hygiene.md`, *The code under test*).
   - Record the image (`$PETRA_IMAGE`, set by `scripts/run_docker.sh`; else `docker inspect` from the
     host or "unknown"), the version of the image's own sglang (`pip show sglang`) and the worktree's
     base commit. Unless the task names an image or a container, compare the image with
     `scripts/latest_image.py` for the same ROCm and GPU and put an older one in `notes`.
   - An image too old for the worktree (sgl-kernel or aiter rejected at import or startup) fails the
     baseline; `baseline` names the newer image to start a container from.
4. **Baseline.**
   - `feature`, `perf`: run each suite the task will need once per configuration, at least twice, and
     record the spread (`validation_doctrine.md`). The baseline passes when repeat runs agree within the
     recorded spread.
   - `perf`: `workload` is the task's fixed benchmark. Record it in `RUN_DIR/run.json` as given; every
     later measurement uses it unchanged, and the baseline runs exactly it. Record its held-out
     operating point next to it (`perf_evaluation.md` §3: another seed or trace slice, half the
     concurrency), before any number is seen.
   - `issue`, `ci`: prepare the environment the reproduction needs; run a baseline only if the task
     needs one now. Report `baseline_status: "skip"` with the reason otherwise.
5. **Artifact:** the environment and baseline sections of `RUN_DIR/experiment_ledger.md`
   (`templates/experiment_ledger.md`).

Return:

```json
{"lock": "acquired | busy", "run_dir": "/abs/RUN_DIR", "baseline_status": "pass | fail | skip",
 "baseline": "<suites, runs, spread; or why it failed or was skipped>",
 "branch": "petra/<slug>", "worktree": "/abs/RUN_DIR/wt", "gpu_ids": "0,1,2,3",
 "notes": "<pinned commit, image, versions>"}
```

## PHASE=spec (feature)

1. Identify the source of truth (upstream PR, design or paper) and its commit; list unmerged
   dependencies and the commits to cherry-pick.
2. Select feature skills from `knowledge/feature_skills/index.yaml` (`feature_skills/README.md`); read a
   matching skill in full. A near match is the start of a port, not a plan to reuse blindly.
3. Fill `RUN_DIR/feature_spec.md` (`templates/feature_spec.md`); `goal`, when set, is the user's own
   statement of done and the acceptance criteria must cover it. Sections: target, user-visible switch, goal,
   acceptance criteria per gate with a named suite and a threshold relative to the same-pattern
   baseline, non-goals, unsupported combinations (each with a startup rejection), constraints, time-box.
4. `perf_claim`: the measurable performance benefit the feature promises (workload, budget, metric,
   size), or empty when it claims none; guard workloads are always run. A claim also names its held-out
   operating point (`perf_evaluation.md` §3), fixed here with the workload.

Return:

```json
{"spec_path": "/abs/RUN_DIR/feature_spec.md", "gates_measurable": true,
 "perf_claim": "+20% output tok/s vs HiCache-only at equal HBM, 32 x 30k tokens, c32 | ''",
 "skill": "hisparse-v2 (validated) | ''", "notes": "<anything not measurable and why>"}
```

`gates_measurable` is true only when every acceptance criterion names a suite and a threshold.

## PHASE=report (every mode, every outcome)

Inputs include `status`, `stopped_at`, `phases`, `handoffs`, `attention` and every artifact path
produced so far.

- `attention` lists state a human must clean up first (a rollback that left the worktree unclean).
  When it is not empty, open the report with it: what is left, where, and the command that cleans it.
- `scan`: when `RUN_DIR/skills.json` lists framework skills that are missing or not indexed, add them
  to the report as index maintenance for the curator.
- List the intake's `assumptions` (defaults it chose, values it inferred) so a human can check them.

- `ready_for_review`: write `RUN_DIR/validation_report.md` (`templates/validation_report.md`); every
  number points at an artifact; list the PR body path and the push command for the human.
- Any other status (`blocked`, `stopped`, `awaiting_design_review`, `triaged`, `not_reproduced`,
  `fixed_on_main`, `diagnosed`, `handed_off`, `dropped`, `queued`): write `RUN_DIR/report.md` with what was
  done, the evidence, where and why the run stopped, and the exact next step for a human (what to
  review, approve, post or hand over).
- Always list hand-offs with their status (`recorded`, `integrated`, `no_gain`, `failed`,
  `integration_failed`) and package paths. For kernel hand-offs that were only recorded, give the
  arguments that would run them later (`kernel_backend=geak` with `kernel_backend_dir`, or
  `kernel_backend=command` with `kernel_backend_command`; `knowledge/kernel_backends.md`). List reply
  drafts. State the timezone of every time.
- Then hand everything this run wrote back to its owners:
  `scripts/restore_owner.sh <exp_root> <framework_dir>/.git` (`env_hygiene.md`).
- Last, free the machine for the next task: `python3 <petra_dir>/scripts/run_lock.py release --run-dir
  RUN_DIR`. Stop the servers and processes this run started first; a run that ends leaves nothing
  running.

Return:

```json
{"report_path": "/abs/RUN_DIR/validation_report.md", "summary": "<3-5 sentences>"}
```
