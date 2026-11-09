<!-- petra:daily-report -->
# Petra daily report <YYYY-MM-DD> — <framework> main `<sha>`

<!-- mode=scan artifact, for a human to share, e.g. as an issue titled "Petra daily report <YYYY-MM-DD>"
     in Petra's repository; the first line lets later scans find a shared copy there. Public: nothing
     about the machine, its paths or internal sources. `scripts/daily_report.py check` verifies that and
     the length: an issue holds 65,536 characters, so aim for about 40,000. Every row links to its
     evidence; *new* marks what the previous report did not have. Times are UTC. -->

| Window (UTC) | Sources | Previous report |
|---|---|---|
| <since> → <scan time> | ci, issues, upstream | <link or run name, or none> |

## Summary

<!-- Three to six lines a reader can act on without scrolling: what blocks AMD now, what changed since
     the previous report, what to start first. -->

- **CI on main:** <n> AMD jobs failing, <k> of them *new*, <r> resolved; <the one that blocks most>.
- **User issues:** <p0> P0 and <p1> P1; <u> have no reply, <a> auto-close within 7 days.
- **Upstream:** <m> changes AMD needs to follow (<f> CUDA-first features, <g> new CUDA-only gates, <d> new models).
- **Start with:** <rank 1 task>, because <why>.

## 1. CI on main

<!-- ci.json "main": the latest run on main of each AMD workflow and every job failing in it. Class by
     ci_triage.md §2 when the log or the history shows it, else "unclassified". A code regression names
     the commit range between its last pass and its first failure. -->

| Workflow | Latest run | Failing jobs |
|---|---|---|
| PR Test (AMD) | [<time>](<run URL>) `<sha>` | <n> |

| Job | Failing since | Last passed | Failed tests / first error | Class | Fix PR |
|---|---|---|---|---|---|
| [<job>](<job URL>) *new* | <time>, <n> runs | <time, or not in the last n runs> | | code regression / dependency bump / test bug / flaky / infrastructure / unclassified | none / [#<n>](<url>) |

Resolved since the previous report: <jobs that pass again, or none>. Failure Tracker clusters that
main no longer shows: <list, or none>.

## 2. User issues

<!-- Open AMD user issues, prioritized with issue_triage.md §2 against the quarter's AMD roadmap issue;
     within a priority, the nearest auto-close date first. P2 takes one line each. -->

### P0: <n>

| Issue | Model / feature | Configuration | Fix PR | Replied | Auto-close |
|---|---|---|---|---|---|
| [#<n>](<url>) <title> *new* | | default / cookbook | none / [#<pr>](<url>) | no / yes | <date> |

### P1: <n>

| Issue | Model / feature | Configuration | Fix PR | Replied | Auto-close |
|---|---|---|---|---|---|

### P2: <n>

- [#<n>](<url>) <title>: <why P2>

Closed since the previous report: <issues, or none>.

## 3. Upstream changes to bring to AMD

<!-- upstream.json, and upstream_<name>.json for each repository in upstream_repos. Per repository, the
     changes AMD needs to follow, at most 15 rows; count the rest. -->

### <framework>: <n> commits since <since>

| PR | Merged | Kind | What AMD needs | AMD counterpart | Effort |
|---|---|---|---|---|---|
| [#<n>](<url>) <title> | <date> | CUDA-first feature / new CUDA-only gate / new model | | | agent h / GPU h |

## 4. Suggested tasks

<!-- The top 10 of task_queue.md, ranked with dispatch.md §6. -->

| Rank | Task | Source | Type | Level | Priority | Effort |
|---|---|---|---|---|---|---|
| 1 | | | | L1 / L2 / L3 | | agent h / GPU h |

<details><summary>Task definitions: pass one to petra.js as it is</summary>

```json
{"mode": "issue", "task": "https://github.com/sgl-project/sglang/issues/<n>", "stop_after": "Reproduce"}
```

</details>

## Notes

<!-- What this report could not see, and what to check before acting on it: a tracker days behind main,
     a log that could not be read, a source that was left out. -->
