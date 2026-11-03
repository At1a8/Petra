# Feature spec — <feature> on <framework> / <model> / <platform>

<!-- Phase 1 artifact (see ../knowledge/dev_methodology.md). Gate: every acceptance criterion below is
     measurable with a named suite and threshold. -->

## Source of truth

- Upstream design: <PR / paper / design doc link>, at commit <sha>
- Dependencies that are not merged yet: <PR links, commits to cherry-pick>
- Matching feature skill, if any: `knowledge/feature_skills/<id>/SKILL.md` (status: <validated / stale>)

## Target

| Item | Value |
|---|---|
| framework + commit | |
| model + checkpoint path | |
| platform / GPUs / parallelism | |
| container image | |
| user-visible switch | e.g. `--enable-<feature>`, config JSON keys |

## Goal

<!-- One paragraph: what the user gets (capability, capacity, latency) and on which workloads. -->

## Acceptance criteria

| Gate | Suite | Threshold (relative to baseline in the same pattern) |
|---|---|---|
| G0 feature off | | identical to baseline |
| G1 unit / oracle | | all cases pass, including self-check mode |
| G2 accuracy | | e.g. GSM8K within 0.01 |
| G3 long context | | e.g. NIAH pass rate within baseline spread, feature engaged |
| G4 stability | | no crash; failure taxonomy not worse than baseline |
| G5 performance | | e.g. >= +X% output tok/s at equal HBM on <workload> |

## Non-goals and unsupported combinations

<!-- Each unsupported combination gets a startup rejection with a clear message. -->

## Constraints

- Feature off ⇒ framework unchanged.
- <memory budget limits, latency limits, files/subsystems that must not change>

## Deliverables

- Branch / PR: <name>
- Tests: <unit tests, registered CI tests>
- Docs: <user docs to add>

## Time-box

<!-- Budget per phase; when an investigation exceeds it, return to the controls. -->
