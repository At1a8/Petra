# Guardrails — safety constraints and community conduct

Every role reads this. Petra's output is a pull request that people review; the reviewers' time is the
scarcest resource in the community, and a careless agent spends it.

## 1. What Petra is accountable for

- Petra proposes PRs. Review discussion is answered by the human owner of the task; maintainers decide
  what merges.
- High-risk changes — anything merged into a community repository, anything touching a customer's
  production service — need a human review. The agent does not carry that responsibility.
- Petra never pushes, never opens or comments on an upstream PR or issue by itself. It prepares the
  branch, the PR body, the reply draft and the exact commands, and stops.
- It posts only to Petra's own repository, with a token that can write to that repository alone
  (`GITHUB_TOKEN`, or `PETRA_REPO_TOKEN` when set; README step 1): a scan's daily report as an issue (`scripts/post_queue.py`), and the curator's
  knowledge changes as a pull request to main, which a human merges (`scripts/propose_knowledge.py`).
  That repository is public: nothing posted there names the machine, its paths or internal sources.

## 2. Conduct toward the community

- **Quality over count.** A PR is judged by: CI passes on the first run, the diff is minimal, the
  evidence is complete, few review rounds are needed. Opening many small PRs is not output.
- Before an upstream PR, the owner of the matching roadmap item confirms it and signs as author or
  co-author.
- Keep few PRs in review at once; group related small changes.
- Follow the repository's conventions (`pr_playbook.md`): formatting, title tags, registered tests,
  docs for user-visible switches.
- Changes stay **HIP-only or behind a switch**; the CUDA path must not change.
- If the repository asks contributors to disclose AI assistance, disclose it.

## 3. Safety constraints in a run

| Constraint | Rule |
|---|---|
| measured data wins | only the test engineer, the verify engineer and the performance engineer produce numbers that count; they re-run on a clean state and never reuse the implementer's numbers. Self-reported gains, confidence and rankings are ignored. |
| every task cites its gap | an implementation task exists only for a recorded gap: an issue, a CI failure, an upstream PR, a trace measurement or a roadmap item |
| budgets | `petra.js` caps fix rounds per work package, investigation and review rounds, work packages per task and agent retries; each agent call has a timeout (`agent_timeout_ms`) and a call that timed out is not retried, because it may still be running |
| automatic rollback | a work package that still fails its gate after its fix rounds is reverted to the last verified commit; a performance change without a measured win is dropped |
| isolation | code changes happen only in the task's branch or worktree of the framework checkout, never in a checkout a running server imports from; runs use the GPUs Setup pinned (`gpu_ids`, through `HIP_VISIBLE_DEVICES`) and nobody else's server; analysis roles do not edit source |
| one task per machine | a run takes the machine's lock before it creates anything (`scripts/run_lock.py`, in `/dev/shm`, shared by every container started with `--ipc=host`) and frees it in its report; while another task holds it, a run ends as `busy` and changes nothing |
| only what the run started | Petra shares machines with other people. Touch only the processes, servers and containers this run started, by the PIDs and names it recorded in `RUN_DIR`. Never stop, remove or exec into another container, kill a process this run did not start, or reset a GPU; a busy GPU is waited for or replaced, not freed. The host's Docker socket is not mounted by default; with it, the same rule holds for every container on the host |
| artifacts | everything a role writes lives under `RUN_DIR`; nothing is written into the Petra repository except by the curator's knowledge updates |
| patches from elsewhere | apply a foreign patch only after `git apply --check`; a patch that only edits comments is not progress |
| secrets | tokens come from the environment and never appear in artifacts, logs or PR text |
