# sglang's own skills — which role reads which, from the task worktree

sglang keeps executable development procedures in its repository: `.agents/skills/<name>/SKILL.md`
(`.claude/skills` links there), diffusion ones under `python/sglang/multimodal_gen/.agents/skills/`, and
code-style rules under `.claude/rules/`. They are the framework's own conventions — how a test is
registered, where a kernel goes, how a trace is triaged — and they change with the code. Petra
therefore **references them in place and never copies them**: a role reads the file in the task
worktree (`<worktree>/.agents/skills/<name>/SKILL.md`), which matches the code it is changing.
Index checked against sglang main `e2982985` (2026-11-01): 29 skills, 5 diffusion skills, 11 rules.

Claude Code runs from the Petra checkout, so it does not load these skills by itself; read the files
this index names.

## Precedence

1. `../../guardrails.md` and Petra's gates come first. Skills that act on GitHub —
   `babysit-pr-to-pass-ci`, `rerun-test`, `sglang-cherrypick`, the review steps of `cookbook-review-pr` —
   are read for what they say about CI and checks; Petra never runs their steps that push, comment,
   label or trigger workflows.
2. Within those limits, the framework's skill decides how a thing is done in the framework (test
   registration, kernel layout, environment variables, code style); follow the version in the worktree.
3. Where a skill is CUDA-specific, apply `../../platforms/rocm_skills.md`.
4. A skill named here that is missing at the task's commit: skip it and say so in your answer.
   `scripts/check_framework_skills.py --framework-dir <dir>` lists that drift and the skills this index
   does not name yet.

## Index

| Role | Phase | Skills | When to read |
|---|---|---|---|
| analyst | recon | `sglang-runtime-context`, `kernel-organization` | the feature touches runtime configuration or process-global state; it needs a kernel API |
| architect | design, perf_plan | `sglang-runtime-context`, `kernel-organization`, `compute-mamba-ratio` | as for the analyst; hybrid-attention models whose memory split the design changes |
| implementer | implement | `.claude/rules/*` | every package: the repository's code-style rules |
| implementer | implement | `write-sglang-test`, `env-var-conventions`, `kernel-organization`, `add-jit-kernel`, `add-sgl-kernel` | the package adds a test, an environment variable or a kernel (JIT or AOT) |
| implementer | implement | `large-class-style`, `speculative-naming`, `mechanical-refactor-verify`, `processor-model-parity`, `scripted-runtime-notes` | it touches `Scheduler`, `TokenizerManager` or `ModelRunner`; speculative-decoding names; a mechanical refactor; chat-template rendering or tokenization; the scripted runtime |
| test_engineer | unit | `write-sglang-test`, `kl-consistency-test` | how a test is structured, which tier and suite it belongs to; prefill-vs-decode logprob consistency |
| verify_engineer | verify | `kl-consistency-test`, `sglang-multi-graph-check` | consistency gates; graph capture and replay correctness for the configurations under test |
| investigator | investigate, diagnose | `debug-cuda-crash`, `debug-distributed-hang`, `sglang-multi-graph-check`, `sglang-runtime-context`, `clean-startup-log` | a crash; a hang across ranks; wrong results only under graph replay; configuration state; anomalies in the startup log |
| issue_triager | reproduce | `sglang-prod-incident-triage` | save the failing request and replay it on a clean server before any deeper tool |
| ci_guardian | classify, bisect | `sglang-bisect-ci-regression`, `ci-workflow-guide`, `write-sglang-test` | the bisect method (signature, window, bisect, confirmation); CI tiers, stages and suites |
| perf_engineer | profile, perf_eval | `generate-profile`, `llm-torch-profiler-analysis`, `compute-mamba-ratio` | capturing the trace; the kernel, overlap and fuse-pattern tables; memory settings of hybrid models |
| reviewer | review | `.claude/rules/*`, `write-sglang-test`, `env-var-conventions`, `kernel-organization`, `large-class-style`, `speculative-naming`, `ci-test-audit` | the conventions the diff must follow |
| pr_engineer | pr | `.claude/rules/*`, `ci-workflow-guide`, `cookbook-review-pr` | lint and the CI a PR goes through; cookbook pages a model PR updates |
| dispatcher | dispatch | `cookbook-add-model` | a new-model task includes its cookbook page |

Diffusion skills (`sglang-diffusion-add-model`, `sglang-diffusion-benchmark-profile`,
`sglang-diffusion-performance`, `sglang-diffusion-cache-dit`, `sglang-diffusion-modelopt-quant`) apply
to diffusion tasks, which no Petra mode targets yet. Not used by Petra: `cookbook-migrate-model`
(rewriting legacy cookbook pages).
