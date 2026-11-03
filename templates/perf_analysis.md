# Performance analysis — <model> on <framework> / <platform>, <workload>

<!-- mode=perf Profile/Plan artifact (see ../knowledge/system_perf.md). Every number needs a trace or
     log path. -->

## Setup

| Item | Value |
|---|---|
| framework commit / image | |
| launch flags | |
| workload | ISL / OSL / concurrency / dataset or trace |
| trace tool and window | torch profiler / rocprofv3, which steps |

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
