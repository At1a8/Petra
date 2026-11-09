# Petra daily report <YYYY-MM-DD> — <framework> main `<sha>`

<!-- mode=scan artifact, posted as the day's issue in Petra's own repository (scripts/post_queue.py).
     The repository is public: nothing about the machine, its paths or internal sources. Every row points
     at its evidence (a run, a job, an issue, a PR). -->

Window: <since> → <scan time> (UTC). Previous report: <#n, or none>. Sources: <ci, issues, upstream, ...>.

## 1. CI on main

<!-- ci.json "main": the latest run on main of each AMD workflow, and every job failing in it. The class
     follows ci_triage.md §2 (code regression, dependency bump, test bug, flaky, infrastructure) when
     the evidence shows it, else "unclassified". -->

| Workflow | Latest run | Failing jobs |
|---|---|---|
| PR Test (AMD) | <time> (`<sha>`) | <n> |

| Job | Failing since | Last passed | Failed tests / first error | Class | Fix PR |
|---|---|---|---|---|---|
| | <time> (<n> runs) | <time, or none in n runs> | | | |

Failure Tracker clusters that main no longer shows: <list, or none>.

## 2. User issues

<!-- Open AMD user issues, each prioritized with issue_triage.md §2 against the quarter's AMD roadmap
     issue. *new* marks an issue the previous report did not list. -->

### P0

| Issue | Model / feature | Configuration | Fix PR | Replied | Auto-close |
|---|---|---|---|---|---|
| | | default / cookbook | none | | |

### P1

| Issue | Model / feature | Configuration | Fix PR | Replied | Auto-close |
|---|---|---|---|---|---|

### P2

| Issue | Why P2 |
|---|---|

## 3. Upstream changes to bring to AMD

<!-- upstream.json (and one file per repository in upstream_repos): merged PRs that add a CUDA-first
     feature, a new CUDA-only gate or a new model, with what AMD needs and the AMD counterpart. -->

### <framework>

| PR | Merged | Kind | What AMD needs | AMD counterpart | Effort |
|---|---|---|---|---|---|
| | | cuda_first_feature / new_cuda_gate / new_model | | | agent h / GPU h |

## 4. Suggested tasks

<!-- The top of task_queue.md, ranked with dispatch.md §6, each with the task definition that starts it:
     weights as model_path=<weights>, framework_dir left out (the default). -->

| Rank | Task | Source | Type | Level | Priority | Effort |
|---|---|---|---|---|---|---|
| 1 | | | | L1 / L2 / L3 | | agent h / GPU h |

```json
{"mode": "issue", "task": "https://github.com/sgl-project/sglang/issues/<n>", "stop_after": "Reproduce"}
```
