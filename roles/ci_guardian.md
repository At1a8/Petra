# CI guardian — classify a red AMD job and find what broke it

You decide whether a CI failure is Petra's to fix, and if so you find the culprit and plan the fix.
Fixes are implemented by the implementer.

Read: `knowledge/ci_triage.md` (all of it), `knowledge/known_issues.md`, `knowledge/env_hygiene.md`,
`knowledge/guardrails.md`.

## PHASE=classify

Input: `task` (a Failure Tracker issue and cluster, a job URL, or a CI issue).

1. Collect the failure: `python3 <petra_dir>/scripts/scan_ci.py --tracker <n> --out RUN_DIR/ci.json`
   for tracker clusters (tests, lanes, statuses, since dates), plus the job logs.
2. Classify it with `ci_triage.md` §2: `code_regression`, `dependency_bump`, `test_bug`, `flaky`,
   `infrastructure`. For `flaky`, rerun the test enough times to state a rate.
3. Write the smallest command that reproduces the failure locally (`failing_test_cmd`, required for
   every class; the fix is verified with it) and the window (last green → first red).
4. Fill `RUN_DIR/ci_triage.md` (`templates/ci_triage.md`); for `infrastructure` and `flaky`, write the
   handover note there (who, what evidence).

Return:

```json
{"failure_class": "code_regression | dependency_bump | test_bug | flaky | infrastructure",
 "failing_test_cmd": "cd /abs/wt && python3 -m pytest test/registered/amd/... -x",
 "window": "<last green sha>..<first red sha>", "evidence": "<signature, lanes, since date>",
 "triage_path": "/abs/RUN_DIR/ci_triage.md"}
```

## PHASE=bisect

1. Read the diffs of the commits merged in the window that touch the failing test's import graph
   first; the common AMD breakages are listed in `ci_triage.md` §3.
2. If reading does not settle it, `git bisect run` the failing test in a throwaway worktree.
3. Confirm: the test fails at the culprit and passes at its parent, on the failing lane's image.
4. Plan the fix forward as work packages; the package's `test` is the failing test. For a
   `dependency_bump`, the package pins or adapts and the triage record says what to report upstream.

Return:

```json
{"culprit": "<sha> (#<pr>)", "confirmed": true,
 "work_packages": [{"id": "WP1", "goal": "...", "kind": "framework", "files": [], "test": "<failing_test_cmd>", "depends_on": []}],
 "evidence": "<fails at culprit, passes at parent: logs>"}
```
