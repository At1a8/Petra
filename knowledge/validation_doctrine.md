# Validation doctrine — what "correct" means for a framework feature

A feature passes when every gate below holds **relative to baseline in the same pattern**. Absolute
pass rates mean little on a low-precision serving stack: the baseline itself has a non-zero failure
rate on long-context tests, so the question is always "does the feature change the failure rate or the
failure kind beyond the measured noise?".

## Gates

| Gate | What it shows | Typical suite |
|---|---|---|
| G0 feature off | the change is inert when disabled | baseline suites on the feature branch with the switch off |
| G1 unit / oracle | each new kernel or data structure does what it claims | standalone tests vs a reference implementation, each failing without the change: on the parent commit, or on a copy broken in one way (`reward_hacks.md` T1) |
| G2 accuracy | short-context quality is unchanged | GSM8K (5-shot, greedy, full set or ≥200 sampled) |
| G3 long context | the feature's own data path is exercised and correct | needle-in-a-haystack: single and multi-needle |
| G4 stability | no crash / hang / collapse under capacity pressure | many long prompts at high concurrency |
| G5 performance | the claimed benefit exists, guards hold | see `perf_evaluation.md` |

Notes per gate:

- **G2 does not prove a long-context feature works.** Short prompts may never engage it (HiSparse V2
  only admits requests longer than its 5120-token reservation; GSM8K prompts are ~1k tokens). G2 is a
  regression check for the non-feature path; G3 must exercise the feature path.
- **G3/G4 must be sized so the feature engages.** For a memory-tier feature that means total context
  well above the device pool (force eviction/demotion), and concurrency high enough that several engaged
  requests decode in the same batch. Log the engagement (e.g. demotion counters) and attach it.
- **Run G3/G4 at more than one concurrency.** Concurrency 1 often passes when concurrency 8–32 fails;
  the batch-level interactions are where bugs live.

## Failure taxonomy — classify before counting

Count each class separately; a single "correct %" hides the signal.

| Class | Looks like | Usual meaning |
|---|---|---|
| catastrophic collapse | every request in a decode batch turns into gibberish at the same step; per-token logprobs drop from ~0 to around −2 and stay there | corrupted state (KV, cache metadata, buffers) — or a pre-existing baseline bug (see `known_issues.md`) |
| mild deviation | one wrong digit in a copied key, a missed end-of-answer EOS, a near-tie token flip; the rest of the output is fine | numeric noise from low-precision paths and batch-dependent numerics |
| empty output | the first generated token is EOS | seen on baseline too; count it, do not chase it unless the rate moves |
| crash / OOM / hang | server error, `Prefill out of memory`, watchdog timeout | capacity accounting, synchronization, or a kernel fault |

How to tell them apart quickly:

- Record **per-token logprobs** (`return_logprob`) for every long-context request. Collapse is a sudden,
  persistent drop shared by the whole batch; mild deviation is one low-logprob token followed by a
  recovery.
- Compare output token ids with a **reference output per prompt** (fixed seeds, greedy). The first
  divergent index, mapped onto the per-step trace, tells you which forward step went wrong and which
  requests were in that batch.
- The task metric can lie: a request that printed every key and then failed to stop (missed EOS, ran to
  `max_new_tokens`) is "correct" by key recall. Track output lengths too.

## Noise characterization

- Repeat every configuration **≥4 times** (≥6 when hunting an intermittent failure) and report the
  distribution, e.g. `27/32, 31/32, 32/32, 25/32`, not an average.
- Use the same prompts in every configuration (fixed seed) and flush the prefix cache between runs.
- A configuration "fixes" an intermittent failure only when its failing-run rate is clearly below the
  baseline rate; one clean run after three failing runs is not evidence.
- Heavy verification (device-wide syncs after every kernel, CPU waits) changes timing and can hide a
  bug. A clean run with heavy checks on proves nothing about the run without them.

## Same-pattern baseline control (the rule that would have saved the most time)

Before instrumenting any failure, reproduce **the same scheduling pattern on baseline**:

1. Describe the pattern the failing run had: how many requests were admitted at once, whether new
   requests joined while others were decoding, how full the pool was, which concurrency.
2. Recreate it on the baseline build — limit concurrency with `--max-running-requests N`, shrink the
   pool with `--max-total-tokens`, send the same prompts in the same waves.
3. Compare the failure taxonomy over repeated runs. Only a difference beyond the noise is attributable
   to the feature; a failure present on baseline goes to `known_issues.md` and the feature is judged on
   the remainder.

Also run the **original upstream code** (an untouched checkout of the framework) when the branch carries
other people's commits, so a failure can be pinned to "framework", "dependency PR" or "this change".

## Checking the checkers

A debugging check that reports a false positive costs as much as a missed bug.

- Key per-request state by request id, not by slot index: slots are reused, and a new request whose
  first decode length happens to equal the previous occupant's last length looks like "state changed".
- Validate a new check on a known-good run before trusting it on a failing one.
- Prefer checks that count into a device tensor and are read at a coarse interval over checks that sync
  the device every step.

## Suites used on the reference stack

The `hisparse-v2` skill records concrete settings and expected numbers; in short:

- **G2:** GSM8K 5-shot greedy, 1319 questions (or a fixed 200-question subset for quick loops).
- **G3:** NIAH single-needle and 8-needle prompts of ~30–37k tokens at concurrency 1, 8 and 16.
- **G4:** 32 prompts × ~37k tokens, 8 needles, concurrency 32, `max_new_tokens` 120, fixed seed, on a
  device pool small enough to force the feature's memory path, plus the same-pattern baseline control.
