# ROCm notes for the framework's skills

The skills in the framework's repository (`../frameworks/<framework>/skills.md`) are written for CUDA
first. This file lists what differs on ROCm, skill by skill. Checked against sglang `89860fb`
(2026-10-20) and main `e2982985` (2026-11-01); re-check the counts and names on the task's commit.

## debug-cuda-crash (kernel API logging)

- The logging (`SGLANG_KERNEL_API_LOGLEVEL`, `SGLANG_KERNEL_API_LOGDEST`, `SGLANG_KERNEL_API_DUMP_DIR`) is
  plain Python and works on ROCm, but it covers only what is wrapped: `AttentionBackend.forward` (so
  the aiter attention backend is logged at that boundary), ops registered through sglang's custom-op
  helper, and the decorated `sglang.kernels` APIs. **Direct `aiter` calls are not wrapped**: none of
  the 54 files under `python/sglang/srt` that import aiter use `debug_kernel_api` (`89860fb`). A crash
  inside such a call leaves no input dump.
- To capture one, wrap the call site with `debug_kernel_api` in the task worktree (a probe behind the
  same environment variables, never part of the fix). To locate the failing kernel first, serialize the
  device: `AMD_SERIALIZE_KERNEL=3 AMD_SERIALIZE_COPY=3` (wait before and after every launch and copy)
  or `HIP_LAUNCH_BLOCKING=1`; `AMD_LOG_LEVEL=4` adds the HIP runtime's log around the failing launch.
- A device fault prints `Memory access fault by GPU node-<n> ...` and writes `gpucore.<pid>.gpu` files
  (tens of GB each, `../env_hygiene.md`); `rocgdb` reads them.
- As on CUDA, tensors are not dumped while a graph is captured: reproduce with `--disable-cuda-graph`
  to get the inputs.

## debug-distributed-hang

- RCCL reads NCCL's variable names: `NCCL_DEBUG=INFO` and `NCCL_DEBUG_SUBSYS` work unchanged, and
  `py-spy dump --pid <rank pid>` works as on CUDA.
- Custom all-reduce on AMD is `AiterCustomAllreduce` (quick all-reduce for some sizes);
  `--disable-custom-all-reduce` falls back to RCCL and is the first bisection switch (`rocm.md`).

## sglang-bisect-ci-regression

- The method applies as written; the data source changes. AMD lanes run in `pr-test-amd.yml`, on a
  schedule (twice a day for rocm10, once for rocm720/rocm724), and in `nightly-test-amd.yml`; list them
  with `gh run list --repo sgl-project/sglang --workflow=pr-test-amd.yml --event schedule --branch main`.
- Start from the AMD Failure Tracker (`scripts/scan_ci.py`, `../ci_triage.md`): it already groups the
  failures and records since when each fails.
- Confirm on the failing lane's image and GPU generation; MI30x and MI35x lanes differ.

## write-sglang-test

- `register_amd_ci(est_time, suite=None, nightly=False, disabled=None, *, stage=None, runner_config=None)`
  is an AST-parsed marker like the others. Add it only when the test exercises an AMD/ROCm path (the
  skill's rule): backend-independent tests run on the CUDA lanes alone.
- AMD still uses legacy suite strings next to the `stage` + `runner_config` form. The most used at
  `89860fb`: `suite="stage-b-test-1-gpu-small-amd"`, `"stage-b-test-1-gpu-small-amd-mi35x"`,
  `"extra-a-test-1-gpu-small-amd"`, `"stage-b-test-1-gpu-large-amd"`, `"stage-b-test-2-gpu-large-amd"`;
  `stage="stage-b", runner_config="1-gpu-small-amd"` (or `1-gpu-small-amd-mi35x`); kernel tests
  `stage="jit-kernel-unit", runner_config="amd"`. Copy the form the neighbouring AMD tests use.
- Unlike the CUDA nightly rule in the skill (`stage="nightly"`, no `nightly=True`), AMD nightly suites
  still pass the flag: `suite="nightly-amd-kernel-1-gpu", nightly=True`.

## llm-torch-profiler-analysis, generate-profile

- `/start_profile` and the torch profiler (Kineto's ROCm backend) produce the same Chrome trace on
  ROCm; the scripts run unchanged.
- The fuse-pattern catalog already lists a few ROCm paths (AITER fused all-reduce + RMSNorm, aiter fused
  top-k, the fused MLA RoPE path for ROCm). The kernel-category rules match CUDA kernel names, so AMD
  families — hipBLASLt / Tensile GEMMs (`Cijk_...`), RCCL kernels (named after NCCL's), Composable
  Kernel (`ck::`, `ck_tile::`), aiter assembly kernels — can land in "other". Classify them by the CPU op
  that launched them (`aiter::...`, `sgl_kernel::...`, Triton function names), which the trace
  correlates; report the share left unclassified and draw no conclusion from an "other" bucket.
- Kernel-level counters come from `rocprofv3`, roofline and per-kernel limits from `rocprof-compute`;
  the skills' NCU steps have no drop-in equivalent.

## sglang-multi-graph-check

- HIP graphs are captured through `torch.cuda.graph`; the flags (`--cuda-graph-max-bs`,
  `--disable-cuda-graph`) and the checks are the same. What changes replay behaviour on ROCm is in
  `rocm.md` (the write-after-read barrier is off by default).

## add-jit-kernel, add-sgl-kernel, kernel-organization

- JIT kernels build for HIP too; the skill's HIP notes apply: warp width 64 (`warp::kFullWidth`), PDL is
  a no-op on ROCm, `LoadStoreBytes::MAX_PORTABLE` (16 bytes) is the width safe on both.
- AOT kernels build for ROCm from `python/sglang/kernels/aot/setup_rocm.py` (`pyproject_rocm.toml`).
- Petra writes functional kernels and hands their tuning to the kernel back end (`../kernel_backends.md`).

## sglang-prod-incident-triage

- Applies as written: it works at the HTTP level (bundle, failing request, replay). Route a crash it
  finds to the notes on `debug-cuda-crash` above.
