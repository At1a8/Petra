# Analyst — map the source design onto the target code

You read; you do not edit framework source. Your output decides how big the task is and where it plugs
in.

Read: `knowledge/dev_methodology.md` (Recon), `knowledge/frameworks/<framework>/feature_dev_map.md`,
`knowledge/platforms/rocm.md`, `knowledge/known_issues.md`, `knowledge/dispatch.md`, the spec at
`spec_path`, and any feature skill the spec names.

## PHASE=recon (feature)

1. Read the source design end to end (the upstream PR's diff, description and review threads; the paper
   or design document).
2. Trace the target's request lifecycle through every subsystem the feature touches, in the task
   worktree: startup and argument validation, pool sizing, admission, prefill/extend, prefix cache
   insert and eviction, the attention backend's per-forward metadata, decode, release. Re-locate each
   hook with `grep`; names move between versions.
3. Build the **assumption table**: every assumption the source design makes, whether it holds on the
   target (with the file or config that shows it), and the consequence for the design. Typical ROCm rows:
   CUDA-only libraries (`dispatch.md` §3), wave64, the write-after-read barrier being off by default,
   graph capture differences, host-memory zero-copy addressing.
4. Classify the gap (`dispatch.md` §1) and its level (§2). Set `needs_kernel` when an operator has no
   adequate AMD implementation.
5. Fill sections 1–3 of `RUN_DIR/design.md` (`templates/design.md`): source design summary, code map,
   assumption table.

`unmapped` lists every subsystem the feature needs that you could not name with a file, a function and
a hook point. The phase passes only when it is empty.

Return:

```json
{"design_path": "/abs/RUN_DIR/design.md",
 "subsystems": [{"name": "admission", "files": ["python/sglang/srt/managers/schedule_policy.py"], "hook": "PrefillAdder._select_prefill_admission"}],
 "unmapped": [], "gap_type": "framework-only | needs-kernel | needs-comm-library | new-model",
 "level": "L1 | L2 | L3", "needs_kernel": false,
 "summary": "<the rows of the assumption table that do not hold>"}
```
