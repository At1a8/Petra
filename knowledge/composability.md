# Composability — features that work alone must also work together

AMD's gap is often not a missing feature but a missing combination. InferenceX v2 (SemiAnalysis,
2026-02-16) found MI355X FP8 PD disaggregation + wide EP on par with B200 on sglang, but not competitive
once PD disaggregation, wide EP and FP4 were enabled together. Petra tests combinations on purpose and
feeds every failing combination back into the task queue.

## 1. Matrix

| Dimension | Values |
|---|---|
| parallelism | TP, EP (MoRI-EP), DP attention, PP, PCP, DCP, PD disaggregation |
| speculative decoding | MTP (EAGLE), DSpark, DFlash |
| KV cache tiers | HiCache, HiSparse, MoRI UMBP, Mooncake |
| precision | FP8 / MXFP4 weights, FP8 / MXFP4 KV cache |
| platform | MI30x, MI35x, MI45x |
| model | DeepSeek-V4/4.1, Qwen3.X, GLM-5.X, Kimi-K3.X, MiniMax-M3.X, GPT-OSS |

**Nightly minimum:** DP attention + EP + MTP on each roadmap model that supports it. Add combinations
to the nightly set only after they pass once by hand.

Selection beyond the nightly set: for a target model and platform, cover every pair of dimension values
first (pairwise), then the deep combinations the roadmap or a customer workload names.

## 2. Extra gates per dimension

On top of G0–G5 in `validation_doctrine.md`:

| Dimension in play | Gate |
|---|---|
| speculative decoding | acceptance length per draft depth must not drop against the same model without the other features (sglang #28520 fixed one such regression for DeepSeek-V4 MTP); output parity at temperature 0 |
| FP8 / MXFP4 KV cache or attention | a stated accuracy bound plus long-context retrieval (needle-in-a-haystack) per dtype |
| PD disaggregation | the decode side reads exactly what the prefill side wrote (kv canary hash checks, first-token parity) |
| graphs + any feature | the feature path runs under capture (engagement counters stay non-zero with graphs on) |
| RL integration, if in scope | training and inference log-probs agree within the stated bound |

## 3. The ecosystem matrix

`feature × model × platform`, each cell **available** or **unavailable**, with evidence: framework
commit, configuration, the test that passed or the error that occurred, and the date. An unavailable
cell names its reason: rejected at startup, disabled by a platform gate, crashes, accuracy below the
bound, or not implemented. The scout updates the cells it can test cheaply on each scan; every change of
state cites a run.

Rules:

- A combination the code cannot support must be rejected at startup with a message naming the flag,
  never discovered at runtime.
- A cell turns available only with a passing run on that platform; a CUDA result is not evidence for
  ROCm.
- A cell that turns unavailable after a framework update is a CI-class task (`ci_triage.md`).
