# Performance evaluation — proving the benefit without flattering it

Start only after the correctness gates pass. The question is "what does the feature buy, under which
conditions, at what cost", answered with an A/B that a reviewer can reproduce.

## 1. Compare at an equal budget

A feature usually spends a resource to save another. Hold the scarce resource equal:

- **Memory features** (cache tiers, sparse attention buffers): compare at equal HBM spent on KV state.
  If the feature adds bytes per token, shrink its device pool or grow the baseline's pool by the same
  ratio. Example: HiSparse V2 on DeepSeek-V4.1 raises the per-token KV budget from 1630 B to 1970 B
  (host ratio 2), so a V2 run with a 131,072-token device pool is compared against a baseline/HiCache
  run with `131072 × 1970 / 1630 ≈ 158,412` tokens.
- State the budget in the report (`--max-total-tokens`, host ratio, memory fraction).

## 2. Choose workloads on purpose

| Workload | Why |
|---|---|
| where the feature should help | e.g. long context, many concurrent requests, decode-heavy, capacity-bound |
| where it should be neutral | short prompts that never engage it — must not regress |
| where it costs | e.g. prefill-heavy, low concurrency — quantify the overhead |

Report input and output token totals; a prefill-dominated run (e.g. 960k input vs 16k output tokens)
hides a decode-side benefit. **Run at least one decode-heavy workload**: the HiSparse V2 admission bug
(server crash with `Prefill out of memory`) only appeared once requests generated 512 tokens; 30-token
outputs never triggered it.

## 3. Procedure

- **Fix the benchmark before reading any profile.** The workload (cases, lengths, concurrency, budget)
  is set before the first trace and never changed after results are seen: no case dropped because the
  change loses there, no shape added because it wins there. A workload that must change restarts the
  evaluation and says why.
- **Check the path before trusting a number.** Compare the intended and the effective configuration of
  every arm — attention, MoE and GEMM backends, graph capture, torch.compile, quantization, and any
  fallback or "disabling" warning in the log. A run that silently left the intended path measures a
  different system; it is not evidence for or against the change.
- **Hold out an operating point before claiming a win.** A gain counts only if it also holds where
  nobody tuned: the same workload with another seed (or another slice of a trace), at half the
  concurrency (at least 1). It is fixed with the workload at Setup and measured like the claim; the
  change must still win beyond the noise band there, if not by as much. A gain that vanishes is fitted
  to the benchmark (`reward_hacks.md` P7), not evidence.
- Check the measurement entries of [`reward_hacks.md`](reward_hacks.md) (P) on both arms before
  reporting any number.
- Fresh server per configuration; same container, commit family, GPU set and launch flags apart from
  the feature switch and the budget.
- Flush the prefix cache between runs; use random-token or seed-fixed distinct prompts so prefix hits do
  not differ between arms.
- One warm-up, then ≥2 timed runs per arm (more when the spread is wide). Interleave arms when the box
  is shared.
- Metrics: elapsed time, output tok/s, total tok/s, p50 and max request latency, the concurrency the
  scheduler actually reached (`#running-req` in decode logs), and the feature's own counters (e.g.
  demotions, rows swapped in).
- Check the server log after every run for out-of-memory, retraction and watchdog messages; a run that
  crashed or retracted is not a performance number.

## 4. Admission and capacity checks

A feature that lets more requests run concurrently must also keep the scheduler from admitting more
than it can hold:

- Test a load that drives the pool to its limit with long outputs and high concurrency.
- Make sure the admission rule accounts for everything that must stay on device: per-request scratch,
  each request's own tail and decode growth, and any request whose prefix is pinned (e.g. locked during
  chunked prefill).
- Requests that bypass the admission path (e.g. too long to reserve for) must not bypass the accounting.

## 5. Reference numbers (HiSparse V2, DeepSeek-V4.1-Flash, TP4, gfx950)

32 requests × 30,000 random input tokens, concurrency 32, `ignore_eos`:

| Output per request | HiCache only (158k device tokens) | HiSparse V2 (131k device + 262k host) |
|---|---|---|
| 512 | 37.9 s, 432 out tok/s, ≤5 running | 30.3 s, 540 out tok/s, ≤10 running (+25%) |
| 2048 | 110.9 s, 591 out tok/s, p50 69.2 s | 77.3 s, 848 out tok/s, p50 43.8 s (+43%) |

The gain grows with the decode share, as expected for a feature whose benefit is concurrent decode
capacity.
