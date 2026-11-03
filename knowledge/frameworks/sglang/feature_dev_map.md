# sglang — where features plug in

Written against sglang `main` around commit `b057d5b3f1` (October 2026), verified while porting
HiSparse V2 to DeepSeek-V4.1 on ROCm. Paths are relative to `python/sglang/srt/`. Names move between
versions — re-locate each hook with `grep` before relying on it. For "how do I swap a kernel without
touching site-packages", see GEAK's `$GEAK_HOME/e2e_workflow/knowledge/sglang_internals.md`; this file is about changing
behaviour.

## 1. Scheduler loop and streams (`managers/scheduler.py`)

`event_loop_overlap` runs, per iteration:

1. `ingest_requests()`
2. `get_next_batch_to_run()` — builds batch *i+1* (prefill admission or decode preparation; may
   allocate, evict, write `req_to_token`).
3. `run_batch(batch)` — launches batch *i+1* on the **forward stream**; before launch the forward stream
   waits for the **schedule stream** (`forward_stream.wait_stream(schedule_stream)`).
4. `_apply_war_barrier()` — makes the schedule stream wait for the forward stream's shared reads. On
   CUDA always on; on ROCm **off unless `SGLANG_ENABLE_WAR_BARRIER=1`**.
5. Process batch *i*'s results (finishes, frees, prefix-cache inserts, admissions).

Consequences for feature code:

- When batch *i*'s results are processed, batch *i+1* — which may still contain requests that just
  finished — is already queued on the GPU. Scheduler-side GPU writes that an in-flight forward may read
  need an explicit wait on the forward stream (HiSparse V2's coordinator calls `wait_stream(forward)`
  before every write it makes).
- `--disable-overlap-schedule` serialises CPU and GPU: the fastest way to tell a race from a logic bug.
- TP ranks each run their own scheduler and must make identical decisions; tree-cache entry points
  carry `@rank_consensus` checks.

## 2. Request lifecycle hooks

| When | Where | Typical feature use |
|---|---|---|
| prefill admission (each candidate) | `managers/schedule_policy.py` `PrefillAdder` (`_select_prefill_admission`, `_commit_prefill_admission`) | capacity checks, scratch reservations (return `NO_TOKEN` to make the request wait) |
| after a request's prefill completes | `managers/scheduler_components/batch_result_processor.py` (after `checkpoint_kv_cache`) | register the request with the feature |
| every forward | `model_executor/model_runner.py` (before eager forward / graph replay) | per-batch device state (e.g. real batch size for padded graphs) |
| request release | `mem_cache/common.py` `release_kv_cache`: checkpoint → `free_kv_row(protected_len, owned_len)` → unlock → free over-allocation → `tree_cache.on_release(req)` → free the request row | unregister, free scratch, reset per-row state |

Chunked prefill: each chunk ends with a checkpoint that inserts the chunk into the radix tree and moves
the request's lock to the new last node, so **the request's whole prefix is locked on device until
its prefill finishes**. Capacity rules must count it.

## 3. Memory (`mem_cache/`)

- `ReqToTokenPool.req_to_token[row, pos]` — the request's KV slot per position. Rows are reused; rows of
  finished requests keep stale values until overwritten. Page tables for attention are built from it on
  every forward.
- Allocators: paged token allocators; with sliding-window attention, `SWATokenToKVPoolAllocator`
  (`allocator/swa.py`) pairs a full allocator and an SWA allocator through `full_to_swa_index_mapping`.
  Its plain `alloc` asserts `page_size == 1`; paged allocation goes through `alloc_extend` /
  `alloc_decode` (decode reuses `last_loc + 1` within a page). `free` releases full and SWA slots,
  `free_full` expects the SWA mapping already cleared, `free_swa` releases only the window side.
  Feature scratch that needs no SWA peer can be taken straight from `full_attn_allocator`.
- Pool sizing: `model_executor/pool_configurator.py` (bytes per token per pool) and
  `mem_cache/kv_cache_configurator.py` (pool construction kwargs). Extra per-token state must be added
  to the budget there, or the pool silently overcommits HBM.
- DeepSeek-V4 family (`mem_cache/deepseek_v4_memory_pool.py`): compressed-KV pools per compression
  ratio (`kv_pools[ratio]`), indexer-key pools (`index_pools[ratio]`, FP4 payload + scale on ROCm), an
  SWA pool whose storage is `paged`, `ring` or `request_window` (logged as `DSV4 SWA storage`), and
  compressor state pools indexed by request row.

## 4. Prefix cache and HiCache

- Unified radix cache (`mem_cache/unified_radix_cache.py`, tree in `mem_cache/unified_cache/`): nodes
  carry per-component values (FULL, SWA, …). Eviction priority: FULL leaf 0 / internal 2, SWA leaf 0 /
  internal 1 — an SWA eviction on an internal node tombstones SWA only.
- Locks: `inc_lock_ref` pins device data on the path; `inc_host_lock_ref` pins the host copy.
- `checkpoint(req, up_to)` → `checkpoint_into_tree`: frees out-of-window SWA slots, inserts
  `[cache_protected_len, up_to)`, rewrites the request's `req_to_token` with the tree's indices, moves
  the lock, updates `cache_protected_len`. Positions below `cache_protected_len` belong to the tree;
  `free_swa_out_of_window_slots` never frees below `swa_dead_lo ≥ cache_protected_len`.
- HiCache (`--enable-hierarchical-cache`): host pool sized by `--hicache-ratio` (× device) or
  `--hicache-size`; `--hicache-write-policy` `write_through` | `write_through_selective` | `write_back`;
  `--hicache-mem-layout` `layer_first` | `page_first` (+ `page_first_direct`).
- Write-back eviction path: pick a device leaf → back it up
  (`_execute_and_commit_kv_backup`) → `writing_check(write_back=True)` waits on the copy's completion
  events → `_demote` (free device values; a feature hook can run first) → cascade to lower-priority
  components. If the host is full, `drop_subtree_no_host` drops an unlocked subtree instead (logged as
  `write_back: KV subtree dropped without backup ...`).

## 5. Attention backends and per-forward metadata

DeepSeek-V4.1 on ROCm uses `layers/attention/deepseek_v4_backend_hip_radix.py`:

- Decode metadata is rebuilt every forward (`make_forward_metadata_from_raw_decode` →
  `make_core_attn_metadata`: page tables from `req_to_token`); the indexer metadata expands the full-page
  table into indexer pages. A feature may patch these per-forward tensors in place before the indexer
  metadata is built.
- Index-source layers run the indexer + top-k and write `sparse_raw_indices` (compressed positions) and
  `sparse_page_indices` (slots in the ratio's KV pool) **in place**; later layers of the same group reuse
  them. Hooks that rewrite slots (e.g. swap-in) go right after the top-k.
- A candidate-source layer publishes candidate blocks consumed by later index layers.
- gfx950 + V4.1: indexer/compressor of ratio-1/2 layers may run on side streams
  (`SGLANG_OPT_USE_MULTI_STREAM_OVERLAP`, batch ≤ 64), joined before attention.

## 6. CUDA graphs (`model_executor/runner/`)

- Decode graphs are captured for `--cuda-graph-bs-decode` sizes up to `--cuda-graph-max-bs-decode`.
  A batch is padded to the smallest captured size ≥ its size (`bisect_left`), unless
  `--disable-cuda-graph-padding`; padded rows must be inert (feature kernels should early-exit on rows ≥
  the real batch size, read from a device tensor set before replay).
- Graph-safe feature code: no host syncs, no data-dependent shapes, all buffers allocated before capture,
  host bindings (e.g. host-pool addresses known only after HiCache attaches) passed through device
  tensors written later.

## 7. DeepSeek-V4.1 specifics that features run into

- Decoder SWA bounded replay is **auto-enabled**: in prefill, layers from the last KV-source layer on run
  only over each request's last `sliding_window` extend tokens. Disable with
  `--no-enable-decoder-swa-bounded-replay` (omitting the enable flag is not enough).
- The model's architecture name `DeepseekV41ForCausalLM` is mapped to `DeepseekV4ForCausalLM`, so
  `is_deepseek_v4` holds for V4.1.
- Compressed KV and indexer pools are addressed by full-token slot (`slot = loc // ratio`); one full page
  maps to a fixed number of indexer pages per ratio.
