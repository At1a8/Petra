# PR playbook — from a working branch to a reviewable upstream PR

## Before opening the PR

Petra's implementer meets these in every work package; the reviewer and the PR engineer check them and
send what is missing back as work packages, so the branch that is pushed is the one that was verified.

- [ ] Debug instrumentation removed, or gated behind an environment switch that is off by default.
- [ ] Feature-off check (G0) passes on the final commit.
- [ ] The target repo's formatters/linters pass locally (sglang: `pre-commit run --all-files`, which
      includes isort, ruff format and clang-format; CI's `lint` job runs the same).
- [ ] New tests registered where the repo's CI discovers them (sglang: `test/registered/...` with the
      CI registration helper), not only in a private scratch directory.
- [ ] Docs updated for the user-visible switch.
- [ ] Commits tell the story: one per work package, follow-up fixes squashed into the commit they fix.
- [ ] Description written from `validation_report.md`, citing artifacts.

## Title

Follow the target repo's convention. sglang: `[Type] [Platform] scope: Description`, e.g.
`[Feat] [AMD] DeepSeek-v4.1: Support HiSparse V2 with HiCache-backed compressed KV`. Use "X-backed"
(supported by X) rather than "X-backend" (a noun that, in sglang, suggests a storage backend).

## Description

Use `../templates/pr_body.md`: Motivation (including `Depends on #NNNN`), Modifications (per subsystem),
Accuracy Tests, Speed Tests, known limitations, checklist.

## Building on an unmerged PR

- Cherry-pick the dependency's commits as the base of your branch and say `Depends on #NNNN` in the
  description; reviewers then read only your commits.
- If you must change the dependency's content on your branch (e.g. revert its docs so your PR carries no
  docs change), make it a separate commit whose message says to **drop it together with the
  dependency's commits when rebasing after the dependency merges** — otherwise your PR's final diff will
  revert the dependency in main.
- After the dependency merges: rebase onto main, drop its commits and any such revert commits, re-run
  the gates.

## Keeping up with main

- Before the PR exists, Petra only trial-merges main to report conflicts; it does not update a
  verified branch. Updating it is the owner's step, and the gates run again on the merged tree.
- Prefer merging main into the PR branch (no force push, review history kept); maintainers squash at
  merge time.
- Do a trial merge in a throwaway worktree first; list conflicts; compile-check and smoke-test the merged
  tree (start the server from the worktree via `PYTHONPATH`) before touching the branch.
- Resolve a modify/delete conflict by following upstream's intent: if main deleted a file in a cleanup,
  do not resurrect it to keep a test you added there — move or drop the test and say so in the merge
  commit message.

## CI on sglang (as observed)

- `lint` and title checks run on every push; most test jobs need a maintainer to add the `run-ci` label,
  so gate jobs (`pr-gate`, `*-finish`) show as failed on a fresh fork PR — expected.
- A docs change on a fork PR produces a **neutral** "Mintlify Preview (fork)" check (preview build waits
  for a maintainer's approval). Neutral does not block merging.
- AMD CI runs separately and also needs to be requested.
