# System-level performance — the time between and around the kernels

Read this in `mode=perf` and in the Performance phase of any mode. Petra optimizes the end-to-end
timeline outside kernel compute: GPU idle gaps, host-device synchronization and copies, compute and
communication that run one after another, padding, scheduling overhead and memory-management stalls.

Boundaries:

| Work | Owner |
|---|---|
| making one kernel faster (tiling, fusion inside a kernel, a new kernel) | the kernel workflow on the selected back end (`kernel_backends.md`, e.g. GEAK) — Petra hands it an op spec and a reference |
| searching launch flags and backend choices for a workload | Hyperloom / GEAK `e2e_workflow` |
| changing how the framework executes: graphs, streams, syncs, overlap, scheduling, memory | **Petra** |

## 1. Measure first

Collect a trace of the steady state (torch profiler or `rocprofv3`) on the target workload and compute:

| Metric | Meaning |
|---|---|
| GPU busy ratio | kernel time / wall time per step; gaps between kernels are the bubbles |
| syncs per step | device-to-host copies and stream or device synchronizations issued per forward |
| compute–communication overlap | share of collective time hidden under compute on another stream |
| CPU time / GPU time per step | above 1 the scheduler, not the GPU, sets the pace |
| padding share | tokens computed for padding (graph buckets, DP ranks aligned to the longest) |
| allocator stalls | `empty_cache`, segment growth, reserved-but-unused memory |

Estimate the gain before writing code: the time an optimization can remove is bounded by what the
trace shows. Example of a change that looked good and was not: replacing all-reduce + scatter after
the MoE with a reduce-scatter halved the bytes, but in decode the collective was dominated by waiting
across ranks, the segment got ~6% faster (582 vs 617 µs per layer) and end-to-end throughput did not
move.

## 2. Catalogue

Each entry: what to look for, how to fix it, evidence from the reference stack (sglang on MI355X).

### 2.1 Graph coverage

- **Look for:** eager steps (decode or verify batches above the captured sizes, features that disable
  capture, capture failures that fall back to eager). Each eager kernel pays a host launch.
- **Fix:** capture the missing shapes; make the feature graph-safe (no host syncs, no data-dependent
  shapes, buffers allocated before capture, host-side values passed through device tensors); piecewise
  graphs for prefill.
- **Evidence:** piecewise CUDA graph for DeepSeek-V4 on ROCm improved TTFT by 4–10%. In isolation a
  launch-bound all-reduce (≤ 256 tokens) ran 5–12× faster inside a graph (110–140 µs saved per call);
  a bandwidth-bound one (≥ 2048 tokens) did not change. Open gaps: torch-compile decode capture failing
  on the rocm720 lane; breakable decode graphs failing at startup on DSA models (sglang #38708). Prefill
  shapes vary per chunk, and per-shape JIT/autotune can exhaust HSA resources, so prefill graphs need
  a bounded shape set.

### 2.2 Host-device synchronization and copies (including MTP)

- **Look for:** `.item()`, `.tolist()`, `.cpu()`, `.numpy()`, `torch.cuda.synchronize()`, blocking
  `.to(device)` from pageable memory, `torch.tensor(list, device=...)` inside the forward path or the
  per-step metadata builders. The overlap scheduler is on by default on ROCm; one sync makes the host
  wait until the GPU queue drains, so the next step's preparation and launches stop overlapping.
- **Fix:** take the value from host-side state that already exists (`seq_lens_cpu`, server arguments),
  size buffers by an upper bound instead of an exact count, keep the computation on the device, use
  pinned buffers with `non_blocking=True`.
- **Evidence:** upstream's EAGLE code already avoids these (comments: skip per-iteration
  `.sum().item()`; a blocking `.to()` syncs the schedule stream). The AMD-only aiter attention backend
  on sglang main (2026-11-01) still has: `_resolve_v2_num_draft_tokens` reading the draft-token count
  from a device tensor (MTP); the draft-extend-v2 eager branch of `forward_extend` calling
  `qo_indptr[-1].item()` per layer; `_build_dcp_verify_ragged_indices` calling `.sum().item()` only to
  size a buffer; `_resolve_mla_gluon_min_kv_seq_len` taking `seq_lens.max()` on the device while
  `seq_lens_cpu` exists; `_build_paged_kv_view` issuing three blocking `.to(device)` copies per prefill.
  `scripts/audit_host_syncs.py` lists candidates; confirm each in a trace.

### 2.3 Multiple streams

- **Look for:** independent work serialized on one stream (indexer vs main attention, shared experts vs
  routed experts, KV writes vs compute).
- **Fix:** a side stream with explicit events; measure, because two streams compete for compute units.
- **Evidence:** the DSA indexer's dual-stream path is disabled on ROCm by its threshold
  (`DUAL_STREAM_TOKEN_THRESHOLD = 1024 if _is_cuda else 0`, sglang #38745). DeepSeek-V4.1 already runs
  ratio-1/2 indexer and compressor work on side streams on gfx950 (`SGLANG_OPT_USE_MULTI_STREAM_OVERLAP`,
  batch ≤ 64).

### 2.4 Compute–communication overlap

- **Look for:** collectives (DP gather/scatter, EP dispatch/combine, TP all-reduce) with idle compute.
- **Fix:** two-batch overlap (split the batch into two micro-batches so one's communication runs under
  the other's compute), asynchronous collectives on a communication stream.
- **Evidence:** DeepSeek-V4-Pro prefill TBO on MI355X: +8.5% throughput and −7.8% TPOT (8k/1k,
  concurrency 256), and +4.8–5.6% on top of MTP. Decode/verify TBO was still blocked by a MoRI
  dual-stream all-to-all deadlock and by idle DP ranks reporting batch sizes that hang the collectives.

### 2.5 Communication fusion and redundant copies

- **Look for:** separate all-reduce, residual add and norm kernels; gathers that copy into a staging
  buffer and then again into the destination.
- **Fix:** use the existing fused path (aiter all-reduce + residual + RMSNorm) where it applies; write
  collectives straight into their destination (`output=`).
- **Evidence:** the aiter all-reduce fusion was not auto-enabled while the log claimed it was (sglang
  #38710; enabled for GLM by #39790). Writing `all_gatherv` directly into the DP buffer removed two
  ~940 MB device-to-device copies, about 700 µs per layer at concurrency 512.

### 2.6 Data-parallel attention balance

- **Look for:** DP ranks padded to the longest rank; idle ranks joining collectives.
- **Fix:** choose the gather layout by load (prefill: concatenate actual lengths; decode: pad to the
  maximum when `max_len × dp_size ≤ 2 × sum_len`); balance requests across ranks at dispatch.

### 2.7 Scheduler CPU overhead

- **Look for:** CPU time per step above GPU time at high concurrency (per-request Python loops in batch
  construction, prefix matching, output processing).
- **Fix:** vectorize or move the hot loop to native code; upstream plans a Rust scheduler (#42473), so
  check before investing.

### 2.8 Memory-management stalls

- **Look for:** growing `reserved` memory, out-of-memory with free memory reported, periodic
  `empty_cache()`.
- **Evidence:** `tensor.record_stream(comm)` delayed frees until the communication stream drained, every
  later allocation opened a new segment and the server hit `HSA_STATUS_ERROR_OUT_OF_RESOURCES`; keeping a
  Python reference until a completion event instead cut reserved memory from 269.7 GB to 235.5 GB. A
  workaround that calls `empty_cache()` on all decode ranks (sglang #46831) synchronizes and stalls;
  find the allocation source instead.

### 2.9 KV transfer and cache tiers

- **Look for:** PD transfers or HiCache loads that block compute.
- **Fix:** layer-wise transfer overlapped with compute, prefetch and write-back on their own streams,
  KV reuse across agentic turns in PD mode.

## 3. Applying existing PRs

Short-term path for performance: take a candidate PR (an upstream PR not yet effective on AMD, an
unmerged AMD PR, or a candidate from Hyperloom's discovery), apply it in a worktree, run the
correctness gates, then the equal-budget A/B from `perf_evaluation.md`. Keep it only on a measured win
with guards holding; report the numbers on the PR either way.

## 4. Correctness first

A performance change passes the same gates as a feature: G0 (off means untouched), G2 accuracy, output
parity on fixed prompts, and for speculative decoding the acceptance length must not drop
(`composability.md`).
