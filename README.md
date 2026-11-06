# Petra

**English** | [简体中文](README.zh-CN.md)

Petra is the framework agent for AMD GPUs in open-source LLM inference frameworks, starting with
sglang. It turns one task — an upstream feature to bring to AMD, an AMD user's issue, a red AMD CI
job, a system-level performance gap — into a pull request a maintainer can review: **correct first**
(independent unit gates, accuracy / long-context / stress gates against a same-pattern baseline, a
controlled investigation loop), **then fast** (equal-budget A/B), within the community rules in
[`knowledge/guardrails.md`](knowledge/guardrails.md). Petra proposes; people review, push and merge.

Why it exists and how it maps onto the agreed design: [`docs/design.md`](docs/design.md).

## Modes

| Mode | Task | Phases | Ends with |
|---|---|---|---|
| `feature` | an upstream PR or design to bring to AMD | Setup → Spec → Recon → Design → Implement → (Kernel) → Verify → Performance → Review → PR → Report | branch + PR body + validation report |
| `issue` | an AMD user issue | Setup → Triage → Reproduce → Diagnose (skipped for an existing fix PR) → Implement → (Kernel) → Verify → (Performance) → Review → PR → Report | fix PR, or a conclusion (triaged, not reproduced, fixed on main, diagnosed); always a reply draft |
| `ci` | a red AMD CI job or Failure Tracker cluster | Setup → Classify → Bisect → Implement → (Kernel) → Verify → Review → PR → Report | fix PR, or a handover for flaky/infrastructure failures |
| `perf` | a system-level performance goal for a model and a fixed workload | Setup → Profile → Plan → Implement → (Kernel) → Verify → Performance → Review → PR → Report | PR with a measured win, or the change dropped; kernel-level items go to the kernel back end |
| `scan` | none — collect tasks from upstream commits, AMD issues, CI failures and platform gates (host-sync leads on request) | Collect → Dispatch → Report | a ranked task queue with the task definition that starts each task |

Phases in parentheses run only when they apply: Kernel when there is a kernel hand-off and
`kernel_backend` is not `none`; Performance in issue mode for issues triaged as `performance`.

A task starts from a **task definition** ([`templates/task_definition.md`](templates/task_definition.md)):
the fields `petra.js` takes, the same names every role reads. It can be given as fields, or as a
request in plain words: then an Intake phase runs first and turns the request into a definition,
checking what it can without changing anything (the checkout, the model on this machine, the GPUs,
the issue). A definition that still lacks something its mode needs — the issue, the checkout, the
model for `feature` and `perf`, the fixed workload for `perf` — starts nothing and comes back as
questions, one per field, each with options or a default. A complete definition skips the Intake.

Every implementation runs one work package at a time; an independent test engineer re-runs its unit
test, checks that the test fails without the change, and runs the feature-off check; a package that
keeps failing is rolled back. Verification failures go to an investigator that runs the controls
before any instrumentation and returns a fix, a proof that the failure is pre-existing on the
baseline, or an inconclusive verdict that stops the task. Before the PR, a reviewer reads the diff and
its evidence the way a maintainer would, starting from a catalog of known reward hacks — changes that
move a number while breaking what it meant ([`knowledge/reward_hacks.md`](knowledge/reward_hacks.md));
requested changes, and a test for every confirmed hack, become work packages that go through
Implement and Verify again. Performance numbers count only on the workload fixed at Setup and on the
serving path the task targets, and a gain only if it also holds at a held-out operating point fixed
with the workload ([`knowledge/perf_evaluation.md`](knowledge/perf_evaluation.md) §3).

Kernel-level work — tuning a kernel Petra wrote for a feature, or a kernel-level performance
opportunity — is handed to a **kernel workflow back end** in the Kernel phase between Implement and
Verify ([`knowledge/kernel_backends.md`](knowledge/kernel_backends.md)):

| `kernel_backend` | What happens to a hand-off |
|---|---|
| `none` (default) | recorded in the report with its package; nothing runs |
| `geak` | GEAK's `kernel_workflow/kernel_lane.js` runs it from the GEAK checkout given as `kernel_backend_dir` (nested once, as GEAK's e2e_workflow does) |
| `command` | any other CLI given as `kernel_backend_command` |

A gain comes back as a work package: the implementer integrates it and Petra's own gates judge it. A
back end that fails or finds nothing never blocks the task. An integrated kernel that then fails
Verify goes back to the functional kernel and is handed to the back end once more, with the failing
case added to its tests; it is integrated again only if it passes.

## Roles

Each phase calls a role: an agent that reads `roles/<role>.md`, does its part and returns structured
JSON; `petra.js` holds the schemas and branches only on their required fields. Four rules hold across
the roles:

- only the **implementer** edits framework source, and only in the task's worktree;
- the roles that measure (test engineer, verify engineer, performance engineer), the intake and the
  reviewer never edit framework source; the measuring ones never reuse anyone else's numbers but run
  everything again;
- the **curator** edits only Petra's own `knowledge/` and leaves the edits uncommitted for review;
- no role pushes or posts: the PR engineer returns the exact `git push`, issue replies are drafts.

| Role | Phases | What it does |
|---|---|---|
| `intake` | Intake | turns a request in plain words, or a definition with gaps, into the task definition: decides the mode, fills fields with read-only checks, records defaults as assumptions, asks instead of guessing (a missing source of truth, model or workload, anything that would cost something to obtain), rejects what Petra does not do |
| `director` | Setup, Spec, Report | creates the run directory, task branch and worktree, pins commit, image and GPUs and runs the baseline; writes the feature spec with measurable acceptance criteria; writes the final report for every outcome, with the next step for a human |
| `scout` | Collect | gathers candidate tasks with the scripts below |
| `dispatcher` | Dispatch | sets each candidate's gap type, level, CUDA dependencies with their AMD starting points, effort and priority, and ranks them into a queue |
| `analyst` | Recon | maps every subsystem a feature needs to a file, function and hook in the target framework, and tables which assumptions of the source design hold on AMD; reads only |
| `architect` | Design, Plan | turns the recon or the profile into work packages that can each be tested alone, with invariants, memory budget, synchronization, startup rejections and a test plan; flags designs a human must review; assigns each performance opportunity to Petra, the kernel back end or Hyperloom |
| `issue_triager` | Triage, Reproduce | sets the priority and the action from the issue, its comments and linked PRs; drafts the reply; writes the reproduction that becomes the issue's gate |
| `ci_guardian` | Classify, Bisect | classifies a red job (code regression, dependency bump, test bug, flaky, infrastructure) and hands the last two over; finds and confirms the culprit commit and plans the fix |
| `implementer` | Implement | one work package at a time, smallest diff, neutral with the feature off, HIP-only or behind a switch, committed lint-clean with its tests registered; functional kernels with unit tests (tuning is a hand-off); applies existing PRs and verified kernel gains; rolls back a failed package |
| `test_engineer` | Implement | re-runs each package's unit test on its commit, checks that the test can fail (on the parent commit when the change alters behaviour, on a broken copy when it keeps it) and that behaviour with the feature off is unchanged |
| `verify_engineer` | Verify | runs the correctness gates (G0, G2–G4, composability, the mode's gate) on fresh servers against a same-pattern baseline, classifying and counting every failure |
| `investigator` | Investigate, Diagnose | runs the controls first, then one-mechanism-at-a-time experiments with a hypothesis ledger; returns fix work packages, a known issue the baseline shares, an inconclusive verdict, or (for an issue) a root cause outside the AMD side; probes only behind switches |
| `perf_engineer` | Profile, Performance | checks the run took the intended path, turns a steady-state trace into fixed tables (kernels, overlap, fuse patterns, layers), metrics and opportunities with upper bounds; evaluates changes at equal budget on the fixed workload, against noise, guard workloads and a held-out operating point, checking the known measurement hacks |
| `reviewer` | Review | reads the diff and its evidence as a maintainer would, starting from the catalog of known reward hacks: shapes, dtypes, parallel layouts, graphs, fallbacks, do-no-harm, the framework's conventions, a fair benchmark; requested changes, and a test for every confirmed hack, come back as work packages; can run on another model (`review_model`) |
| `kernel_liaison` | Kernel | turns a kernel hand-off into the back end's task, runs `command` back ends, judges the result on the back end's own verification and returns a gain as a work package |
| `pr_engineer` | PR | changes no code: checks hygiene, lint and CI registration (gaps go back as work packages), arranges one commit per work package without changing the tree, trial-merges main to report conflicts, checks feature off on the final commit, writes the PR body and the push command |
| `curator` | Report | writes what the run proved into `knowledge/` (known issues, feature skills, CUDA → AMD rows, new reward hacks, method lessons), every number traceable to the run |

## Setup

Petra runs inside a ROCm container, as root, the way GEAK does: Claude Code, Petra, git and the
framework's servers and tests all run there, next to the GPUs and the framework's Python environment.
The container is disposable (`scripts/run_docker.sh` starts a new one every time), so everything that
has to last stays on the host under `/home`, mounted at the same path: Claude Code, installed once, its
state, the checkouts and your keys. What a run writes into the checkouts as root goes back to their
owner ([`scripts/restore_owner.sh`](scripts/restore_owner.sh), [`knowledge/env_hygiene.md`](knowledge/env_hygiene.md)),
so git on the host and your `git push` keep working.

Apart from the container, which run_docker.sh replaces by design, every step can be run again: it
checks first, keeps what is already there and adds only what is missing. Nothing is deleted,
overwritten or re-cloned.

### What the host needs

- Linux with AMD Instinct GPUs (MI300 or MI350 series) and the ROCm driver loaded (`/dev/kfd` exists).
- Docker you can run (your user in the `docker` group, or sudo), git, curl, python3 and tmux.
- Network access to claude.ai, github.com and Docker Hub, and about 45 GB of disk per sglang image.
- An AMD LLM gateway key (`LLM_GATEWAY_KEY`), an Anthropic API key or another gateway; without any, a
  Claude subscription to log in with.
- A read-only GitHub token (`GITHUB_TOKEN`), strongly recommended: scans and issue runs read GitHub's
  API.
- Model weights in a directory the container mounts (`/data`, `/mnt`, `/home`, ...): Petra never
  downloads weights.

### 1. Install Claude Code and keep your keys (host)

```bash
command -v claude >/dev/null || [ -x ~/.local/bin/claude ] || curl -fsSL https://claude.ai/install.sh | bash
~/.local/bin/claude --version    # 2.1.177 or later: the first with the Workflow tool petra.js runs in
[ -e ~/.petra_env ] || (umask 077 && echo 'export LLM_GATEWAY_KEY=<your AMD LLM gateway key>' > ~/.petra_env)
(umask 077 && grep -qs GITHUB_TOKEN ~/.petra_env || echo 'export GITHUB_TOKEN=<your GitHub token>' >> ~/.petra_env)
```

The native installer puts Claude Code in `~/.local/bin`, inside your home, which the container mounts;
that is how the container calls it. The host keeps it up to date; the container never updates it.

Put your own values in place of `<your AMD LLM gateway key>` and `<your GitHub token>` before you run
the last two lines: each writes its key only when `~/.petra_env` does not have it yet, so a key is
changed later by editing the file. `~/.petra_env` keeps the keys on the host, readable only by you;
every container loads it.

- **LLM key (required).** With the AMD LLM gateway key, step 3 points Claude Code at the gateway
  (`https://llm-api.amd.com/Unified`, the key in its `Ocp-Apim-Subscription-Key` header), which serves
  the Claude models under their usual names. Outside AMD, write `export ANTHROPIC_API_KEY=sk-ant-...`
  instead, or another gateway (`ANTHROPIC_BASE_URL` with `ANTHROPIC_AUTH_TOKEN` or
  `ANTHROPIC_CUSTOM_HEADERS`). With a Claude subscription, leave the key out and log in at the first
  start (step 4).
- **GitHub token (strongly recommended).** Scans and issue runs read issues, pull requests and CI
  trackers through GitHub's API. Without a token GitHub allows 60 requests an hour and 10 searches a
  minute per IP address, shared with everyone behind the same address, so a scan crawls and can stop
  partway; with one, 5000 requests an hour. Read-only is enough, since Petra never pushes or posts: on
  github.com, Settings → Developer settings → Personal access tokens → Fine-grained tokens, with
  *Public repositories (read-only)* access (a classic token with no scopes also works).

### 2. Start the container (host)

```bash
[ -d ~/Petra/.git ] || git clone https://github.com/At1a8/Petra ~/Petra
tmux new -s petra                # a run takes hours; tmux keeps it through a dropped connection
~/Petra/scripts/run_docker.sh    # NAME defaults to your user name
```

[`scripts/run_docker.sh`](scripts/run_docker.sh) is the usual ROCm `run_docker.sh`: a privileged
container with the GPUs, `/home` and the data directories that exist (`/data`, `/mnt`, ...) mounted at
the same paths, and a root shell in it. Unlike many such scripts it does not mount the host's Docker
socket (`DOCKER_SOCKET=1` does): Petra's agents run as root with permissions auto-approved, and the
socket would put every container on the host within their reach.

- **Image.** Tasks test the newest sglang, so it starts from the newest daily `rocm/sgl-dev` build for
  ROCm 10 and MI35x ([`scripts/latest_image.py`](scripts/latest_image.py), e.g.
  `v0.5.23-rocm10-mi35x-20261103`; the `miles` images on the same page are for reinforcement learning
  and are skipped). A new day's image is pulled at its first use, about 43 GB. On MI30x, set
  `IMAGE_VARIANT=rocm10-mi30x`; for a fixed image, `IMAGE=rocm/sgl-dev:<tag>`.
- **What is tested.** The image provides PyTorch, aiter, sgl-kernel and its own copy of sglang. Petra
  tests the code of the task's worktree, created from the current upstream main, by putting it first on
  `PYTHONPATH`; the run records the image, the image's sglang version and the worktree's base commit.
- **A new container every time.** It removes the previous container of the same name first, and with
  it anything still running there. To get back into a running container, reattach tmux
  (`tmux attach -t petra`) or open a shell in it (`docker exec -it <name> bash`); do not run
  run_docker.sh again. A run_docker.sh of your own works too, as long as it mounts `/home` at the same
  path.

`claude` is not callable yet: the host's binary is in the container through the `/home` mount, but not
on root's `PATH` (`claude: command not found`). Step 3 links it; nothing is installed in the container.

### 3. Install Petra (inside the container, in every new container)

```bash
cd /home/<you>/Petra && python3 -B -m petra.bootstrap --framework-dir /home/<you>/sglang
source ~/.bashrc
claude --version    # the host's Claude Code
```

| Step | In a new container |
|---|---|
| `claude` | a link `/usr/local/bin/claude` to the host's `/home/<you>/.local/bin/claude`; Claude Code is installed in the container only when the host has none |
| Claude Code state | kept on the host in `/home/<you>/.petra/claude` (`CLAUDE_CONFIG_DIR`, apart from your own `~/.claude`): the first-start answers and a `/login` outlive the container |
| git | trusts the mounted checkouts, which belong to you, not root (`safe.directory '*'`) |
| shell | root's `~/.bashrc` gets `PYTHONDONTWRITEBYTECODE=1` (no root-owned `__pycache__` in your checkouts), `DISABLE_AUTOUPDATER=1` (the host updates Claude Code) and loads `/home/<you>/.petra_env`; with `LLM_GATEWAY_KEY` and no `ANTHROPIC_BASE_URL`, it points Claude Code at the AMD LLM gateway |
| framework (`--framework-dir`) | an existing checkout is used as it is (a shallow one is reported, not deepened); a missing one is cloned with its whole history (`--filter=blob:none`) and given to you |
| checks | GPUs, sglang, API access, `GITHUB_TOKEN`, counting what `~/.petra_env` sets (detect only) |

`python3 -B` keeps this first run from writing root-owned `__pycache__` into the checkout. The command
never writes keys.

### 4. Start Claude Code and give it a task (inside the container)

```bash
cd /home/<you>/Petra && IS_SANDBOX=1 claude --dangerously-skip-permissions
```

`IS_SANDBOX=1` lets Claude Code auto-approve permissions as root, which Petra's agents need. The very
first start asks a few questions; the answers are kept in `/home/<you>/.petra/claude`, so later
containers skip them. Three of the defaults would stop you:

| Question | Answer |
|---|---|
| Do you want to use this API key? (asked only for an `ANTHROPIC_API_KEY`; the gateway key is not) | **Yes**; the default, No, asks you to log in instead |
| Is this a project you trust? | **Yes, I trust this folder**; the default exits |
| Bypass Permissions mode | **Yes, I accept**; the default exits |

Without a key, pick a login method instead and log in once. Then ask:

```
use /home/<you>/Petra/petra.js with mode=scan, petra_dir=/home/<you>/Petra,
framework_dir=/home/<you>/sglang
```

The scan changes no code. It collects open AMD issues, red AMD CI, CUDA-first upstream changes and
hardware gaps since the last scan (else the last 7 days), ranks them, and writes
`exp/scan_<time>/task_queue.md` with the task definition that starts each task. To take one task,
stopping after the reproduction to confirm the environment, name its fields:

```
use /home/<you>/Petra/petra.js with mode=issue, task=https://github.com/sgl-project/sglang/issues/41299,
petra_dir=/home/<you>/Petra, framework_dir=/home/<you>/sglang, model_path=<weights>,
gpu_ids=0, stop_after=Reproduce
```

or say it in plain words and let the Intake phase write the definition:

```
use /home/<you>/Petra/petra.js with petra_dir=/home/<you>/Petra, request="DeepSeek-V4.1 decode
is slow on MI355X, make it faster; my sglang is /home/<you>/sglang"
```

When something is missing (here: which fixed workload every measurement uses), the run starts
nothing and returns `status: needs_input` with one question per field. Answer them in the chat;
Claude Code runs `petra.js` again with the same arguments plus `answers={"workload": ...}`.
[Running it](#running-it) lists all arguments.

### 5. After a run (host)

A run that got past Setup leaves its report in its run directory under `/home/<you>/Petra/exp/` (`validation_report.md`
when a PR is ready, `report.md` for any other outcome; the result names it as `report_path`), next to
the task's worktree and branch, and what root wrote there is yours again. Petra never pushes: the
report lists the PR body and the exact `git -C <worktree> push ...`. Run it on the host, where your git
credentials are.

### Re-running and options

Each step of `petra.bootstrap` reports `kept`, `installed`, `updated`, `added`, `created`, `skipped` or
`failed`; a summary lists them, the next steps list only what is still missing, and the exit code is 1
when a step failed. In a new container it re-creates the link and the git, shell and Claude Code state
settings in seconds and installs nothing. `--claude-only` runs only the Claude Code steps, `--check`
only the checks. Inside a container, `cd /home/<you> && pip install -v git+https://github.com/At1a8/Petra` runs
step 3 the GEAK way (pip shows the output only with `-v`; a cached wheel skips it).

| Variable | Used by | Default |
|---|---|---|
| `IMAGE` | `scripts/run_docker.sh` | the newest daily `rocm/sgl-dev` image of `IMAGE_VARIANT` (the newest local one when Docker Hub cannot be reached) |
| `IMAGE_VARIANT`, `NAME`, `EXTRA_MOUNTS` | `scripts/run_docker.sh` | `rocm10-mi35x`; your user name; more directories to mount, space-separated |
| `DOCKER_SOCKET` | `scripts/run_docker.sh` | unset; `1` also mounts the host's Docker socket and `docker` |
| `PETRA_LOCK_FILE` | `scripts/run_lock.py` | `/dev/shm/petra-run.lock`, the machine's one-task lock |
| `PETRA_HOME` | bootstrap | `./Petra`, or the checkout you run from |
| `PETRA_REPO_URL`, `PETRA_REF` | bootstrap | `https://github.com/At1a8/Petra.git`, its default branch |
| `CLAUDE_VERSION`, `CLAUDE_BIN_DIR` | bootstrap | `latest`, `~/.local/bin` |
| `CLAUDE_CONFIG_DIR` | bootstrap, Claude Code | `/home/<you>/.petra/claude` for root in the container; when already set, used as it is |
| `LLM_GATEWAY_KEY` | `~/.petra_env`, the container's shell settings | unset; set, Claude Code runs on the AMD LLM gateway unless `ANTHROPIC_BASE_URL` names another |
| `PETRA_FRAMEWORK_DIR`, `PETRA_FRAMEWORK_REPO` | bootstrap: `--framework-dir`, `--framework-repo` | none (step skipped); sglang |
| `PETRA_SKIP_BOOTSTRAP` | bootstrap | unset; set it to install the package with no side effects (CI, images) |

## Running it

Petra is a GEAK-style workflow: `petra.js` holds the control flow, `roles/` the agent instructions,
`knowledge/` the method, `templates/` the artifacts. In Claude Code, name `petra.js` and its arguments
in one sentence, as in [step 4](#4-start-claude-code-and-give-it-a-task-inside-the-container). GEAK is needed in two cases
only: the `geak` kernel back end (`kernel_backend_dir`), and running `petra.js` outside Claude Code,
which uses GEAK's workflow runtime (Node 20+; also what the dry run uses):

```bash
node /path/to/GEAK/interface/runtime/engine/run_workflow.mjs petra.js --agent codex \
  --args '{"mode":"scan","petra_dir":"'"$PWD"'","framework_dir":"/path/to/sglang"}'
```

| Argument | Meaning |
|---|---|
| `petra_dir` | absolute path of this checkout (required) |
| `request` | the task in plain words, any language; the Intake phase turns it into the fields below (`roles/intake.md`), and fields given with it win |
| `answers` | replies to a `needs_input` result, `{"<field>": <value>}`, passed with the same arguments as before |
| `mode` | `feature` \| `issue` \| `ci` \| `perf` \| `scan` (required; inferred from `request` when not given) |
| `task` | the upstream PR/design, issue URL, CI job/cluster or performance goal (required except `scan`) |
| `goal` | what done means, measurable when the mode measures; the spec and the performance plan address it |
| `framework_dir` | the framework checkout; Petra works in a worktree of it (required except `scan`) |
| `model_path` | the model the baseline and the gates run (required for `feature` and `perf`) |
| `framework`, `platform`, `gpu_ids` | target and environment (`sglang`; empty `gpu_ids` lets Setup pick idle GPUs, which every later role then uses through `HIP_VISIBLE_DEVICES`) |
| `workload` | the benchmark every measurement uses, e.g. `{"isl":8192,"osl":1024,"conc":64}`; required for `perf`, fixed at Setup |
| `container` | only when Petra runs on the host: the framework's container, reached with `docker exec` |
| `exp_root` | where run directories go (default `<petra_dir>/exp`) |
| `kernel_backend` | `none` (default) \| `geak` \| `command`: where kernel hand-offs go |
| `kernel_backend_dir` | `geak` back end: the GEAK checkout providing `kernel_workflow/kernel_lane.js` |
| `kernel_backend_command` | `command` back end: shell command with `{task_dir}`, `{out_dir}`, `{gpu_ids}` |
| `kernel_budget` | optimization rounds for the kernel back end (default 6) |
| `apply_prs` | `perf`: candidate PRs to apply and A/B |
| `sources`, `since` | `scan`: any of `upstream`, `issues`, `ci`, `hardware`, `perf`; the start of the window |
| `stop_after` | stop after the named phase of the mode (e.g. `Design`, `Reproduce`); a phase the mode does not run comes back as a question |
| `resume_from`, `run_dir` | `feature`: `implement` continues a run that stopped at Design once a human approved `design.md` |
| `review_model` | the reviewer's model, passed with its agent call (GEAK's runtime takes a model per call; elsewhere it depends on the runtime) |
| `max_fix_rounds`, `max_investigate_rounds`, `max_review_rounds`, `max_work_packages` | budgets |
| `agent_retries`, `agent_timeout_ms` | an agent call is retried after an error (the retry checks what the failed attempt left), never after a timeout: the timed-out agent may still be running, so it goes on the report's attention list. Default timeout 3 h, 6 h for the verify and performance engineers and the investigator |

Everything but `petra_dir`, `request`, `answers`, `exp_root`, `review_model` and the budgets is the task
definition; the result of every run that started records the definition it used (`task_def`), where
each field came from (`provenance`) and the intake's `assumptions`.

Human checkpoints: questions from the Intake (`needs_input`); any `stop_after`; L3 tasks and designs
the architect flags stop at Design (`awaiting_design_review`); a review the reviewer marks `blocked`
stops before the PR; the PR engineer returns the exact `git push` instead of pushing; issue replies
are drafts in the run directory. A run that has its run directory ends with a report, whatever its
status; one that ends at the Intake (questions, a rejection) or before Setup created its directory
(`busy`) returns only its result.

**One task per machine.** A run takes the machine before it creates anything — a lock in `/dev/shm`,
which every container started with `--ipc=host` shares with the host and no other machine sees — and
frees it at the end of its report. While another task holds it, a new run ends at once as `busy` and
names the holder. A lock whose run finished, or wrote nothing in its run directory for twice its
longest agent call (12 h by default), is taken over by the next run; one left by a run that died is
freed at once:

```bash
python3 scripts/run_lock.py status            # who holds this machine
python3 scripts/run_lock.py release --force   # free it after that run died
```

The framework's own skills (sglang's `.agents/skills/`) are referenced in place, never copied: each
role reads the ones [`knowledge/frameworks/sglang/skills.md`](knowledge/frameworks/sglang/skills.md)
lists for it from the task worktree, so they match the code it changes, with ROCm differences in
[`knowledge/platforms/rocm_skills.md`](knowledge/platforms/rocm_skills.md).

## Scripts

Standard-library Python; the GitHub ones read `GITHUB_TOKEN` or `GH_TOKEN` (step 1; without a token
GitHub allows 60 requests an hour and 10 searches a minute per IP address).

| Script | Source of tasks |
|---|---|
| `scripts/scan_issues.py` | open AMD issues with linked PRs, replies and the projected 60-day auto-close date |
| `scripts/scan_ci.py` | Failure Tracker state → failure clusters with statuses and since dates |
| `scripts/scan_upstream.py` | merged upstream commits: new CUDA gates, CUDA-first features, new models |
| `scripts/audit_platform_gates.py` | platform gates to re-check on a new architecture (capability checks true on gfx1250, wave32 assumptions) |
| `scripts/audit_host_syncs.py` | host-device sync and copy candidates on the hot path (leads for a profile) |

`scripts/restore_owner.sh` (POSIX sh) gives what root wrote in the container back to the owner of the
checkout it lives in; every agent runs it after a git write ([`knowledge/env_hygiene.md`](knowledge/env_hygiene.md)).
`scripts/check_framework_skills.py --framework-dir <dir>` checks the skills index against a framework
checkout: skills it names that are gone, and new ones it does not name yet (the scout runs it on every
scan). `scripts/latest_image.py [--variant rocm10-mi30x]` prints the newest daily sglang image
(`run_docker.sh` starts from it; the director compares a run's image with it). `scripts/run_lock.py`
keeps one Petra task per machine (`acquire`, `release`, `status`).

## Tests

```bash
GEAK_HOME=/path/to/GEAK node tests/dry_run.mjs   # every control path of petra.js on GEAK's runtime, no GPU
python3 -m unittest discover -s tests             # the scripts' parsers and rules, the bootstrap, the two READMEs in step; offline
```

## Layout

```
Petra/
├── petra.js                 # orchestration: five modes, gates, budgets, rollback, kernel back ends
├── roles/                   # intake, director, scout, dispatcher, analyst, architect, implementer,
│                            # test_engineer, verify_engineer, investigator, perf_engineer, issue_triager,
│                            # ci_guardian, kernel_liaison, reviewer, pr_engineer, curator
├── knowledge/
│   ├── dev_methodology.md   # phases, artifacts, gates (the contract)
│   ├── validation_doctrine.md, debugging_playbook.md, perf_evaluation.md, env_hygiene.md, pr_playbook.md
│   ├── guardrails.md        # safety constraints and community conduct
│   ├── reward_hacks.md      # changes that move a number while breaking what it meant: tell, killed by
│   ├── dispatch.md, issue_triage.md, ci_triage.md, system_perf.md, composability.md, kernel_backends.md
│   ├── frameworks/sglang/feature_dev_map.md, platforms/rocm.md, known_issues.md
│   ├── frameworks/sglang/skills.md, platforms/rocm_skills.md   # sglang's own skills: index + ROCm notes
│   └── feature_skills/      # validated plans per feature (hisparse-v2 first)
├── templates/               # task_definition, feature_spec, design, experiment_ledger, validation_report,
│                            # pr_body, issue_triage, ci_triage, perf_analysis, task_queue
├── scripts/                 # task collection, audits, run_docker.sh, latest_image.py, run_lock.py,
│                            # restore_owner.sh
├── petra/bootstrap.py       # setup step 3, in the container; safe to re-run
├── setup.py, pyproject.toml # packaging; setup.py runs the bootstrap when pip builds the wheel
├── tests/                   # dry run of petra.js, unit tests of the scripts, the bootstrap and the READMEs
├── README.md, README.zh-CN.md
└── docs/design.md
```

## Relationship to GEAK and Hyperloom

- A kernel's speed is the kernel workflow's job, on whichever back end is selected (GEAK's kernel lane
  is one): Petra writes a functional kernel with a unit test, hands over the op spec with the reference
  as the oracle, and integrates a verified gain.
- Flag and backend searches for a workload belong to Hyperloom and GEAK `e2e_workflow`; their upstream
  candidates are Petra inputs, and features Petra lands become their options.

## Origin

The method, validation doctrine, known-issue register, templates and the HiSparse V2 feature skill come
from GEAK's `framework_workflow` (branch `fangyuan/framework_agent_init`, commit `fc857c9`), which was at
its knowledge-first phase. Petra adds the orchestration that was planned there, the roles, the issue /
CI / performance / scan entry points from the design, and the task-collection scripts.
