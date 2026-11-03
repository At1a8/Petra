# Issue triage — from an AMD user report to a reply, a reproduction and a fix

Read this in `mode=issue` and whenever a user report is the task source. The goal is that every AMD
user report gets an answer: a reproduction conclusion, a fix PR, or a clear reason why it is not
Petra's to fix. On sglang in late October 2026, 20 of the 21 open P0/P1 AMD issues had no reply from
anyone but the reporter, and issues untouched for 60 days are closed automatically (see *Auto-close*).

## 1. Intake

- **In scope:** open issues whose title or labels mention AMD, ROCm, MI3xx, aiter, gfx9xx, HIP or MoRI,
  plus customer requests imported by hand. `scripts/scan_issues.py` collects them with the linked PRs,
  the reply status and the projected auto-close date.
- **Not user issues** (list them, do not triage them): roadmaps, `[Failure Tracker]` issues (those are
  `ci_triage.md` input), internal tracking issues (AITER upgrade readiness, PR review trackers, CI plans).
- **Not AMD** although the title mentions HIP or ROCm: e.g. an NVIDIA crash whose title says that a
  workaround path is HIP-only. These are P2.

## 2. Priority

The roadmap is the AMD roadmap issue of the quarter (sglang #46462 for 2026 Q4): its frontier models
(DeepSeek-V4.1, Kimi-K3/3+, GLM-5.3, MiniMax-M3.1, Qwen3.8 Flash, Muse Spark Open), its model families
for distributed inference and speculative decoding (DeepSeek-V4/4.1, Qwen3.X, GLM-5.X, Kimi-K3.X,
MiniMax-M3.X, GPT-OSS), its features (PD disaggregation, parallelisms, speculative decoding, KV-cache
tiers, load balancing, attention and low-precision KV cache, quantization, diffusion) and its platforms
(MI30x, MI35x, MI45x, Ryzen AI Halo).

| Priority | Definition |
|---|---|
| **P0** | A roadmap model or feature crashes or loses accuracy under the **default or cookbook** configuration, directly blocking a roadmap deliverable, and no usable fix PR exists |
| **P1** | A roadmap model or feature crashes or loses accuracy under a **specific** configuration; a CI failure that blocks testing of a roadmap feature; a performance problem |
| **P2** | Not on the AMD side: main shows a similar failure and the root cause is outside AMD code; or a model or platform outside the roadmap |

Judgement calls, decided once so they are applied the same way every time:

- A roadmap deliverable that is itself an opt-in feature (e.g. DCP for GLM-5.x) counts as default when
  it fails in the feature's standard usage (e.g. `--tp-size 8 --dcp-size 8`).
- A cookbook recipe the reporter changed (e.g. multi-GPU recipe run at TP1) stays P0 until the
  original recipe is shown not to fail; if only the changed setting fails, it becomes P1.
- A default-configuration failure that already has an open fix PR is P1: the work left is to verify
  and push that PR.
- "Accuracy failure" means a measured loss (e.g. a GSM8K or needle-in-a-haystack drop). A report of a
  precision difference without a measured loss is P1 until someone measures it.
- "AMD side" means AMD-specific code paths in the framework and AMD-maintained stacks (aiter, MoRI,
  ROCm, the ROCm build of PyTorch). Generic framework code and third-party libraries (flashinfer,
  Mooncake, UCX) are not, unless the failure only occurs on AMD.
- Already fixed but still open, feature requests and developer-tool problems are listed with P2 and
  an action of *close*, *plan* or *hand over*.

## 3. State checks before any work

| Check | Why | How |
|---|---|---|
| Linked PRs and their state | a fix PR is not a fix: of 44 AMD bugs with a fix PR from someone else in 2026, 21 were merged by November; PRs also get closed unmerged | PRs whose title or body cites `#<n>` or the issue URL; `scan_issues.py` |
| Replies from anyone but the reporter | an unanswered report is the first thing to fix | issue comments, excluding the reporter and bots |
| Projected auto-close date | the report disappears without a fix | see *Auto-close* |
| Partial fixes | a merged PR may fix one of two problems (e.g. the correction-bias half of a routing precision report while the router GEMM still returns bf16) | read the merged diff against every point of the report |
| Tests skipped instead of fixed | a CI skip hides the problem (e.g. a nightly accuracy test skipped for an FP8 checkpoint that still loses ~10 points) | look for `skip` commits that cite the issue |

## 4. Actions

| Action | When | Output |
|---|---|---|
| `reproduce` | no usable fix exists | reproduction on the reporter's configuration, then diagnosis and a fix PR |
| `push_existing_pr` | an open fix PR exists | verify it on AMD hardware, rebase, add the missing test, report results on the PR |
| `close_fixed` | the fix is merged and covers every point | verification on main and a closing comment draft |
| `needs_info` | the report cannot be reproduced as written | a reply asking for the exact command, image and commit |
| `not_amd` | the root cause is outside AMD code | a reply saying so, with the evidence |
| `plan` | feature request | a dispatch entry (`dispatch.md`) and a reply with the plan or the reason |

Every action ends with a **reply draft** for the issue (`templates/issue_triage.md`). Posting it is a
human decision.

## 5. Reproduction

- Use the reporter's image, commit and command first; record them in the triage record.
- Pin what you change: one change at a time, each with its log.
- Run the same-pattern baseline control from `validation_doctrine.md` before blaming a recent change;
  for long-running crashes (e.g. a segfault after about a million served tokens) define the soak test
  and its length up front.
- "Not reproduced" is a result: state the environment, the duration and the counts.
- A reproduction becomes an extra verification gate for the fix (`issue_repro`).

## 6. Auto-close

sglang's `.github/workflows/close-inactive-issues.yml` runs daily (cron `0 0 * * *` UTC) and closes
every open issue whose last update is older than 60 days, adding the `inactive` label. Projected close
date = first daily run after `updated_at + 60 days`. Any comment resets the clock, but the purpose of
triage is a conclusion, not a bump.
