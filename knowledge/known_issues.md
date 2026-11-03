# Known issues — check here before blaming your change

Pre-existing behaviour of the reference stacks that a feature run can mistake for its own bug. Each
entry says how it was reproduced **without** any feature change. Add an entry whenever a same-pattern
baseline control (see `validation_doctrine.md`) shows a failure is pre-existing; update the status when
upstream fixes it.

Format: symptom · reproduction · what was excluded · workaround · status.

---

## KI-001 — DeepSeek-V4.1 / ROCm: decode CUDA graph at batch size 1 produces garbage

- **Stack:** sglang `main` (Oct 2026) and an untouched October-8 snapshot, DeepSeek-V4.1-Flash, TP4,
  gfx950.
- **Symptom:** when exactly one request is decoding and the bs=1 decode graph is replayed, the output
  turns into gibberish.
- **Reproduction:** baseline server (no HiCache, no HiSparse), single request; also on the October-8
  snapshot.
- **Excluded:** `--disable-overlap-schedule` does not fix it. A test meant to disable decoder SWA
  bounded replay only dropped the explicit enable flag, which leaves the auto-enabled feature on — so
  bounded replay is **not** yet excluded; re-test with `--no-enable-decoder-swa-bounded-replay`.
- **Workaround:** do not capture bs=1:
  `--cuda-graph-bs-decode 2 4 8 12 16 24 32 ...`. A single request is then padded to the bs=2 graph and
  still replays a graph (one inert padded row). Concurrency-1 accuracy tests pass with this setting.
- **Status:** open; root cause unknown.

## KI-002 — DeepSeek-V4.1 / ROCm: whole-batch collapse when long requests join a running batch

- **Stack:** sglang `main` (Oct 2026) and the October-8 snapshot, DeepSeek-V4.1-Flash, TP4, gfx950.
- **Symptom:** at one decode step every request in the batch collapses together — per-token logprobs
  drop from ~0 to about −2 and stay there; outputs become multilingual gibberish until
  `max_new_tokens`. Requests that never touched any feature path collapse too. The first admitted group
  is fine; groups formed after earlier requests finish are the ones that fail.
- **Reproduction** (NIAH: 32 prompts × ~37k tokens, 8 needles, concurrency 32, `max_new_tokens` 120,
  seed 3; correct out of 32 per run):

  | Configuration (baseline unless noted) | Results |
  |---|---|
  | default pool, `--max-running-requests 8` (pool ~1% used) | 17, 30, 16, 16 |
  | `--max-total-tokens 300000` (≈8 requests fit) | 15, 24, 8, 16, 13 |
  | October-8 snapshot, `--max-running-requests 8` | 16, 8, 24, 8 |
  | waves of 8 requests sent one after another, no flush | waves 1–4 pass, wave 5: 0/8 |
  | **control:** default pool, no concurrency cap (all 32 prefill, then decode together) | 31 (one empty output) |

- **Excluded:** memory pressure (reproduces at ~1% pool usage); decoder SWA bounded replay (reproduces
  with `--no-enable-decoder-swa-bounded-replay`); custom all-reduce (reproduces with
  `--disable-custom-all-reduce`). In HiSparse V2 runs with the same symptom it also survived
  `--disable-overlap-schedule`, eager decode, `SGLANG_OPT_USE_MULTI_STREAM_OVERLAP=0` and
  `SGLANG_ENABLE_WAR_BARRIER=1` — so it is a logic bug, not a CPU/GPU race.
- **Workaround:** none known. Any stress gate on this stack must be judged against the same pattern on
  baseline.
- **Status:** open. Leads not yet checked: state indexed by request row that survives row reuse (e.g.
  compressor state rings), and the forward step at which the batch composition changes.

## KI-003 — long-context NIAH: mild deviations on baseline

- **Symptom:** occasional single wrong digit in a copied key (the same prompt produced `88188` instead of
  `88186` on baseline and with HiSparse V2), a missed EOS after the last key (the request keeps
  generating), or an empty output (first token is EOS).
- **Meaning:** run-to-run noise from low-precision paths (FP8 KV cache, FP4 indexer, FP8/MXFP4 GEMMs) and
  batch-composition-dependent numerics flipping near-tie decisions. Count these separately from
  collapses; they are a regression only if their rate moves beyond the baseline spread.
- **Status:** expected behaviour.

## KI-004 — sglang PR #32314 (HiSparse V2 for DSA): `reserve_prefill` has no rollback after load-back

- **Symptom (code reading, not reproduced):** `reserve_prefill` can return `NO_TOKEN` after
  `init_load_back` already ran, without undoing it. Only prefix-hit requests can reach it.
- **Status:** unverified; the stress tests used distinct prompts (no prefix hits). Check before relying
  on HiSparse V2 with prefix reuse.

## KI-005 — sglang: decoder SWA bounded replay is auto-enabled

- **Symptom:** omitting `--enable-decoder-swa-bounded-replay` leaves the feature on
  (`'enable_decoder_swa_bounded_replay': True` in the `server_args=` log line).
- **Workaround:** pass `--no-enable-decoder-swa-bounded-replay` to disable it; read `server_args=` to
  confirm any toggle.
- **Status:** by design; listed because it silently invalidated one bisection experiment.
