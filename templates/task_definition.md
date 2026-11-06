# Task definition — what Petra needs to start a task

The fields are `petra.js`'s arguments, so a definition can be passed as it is, produced by the Intake
phase from a request in plain words (`roles/intake.md`), or taken from a scan's task queue; every role
reads the same names. Operator settings (`petra_dir`, `exp_root`, budgets, `review_model`) are not part
of it.

## 1. Fields

| Field | Meaning | feature | issue | ci | perf | scan |
|---|---|---|---|---|---|---|
| `mode` | the kind of task | required | required | required | required | required |
| `task` | the source of truth: upstream PR or design URL, issue URL, CI job or tracker cluster, performance goal | required | required | required | required | — |
| `framework_dir` | the framework checkout each task works in, on its own branch from the current main (absolute path; for sglang the image's `/sgl-workspace/sglang` when not given, which the image installs sglang from) | required | required | required | required | the upstream scan reads it |
| `model_path` | the model the baseline and the gates run | required | recommended: the reporter's model | — | required | — |
| `workload` | the fixed benchmark, e.g. `{"isl": 8192, "osl": 1024, "conc": 64}` | when the task claims a gain | for a performance issue | — | required | — |
| `goal` | what done means, measurable when the mode measures | recommended | — | — | recommended | — |
| `framework` | default `sglang` | | | | | |
| `platform`, `gpu_ids`, `container` | target and environment; empty `gpu_ids` lets Setup pick free GPUs | | | | | |
| `apply_prs` | candidate PRs to apply and A/B | | | | optional | |
| `sources`, `since` | what to scan, from when | | | | | optional |
| `stop_after` | stop after this phase | optional | optional | optional | optional | optional |
| `resume_from`, `run_dir` | `implement`: continue after a human approved the design | optional | | | | |
| `kernel_backend` with `kernel_backend_dir` or `kernel_backend_command` | where kernel hand-offs go | optional | optional | optional | optional | |

`petra.js` checks the required fields (and a back end's own field) for every definition; one that
lacks something returns `needs_input` and starts nothing. The intake asks for the recommended fields
when the likely path of the task needs them.

## 2. Telling the modes apart

| The request is about | Mode |
|---|---|
| bringing an upstream PR, design or paper to AMD | `feature` |
| a user's report: an issue URL, a crash, wrong output or an error on AMD | `issue` |
| a red CI job, a Failure Tracker cluster, a test failing on AMD lanes | `ci` |
| making a model faster on a workload: throughput, latency, TTFT/TPOT, idle GPU time | `perf` |
| what to work on next | `scan` |

## 3. Examples

```json
{"mode": "feature", "task": "https://github.com/sgl-project/sglang/pull/<n>",
 "goal": "the feature passes G0–G5 on DeepSeek-V4.1 at TP4",
 "model_path": "/mnt/models/DeepSeek-V4.1-Flash", "gpu_ids": "0-3"}
```

```json
{"mode": "issue", "task": "https://github.com/sgl-project/sglang/issues/<n>",
 "model_path": "/mnt/models/<the reporter's model>", "stop_after": "Reproduce"}
```

```json
{"mode": "ci", "task": "Failure Tracker #<n>, cluster <signature>"}
```

```json
{"mode": "perf", "task": "DeepSeek-V4.1 decode throughput on MI355X",
 "goal": "+5% output tok/s at equal memory, guards unchanged",
 "model_path": "/mnt/models/DeepSeek-V4.1-Flash", "workload": {"isl": 8192, "osl": 1024, "conc": 64}}
```

```json
{"mode": "scan", "sources": ["upstream", "issues", "ci"]}
```

## 4. When something is missing

The run starts nothing and returns:

```json
{"status": "needs_input", "stopped_at": "Intake",
 "task_def": {"mode": "perf", "task": "DeepSeek-V4.1 decode throughput on MI355X"},
 "questions": [{"field": "workload", "question": "Which fixed workload should every measurement use?",
                "why": "performance numbers count only on a workload fixed before any profile is read",
                "options": [], "default": "{\"isl\": 8192, \"osl\": 1024, \"conc\": 64}"}],
 "next": "answer the questions, then run petra.js again with the same arguments plus answers={...}"}
```

Answer, then run again with the same arguments plus `answers` (`{"workload": {"isl": 8192, ...}}`), or
with the fields set directly. Fields set in the call win over answers, answers over what the intake
inferred. `rejected` carries a `reason` and what to do instead. A run that started records the
definition it used (`task_def`) and the intake's `assumptions` in its result and report.
