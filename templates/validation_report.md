# Validation report — <feature> on <framework> / <model> / <platform>

<!-- Phase 6 and Phase 8 artifact; the PR description is written from this file. Every number needs an
     artifact path. -->

## Summary

<!-- Three to five sentences: what was built, whether every gate passed, the headline benefit with its
     budget, and the open issues. -->

## What was built

| Commit | Work package / change |
|---|---|
| | |

## Configuration

<!-- Baseline and feature launch flags, budgets (`--max-total-tokens`, host ratio, memory fraction),
     the framework commit, model, GPUs. -->

## Correctness gates

| Gate | Suite | Baseline (same pattern) | Feature | Verdict | Artifact |
|---|---|---|---|---|---|
| G0 | | | | | |
| G1 | unit tests, each able to fail (parent commit, or a broken copy when the change keeps behaviour) | | | | |
| G2 | | | | | |
| G3 | | | | | |
| G4 | | | | | |

### Failure taxonomy (G3/G4)

| Configuration | Runs | Catastrophic collapse | Mild deviation | Empty output | Crash |
|---|---|---|---|---|---|
| baseline, same pattern | | | | | |
| feature | | | | | |

### Engagement evidence

<!-- Log lines / counters showing the feature path ran in G3–G5 (e.g. admissions, demotions, rows
     swapped in) and that its error counters stayed at zero. -->

## Performance (G5)

| Workload | Budget | Reference arm | Feature arm | Delta | Runs | Artifact |
|---|---|---|---|---|---|---|
| claimed | | | | | | |
| held-out (`perf_evaluation.md` §3) | | | | | | |

<!-- Also: guard workloads where the feature should be neutral; out-of-memory / retraction checks; the
     reward-hack checks (`knowledge/reward_hacks.md` P) with their result. -->

## Known issues encountered

<!-- Pre-existing failures, with the control that proved it and the `known_issues.md` entry. -->

## Limitations and open items

## Lessons

<!-- At most a few; say where each was recorded (feature skill, method docs, known_issues). -->
