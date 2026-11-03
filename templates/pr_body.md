<!-- PR description template (sglang layout). Title: `[Type] [Platform] scope: Description`, see
     ../knowledge/pr_playbook.md. Fill from validation_report.md; keep every number traceable. -->

## Motivation

<!-- The user-visible problem and what the feature changes. -->

Depends on #<NNNN> <!-- unmerged PRs this branch builds on; say which commits are theirs -->

## Modifications

<!-- One bullet group per subsystem: kernel, memory pools / budget, scheduler / admission, prefix cache,
     attention backend, startup validation. Name the files. -->

- **Kernel:**
- **Memory pools:**
- **Scheduler / admission:**
- **Prefix cache:**
- **Attention backend:**
- **Startup validation:** requires … ; rejects …

## Accuracy Tests

| Suite | Baseline | This PR | Notes |
|---|---|---|---|
| GSM8K (<n> questions) | | | |
| NIAH single-needle (<prompts> × <tokens>, c<k>) | | | |
| NIAH multi-needle | | | |
| Kernel unit test | | | |

<!-- Say which suites actually engage the feature, and which pre-existing failures were seen on baseline
     in the same pattern (link issues). -->

## Speed Tests and Profiling

<!-- Workload, equal budget, both arms, runs. -->

| Workload | Reference | This PR | Delta |
|---|---|---|---|
| | | | |

## Limitations

<!-- Unsupported combinations, platforms, known gaps. -->

## Checklist

- [ ] Format the code with `pre-commit run --all-files`
- [ ] Add unit tests (registered for CI)
- [ ] Update documentation
- [ ] Provide accuracy and speed results
- [ ] Feature-off behaviour unchanged
