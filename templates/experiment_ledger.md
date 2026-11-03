# Experiment ledger — <feature>

<!-- Append-only working log for Phases 0, 4, 5 and the investigate loop. One row per run; never edit a
     past result, add a correction row instead. Times in one stated timezone. -->

## Environment

| Item | Value |
|---|---|
| container / image | |
| framework commit (baseline) | |
| branch / commit (feature) | |
| GPUs / parallelism | |
| launch script + mode switch | |
| effective flags checked in `server_args=` log line | yes / no |

## Baseline (Phase 0)

| Suite | Config | Runs | Results (each run) | Spread | Artifact |
|---|---|---|---|---|---|
| | | | | | |

## Unit tests (Phase 4)

| WP | Commit | Test | Result | Artifact |
|---|---|---|---|---|
| | | | | |

## Run log (Phases 5–6)

| # | Time | Commit | Server config (tag) | Command | Result (each run) | Failure classes | Artifact |
|---|---|---|---|---|---|---|---|
| 1 | | | | | | collapse / mild / empty / crash counts | |

## Controls

| Control | Pattern reproduced | Runs | Results | Conclusion |
|---|---|---|---|---|
| same-pattern baseline | | | | |
| feature off on branch | | | | |
| untouched upstream code | | | | |

## Hypothesis ledger (investigate loop)

| # | hypothesis | experiment | runs | result | verdict | artifact |
|---|---|---|---|---|---|---|
| H1 | | | | | confirmed / excluded / inconclusive | |

<!-- An "excluded" verdict needs the failure to reproduce with the suspected mechanism truly off (check
     the effective flags), over as many runs as the baseline failure rate requires. -->

## Decisions

<!-- Date, decision, the ledger rows that justify it. -->
