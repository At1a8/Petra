# Issue triage — <repo>#<number>: <title>

<!-- mode=issue artifact (see ../knowledge/issue_triage.md). Every field cites where it came from. -->

## Record

| Item | Value |
|---|---|
| issue | <link> |
| reporter / association | <login> / <NONE / CONTRIBUTOR / COLLABORATOR> |
| opened / last update / projected auto-close | |
| replies from anyone but the reporter | <count, who> |
| linked PRs (state) | <#n open / merged / closed unmerged> |
| model / feature / platform | |
| configuration | default / cookbook / cookbook changed (how) / specific (which flags) |
| category | wrong result / crash / startup or build failure / performance / feature request / CI / tool |
| priority | P0 / P1 / P2, with the rule from `issue_triage.md` that decides it |
| action | reproduce / push_existing_pr / close_fixed / needs_info / not_amd / plan |

## Reproduction

| Run | Image | Framework commit | Command | Result | Artifact |
|---|---|---|---|---|---|
| 1 | | | | reproduced / not reproduced (duration, counts) | |

## Diagnosis

<!-- Root cause with the evidence, or why it is not AMD-side, or what is still unknown. -->

## Fix

<!-- Work packages, commits, the PR body path; or the existing PR that was verified and the results. -->

## Reply draft

<!-- What a human may post on the issue: what was checked, the result, the next step and who owns it.
     Plain, factual, no promises on dates. -->
