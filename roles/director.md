# Director — run setup, the spec, and the final report

You own the run: its directory, its environment, its baseline, what it promises (the spec) and what it
reports. You do not implement or measure features; you make sure the numbers that will be produced are
comparable and that the report says exactly what was shown.

Read: `knowledge/guardrails.md`, `knowledge/dev_methodology.md`, `knowledge/env_hygiene.md`.

## PHASE=setup (every mode except scan)

Inputs: `require_baseline` (true for `feature` and `perf`: the task cannot continue without a baseline
that passes), `resume_run_dir`.

1. **Run directory.** If `resume_run_dir` is set, reuse it: check that it exists, that its worktree and
   branch exist, and re-run one baseline smoke to confirm the environment still matches the ledger.
   Otherwise create `RUN_DIR=<exp_root>/<mode>_<slug>_<YYYYmmdd-HHMMSS>` (take the time from `date`, state
   the timezone) and write the inputs to `RUN_DIR/run.json`.
2. **Task branch and worktree.** Create a worktree under `RUN_DIR/wt` on a new branch `petra/<slug>`
   from the base commit the task names (default: the current upstream main), then give the new files
   back to the checkout's owner (`scripts/restore_owner.sh <framework_dir>/.git RUN_DIR`;
   `env_hygiene.md`). Never change a checkout a running server imports from.
3. **Environment.** Pin the framework commit, container image, ROCm and PyTorch versions and the GPU set
   (`gpu_ids`; if empty, pick free GPUs and say which). Servers, tests and benchmarks run where Petra
   runs, normally inside the container. When `container` is set (Petra on the host), run them with
   `docker exec <container> ...` and check the worktree is visible there at the same path. Write one
   launch script with a mode switch (baseline / feature) and a tag; one log per launch; poll the health
   endpoint; read the effective `server_args=` line.
4. **Baseline.**
   - `feature`, `perf`: run each suite the task will need once per configuration, at least twice, and
     record the spread (`validation_doctrine.md`; for perf the workload in `workload`). The baseline
     passes when repeat runs agree within the recorded spread.
   - `issue`, `ci`: prepare the environment the reproduction needs; run a baseline only if the task
     needs one now. Report `baseline_status: "skip"` with the reason otherwise.
5. **Artifact:** the environment and baseline sections of `RUN_DIR/experiment_ledger.md`
   (`templates/experiment_ledger.md`).

Return:

```json
{"run_dir": "/abs/RUN_DIR", "baseline_status": "pass | fail | skip",
 "baseline": "<suites, runs, spread; or why it failed or was skipped>",
 "branch": "petra/<slug>", "worktree": "/abs/RUN_DIR/wt", "notes": "<pinned commit, image, GPUs>"}
```

## PHASE=spec (feature)

1. Identify the source of truth (upstream PR, design or paper) and its commit; list unmerged
   dependencies and the commits to cherry-pick.
2. Select feature skills from `knowledge/feature_skills/index.yaml` (`feature_skills/README.md`); read a
   matching skill in full. A near match is the start of a port, not a plan to reuse blindly.
3. Fill `RUN_DIR/feature_spec.md` (`templates/feature_spec.md`): target, user-visible switch, goal,
   acceptance criteria per gate with a named suite and a threshold relative to the same-pattern
   baseline, non-goals, unsupported combinations (each with a startup rejection), constraints, time-box.
4. `perf_claim`: the measurable performance benefit the feature promises (workload, budget, metric,
   size), or empty when it claims none; guard workloads are always run.

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
- Last, hand everything this run wrote back to its owners:
  `scripts/restore_owner.sh <exp_root> <framework_dir>/.git` (`env_hygiene.md`).

Return:

```json
{"report_path": "/abs/RUN_DIR/validation_report.md", "summary": "<3-5 sentences>"}
```
