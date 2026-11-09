# Petra design

Petra is the framework agent for AMD GPUs in open-source LLM inference frameworks, starting with
sglang. This document records why it exists and how its parts map onto the design agreed in the
internal "Framework Agent on GEAK" page. The operational contract lives in `knowledge/` and
`petra.js`; this file explains the shape.

## 1. Demand: building the AMD ecosystem in the community

AMD's public roadmap for sglang (2026 Q4: sgl-project/sglang#46462) commits to:

- Day-0 support and a fast performance ramp for frontier models (DeepSeek-V4.1, Kimi-K3/3+, GLM-5.3,
  MiniMax-M3.1, Qwen3.8 Flash, Muse Spark Open);
- full compatibility of PD disaggregation, the parallelisms, speculative decoding, KV-cache tiers and
  load balancing on MI30x, MI35x and MI45x;
- new platforms (MI45x, Helios, MI350P, Ryzen AI);
- upstream CI coverage, pass rate and time to fix;
- up-to-date documentation and recipes.

Where that stands, from sglang's history and issues (October 2026):

| Gap | Evidence |
|---|---|
| features arrive on CUDA first | new models reach AMD in a median of ~8 days; framework-level features ~84 days (~67 of them before AMD opens a PR); features that need a new kernel ~136 days, a new communication library ~304 days. Single features work; combinations (PD + wide EP + FP4) are where AMD falls behind (InferenceX v2) |
| user reports go unanswered | 32 open AMD issues; 20 of the 21 P0/P1 ones had no reply from anyone but the reporter; issues untouched for 60 days are closed automatically |
| maintenance eats the people | upstream refactors break AMD paths (piecewise CUDA graphs and prefill context parallelism had to be re-supported several times); CI regressions are fixed fast only when one person happens to watch |

## 2. Why an agent

- **The work multiplies.** Architectures × models × PD × parallelisms × speculative decoding × cache
  tiers × overlap modes; people add linearly. Upstream itself is getting faster (sglang commits per
  quarter: 1035 in 2025Q1, 4504 in 2026Q3) and is moving to agent-native development (#42473).
- **The time goes to discovery, judgement and verification**, not to typing code: finding a gap among
  upstream PRs, issues, CI and customer requests; deciding whether a feature is blocked by hardware
  (TMA, NVLink) or by a library (kernels, communication); proving a port correct against 150+ CI tests
  and controlled experiments.
- **Porting is knowledge-driven.** CUDA–ROCm differences, library correspondences and enablement moves
  repeat; written down as skills, each port makes the next one faster.
- **Existing tools do not cover it.** Hyperloom's framework agent keeps an upstream PR only when it
  raises the throughput of the current workload, so correctness-first features (deterministic
  inference), capacity features (HiCache) and ports that need redesign (HiSparse V2 from DSA to
  DeepSeek-V4.1's compressed KV) stay out of scope. The two complement each other: Hyperloom's
  candidates are Petra inputs, Petra's features become Hyperloom options.

| | GEAK kernel_workflow | GEAK e2e_workflow | Hyperloom framework agent | Petra |
|---|---|---|---|---|
| goal | one faster kernel | a faster serving stack | higher throughput for a workload (with a PR to start from) | the AMD ecosystem: periodic scanning, bug fixes, fast full-compatibility feature support, NV-level performance without a PR to start from |
| input | kernel + reference | model + serving config | model + workload | upstream features, user issues, CI failures, with target model and platform |
| judged by | correctness + speedup | e2e throughput | throughput gate, accuracy drop ≤ 0.05 | correctness gates first (accuracy, long context, stress, same-pattern baseline), then performance, then community submission standards |
| output | kernel | tuned config + kernels | best config + local patches | upstream-quality PRs, validation reports, reusable feature skills |

## 3. Task sources

| Source | What |
|---|---|
| CI failures | AMD Failure Tracker and nightly failures |
| upstream code updates | newly merged PRs in sglang (later vLLM, ATOM) and newly added CUDA-only gates |
| user issues | issues whose title or labels mention AMD/ROCm; customer requests imported by hand |
| new hardware | platform gates to re-audit on a new gfx architecture (e.g. gfx1250) |
| performance | system-level end-to-end analysis and optimization |

`mode=scan` collects all of them (`scripts/scan_*.py`, `scripts/audit_*.py`) and ranks the queue.

## 4. Modules → Petra

| Design module | Petra |
|---|---|
| task intake: a request in plain words becomes a task definition every phase can start from; missing information comes back as questions | `intake` (define), `templates/task_definition.md`; `petra.js` checks every definition against what its mode needs |
| upstream code scan, ecosystem matrix (feature × model × platform: available / unavailable) | `scout` (collect), `scripts/scan_upstream.py`, `knowledge/composability.md` §3 |
| dispatch: gap type, CUDA dependencies and AMD counterparts, effort, priority by customer workload | `dispatcher`, `knowledge/dispatch.md` |
| analysis: upstream design, do its assumptions hold on ROCm | `analyst` (recon: code map + assumption table) |
| implementation (framework / kernel / communication), isolated, feature off = untouched; kernels to the kernel workflow | `architect` + `implementer` (worktree per task), `test_engineer`; kernel hand-offs through `kernel_liaison` to the selected back end (`kernel_backend`: none, geak, command; `knowledge/kernel_backends.md`) |
| issue handling: reproduce, locate, minimal fix PR | `issue_triager`, `investigator` (diagnose), `knowledge/issue_triage.md` |
| CI failures: flaky / infrastructure / regression, culprit, fix PR | `ci_guardian`, `knowledge/ci_triage.md` |
| performance optimization: bubbles, H2D/D2H copies, overlap; kernels to the kernel agent | `perf_engineer` (profile), `architect` (perf_plan), `knowledge/system_perf.md`, `scripts/audit_host_syncs.py`; kernel-level opportunities as kernel hand-offs |
| accuracy validation: accuracy, long context, stress, concurrency, same-pattern baseline first | `verify_engineer`, `investigator`, `knowledge/validation_doctrine.md`, `debugging_playbook.md` |
| performance and composability: A/B, combination tests (parallelism × speculative decoding × quantization × operator) | `perf_engineer` (perf_eval), `knowledge/perf_evaluation.md`, `composability.md` |
| review before the PR: agents produce plausible changes, so the diff and its evidence get an independent read | `reviewer` (review; optionally on another model, `review_model`); requested changes go back through Implement and Verify |
| PR and upstream CI: formatting, minimal diff, HIP-only or switch-gated, data in the description, CI fixes and rebases; owner answers review, maintainers merge | `pr_engineer`, `knowledge/pr_playbook.md`, `guardrails.md` |
| the framework's own procedures (tests, kernels, profiling, crash debugging) | referenced in place from the task worktree through `knowledge/frameworks/sglang/skills.md`; ROCm differences in `knowledge/platforms/rocm_skills.md`; drift checked by `scripts/check_framework_skills.py` |
| knowledge: feature skills, known issues, CUDA → AMD table, pitfalls | `curator`, `knowledge/` |
| safety: measured data wins, budgets, automatic rollback | `petra.js` (budgets, independent gates, rollback), `knowledge/guardrails.md` |

## 5. Orchestration

`petra.js` follows GEAK's rule: control flow is deterministic code; agents are called only for
judgement and for the work, and return structured JSON whose gate fields the script reads.

```
(Intake: request or incomplete definition → task definition, or questions / rejected — nothing starts)
feature  Setup → Spec → Recon → Design ─┐
issue    Setup → Triage → Reproduce → Diagnose ─┤
ci       Setup → Classify → Bisect ─────────────┼→ Implement (per WP: implementer → test_engineer, rollback on failure)
perf     Setup → Profile → Plan ────────────────┘   → Kernel (hand-offs → kernel back end, gains integrated as WPs)
                                                     → Verify (↔ Investigate) → Performance → Review → PR → Report
scan     Collect → Dispatch → Report
```

The task definition (`templates/task_definition.md`) is `petra.js`'s own arguments, so a definition
from the intake, from a scan's queue or written by hand starts the same way. Fields given in the call
win over the user's answers, answers over what the intake inferred; a deterministic check of what each
mode needs runs on every definition, so an intake that calls a definition ready cannot start a run
that lacks its model or its workload.

Kernel back ends (`kernel_backend`): `none` records hand-offs (default), `geak` nests GEAK's single-
language kernel lane once from the checkout `kernel_backend_dir` (as GEAK's e2e_workflow does),
`command` runs any other CLI. A gain is integrated by the implementer and judged by Petra's own gates;
a failing back end never blocks a task. An integrated kernel that fails Verify is reverted to the
functional kernel and handed back once with the failing case as a test (`kernel_backends.md`). The
`geak` back end is the only place a run uses GEAK;
outside Claude Code, GEAK's workflow runtime is what executes `petra.js` (other CLIs, the dry run).

Petra runs inside the framework's ROCm container as root, as GEAK does, next to the GPUs and the
framework's Python environment. Each task gets its own container, and what it works on lives in that
container, apart from every other container's: Petra's checkout and the run directories in `/workspace`,
and the image's own sglang checkout. `scripts/run_docker.sh` takes the user back into an existing container and never
removes one. Claude Code, installed once on the host, is linked into the container; its state and the
keys stay in the user's home on the host (`PETRA_HOST_HOME`), shared by their containers. What a run
writes as root into a checkout on a host mount goes back to its owner (`scripts/restore_owner.sh`).
Machines are shared: one Petra task runs per machine at a
time (a lock in `/dev/shm`, `scripts/run_lock.py`; a second run ends as `busy`), a run uses only the
GPUs Setup pinned (through `HIP_VISIBLE_DEVICES`) and touches only the processes and containers it
started; the host's Docker socket is not mounted by default. Tasks test the newest sglang: unless the user names an
image or a container, the container runs the newest daily `rocm/sgl-dev` image for its ROCm and GPU
(`scripts/latest_image.py`). The image installs sglang in editable mode from its own full-history
checkout, `/sgl-workspace/sglang`, so what runs is what is checked out there: setup puts it on main
once per container (discarding only the image build's packaging changes), and each task works in it
on its own branch from the current main, which Setup fetches first; a dirty checkout stops Setup. A
baseline at the base commit, and a scan of the current main, read worktrees of the same repository
under the run directory. Run directories live in the container's `<petra_dir>/exp`, with an `index.md`
that lists every run; the PR engineer writes the task's commits there as patches, so the change can
leave the container. A run in another container is never taken over for silence, since its run
directory is not visible: `run_lock.py release --force` frees a lock whose run is gone.

- Gates G0–G5 (`validation_doctrine.md`), plus mode gates (`issue_repro`, `failing_test`) and the
  composability gates of every dimension a task touches.
- Performance evidence counts only on the workload fixed before any profile is read and on the
  serving path the task targets, and a gain only if it also holds at a held-out operating point fixed
  with the workload (`perf_evaluation.md` §3); `mode=perf` requires the workload.
- An independent review closes every code change before the PR; its requested changes are work
  packages, bounded by `max_review_rounds`.
- Reward hacks — changes that move a number while breaking what it meant — are hunted from a catalog
  (`reward_hacks.md`, each entry with how to spot it and the check that kills it): the reviewer and the
  performance engineer start from it, a confirmed hack comes back as a work package whose test kills
  it, the curator adds new ones, and every unit test must fail without its change (parent commit or a
  broken copy). Adapted from SkyDiscover-Synthesize's auditor and mutation-checked tests.
- A failed verification goes to the investigator: a fix becomes new work packages; a failure the
  same-pattern baseline shares becomes a known issue and the gate is re-judged on the rest.
- Budgets: fix rounds per work package, investigation and review rounds, work packages per task, agent
  retries. A retry is told to check what the failed attempt left; a call that timed out is not
  retried, because the agent cannot be cancelled and may still be running.
- The PR phase changes no code: hygiene and lint happen in Implement, gaps found at PR come back as work
  packages through Implement, Verify and Review, and main is only trial-merged to report conflicts, so
  the pushed branch is the one that was verified.
- Human checkpoints: the intake's questions (`needs_input`); `stop_after` any phase; L3 tasks and designs the architect flags stop at Design
  (`awaiting_design_review`) and continue with `resume_from: "implement"`; the PR is prepared, never
  pushed; issue replies are drafts; a scan's daily report is a file a human shares, checked to name
  nothing about the machine (`scripts/daily_report.py`), and a shared copy is where the next scan, in
  any container, continues from. The one post is the curator's knowledge changes, as a pull request to
  main of Petra's own repository with a token for it alone (`scripts/propose_knowledge.py`), so
  knowledge a run proved reaches later runs only once a human merged it.

## 6. Priorities and difficulty

Ranking: CI code regressions (they block every AMD PR) → P0 issues → roadmap items ordered by customer
workloads → P1 issues and performance opportunities → the rest. Issue priorities:

| | |
|---|---|
| P0 | a roadmap model or feature crashes or loses accuracy under the default or cookbook configuration, directly blocking a roadmap deliverable, with no usable fix PR |
| P1 | a roadmap model or feature fails under a specific configuration; a CI failure blocking a roadmap feature's tests; a performance problem |
| P2 | not AMD-side (main shows a similar failure, root cause outside AMD code); models or platforms outside the roadmap |

Difficulty: **L1** — a similar implementation exists in the same framework (an AMD sibling model or
the NV path); **L2** — on another platform or framework (ATOM's two-batch overlap → sglang); **L3** —
only a paper or a document. L1 is routine; L2 needs an expert's design review; L3 starts from a
human-approved design.

## 7. Composability

Matrix: parallelism (TP, EP with MoRI-EP, DP attention, PP, PCP, DCP, PD) × speculative decoding (MTP
via EAGLE, DSpark, DFlash) × cache (HiCache, HiSparse, MoRI UMBP, Mooncake) × precision (FP8/MXFP4
weights and KV cache) × platform (MI30x, MI35x, MI45x) × model (DeepSeek-V4/4.1, Qwen3.X, GLM-5.X,
Kimi-K3.X, MiniMax-M3.X, GPT-OSS). Nightly minimum: DP + EP + MTP.

## 8. Community conduct and safety

The agent proposes PRs; the owner answers review; maintainers merge. High-risk changes (community
merges, customer production services) always get a human review; the agent cannot carry that
responsibility. PRs are judged by quality, not count. Petra adopts Hyperloom's lessons in its own form:
only the implementer edits source, in its own worktree; numbers come only from independent
measurement; foreign patches pass `git apply --check`; a change without a measured win is rolled back.
See `knowledge/guardrails.md`.

## 9. Roadmap

| Horizon | Capabilities |
|---|---|
| short (~1 month) | shared scripts, roles and workflow orchestration validated on real features (candidate: HiSparse V2-class roadmap items), with agent vs human development time compared; applying existing PRs to raise system performance |
| mid (~3 months) | feature scanning: a feasibility verdict within one working day of a CUDA-first upstream feature, a gate-passing draft PR within a week for framework/kernel-level gaps; fixing poorly defined problems (unexplained core dumps or accuracy loss) in 2–3 weeks; CI-failure and user-issue entry points |
| long (~6 months) | Day-0 support with CUDA graphs, MTP/DSpark, EP/CP/DP and PD available together; nightly tests of the main combinations; pure performance work without a new feature; vLLM and ATOM; a closed loop with GEAK e2e_workflow and Hyperloom; a knowledge base that makes every port at least as fast as the last |

Metric definitions (targets are kept in the internal design page): start delay (NV merge → AMD PR,
framework-level, median); issue report → fix PR by someone else (median) and the share never answered;
CI failure → fix PR (code regressions vs the rest); roadmap items with a Petra PR; PR quality (first-run
CI pass rate, review rounds).

## 10. Status

Implemented: the orchestration with five modes and pluggable kernel back ends (none, geak, command), an
intake from plain-words requests, 17 roles, the migrated knowledge base and templates, the framework's own skills referenced in place with
ROCm notes,
the task-collection and audit scripts, a dry run of every control path on GEAK's runtime, offline unit
tests. Not yet: shared server control and A/B runners (the director writes a launch script per run), a
persistent ecosystem-matrix store, queue → run automation, resume for modes other than `feature`,
framework maps for vLLM and ATOM, and validation of the workflow itself on a real port against the
hand-driven HiSparse V2 run.
