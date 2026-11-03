# Debugging playbook — narrowing a failure without fooling yourself

Use this when a gate in `validation_doctrine.md` fails. The goal is to reach either a fix or a proof
that the failure is pre-existing, with the fewest experiments.

## 0. Write the symptom down precisely

Which requests, which forward step, how often, in which configuration. Classify it with the failure
taxonomy. "Some outputs are wrong under stress" is not a symptom; "all 6 requests that joined the last
decode batch collapse at their 13th output token in 2 of 4 runs" is.

## 1. Controls first

Run these before adding any instrumentation, in this order:

1. **Same-pattern baseline** (see `validation_doctrine.md`). If baseline fails the same way, stop: record
   it in `known_issues.md` and judge the feature on what remains.
2. **Feature off on the branch** — separates "my change" from "everything else on the branch".
3. **Untouched upstream checkout** — separates "framework" from "dependency PR" when the branch carries
   cherry-picked commits.

## 2. Keep a hypothesis ledger

One row per hypothesis, in `experiment_ledger.md`:

| # | hypothesis | experiment | runs | result | verdict | artifact |
|---|---|---|---|---|---|---|

Write the expected outcome **before** running. A hypothesis is excluded only by a configuration that
still fails at a comparable rate; it is supported only by one that stops failing over repeated runs.

## 3. Toggle bisection — remove one mechanism at a time

Turn off one mechanism per experiment and see whether the failure survives. Useful switches on sglang:

| Mechanism | Switch |
|---|---|
| CUDA graphs (decode) | `--disable-decode-cuda-graph` (eager) |
| overlap scheduling (CPU/GPU race class) | `--disable-overlap-schedule` |
| scheduler write-after-read barrier (ROCm default off) | `SGLANG_ENABLE_WAR_BARRIER=1` (+ `SGLANG_FORCE_COARSE_WAR_BARRIER=1`) |
| side-stream overlap in DSv4.1 layers | `SGLANG_OPT_USE_MULTI_STREAM_OVERLAP=0` |
| custom all-reduce | `--disable-custom-all-reduce` |
| decoder SWA bounded replay (auto-on) | `--no-enable-decoder-swa-bounded-replay` (dropping the enable flag is **not** enough) |
| feature sub-paths | the feature's own debug switches (e.g. "no hits", "drop demoted rows") |

Read the effective configuration from the `server_args=` line of the log after every launch; an
auto-enabled feature stays on when you merely omit its flag.

A failure that survives `--disable-overlap-schedule` + eager decode is a **logic bug**, not a
CPU/GPU race — that single result rules out a whole family of hypotheses.

## 4. Instrumentation rules

- Gate every probe behind an environment switch; default off; zero cost when off.
- Log on one rank (rank 0) to a separate file; record a **step counter** on every forward and stamp every
  event (admission, eviction/demotion, finish, allocation) with it, so a divergence can be aligned with
  what happened just before it.
- Avoid device syncs in the probe where possible; if a probe must sync, say so in the ledger — the bug
  may disappear while it runs (it happened: a sync-heavy verification mode never reproduced the failure).
- Snapshot debug versions of files outside the repo before cleaning up, so instrumentation can be
  restored if the failure returns.

## 5. Localize, then explain

1. First divergent output token per failing request (vs a reference output for the same prompt).
2. Map it onto the step trace → the forward step, the batch composition, the events around it.
3. Check data at rest (checksums of the state the step reads) and data in flight (what the step's
   kernels actually read) separately; a clean at-rest check points at the read path.
4. Explain the mechanism before fixing. A fix that "makes it go away" without a mechanism is a
   timing change, not a fix.

## 6. Fix and lock it in

Add the regression test that would have caught it (unit test, or a validation case sized to trigger it),
then re-run the gate that failed and G0.

## Stop rules

- After ~5 experiments that did not narrow the hypothesis space, return to step 1: re-run the controls in
  the exact failing pattern. The most expensive investigation on record (≈20 experiments) ended with a
  same-pattern baseline control that should have been step 1.
- After a fix, if the failure rate drops but does not reach the baseline rate, there is a second cause.
- When the evidence says "baseline bug", write it up (`known_issues.md`), report it upstream, and stop.

## Traps that cost time on the reference run

- Concluding from one clean run that a change "fixed" an intermittent failure.
- A checker that flagged a reused request slot as corrupted state (keyed by slot, not request id).
- Assuming a flag disabled a feature that is auto-enabled.
- `pkill -f "<pattern>"` inside `bash -lc "..."` matching and killing the shell that runs it — use a
  pattern like `'[s]glang serve'`.
- Looking for a process by the wrong name (`sglang serve` vs `sglang.launch_server`) and concluding the
  server is down while its health endpoint answers.
