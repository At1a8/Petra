# feature_skills — validated development plans for one feature

> **Contract.** A feature skill is an **advisory prior**: a validated, reusable plan for landing one
> feature (`feature × framework × model family × platform`). It shortens Recon and Design and lists the
> pitfalls already paid for. It never replaces the gates in `../validation_doctrine.md`: a run that uses
> a skill still runs every gate, and when the target code or a measurement disagrees with the skill, the
> code and the measurement win and the skill is marked `stale`.

## How it differs from the other knowledge tiers

| Tier | Unit | Judged by |
|---|---|---|
| GEAK `perf_knowledge/expert_skills/` | an optimization recipe for `operator × scenario` | isolated / e2e speed A/B |
| GEAK `*/knowledge/learned/` cards | one distilled principle | the A/B that produced it |
| **`feature_skills/` (here)** | a development plan for a feature on a stack | Petra's gates (G0–G5) |

## Layout

```
feature_skills/
├── README.md              # this contract
├── index.yaml             # selector registry (one entry per skill)
├── _template/SKILL_TEMPLATE.md
└── <id>/
    ├── SKILL.md           # REQUIRED: frontmatter selector + the plan
    ├── scripts/           # optional: unit tests, eval clients the validation recipe uses
    └── references/        # optional: design notes, diagrams, captured configs
```

## Selection

A run reads `index.yaml` and keeps the entries whose `match` fits the task:

```
match.framework == task.framework
AND match.feature == task.feature            (or the task is "port <feature> to <target>")
AND task.model_arch ∈ match.model_arch       (or the skill is the closest source to port from)
AND task.platform ∈ match.platforms          (a different platform is a port: read, do not reuse blindly)
AND validation_status ∈ {validated, stale}   (stale = read as reference, re-verify every step)
```

There is no ranking. A matching skill is read in full; a near match (same feature, different model or
platform) is the starting point of a port — its *assumption table* tells you what to re-check.

## Lifecycle

`draft` → (all gates pass with recorded numbers and artifacts) → `validated` → (the framework moved past
`framework_ref` and a hook point named in the skill changed, or a gate result contradicts the skill) →
`stale` → (re-validated) → `validated`. A skill whose plan fails its gates is `failed` and is kept only
as a reference.

## Required sections (see the template)

When to use · Source design · Assumption table (source → target) · Design as built · Invariants ·
Work packages (ordered, with files) · Launch configuration · Validation recipe (gates, commands,
expected numbers) · Pitfalls (symptom → cause → fix) · Do-no-harm · Limitations and open items ·
Porting checklist · Scripts · Sources.

## Adding a skill

1. Copy `_template/SKILL_TEMPLATE.md` to `<id>/SKILL.md` and fill every section; put the scripts the
   validation recipe runs under `<id>/scripts/`.
2. Add an entry to `index.yaml` with `validation_status: draft`.
3. Run the gates; record the measured numbers, the framework commit, model and GPU in the frontmatter's
   `validation` block, with pointers to the artifacts (PR, branch, result files).
4. Set `validated` only when every gate the skill claims has a recorded result.
