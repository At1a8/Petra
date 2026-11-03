# ROCm notes for framework feature work

Behaviours that differ from the CUDA path and matter when a feature touches scheduling, memory or
kernels. Verified on gfx950 (MI355X class) with sglang `main` around `b057d5b3f1`; re-check on other
generations. Hardware tables for kernel work live in GEAK
(`$GEAK_HOME/kernel_workflow/knowledge/amd_instinct.md`).

## Scheduling and synchronization

- The scheduler's write-after-read barrier is **off by default on ROCm**
  (`_war_barrier_enabled = is_cuda() or SGLANG_ENABLE_WAR_BARRIER`). Feature code that writes state an
  in-flight forward may read must synchronize itself (wait on the forward stream).
- HIP decode graphs have no in-graph "metadata read done" marker (external events are CUDA-only), so
  when the barrier is enabled it waits for the whole replay.
- gfx950 + DeepSeek-V4.1 can overlap indexer/compressor work on side streams in ratio-1/2 layers
  (`SGLANG_OPT_USE_MULTI_STREAM_OVERLAP`, default on, batch ≤ 64; observed to apply under graph
  capture). A feature hook inside the indexer path runs on that side stream.
- Custom all-reduce on AMD defaults to `AiterCustomAllreduce`; `--disable-custom-all-reduce` falls back
  to RCCL (useful as a bisection switch).

## Kernels

- Wavefront size is 64 on Instinct: ballots, shuffles and warp-level scans must be written for 64 lanes
  (hipified CUDA code that assumes 32 lanes breaks silently).
- JIT-compiled kernels are hipified at build time; the generated `*.hip` files appear as untracked files
  in the checkout — keep them out of commits.
- A GPU memory fault kills the server and writes `gpucore.<pid>.gpu` dumps (tens of GB each) into the
  working directory.

## Host memory

- Pinned host pools registered with `hipHostRegister` were observed to have a device-accessible pointer
  equal to the host pointer, so a kernel can read host rows directly (zero copy over the fabric). Verify
  it at startup (HiSparse V2 checks the first and last element with `get_device_accessible_ptr`) rather
  than assuming it.
- A single registration was observed to be limited to 256 GB.

## Known ROCm baseline issues

See `../known_issues.md` (bs=1 decode graph output, whole-batch collapse under continuous batching).
