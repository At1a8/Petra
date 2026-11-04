# Task queue — scan of <sources> at <time, timezone>

<!-- mode=scan artifact (see ../knowledge/dispatch.md). One row per candidate; the ranking follows
     dispatch.md §6. -->

## Sources scanned

| Source | Scope | Candidates | Artifact |
|---|---|---|---|
| upstream | <repo>, <commit range> | | `upstream.json` |
| issues | open AMD-related issues | | `issues.json` |
| ci | Failure Tracker / nightly | | `ci.json` |
| hardware | platform-gate audit of <arch> | | `gates.json` |

## Ranked tasks

| Rank | Task | Source | Type | Level | Priority | Depends on (AMD counterpart) | Effort | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | | | | L1 / L2 / L3 | | | agent h / GPU h | |

## Starting the top tasks

<!-- One task definition per top entry (task_definition.md), passed to petra.js as it is. Fields the
     scan cannot establish (a model not on this machine, a performance task's workload) stay out; the
     run asks for them. -->

```json
{"mode": "issue", "task": "<issue URL>", "framework_dir": "<checkout>", "model_path": "<the reporter's model>"}
```

## Ecosystem matrix changes

| Feature | Model | Platform | Was | Now | Evidence |
|---|---|---|---|---|---|
| | | | | | |

## Not taken

<!-- Candidates dropped, with the reason (duplicate, not AMD, already fixed, out of scope). -->
