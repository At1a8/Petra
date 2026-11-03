---
id: REPLACE-kebab-slug
title: "REPLACE — one line: feature + target model family + platform"
kind: feature_skill
authors: [REPLACE]
# ---- selector: matched against the task ----
match:
  framework: sglang                 # sglang | vllm | atom
  framework_ref: REPLACE            # commit the skill was validated on
  feature: REPLACE                  # snake_case feature name
  model_arch: [REPLACE]             # e.g. [deepseek_v4]
  platforms: [REPLACE]              # e.g. [rocm-gfx950]
depends_on: []                      # upstream PRs the plan builds on, e.g. ["sgl-project/sglang#12345"]
reference_pr: ""                    # the PR that landed this plan, if any
# ---- what the gates must show ----
expects:
  accuracy: REPLACE                 # e.g. "GSM8K within 0.01 of baseline"
  long_context: REPLACE             # e.g. "NIAH pass rate within baseline spread"
  stability: REPLACE                # e.g. "no crash; failure taxonomy equal to same-pattern baseline"
  perf: REPLACE                     # e.g. ">= +20% output tok/s vs <reference> at equal HBM"
# ---- validation record (fill from real runs; never estimate) ----
validation:
  status: draft                     # draft | validated | stale | failed
  last_verified: ""
  framework_commit: ""
  model: ""
  gpu: ""
  measured: {}                      # gate -> measured result with the baseline it was compared to
  artifact: ""                      # branch / PR / result directory
role: advisory_prior
---

## When to use
<!-- The task this plan solves, and the closest tasks it can be ported to. -->

## Source design
<!-- The upstream design in one paragraph: data structures, control flow, the lifecycle hooks it uses. -->

## Assumption table (source → target)
<!-- One row per assumption the source design makes: does it hold on the target? what follows?
     | source assumption | holds on target? | consequence for the design | -->

## Design as built
<!-- Numbered decisions, each with the reason. Include memory budget formulas and addressing schemes. -->

## Invariants
<!-- Numbered, testable statements. For each: where it is enforced and how a violation shows up. -->

## Work packages
<!-- Ordered. For each: goal, files, the test that closes it. -->

## Launch configuration
<!-- Exact flags/env used for validation, including flags needed only to force the feature path in tests. -->

## Validation recipe
<!-- Per gate (G0-G5): command, size, number of runs, expected result, baseline comparison, engagement evidence. -->

## Pitfalls
<!-- symptom → root cause → fix. Include issues that turned out to be baseline bugs (link known_issues). -->

## Do-no-harm
<!-- Feature-off behaviour, requests that must never be affected, startup rejections. -->

## Limitations and open items

## Porting checklist
<!-- The facts to collect about a new target before reusing this plan. -->

## Scripts
<!-- Files under scripts/ and how to run them. -->

## Sources
<!-- PRs, commits, result directories. Every number above needs a pointer. -->
