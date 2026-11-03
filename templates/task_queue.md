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

## Ecosystem matrix changes

| Feature | Model | Platform | Was | Now | Evidence |
|---|---|---|---|---|---|
| | | | | | |

## Not taken

<!-- Candidates dropped, with the reason (duplicate, not AMD, already fixed, out of scope). -->
