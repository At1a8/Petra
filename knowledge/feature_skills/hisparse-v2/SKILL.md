---
id: hisparse-v2
title: "HiSparse V2 on DeepSeek-V4.1 compressed KV (sglang, ROCm gfx950): demote admitted prefixes to the HiCache host tier, keep indexer keys on GPU, swap selected rows in each decode step"
kind: feature_skill
authors: [geak]
match:
  framework: sglang
  framework_ref: b057d5b3f1          # sglang main the branch was merged with (Oct 2026)
  feature: hisparse_v2
  model_arch: [deepseek_v4]          # DeepSeek-V4 / V4.1: compressed KV with ratios 1 and 2
  platforms: [rocm-gfx950]
depends_on: ["sgl-project/sglang#32314"]   # HiSparse V2 for DSA (CUDA), unmerged at the time
reference_pr: "sgl-project/sglang#45707"
expects:
  accuracy: "GSM8K within 0.01 of baseline"
  long_context: "NIAH single- and multi-needle at baseline level"
  stability: "no crash; collapse rate not above the same-pattern baseline (KI-002)"
  perf: ">= +20% output tok/s vs HiCache-only at equal HBM on decode-heavy long-context load"
validation:
  status: validated
  last_verified: "2026-10-22"
  framework_commit: "a6aa1c2e34 (branch merged with main b057d5b3f1)"
  model: DeepSeek-V4.1-Flash
  gpu: "gfx950 x4 (TP4)"
  measured:
    kernel_unit_test: "36/36, also with KERNEL_VERIFY=1"
    gsm8k: "0.895 on 1319 questions (baseline 0.901, HiCache-only small pool 0.896)"
    niah: "single-needle 8/8 at concurrency 1 and 8; 8-needle 14/16 (c1), 15/16 (c16)"
    stress: "24-32/32 across runs, final build 30/32 and 31/32; same-pattern baseline 8-30/32"
    perf: "+25% (512 output tokens) and +43% (2048) output tok/s vs HiCache-only at equal HBM"
  artifact: "sglang branch fangyuan/dsv4p1-hisparse-v2 (PR #45707)"
role: advisory_prior
---

## When to use

- Bringing HiSparse V2 (sglang PR #32314) to DeepSeek-V4 / V4.1 on ROCm, or extending this port.
- Porting HiSparse V2 to another model whose sparse attention reads a **compressed** KV cache. Read the
  assumption table first: it lists what changed between the DSA source and this target.
- Goal of the feature: run more long-context requests concurrently on a fixed HBM budget. Admitted
  requests' radix-tree prefixes move to the HiCache host tier; each decode step brings back only the
  rows the indexer selects.

## Source design (PR #32314)

HiCache is the logical KV pool (`write_back`, `page_first`). After prefill, a long request is
**admitted**: it reserves temporary "hot" device slots and its radix-tree lock is released, so its
prefix nodes become evictable. When the device pool needs room, write-back eviction backs a node up to
host and demotes it; the coordinator's eviction hook records the host location of every affected
request position. Each decode step the indexer scores the request's full history, top-k runs, and a
swap-in kernel copies the selected demoted rows from host into the request's hot slots (hash lookup +
LRU), while resident rows are read in place. Hooks used: `reserve_prefill` (admission),
`admit_request` (after `checkpoint_kv_cache`), the write-back eviction callback, and `request_finished`.

## Facts about the target (DeepSeek-V4.1-Flash config)

| Field | Value |
|---|---|
| layers | 40; `compress_ratios`: ratio 2 for layers 2–19, ratio 1 for 20–39 |
| `kv_source_layer_ids` | [2, 8, 14, 20] (C2 KV pool: 3 layers; C1 KV pool: 1 layer) |
| `index_source_layer_ids` | [2, 8, 14, 20, 24, 28, 32, 36] |
| `index_topk` | 512 |
| `sliding_window` | 128 (read by decode through `req_to_token`) |
| page size | 256 tokens (full), compressed entry j covers tokens [jR, (j+1)R) |
| compressed page bytes | 74,880 (C2), 149,760 (C1); 2^bits data rows then scale rows, page rounded to the data size |
| KV bytes per full token | 1630 B; 1970 B once the index pools carry the host region (host ratio 2) |

## Assumption table (DSA source → DeepSeek-V4.1)

| Source assumption | Holds? | Consequence |
|---|---|---|
| One KV layer per attention layer | No: layers share compressed KV (4 KV sources) | swap per **index-source** layer into its pool layer; the 5 C1 index layers share C1 pool layer 0 and need disjoint slot runs |
| Indexer keys live in a per-token buffer | No: paged index pools per ratio (FP4 payload + scale) | expand the ratio-1/2 index pools with a region addressed by host page; copy pages there on demotion; patch page tables |
| A KV row is one token | No: compressed positions | slot = `loc // R`; ratio-2 hot slots come from even temporary tokens `// 2` |
| Attention reads only top-k rows | No: also an SWA window of 128 tokens | keep the window request-owned (tree prefix ends ≥ one window before the prompt end) |
| `allocator.alloc()` works for scratch slots | No: `SWATokenToKVPoolAllocator.alloc` asserts `page_size == 1` | take hot slots from `full_attn_allocator.alloc`, free with `free_full` |
| CUDA | No: ROCm | wave64 kernel; host rows read zero-copy at their host address (checked at startup) |

## Design as built

1. **Swap layers.** One per ratio-1/2 index-source layer: (layer, ratio, pool layer, slot run, device
   buffer, slots per page, data/scale bytes). DeepSeek-V4.1 has 8: C2 layers 2/8/14 → C2 pool layers
   0/1/2 (they share slot numbers, the buffers differ); C1 layers 20/24/28/32/36 → C1 pool layer 0 with
   slot runs 0–4.
2. **Hot rows.** `device_buffer_size` B rows per swap layer per request (validated B = 1024; default is
   `top_k`; must lie in [top_k, 32767] and be page-aligned). Temporary tokens per request =
   `ceil_page(max(n_C1 × B, 2B))` = 5120 for B = 1024. Requests shorter than that are never admitted.
3. **Expanded index pools.** Capacity `(full_size + page_size + host_tokens) // ratio`, with
   `host_tokens = int(ceil(full_size / page) × hicache_ratio) × page`. `base_full_pages =
   (full_size + page_size) // page_size`; host page h lives at index pages `(base_full_pages + h) ×
   per_page + j` (`per_page` 4 for C1, 2 for C2).
4. **Demotion hook** (runs before the device rows are freed): wait for the forward stream; pair the
   node's sorted device rows with its host rows; take host locks for affected requests; copy their
   indexer pages into the expanded region (`preserve_index`); write `host_locs` for those positions,
   then set `req_to_token` to −1 there.
5. **Page-table patch** (each decode forward, before indexer metadata): demoted pages →
   `base_full_pages + host page`; every other entry clamped to ≥ 0 (stale −1 from earlier occupants).
6. **Swap-in kernel** (per swap layer, after decode top-k): resident → slot `req_to_token[pos·R] / R`;
   demoted → hash + LRU over B hot rows; misses copy the data and scale row from the host page
   (`page_first`: `base + (row >> bits) · stride`). Padded rows exit early (`num_real_reqs`). Counters
   `stats[3]`: positions neither tier holds, rows swapped in, copies skipped for an out-of-pool hot slot.
7. **SWA window.** For running requests `checkpoint_up_to(req, up_to) = max(cache_protected_len,
   up_to − sliding_window)`; admitted requests skip checkpoints.
8. **Release.** Drop host locks; reset `host_locs`, hot slots, residency, LRU; clamp the request's
   `req_to_token` row to ≥ 0; free the temporary tokens with `free_full`.
9. **Budget.** `pool_configurator` multiplies the ratio-1/2 index bytes by (1 + hicache_ratio):
   1630 → 1970 B per full token at ratio 2.
10. **Admission** (`reserve_prefill`), both must hold:
    - device: `temps + growths + Σ prefill-locked prefixes + this fill ≤ 0.95 × device tokens`
    - total: `Σ admitted prefixes + pending + this prefix + temps + growths ≤ host + 0.95 × device`
    - with `growth = ceil_page(fill + max_new) − floor_page(max(0, fill − sliding_window))`.
11. **Startup validation** (`validate_hisparse_v2_dsv41`): ratios ⊆ {0, 1, 2} with 1 or 2 present;
    requires HiCache, radix cache, `write_back`, `page_first`, host memory mode `cache`, HIP; rejects
    speculative decoding, mixed chunk, sessions, PD disaggregation, PP/CP/DCP, two-batch overlap,
    prefill without KV, unified memory, routed-expert recording, encoder SWA bounded replay, the
    unified-KV path; `top_k` must equal `index_topk`; `swap_in_block_size` (default 960) a multiple of 64.

## Invariants

| # | Invariant | Enforced by / how a violation shows |
|---|---|---|
| I1 | The SWA window decode reads is request-owned, never a demotable tree page | `checkpoint_up_to`; violation = garbage after demotion |
| I2 | Every admitted position is resident (`req_to_token ≥ 0`) or has a host row (`host_locs ≥ 0`) | demotion hook; `stats[0]` counts violations |
| I3 | Host pages an admitted request references stay host-locked until release | host locks in the hook; release drops them |
| I4 | Indexer keys of demoted pages sit at `base_full_pages + host page` | `preserve_index` + page-table patch |
| I5 | Hot slots are the request's temporary tokens; nobody else writes them | temp reservation; kernel skips out-of-pool slots (`stats[2]`) |
| I6 | Page tables never hold negative pages | clamp in patch and release; violation = memory fault in the FP4 indexer kernel |
| I7 | Scheduler-side writes to state an in-flight forward reads wait on the forward stream | `_wait_for_forward()` in every hook |
| I8 | Feature off ⇒ every hook is a no-op | coordinator is `None`; G0 |
| I9 | Admission never commits more device memory than demotion can free | the two admission conditions |

## Work packages

| WP | Goal | Files (sglang) | Closed by |
|---|---|---|---|
| 1 | swap-in kernel + JIT wrapper | `kernels/jit/csrc/kvcacheio/hisparse.cuh` (`load_cache_to_device_buffer_v41`), `kernels/ops/kvcache/hisparse.py` | `scripts/test_v41_swap_kernel.py` 36/36, also with `KERNEL_VERIFY=1` |
| 2 | expanded index pools + budget | `srt/mem_cache/deepseek_v4_memory_pool.py`, `srt/mem_cache/sparsity/hisparse_v2_config.py`, `srt/mem_cache/kv_cache_configurator.py`, `srt/model_executor/pool_configurator.py` | server starts; startup log shows device + host tokens |
| 3 | cache + coordinator | `srt/managers/hisparse_v2_dsv41.py`; `checkpoint_up_to` hook in `srt/managers/hisparse_v2_coordinator.py` | NIAH with a small device pool |
| 4 | framework hooks | `srt/model_executor/model_runner.py` (build for DSv4, skip draft runners), `srt/layers/attention/deepseek_v4_backend_hip_radix.py` (page-table patch, swap-in after top-k), `srt/mem_cache/unified_radix_cache.py` (checkpoint) | G3 |
| 5 | startup validation | `srt/arg_groups/hisparse_hook.py` | unsupported flags fail at startup |
| 6 | admission accounting | `reserve_prefill` / `admit_request` / `request_finished` in `hisparse_v2_dsv41.py` | decode-heavy throughput run without `Prefill out of memory` |

## Launch configuration (as validated)

DeepSeek-V4.1-Flash, TP4, `--mem-fraction-static 0.85`, `--chunked-prefill-size 8192`,
`--max-running-requests 128`, `--cuda-graph-max-bs-decode 128`, `--enforce-shared-experts-fusion`,
`--fp8-gemm-backend aiter`, `--cuda-graph-backend-prefill disabled`, text-only override
`--json-model-override-args {"vision_n_layers":0}`, plus:

```
--enable-hierarchical-cache --hicache-ratio 2 \
--hicache-write-policy write_back --hicache-mem-layout page_first \
--enable-hisparse-v2 --hisparse-config '{"top_k":512,"device_buffer_size":1024}' \
--max-total-tokens 131072 \
--cuda-graph-bs-decode 2 4 8 12 16 24 32 40 48 56 64 72 80 88 96 104 112 120 128
```

- `--max-total-tokens 131072` keeps the device pool small so tests force demotion.
- The decode graph list leaves out bs=1 to avoid KI-001.
- Startup log to check: `HiSparse V2 (DeepSeek-V4.1): 8 swap layers, 1024 hot rows each, 5120
  temporary tokens per request, 131072 device + 262144 host tokens`.

## Validation recipe

| Gate | Command / setup | Expected |
|---|---|---|
| G1 | `python scripts/test_v41_swap_kernel.py` (36 cases: ratio 1/2 × hot rows 512/1024/2048 × batch of 4 real rows or 5 rows with 3 real × block size 512/960/1024, `v4` row layout); repeat with `KERNEL_VERIFY=1` | all pass; `stats[2] == 0` |
| G0 | baseline suites on the branch with V2 off | unchanged |
| G2 | GSM8K 5-shot greedy, 1319 questions | 0.895 (baseline 0.901, HiCache-only 0.896). GSM8K prompts never reach the 5120-token admission threshold, so this only checks the non-V2 path |
| G3 | `scripts/niah_test.py --context-tokens 30000 --passes 1` (prompts come out at ~37k tokens): single-needle `--num-prompts 8 --needles 1 --max-new-tokens 24 --seed 5` at c1 and c8; 8-needle `--num-prompts 16 --needles 8 --max-new-tokens 80 --seed 1` at c1 and c16 | 8/8 and 8/8; 14/16 (119/128 keys) and 15/16 (120/128). Before the KI-001 workaround both c1 runs were 0/8 and 0/16 |
| G4 | `niah_test.py --num-prompts 32 --context-tokens 30000 --needles 8 --concurrency 32 --passes 1 --max-new-tokens 120 --seed 3` (add `--logprobs` to classify failures), ≥4 runs; the same set at concurrency 1 | c32: 24–32/32, final build 30/32 and 31/32; same-pattern baseline (`--max-running-requests 8`): 8–30/32 (KI-002). c1: 32/32 |
| G5 | `scripts/throughput_test.py`, 32 × 30,000 random tokens, concurrency 32, output 512 and 2048, V2 (131,072 device + 262,144 host) vs HiCache-only at 158,412 device tokens | +25% / +43% output tok/s; see `../../perf_evaluation.md` |

Engagement evidence to attach to G3–G5:
- `HiSparse V2: admitted request #N` lines, logged for the 1st request and then every 64th.
- `HiSparse V2: demotion #N moved node ...` lines, logged for the 1st demotion and then every 256th.
- No `selected %d rows held by neither tier` and no `skipped %d swap-ins` errors.
- To check the data path itself, set `SGLANG_HISPARSE_V2_VERIFY=1`: the kernel re-reads every demoted
  selection against its host row and counts mismatches in `stats[0]`. It is slower, so use it for
  debugging only.

## Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| GPU memory fault in the FP4 paged MQA logits (indexer) kernel during a short-request run | a reused request row still held −1 from demotion; columns past the new request's length became negative pages | clamp in `patch_page_table`; clamp the row at release (I6) |
| assertion in `SWATokenToKVPoolAllocator.alloc` (`page_size == 1`) when reserving hot slots | hot slots taken through the SWA allocator | `full_attn_allocator.alloc` / `free_full` (hot slots need no SWA peer) |
| server crash `Prefill out of memory` under decode-heavy load (512+ output tokens, ~10 concurrent 30k-token requests) | admission counted only prefixes and temps against host + device | add the device condition with prefill-locked prefixes and per-request growth (Design 10) |
| gibberish at concurrency 1 | KI-001 (bs=1 decode graph), not V2 | drop bs=1 from `--cuda-graph-bs-decode` |
| whole batch collapses at one step under stress | KI-002 (baseline), not V2 | judge against the same-pattern baseline control |
| debug check reports per-request state "changed" | the check keyed state by row; rows are reused | key by request id |
| lint fails on the PR (isort, ruff-format, clang-format) | new modules not formatted | run the container's pre-commit before pushing |
| hipify `.hip` files appear in `git status` | JIT build output | never commit them |

## Do-no-harm

- With `--enable-hisparse-v2` off, the coordinator is `None` and every hook returns immediately (G0).
- Requests shorter than the reservation (5120 tokens at B = 1024) are never admitted and follow the
  normal path.
- Unsupported combinations fail at startup with a message naming the flag (Design 11).

## Limitations and open items

- No speculative decoding (draft runners are skipped; the combination is rejected at startup).
- HIP only: the CUDA DeepSeek-V4 backend is not wired.
- Requires HiCache `write_back` + `page_first`.
- A request whose prompt + reservation + `max_new_tokens` + one page exceeds the device pool skips
  `reserve_prefill`, and `admit_request` then allocates its temps without the admission conditions.
  Fix: refuse admission without a reservation.
- KI-004 (dependency: `reserve_prefill` returns `NO_TOKEN` after `init_load_back` without rollback) is
  unverified; the stress tests used distinct prompts with no prefix hits.
- No user docs for DeepSeek-V4.1 usage, and no registered CI test for the V4.1 kernel yet.

## Porting checklist (another compressed-KV model or platform)

Collect before reusing this plan:
- compression ratio per layer, KV-source and index-source layer ids, `index_topk`, any candidate /
  pre-selection stage, sliding window and how decode reads it;
- compressed KV layout: data/scale bytes per row, slots per page, page bytes and alignment;
- indexer pool layout: page size, payload and scale buffers, index pages per full page;
- HiCache host pools for those KV pools: must mirror device pages in `page_first` layout;
- allocator class and its `alloc` / `free` constraints;
- attention backend hook points: where decode builds indexer metadata from `req_to_token`, and where
  top-k results are available before the sparse attention reads rows;
- platform: wavefront size, host-memory zero-copy addressing, and whether the WAR barrier and in-graph
  read-done markers exist (see `../../platforms/`).

Then redo Design 1–3 and 9 for the new numbers and re-run every gate.

## Scripts

- `scripts/test_v41_swap_kernel.py`: kernel unit test against a PyTorch reference. Needs the branch's
  sglang; set `KERNEL_VERIFY=1` to test the verify build.
- `scripts/niah_test.py`: needle-in-a-haystack client (`--needles`, `--concurrency`, `--seed`,
  `--logprobs` to save per-token logprobs for failure classification).
- `scripts/throughput_test.py`: throughput client (random-token prompts, `ignore_eos`, concurrency;
  prints elapsed time, output tok/s, p50 latency).

## Sources

- sglang PR #32314 (dependency): commits cf74cacc8e, 3cb76ff317, db079bc335, fd759157e9.
- sglang PR #45707 (this port), branch `fangyuan/dsv4p1-hisparse-v2`: 18673ecf23 (kernel), 8dc15420d7
  (DeepSeek-V4.1 support), 4a6876569b (swap-in counters, out-of-pool guard), 0303773863 (admission),
  a6aa1c2e34 (merge main), ca2e79e883 (pre-commit format), 7c37cbeb4b (leave the docs to #32314).
- Measurements: 2026-10-22 runs on DeepSeek-V4.1-Flash, TP4 on gfx950; logs stay with the run, not in
  this repository.
