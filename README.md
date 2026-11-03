# Petra

Petra is the framework agent for AMD GPUs in open-source LLM inference frameworks, starting with
sglang. It turns one task — an upstream feature to bring to AMD, an AMD user's issue, a red AMD CI
job, a system-level performance gap — into a pull request a maintainer can review: **correct first**
(independent unit gates, accuracy / long-context / stress gates against a same-pattern baseline, a
controlled investigation loop), **then fast** (equal-budget A/B), within the community rules in
[`knowledge/guardrails.md`](knowledge/guardrails.md). Petra proposes; people review, push and merge.

Why it exists and how it maps onto the agreed design: [`docs/design.md`](docs/design.md).

## Modes

| Mode | Task | Phases | Ends with |
|---|---|---|---|
| `feature` | an upstream PR or design to bring to AMD | Setup → Spec → Recon → Design → Implement → Kernel → Verify → Performance → PR → Report | branch + PR body + validation report |
| `issue` | an AMD user issue | Setup → Triage → Reproduce → Diagnose → Implement → Verify → PR → Report | fix PR, or a triage conclusion; always a reply draft |
| `ci` | a red AMD CI job or Failure Tracker cluster | Setup → Classify → Bisect → Implement → Verify → PR → Report | fix PR, or a handover for flaky/infrastructure failures |
| `perf` | a system-level performance goal for a model and workload | Setup → Profile → Plan → Implement → Kernel → Verify → Performance → PR → Report | PR with a measured win, or the change dropped; kernel-level items go to the kernel back end |
| `scan` | none — collect tasks from every source | Collect → Dispatch → Report | a ranked task queue with the arguments to start each task |

Every implementation runs one work package at a time; an independent test engineer re-runs its unit
test and the feature-off check, and a package that keeps failing is rolled back. Verification failures
go to an investigator that runs the controls before any instrumentation and returns either a fix or a
proof that the failure is pre-existing on the baseline.

Kernel-level work — tuning a kernel Petra wrote for a feature, or a kernel-level performance
opportunity — is handed to a **kernel workflow back end** in the Kernel phase between Implement and
Verify ([`knowledge/kernel_backends.md`](knowledge/kernel_backends.md)):

| `kernel_backend` | What happens to a hand-off |
|---|---|
| `none` (default) | recorded in the report with its package; nothing runs |
| `geak` | GEAK's `kernel_workflow/kernel_lane.js` runs it (nested once, as GEAK's e2e_workflow does) |
| `command` | any other CLI given as `kernel_backend_command` |

A gain comes back as a work package: the implementer integrates it and Petra's own gates judge it. A
back end that fails or finds nothing never blocks the task.

## Running it

Petra is a GEAK-style workflow: `petra.js` holds the control flow, `roles/` the agent instructions,
`knowledge/` the method, `templates/` the artifacts. A GEAK checkout (`$GEAK_HOME`) provides the runtime
outside Claude Code and the server adapters (`e2e_workflow/scripts/adapters/`), and the kernel lane when
`kernel_backend=geak`.

**Claude Code** (Workflow tool, ≥ 2.1.177), with permissions auto-approved as GEAK requires:

```
use /home/fangyuan/Petra/petra.js with mode=issue, task=https://github.com/sgl-project/sglang/issues/38849,
petra_dir=/home/fangyuan/Petra, framework_dir=/path/to/sglang, gpu_ids=0-7, container=<container>
```

**Other CLIs** through GEAK's runtime (Node 20+):

```bash
node $GEAK_HOME/interface/runtime/engine/run_workflow.mjs petra.js --agent codex \
  --args '{"mode":"scan","petra_dir":"'"$PWD"'","framework_dir":"/path/to/sglang"}'
```

| Argument | Meaning |
|---|---|
| `mode` | `feature` \| `issue` \| `ci` \| `perf` \| `scan` (required; no natural-language detection) |
| `petra_dir` | absolute path of this checkout (required) |
| `task` | the upstream PR/design, issue URL, CI job/cluster or performance goal (required except `scan`) |
| `framework_dir` | the framework checkout; Petra works in a worktree of it (required except `scan`) |
| `framework`, `model_path`, `platform`, `gpu_ids`, `container`, `workload` | target and environment |
| `exp_root` | where run directories go (default `<petra_dir>/exp`) |
| `geak_home` | GEAK checkout (adapters; the kernel lane for `kernel_backend=geak`) |
| `kernel_backend` | `none` (default) \| `geak` \| `command`: where kernel hand-offs go |
| `kernel_backend_command` | `command` back end: shell command with `{task_dir}`, `{out_dir}`, `{gpu_ids}` |
| `kernel_budget` | optimization rounds for the kernel back end (default 6) |
| `apply_prs` | `perf`: candidate PRs to apply and A/B |
| `sources`, `since` | `scan`: any of `upstream`, `issues`, `ci`, `hardware`, `perf`; the start of the window |
| `stop_after` | stop after the named phase (e.g. `Design`) |
| `resume_from`, `run_dir` | `feature`: `implement` continues a run that stopped at Design once a human approved `design.md` |
| `max_fix_rounds`, `max_investigate_rounds`, `max_work_packages`, `agent_retries`, `agent_timeout_ms` | budgets |

Human checkpoints: any `stop_after`; L3 tasks and designs the architect flags stop at Design
(`awaiting_design_review`); the PR engineer returns the exact `git push` instead of pushing; issue
replies are drafts in the run directory. Every run ends with a report, whatever its status.

## Scripts

Standard-library Python; the GitHub ones read `GITHUB_TOKEN` or `GH_TOKEN` (without a token the
search API allows 10 requests a minute).

| Script | Source of tasks |
|---|---|
| `scripts/scan_issues.py` | open AMD issues with linked PRs, replies and the projected 60-day auto-close date |
| `scripts/scan_ci.py` | Failure Tracker state → failure clusters with statuses and since dates |
| `scripts/scan_upstream.py` | merged upstream commits: new CUDA gates, CUDA-first features, new models |
| `scripts/audit_platform_gates.py` | platform gates to re-check on a new architecture (capability checks true on gfx1250, wave32 assumptions) |
| `scripts/audit_host_syncs.py` | host-device sync and copy candidates on the hot path (leads for a profile) |

## Tests

```bash
GEAK_HOME=/path/to/GEAK node tests/dry_run.mjs   # every control path of petra.js, scripted agents, no GPU
python3 -m unittest discover -s tests             # the scripts' parsers and rules, offline
```

## Layout

```
Petra/
├── petra.js                 # orchestration: five modes, gates, budgets, rollback, kernel back ends
├── roles/                   # director, scout, dispatcher, analyst, architect, implementer, test_engineer,
│                            # verify_engineer, investigator, perf_engineer, issue_triager, ci_guardian,
│                            # kernel_liaison, pr_engineer, curator
├── knowledge/
│   ├── dev_methodology.md   # phases, artifacts, gates (the contract)
│   ├── validation_doctrine.md, debugging_playbook.md, perf_evaluation.md, env_hygiene.md, pr_playbook.md
│   ├── guardrails.md        # safety constraints and community conduct
│   ├── dispatch.md, issue_triage.md, ci_triage.md, system_perf.md, composability.md, kernel_backends.md
│   ├── frameworks/sglang/feature_dev_map.md, platforms/rocm.md, known_issues.md
│   └── feature_skills/      # validated plans per feature (hisparse-v2 first)
├── templates/               # feature_spec, design, experiment_ledger, validation_report, pr_body,
│                            # issue_triage, ci_triage, perf_analysis, task_queue
├── scripts/                 # task collection and audits
├── tests/                   # dry run of petra.js, unit tests of the scripts
└── docs/design.md
```

## Relationship to GEAK and Hyperloom

- A kernel's speed is the kernel workflow's job, on whichever back end is selected (GEAK's kernel lane
  is one): Petra writes a functional kernel with a unit test, hands over the op spec with the reference
  as the oracle, and integrates a verified gain.
- Flag and backend searches for a workload belong to Hyperloom and GEAK `e2e_workflow`; their upstream
  candidates are Petra inputs, and features Petra lands become their options.

## Origin

The method, validation doctrine, known-issue register, templates and the HiSparse V2 feature skill come
from GEAK's `framework_workflow` (branch `fangyuan/framework_agent_init`, commit `fc857c9`), which was at
its knowledge-first phase. Petra adds the orchestration that was planned there, the roles, the issue /
CI / performance / scan entry points from the design, and the task-collection scripts.
