# CI triage — <cluster or test>

<!-- mode=ci artifact (see ../knowledge/ci_triage.md). Times in one stated timezone. -->

## Failure

| Item | Value |
|---|---|
| source | Failure Tracker #<n> / nightly run / CI issue #<n> |
| tests affected | <count>, e.g. `test/registered/amd/...::Class.test` |
| lanes | rocm720 / rocm724 / rocm10 / ... |
| error signature | |
| first red run / last green run | <run links and times> |

## Classification

| Class | Evidence |
|---|---|
| code regression / dependency bump / test bug / flaky / infrastructure | |

## Culprit (code regression or dependency bump)

| Item | Value |
|---|---|
| window | <last green commit>..<first red commit> |
| culprit | <commit, PR, merge time> |
| how found | diff reading / `git bisect run` (<steps>) |
| confirmation | fails at culprit, passes at its parent (artifacts) |

## Fix or handover

<!-- Fix PR: commits, the failing test now passing on every lane, G0. Handover: who, what evidence. -->

## Dates

| First red | Culprit merged | Fix PR opened | Fix merged |
|---|---|---|---|
| | | | |
