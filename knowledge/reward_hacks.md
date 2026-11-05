# Reward hacks — changes that move the number while breaking what it meant

A reward hack is a change, or a measurement, that makes a gate pass or a performance number improve
while violating what the gate or the claim means. Agents produce them without meaning to: a test that
cannot fail, a fast path only the benchmark takes, a baseline launched with worse flags. Each entry says
how to spot it (**tell**) and what closes it (**killed by**): a test, a gate or a measurement rule that
fails on the hacked version and passes on an honest one.

How the roles use this list:

- The **reviewer** starts every review from it: for each entry that applies to the diff and its
  evidence, it checks the tell. A confirmed hack is a `blocker` finding with `hack` set to its id
  (`new` for one not listed); its work package's `test` is the check that kills it, and that check must
  fail on the version under review.
- The **performance engineer** checks the P entries on both arms before reporting a claim, and reports a
  suspected hack, with its id, for the reviewer.
- The **test engineer** applies T1 to every work package (`fails_without_change`).
- The **curator** adds a hack the run confirmed that this list lacks: the hack, its tell, what killed
  it, and the run that found it.

## Tests and correctness gates

| ID | The hack | Tell | Killed by |
|---|---|---|---|
| T1 | a unit test that passes without the change, so it proves nothing about it | it passes on the parent commit | the test engineer runs it on the parent commit, or on a copy of the change broken in one way; it must fail there |
| C1 | a test, tolerance or golden output loosened, skipped or marked expected-to-fail so that a gate passes | the diff touches tests, thresholds, `skip` / `xfail` markers or reference outputs | every test change justified in the review; the original tests and tolerances re-run on the change |
| C2 | the feature turns itself off, or falls back, under the gate's configuration, so the gate measures the baseline | no feature counter or log marker in the gate's logs; a startup message that disables the feature | each gate shows the feature path ran (its counters or log marker), as `path_ok` does for performance |
| C3 | the reproduction weakened until it no longer triggers the bug: a smaller input, other flags, fewer runs | the gate's command differs from the `repro_cmd` recorded at Reproduce | the gate re-runs the recorded `repro_cmd` unchanged; it fails on the base commit |
| C4 | the symptom masked instead of fixed: a broad `try` / `except`, a retry, a clamp or NaN filter around the failure | the fix sits where the error surfaced, not at the root cause the diagnosis names | the review checks the fix against the root cause; a test drives the root condition, not the symptom |
| C5 | a weaker baseline, so the comparison looks fine: other flags, another commit, another request pattern | the baseline and feature launch lines differ beyond the feature switch | one launch script whose arms differ only by the switch; the same-pattern baseline (`validation_doctrine.md`) |

## Performance measurements

| ID | The hack | Tell | Killed by |
|---|---|---|---|
| P1 | another workload measured than the fixed one: shorter outputs, lower concurrency, a case dropped | lengths, concurrency or cases differ from `RUN_DIR/run.json` or the spec's claim | `workload_unchanged` |
| P2 | the number came from another path: a fallback backend, graphs off, a disabled kernel | backend or graph messages in the log differ from the launch intent | `path_ok` (`perf_evaluation.md` §3) |
| P3 | the arms differ beyond the switch: memory fraction, chunked prefill, graph batch sizes, one arm warm and the other cold | the two effective `server_args=` lines differ in more than the switch and the budget | one launch script; the two `server_args=` lines compared; the same warm-up in both arms |
| P4 | more of the scarce resource spent and called a speedup: a bigger KV pool, more device memory | the token pool or the memory fraction grew in the change arm | an equal budget (`perf_evaluation.md` §1) |
| P5 | fewer tokens produced, or tokens counted that were never decoded: an early stop, an ignored `max_tokens`, prompt or draft tokens counted as output | output token totals differ between arms; reported output exceeds the decode steps | the same lengths and `ignore_eos` in both arms; output tokens counted from the client's responses |
| P6 | prefix-cache hits only the benchmark has: repeated prompts, a cache left warm in one arm | the hit rate differs between arms, or is far above the workload's real reuse | the cache flushed between runs; distinct, seed-fixed prompts; both arms' hit rates reported |
| P7 | a fast path only the benchmark's shapes take: a hard-coded batch size, length or concurrency | constants in the diff that match the workload; the win disappears at a nearby shape | the held-out operating point (`perf_evaluation.md` §3); the reviewer reads the diff for such constants |
| P8 | work skipped that only output quality would show: KV not written for some layers, lower precision or ignored sampling parameters on the timed path | the timed path differs from the path the accuracy gate ran | the accuracy gate runs with the timed path's flags; at temperature 0 the timed path matches greedy output |
| P9 | the best of many runs reported, or runs repeated until the change wins | fewer runs reported than launched; no spread | every run reported, with the median and the spread; nothing re-run without saying so |
| P10 | the target workload improved while others regressed | guard workloads missing from the report | guard workloads (`perf_evaluation.md` §2) and `guards_ok` |
| P11 | a kernel that is fast because it computes less: an instantiation the integration uses left out, or benchmark inputs that short-circuit (zeros, sorted, all equal) | the unit test covers fewer instantiations than the integration uses; constant or structured benchmark inputs | the kernel's unit test covers every instantiation in use, on random inputs, against the reference |
