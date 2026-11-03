# Kernel back ends — handing kernel-level work to a kernel workflow

Petra does not tune kernels. Two kinds of kernel-level work leave a framework run:

1. a kernel Petra wrote for a feature (functional and unit-tested, e.g. HiSparse V2's swap-in kernel)
   whose speed matters — the implementer returns a `kernel_handoff`;
2. a kernel-level performance opportunity found by a profile — the architect's performance plan
   returns a hand-off with `owner: "kernel_workflow"`.

`args.kernel_backend` decides what happens to them in the **Kernel** phase, between Implement and
Verify:

| Back end | What runs | Needs |
|---|---|---|
| `none` (default) | nothing: the hand-off package is written and listed in the report | — |
| `geak` | GEAK's single-language kernel lane `kernel_workflow/kernel_lane.js`, nested once, the way GEAK's own `e2e_workflow` calls it | `kernel_backend_dir`, the GEAK checkout; GPUs from `gpu_ids`; `kernel_budget` optimization rounds (default 6) |
| `command` | any other CLI: the kernel liaison runs `kernel_backend_command` with `{task_dir}`, `{out_dir}` and `{gpu_ids}` substituted and reads the JSON result it writes | `kernel_backend_command` |

Adding a back end: a CLI needs no code (`command`); a native one is one branch in `kernelStage()` of
`petra.js` plus a row here.

## 1. The hand-off package

The implementer (functional kernel) or the architect (performance opportunity) writes it under
`RUN_DIR/handoffs/<id>/`:

- `op_spec.md`: the operator, the shapes and dtypes the framework calls it with (from a trace when one
  exists), the math contract, the tolerance, the regime (prefill or decode, graph-captured or not);
- the **reference**, frozen: the functional kernel or the framework's current implementation; it is the
  correctness oracle;
- a unit test the reference passes;
- the plug-in point (file : function) and how the kernel is built (JIT, AOT, Triton).

The kernel liaison turns it into the back end's task format. For GEAK
(`<kernel_backend_dir>/kernel_workflow/README.md`):

- `mode: "optimize"` — `kernel_path` holds the kernel source to edit and its test;
- `mode: "author"` — `kernel_path` is an op task dir with the immutable oracle (`meta.json`,
  `unittest.py`, frozen `baseline_src/`), plus `op_spec` `{op_kind, shapes, dtype, math_contract,
  regime}` and `target_language` (triton | flydsl | hip | ck). GEAK's
  `e2e_workflow/roles/kernel_extractor.md` shows how an op is extracted from a serving stack into this
  layout;
- Petra always passes `apply_to_original: "false"`: the back end never writes into the framework; its
  result comes back as a patch.

## 2. Results

| Status | Meaning | What follows |
|---|---|---|
| `improved` | the back end verified correctness against the oracle and a speedup beyond its noise on the shapes in `op_spec` | an `integrate_wp` work package: the implementer applies the patch at the plug-in point in the task worktree; the test engineer re-runs the unit test and the feature-off check; Verify and Performance then judge the integrated kernel with everything else |
| `no_gain` | correct, not faster | the functional kernel stays |
| `failed` | no correct result, or the back end did not run | the functional kernel stays; the report says why |

After integration a hand-off ends `integrated`, or `integration_failed` (rolled back). With
`kernel_backend=none` every hand-off ends `recorded`, and the report says how to run it later.

A back end's own numbers are never Petra's evidence: an integrated kernel passes Petra's gates like
any other change (`guardrails.md`: measured data wins). A failing or slow back end never blocks the
task.
