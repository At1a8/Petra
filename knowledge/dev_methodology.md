# Development methodology — phases, artifacts, gates

Read this on every Petra task that changes framework code: a feature, an issue fix, a CI fix or a
performance change. It defines **what must exist before a phase may end**. The other knowledge files
explain *how*; this one is the contract.

The phases below are written for the longest path, landing a feature. The other modes of `petra.js`
replace the front of the pipeline with their own diagnosis and then run the same phases with the same
gates:

| Mode | Front end (replaces Spec / Recon / Design) | Then |
|---|---|---|
| `feature` | Spec → Recon → Design | Implement → Verify → Performance → Review → PR → Report |
| `issue` | Triage → Reproduce → Diagnose (`issue_triage.md`) | Implement → Verify, with the issue's reproduction as an extra gate → Review → PR → Report |
| `ci` | Classify → Bisect (`ci_triage.md`) | Implement → Verify, with the failing test as an extra gate → Review → PR → Report |
| `perf` | Profile → Plan (`system_perf.md`) | Implement → Verify (correctness first) → Performance → Review → PR → Report |
| `scan` | Collect → Dispatch | writes a ranked task queue and changes no code |

Every mode starts from a task definition (`../templates/task_definition.md`). A request in plain
words, or a definition missing something its mode needs, goes through the Intake first
(`../roles/intake.md`): nothing runs until the definition is complete, and what the user did not say
comes back as questions rather than guesses.

## Principles

1. **Correct before fast.** A feature that moves throughput but changes outputs is a regression. The
   performance phase starts only after the correctness gates pass.
2. **Baseline first, and in the same pattern.** Every number about the feature is a *difference* from a
   baseline measured on the same box, the same commit family, the same workload **and the same
   scheduling pattern**. A failure is attributed to the feature only after the identical pattern was run
   on baseline (see `validation_doctrine.md` → *Same-pattern baseline control*).
3. **Feature off means untouched.** With the feature disabled the framework must behave exactly as
   before: every hook is gated on the feature's own switch, and unsupported configurations are rejected
   at startup, not discovered at runtime.
4. **Evidence over belief.** A claim without an artifact (log, result file, commit) does not go into the
   report. Intermittent behaviour is described with counts over repeated runs, never with one run.
5. **Smallest diff that satisfies the spec.** Keep the change inside the subsystems the design names;
   debug instrumentation lives behind environment switches and leaves before the PR.
6. **Time-box investigations.** When an investigation stops narrowing, go back to the controls before
   adding instrumentation (see `debugging_playbook.md` → *Stop rules*).

## Phases

Each phase lists its goal, the artifact it must leave, the gate that ends it, and the traps seen in
practice. Artifacts live in the run's working directory; the templates are in `../templates/`.

### 0. Setup — reproducible environment and baseline

- Pin the framework commit, the container image and the GPU set. Write launch scripts that take a mode
  switch (baseline / feature) and a tag, write one log per launch (tag + timestamp, timezone stated) and
  poll the health endpoint before returning.
- Measure the baseline once per suite in `validation_doctrine.md` and record the run-to-run spread.
- **Artifact:** environment and baseline section of `experiment_ledger.md`.
- **Gate:** the baseline reproduces (repeat runs agree within the recorded spread).
- **Traps:** a flag that looks optional but is auto-enabled (check the effective `server_args` line in
  the log); a server still holding the GPUs from the previous run; git run as root inside the container
  (see `env_hygiene.md`).

### 1. Spec — what will be true when this is done

- Source of truth (upstream PR, paper, design doc), target (framework, model, platform), the user-visible
  switch, acceptance criteria per gate, explicit non-goals and unsupported combinations.
- **Artifact:** `feature_spec.md`.
- **Gate:** every acceptance criterion is measurable with a named suite and threshold.

### 2. Recon — map the source design onto the target code

- Read the source design end to end, then trace the target's request lifecycle through every subsystem
  the feature touches (`frameworks/<framework>/feature_dev_map.md` is the starting map).
- For a port, list **every assumption the source design makes** and check it against the target:
  `assumption → holds on target? → consequence for the design`. This table is the most valuable recon
  output; most design work follows from the rows that do not hold.
- Check `known_issues.md` for the target stack.
- **Artifact:** recon section of `design.md` (code map + assumption table).
- **Gate:** every subsystem the feature will touch is named with file paths and the hook point.

### 3. Design — work packages, invariants, budgets

- Split the change into **work packages** (WPs) small enough to test alone, ordered so each builds on a
  verified one. Typical order: new kernel + unit test → memory/pool layout → bookkeeping/coordinator →
  framework hooks → startup validation → capacity/admission accounting.
- Write the **invariants** as numbered, testable statements ("the SWA window decode reads is always
  owned by the request"). Each invariant names the check that enforces it.
- Memory budget: extra bytes per token / per request and how the pool sizing accounts for them.
- **Artifact:** `design.md`.
- **Gate:** every WP has a test; every invariant has an enforcement point; unsupported configs have a
  startup rejection.

### 4. Implement — one work package at a time

- Implement a WP, run its unit test, run the feature-off check, lint the changed files, commit. Then
  the next WP. Each commit is ready for the PR, which changes no code.
- New kernels: standalone unit test against a reference implementation, covering every template
  instantiation the integration will use, plus a self-check mode that re-reads written data.
- Debug instrumentation: behind environment switches, off by default, never on a hot path when off.
- **Artifact:** one commit per WP; unit test results in the ledger.
- **Gate:** unit tests pass and can fail (`reward_hacks.md` T1); feature-off behaviour unchanged.

### 5. Integrate & verify

- Run the suites in `validation_doctrine.md`: accuracy, long-context retrieval, stability under capacity
  pressure, each at several concurrencies, each against baseline in the same pattern.
- Any failure enters the **investigate loop** (`debugging_playbook.md`): classify, run controls, keep a
  hypothesis ledger. Fixes come back here.
- **Artifact:** validation section of `experiment_ledger.md`.
- **Gate:** every acceptance criterion met, or the residual failure is shown (with counts) to be
  pre-existing on baseline in the same pattern and recorded in `known_issues.md`.

### 6. Performance

- Follow `perf_evaluation.md`: equal memory budget, workloads where the feature should matter plus guard
  workloads, repeated runs, admission and out-of-memory checks under decode-heavy load.
- **Artifact:** performance section of `validation_report.md`.
- **Gate:** the claimed benefit reproduces; no guard workload regresses beyond the noise band.

### 7. Review — an independent read before the PR

- A reviewer that did not write the change reads the diff and its evidence the way a maintainer would
  (`../roles/reviewer.md`): the configurations no test ran, do-no-harm, the framework's conventions, a
  fair benchmark.
- **Artifact:** `review.md`.
- **Gate:** approved with no blocker; requested changes are work packages that go back through
  Implement and Verify (and Performance when the task claims a gain) before the next review.

### 8. Hygiene & PR

- Hygiene happens in Implement: each work package is committed lint-clean, with its tests registered,
  its switch documented and debug code off by default. This phase checks it and changes no code: gaps
  go back as work packages through Implement, Verify and Review; a trial merge of main reports
  conflicts without updating the branch; the PR description is written from the report
  (`pr_playbook.md`).
- **Artifact:** clean commits, `pr_body.md`.
- **Gate:** lint passes; the branch's tree is the one that was verified; feature-off check passes on the
  final commit; the PR description cites the validation artifacts.

### 9. Report & learn

- `validation_report.md` summarises what was built, what was verified (with artifact paths), known
  limitations and open issues. Distil at most a few reusable lessons into the feature skill or the
  method docs; record new baseline bugs in `known_issues.md`.

## What the first port taught (sglang HiSparse V2 → DeepSeek-V4.1, ROCm)

The run behind `feature_skills/hisparse-v2/` spent most of its time on one question — "why do whole
batches turn into gibberish under stress?" — and roughly twenty exclusion experiments before a
**same-pattern baseline control** showed the failure was pre-existing (the untouched upstream code
fails the same way under the same concurrency pattern). Three rules in these docs come directly from
that run:

- Run the same-pattern baseline control **before** instrumenting a failure (`validation_doctrine.md`).
- Classify failures before counting them: mild deviations, whole-batch collapse, empty output and
  crashes have different causes (`validation_doctrine.md` → *Failure taxonomy*).
- Test decode-heavy load, not only prefill-heavy: the admission-accounting bug that crashed the server
  only appears when requests generate hundreds of tokens (`perf_evaluation.md`).
