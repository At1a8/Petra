# Performance analysis — <model> on <framework> / <platform>, <workload>

<!-- mode=perf Profile/Plan artifact (see ../knowledge/system_perf.md). Every number needs a trace or
     log path. -->

## Setup

| Item | Value |
|---|---|
| framework commit / image | |
| launch flags | |
| workload | fixed at Setup (`RUN_DIR/run.json`): ISL / OSL / concurrency / dataset or trace |
| trace tool and window | torch profiler / rocprofv3, which steps (steady state: warm-up passes excluded) |

## Path check (before any number is trusted)

| Item | Intended (launch script) | Effective (`server_args=` line, log) |
|---|---|---|
| attention backend | | |
| MoE / GEMM backend | | |
| graph capture (on, captured batch sizes) | | |
| torch.compile | | |
| quantization path | | |
| fallback or disable warnings in the log | none | |

A run whose effective path differs from the intended one is not evidence: fix the launch, re-run.

## Profile tables (steady state)

Kernel table — per stage, the top kernels by GPU time:

| Stage | Kernel | Category (`rocm_skills.md`) | GPU time share | Launches | Launching op / Python source |
|---|---|---|---|---|---|
| decode | | | | | |

Overlap table — time that could still be hidden:

| Stage | Kernel or category | Exclusive time | Hidden under other streams | Dependency risk |
|---|---|---|---|---|
| | | | | |

Fuse-pattern table — known fused paths that match the trace:

| Pattern | Seen in the trace | Existing path (framework, aiter, other frameworks) | Applies here? |
|---|---|---|---|
| | | | |

Layer table — per forward pass and layer type:

| Forward pass / layer type | Wall time | Share by category (attention, MoE, GEMM, communication, other) |
|---|---|---|
| | | |

## Baseline metrics (steady state)

| Metric | Prefill | Decode | Artifact |
|---|---|---|---|
| GPU busy ratio | | | |
| syncs per step | | | |
| compute–communication overlap | | | |
| CPU time / GPU time per step | | | |
| padding share | | | |
| allocator stalls | | | |

## Opportunities

| # | Kind (`system_perf.md` §2) | Where (file : function) | Evidence | Upper bound of the gain | Owner |
|---|---|---|---|---|---|
| O1 | | | | | Petra / kernel_workflow / Hyperloom |

## Plan

<!-- Selected opportunities in order, each as a work package with its test; kernel-level items as
     hand-offs (op_spec + reference); dropped items with the reason. -->

## Result

| Opportunity | Correctness gates | A/B (equal budget) | Kept / dropped | Artifact |
|---|---|---|---|---|
| | | | | |
