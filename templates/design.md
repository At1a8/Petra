# Design — <feature> on <framework> / <model> / <platform>

<!-- Phase 2 (Recon) and Phase 3 (Design) artifact. Gates: every subsystem the feature touches is named
     with file paths and hook points; every work package has a test; every invariant has an enforcement
     point; every unsupported configuration has a startup rejection. -->

## 1. Source design summary

<!-- Data structures, control flow per request lifecycle stage, hooks it relies on. -->

## 2. Code map (target)

| Lifecycle stage | Subsystem | File : function | What the feature does here |
|---|---|---|---|
| startup / argument validation | | | |
| pool sizing / allocation | | | |
| admission (scheduler) | | | |
| prefill / extend | | | |
| prefix cache insert / eviction | | | |
| decode forward (attention backend) | | | |
| request finish / release | | | |

## 3. Assumption table (source → target)

| # | Source assumption | Holds on target? | Evidence (file / config) | Consequence for the design |
|---|---|---|---|---|
| A1 | | | | |

## 4. Design decisions

<!-- Numbered. Each: the decision, the reason, the alternative rejected. Include addressing schemes and
     formulas. -->

## 5. Memory budget

| Item | Bytes per token / per request | Where the sizing accounts for it |
|---|---|---|
| | | |

## 6. Invariants

| # | Invariant | Enforcement point | How a violation shows up / is detected |
|---|---|---|---|
| I1 | | | |

## 7. Synchronization

<!-- Every scheduler-side write to device state that an in-flight forward may read: which stream, which
     wait/event protects it. Note platform differences (e.g. ROCm WAR barrier off by default). -->

## 8. Work packages

| WP | Goal | Files | Test that closes it | Depends on |
|---|---|---|---|---|
| 1 | | | | |

## 9. Startup validation

| Requirement / unsupported combination | Check | Error message |
|---|---|---|
| | | |

## 10. Test plan

| Gate | Suite and size | Concurrencies | Runs | Baseline control | Engagement evidence |
|---|---|---|---|---|---|
| G1 | | | | | |
| G2 | | | | | |
| G3 | | | | | |
| G4 | | | | | |
| G5 | | | | | |

## 11. Risks

<!-- What could make the design wrong; the cheapest experiment that would reveal it. -->
