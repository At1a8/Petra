export const meta = {
  name: 'petra',
  description: 'Petra: the framework agent for open-source LLM inference frameworks on AMD GPUs (sglang first). It turns one task (an upstream feature to bring to AMD, an AMD user issue, a red AMD CI job, a system-level performance gap) into a verified, reviewable pull request: correct first (independent unit gates, G0-G4 against a same-pattern baseline, an investigation loop with controls), then fast (equal-budget G5), within the community rules of knowledge/guardrails.md. mode=scan writes the day\'s report on the framework (the AMD CI on main, user issues by priority, upstream changes AMD needs to follow) and ranks the tasks in it, changing no code. Petra never pushes and never posts upstream: it prepares the branch, the PR body and the reply drafts for a human; it posts only to its own repository: a scan\'s daily report as an issue, and the knowledge a run proved as a pull request for a human to merge.',
  whenToUse: 'Pass args.petra_dir (absolute path of the Petra checkout, required) and the task, either as args.request (the user\'s words, any language; the Intake phase turns it into a task definition) or as the task-definition fields of templates/task_definition.md: args.mode (feature | issue | ci | perf | scan), args.task (the upstream PR or design, issue URL, CI job or tracker cluster, or performance goal), args.framework_dir (the framework checkout; for sglang the image\'s /sgl-workspace/sglang by default), args.model_path (required for feature and perf), args.workload (required for perf: the fixed benchmark every measurement uses), args.goal (what done means), args.framework (default sglang), args.platform, args.gpu_ids, args.container, args.apply_prs (perf), args.sources, args.since, args.upstream_repos and args.rescan (scan: a report from the last 24 hours makes the run ask before scanning again), args.stop_after (a phase title), args.resume_from="implement" with args.run_dir (feature: continue after a human approved design.md), args.kernel_backend (none | geak | command) with args.kernel_backend_dir (geak) or args.kernel_backend_command (command), args.kernel_budget. A definition that lacks something its mode needs returns status=needs_input with questions and starts nothing: answer them and run again with the same args plus args.answers ({"<field>": <value>}). Operator settings: args.exp_root, args.review_model (the reviewer\'s model, where the runtime takes one per call), args.max_fix_rounds, args.max_investigate_rounds, args.max_review_rounds, args.max_work_packages, args.agent_retries, args.agent_timeout_ms.',
  phases: [
    { title: 'Intake', detail: 'intake: turn a request, or a definition with gaps, into a complete task definition; questions when something is missing' },
    { title: 'Setup', detail: 'director: run dir, the task\'s branch in the framework checkout, launch scripts, baseline (not in scan)' },
    { title: 'Spec', detail: 'director: feature_spec.md with measurable acceptance criteria [feature]' },
    { title: 'Recon', detail: 'analyst: code map and assumption table, gap type and level [feature]' },
    { title: 'Design', detail: 'architect: work packages, invariants, memory budget, startup rejections [feature]' },
    { title: 'Triage', detail: 'issue_triager: state checks, P0/P1/P2, action, reply draft [issue]' },
    { title: 'Reproduce', detail: 'issue_triager: reproduce on the reporter configuration [issue]' },
    { title: 'Diagnose', detail: 'investigator: root cause and fix work packages [issue]' },
    { title: 'Classify', detail: 'ci_guardian: code regression / dependency bump / test bug / flaky / infrastructure [ci]' },
    { title: 'Bisect', detail: 'ci_guardian: culprit commit, confirmation, fix work packages [ci]' },
    { title: 'Profile', detail: 'perf_engineer: trace metrics and the opportunity list [perf]' },
    { title: 'Plan', detail: 'architect: performance work packages, kernel hand-offs, PRs to apply [perf]' },
    { title: 'Implement', detail: 'implementer per work package, independent test_engineer unit + feature-off gate, rollback on failure' },
    { title: 'Kernel', detail: 'kernel_liaison: kernel hand-offs to args.kernel_backend (none records; geak runs GEAK kernel_lane; command runs a CLI); gains integrated as work packages' },
    { title: 'Verify', detail: 'verify_engineer: G0-G4 against the same-pattern baseline plus mode gates; investigator loop on failure' },
    { title: 'Investigate', detail: 'investigator: controls first, hypothesis ledger, fix or baseline bug' },
    { title: 'Performance', detail: 'perf_engineer: G5 equal-budget A/B and guard workloads' },
    { title: 'Review', detail: 'reviewer: independent review of the diff and its evidence; requested changes come back as work packages' },
    { title: 'PR', detail: 'pr_engineer: hygiene, lint, upstream sync, pr_body.md, exact push command; never pushes' },
    { title: 'Collect', detail: 'scout: the AMD CI on main, user issues, upstream changes (platform gates, host syncs on request) -> candidates; asks first when a report from the last 24 hours exists [scan]' },
    { title: 'Dispatch', detail: 'dispatcher: type, level, priority, dependencies, effort, ranking, ecosystem-matrix changes -> the daily report [scan]' },
    { title: 'Report', detail: 'director: final report for every outcome of a run that has its run directory (a scan also posts its daily report as an issue in Petra\'s own repository), then frees the machine; curator: knowledge updates, proposed as a pull request to Petra\'s own repository' },
  ],
};

// ---------------------------------------------------------------------------
// Arguments. Control flow (phase order, retries, gates, budgets) lives here;
// agents are called only for judgement and for the work itself, and every agent
// returns structured JSON whose gate fields this script reads.
// ---------------------------------------------------------------------------
const RAW = args || {};
const MODES = ['feature', 'issue', 'ci', 'perf', 'scan'];
// Kernel back ends: where kernel-level work goes (tuning a kernel Petra wrote for a feature, or a
// kernel-level performance opportunity). knowledge/kernel_backends.md describes the contract.
//   none     record the hand-off package in the report and run nothing (default)
//   geak     GEAK's single-language kernel lane from the checkout args.kernel_backend_dir, nested once
//            like GEAK's own e2e_workflow does; the only place Petra uses GEAK
//   command  any other CLI, run by the kernel liaison from args.kernel_backend_command
const KERNEL_BACKENDS = ['none', 'geak', 'command'];
const PETRA = String(RAW.petra_dir || '').replace(/\/+$/, '');
if (!PETRA) {
  throw new Error('args.petra_dir is required: absolute path of the Petra checkout ' +
    '(the directory containing petra.js, roles/, knowledge/ and templates/)');
}

const int = (v, d) => {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n >= 0 ? n : d;
};
const AGENT_RETRIES = Math.max(1, int(RAW.agent_retries, 3));
const TIMEOUT_GIVEN = RAW.agent_timeout_ms != null && String(RAW.agent_timeout_ms).trim() !== '';
const AGENT_TIMEOUT_MS = int(RAW.agent_timeout_ms, 3 * 3600 * 1000);
// Roles that run whole suites or benchmarks get twice the default, unless a timeout is given.
const LONG_ROLES = new Set(['verify_engineer', 'perf_engineer', 'investigator']);
const timeoutFor = (role) => (!TIMEOUT_GIVEN && LONG_ROLES.has(role) ? 2 * AGENT_TIMEOUT_MS : AGENT_TIMEOUT_MS);
// One task per machine (scripts/run_lock.py): a run that wrote nothing in its run directory for twice
// its longest agent call has died, and its lock may be taken over.
const MAX_CALL_MS = TIMEOUT_GIVEN ? AGENT_TIMEOUT_MS : 2 * AGENT_TIMEOUT_MS;
const LOCK_IDLE_HOURS = MAX_CALL_MS > 0 ? Math.ceil((2 * MAX_CALL_MS) / 3600000) : 24;
const ATTENTION = []; // state a human must clean up before anything else runs there (R.attention)
const TIMED_OUT = { timedOut: true };
let PHASE = '';
const cfg = (o) => Object.entries(o)
  .filter(([, v]) => v !== '' && v != null && !(Array.isArray(v) && v.length === 0))
  .map(([k, v]) => `- ${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
  .join('\n');

// ---------------------------------------------------------------------------
// Structured outputs. The role files describe every field; these schemas keep
// the fields this script branches on mandatory.
// ---------------------------------------------------------------------------
const S = (props, required) => ({ type: 'object', properties: props, required: required || [] });
const str = { type: 'string' };
const bool = { type: 'boolean' };
const num = { type: 'number' };
const obj = { type: 'object' };
const arr = (items) => (items ? { type: 'array', items } : { type: 'array' });
const strs = arr(str);

// ---------------------------------------------------------------------------
// The task definition (templates/task_definition.md): the fields that define a task, named as the
// arguments are. A request in plain words, or a definition with gaps, becomes a complete one in the
// Intake phase before anything runs; operator settings (petra_dir, exp_root, budgets, review_model)
// stay outside it.
// ---------------------------------------------------------------------------
const TASK_KEYS = ['mode', 'task', 'goal', 'framework', 'framework_dir', 'model_path', 'platform', 'gpu_ids',
  'container', 'workload', 'apply_prs', 'sources', 'since', 'stop_after', 'resume_from', 'run_dir',
  'kernel_backend', 'kernel_backend_dir', 'kernel_backend_command', 'kernel_budget', 'rescan', 'upstream_repos'];
// '' is accepted for the enums so an undecided field costs no schema retry; pick() drops it.
const TASK_DEF = S({
  mode: { type: 'string', enum: [...MODES, ''] },
  task: str,
  goal: str,
  framework: str,
  framework_dir: str,
  model_path: str,
  platform: str,
  gpu_ids: str,
  container: str,
  workload: { type: ['object', 'string'] },
  apply_prs: strs,
  sources: strs,
  since: str,
  stop_after: str,
  resume_from: str,
  run_dir: str,
  kernel_backend: { type: 'string', enum: [...KERNEL_BACKENDS, ''] },
  kernel_backend_dir: str,
  kernel_backend_command: str,
});
const INTAKE = S({
  status: { type: 'string', enum: ['ready', 'needs_input', 'rejected'] },
  task_def: TASK_DEF,
  provenance: obj,
  assumptions: strs,
  questions: arr(S({ field: str, question: str, why: str, options: arr(), default: {} }, ['field', 'question', 'why'])),
  reason: str,
  summary: str,
}, ['status', 'task_def', 'questions']);

const pick = (o, keys) => Object.fromEntries(keys.filter((k) => o && o[k] != null && o[k] !== '').map((k) => [k, o[k]]));
const asObject = (v) => {
  if (v && typeof v === 'object') return v;
  try {
    const o = JSON.parse(String(v || ''));
    return o && typeof o === 'object' ? o : {};
  } catch (e) {
    return {};
  }
};
const TASK_PROMPTS = {
  feature: 'Which upstream PR, design or paper should be brought to AMD (URL)?',
  issue: 'Which issue (URL or <repo>#<n>)?',
  ci: 'Which CI job or Failure Tracker cluster (URL, or tracker issue and cluster)?',
  perf: 'Which performance goal (model, metric, target)?',
};

// The phases each mode can stop after; a stop_after outside them would be ignored and the task would
// run to its end.
const STOP_PHASES = {
  feature: ['Setup', 'Spec', 'Recon', 'Design', 'Implement', 'Kernel', 'Verify', 'Performance', 'Review'],
  issue: ['Setup', 'Triage', 'Reproduce', 'Diagnose', 'Implement', 'Kernel', 'Verify', 'Performance', 'Review'],
  ci: ['Setup', 'Classify', 'Bisect', 'Implement', 'Kernel', 'Verify', 'Review'],
  perf: ['Setup', 'Profile', 'Plan', 'Implement', 'Kernel', 'Verify', 'Performance', 'Review'],
  scan: ['Collect'],
};

// What a definition still lacks before its mode can start; every gap is a question for the user.
function missingFields(a) {
  const qs = [];
  const ask = (field, question, why, options) => qs.push({ field, question, why, ...(options ? { options } : {}) });
  const mode = String(a.mode || '').trim().toLowerCase();
  if (!MODES.includes(mode)) {
    ask('mode', 'Which kind of task is this?', 'every phase after Intake depends on the mode', MODES);
    return qs;
  }
  if (mode !== 'scan' && !a.task) ask('task', TASK_PROMPTS[mode], 'it is the source of truth the run works from');
  if (mode !== 'scan' && !a.framework_dir) {
    ask('framework_dir', 'Which framework checkout should Petra take the code from (absolute path)?',
      'Setup clones the task\'s own working copy from it');
  }
  if ((mode === 'feature' || mode === 'perf') && !a.model_path) {
    ask('model_path', 'Which model should the baseline and the gates run (local path)?', 'Setup runs the baseline on it');
  }
  if (mode === 'perf' && !a.workload) {
    ask('workload', 'Which fixed workload should every measurement use (input/output lengths, concurrency, dataset)?',
      'performance numbers count only on a workload fixed before any profile is read');
  }
  const kb = String(a.kernel_backend || 'none').trim().toLowerCase();
  if (!KERNEL_BACKENDS.includes(kb)) {
    ask('kernel_backend', 'Where should kernel hand-offs go?', 'the Kernel phase runs the chosen back end', KERNEL_BACKENDS);
  }
  if (kb === 'geak' && !a.kernel_backend_dir) {
    ask('kernel_backend_dir', 'Where is the GEAK checkout (absolute path)?', 'the geak back end runs its kernel_workflow/kernel_lane.js');
  }
  if (kb === 'command' && !a.kernel_backend_command) {
    ask('kernel_backend_command', 'Which command runs a kernel task (with {task_dir}, {out_dir} and {gpu_ids})?',
      'the command back end runs it for every kernel hand-off');
  }
  const resume = String(a.resume_from || '').trim().toLowerCase();
  if (resume && !(mode === 'feature' && resume === 'implement')) {
    ask('resume_from', 'resume_from supports only "implement" in mode=feature: drop it, or is this a feature run?',
      'only an approved feature design can be resumed', ['implement']);
  }
  if (resume && !a.run_dir) ask('run_dir', 'Which run stopped at Design (its run directory)?', 'the resumed run continues in it');
  const stop = String(a.stop_after || '').trim().toLowerCase();
  if (stop && !STOP_PHASES[mode].some((p) => p.toLowerCase() === stop)) {
    ask('stop_after', `After which phase of mode=${mode} should the run stop?`,
      `"${a.stop_after}" is not a phase of this mode; the run would ignore it and go on to the end`, STOP_PHASES[mode]);
  }
  return qs;
}

// Fields the caller set win over answers, answers over what the intake inferred; the same completeness
// check then applies to every definition, from a request or not. Nothing runs before it passes.
async function intakeStage(raw) {
  const request = String(raw.request || '').trim();
  const given = pick(raw, TASK_KEYS);
  const answers = pick(asObject(raw.answers), TASK_KEYS);
  if (!request && missingFields({ ...answers, ...given }).length === 0) return { args: { ...raw, ...answers, ...given } };
  enter('Intake');
  const res = await call('intake', 'define', { request, given, answers, petra_dir: PETRA }, INTAKE, 'intake');
  const merged = { ...(res && res.task_def ? pick(res.task_def, TASK_KEYS) : {}), ...answers, ...given };
  const asked = res && res.status === 'needs_input' ? (res.questions || []) : [];
  const questions = [...asked, ...missingFields(merged).filter((q) => !asked.some((a) => a.field === q.field))];
  const provenance = (res && res.provenance) || {};
  const assumptions = (res && res.assumptions) || [];
  const stopped = (status, summary, extra) => {
    log(`[petra] intake: ${status} — ${summary}`);
    return { record: { mode: String(merged.mode || ''), status, stopped_at: 'Intake', run_dir: '', report_path: '',
      summary, task_def: merged, provenance, assumptions,
      phases: [{ phase: 'Intake', verdict: status, summary }], ...extra } };
  };
  if (res && res.status === 'rejected') {
    const why = res.reason || res.summary || 'outside what Petra does';
    return stopped('rejected', why, { reason: why });
  }
  if (questions.length) {
    return stopped('needs_input', `missing: ${questions.map((q) => q.field).join(', ')}`, {
      questions,
      next: 'answer the questions, then run petra.js again with the same arguments plus answers={"<field>": <value>}',
    });
  }
  return {
    args: { ...raw, ...merged },
    note: { phase: 'Intake', verdict: 'ready', summary: res ? (res.summary || 'task defined') : 'the intake returned nothing; started from the given fields' },
    provenance,
    assumptions,
  };
}

// sglang images carry a full-history checkout of sglang and install sglang from it in editable mode; each
// task works in it on its own branch, so what runs is what is checked out.
const IMAGE_SGLANG = '/sgl-workspace/sglang';
const START = await intakeStage(!RAW.framework_dir && String(RAW.framework || 'sglang').trim().toLowerCase() === 'sglang'
  ? { ...RAW, framework_dir: IMAGE_SGLANG } : RAW);
if (START.record) return START.record;
const A = START.args;
const MODE = String(A.mode).trim().toLowerCase();
const MAX_FIX_ROUNDS = int(A.max_fix_rounds, 2);          // extra implement rounds per work package
const MAX_INVESTIGATE = int(A.max_investigate_rounds, 3); // verify -> investigate -> verify cycles
const MAX_REVIEW = int(A.max_review_rounds, 2);           // review -> fix -> verify -> review cycles
const REVIEW_MODEL = String(A.review_model || '').trim();
const MAX_WPS = Math.max(1, int(A.max_work_packages, 12));
const STOP_AFTER = String(A.stop_after || '').trim().toLowerCase();
const RESUME = String(A.resume_from || '').trim().toLowerCase();
const EXP_ROOT = String(A.exp_root || `${PETRA}/exp`).replace(/\/+$/, '');
const KERNEL_BACKEND = String(A.kernel_backend || 'none').trim().toLowerCase();
const KERNEL_BACKEND_DIR = String(A.kernel_backend_dir || '').replace(/\/+$/, '');

// Context handed to every agent; artifact paths are added as phases produce them.
const C = {
  mode: MODE,
  task: A.task ? (typeof A.task === 'string' ? A.task : JSON.stringify(A.task)) : '',
  petra_dir: PETRA,
  exp_root: EXP_ROOT,
  framework: String(A.framework || 'sglang'),
  framework_dir: String(A.framework_dir || ''),
  model_path: String(A.model_path || ''),
  platform: String(A.platform || ''),
  gpu_ids: String(A.gpu_ids || ''),
  container: String(A.container || ''),
  workload: A.workload ? (typeof A.workload === 'string' ? A.workload : JSON.stringify(A.workload)) : '',
  goal: String(A.goal || ''),
  assumptions: START.assumptions || [],
  kernel_backend: KERNEL_BACKEND,
  kernel_backend_dir: KERNEL_BACKEND_DIR,
  kernel_backend_command: String(A.kernel_backend_command || ''),
  kernel_budget: String(Math.max(1, int(A.kernel_budget, 6))),
  lock_idle_hours: String(LOCK_IDLE_HOURS),
  run_dir: '',
  resume_run_dir: String(A.run_dir || ''),
  branch: String(A.branch || ''),
  worktree: String(A.worktree || ''),
};

// Run record returned to the caller.
const R = {
  mode: MODE,
  status: 'running',
  stopped_at: '',
  run_dir: '',
  report_path: '',
  summary: '',
  task_def: pick(A, TASK_KEYS), // the definition this run started from
  provenance: START.provenance || {}, // per field: given | user | inferred | default
  assumptions: START.assumptions || [],
  phases: START.note ? [START.note] : [], // {phase, verdict, summary}
  done: [],            // verified work packages {wp, commit, evidence}
  handoffs: [],        // {id, owner: kernel_workflow | hyperloom, source, status, ...}
  known_issues: [],    // pre-existing failures proven by a same-pattern baseline control
  knowledge_updates: [],
  attention: ATTENTION, // state a human must clean up before anything else runs there
};

function note(phaseTitle, verdict, summary) {
  R.phases.push({ phase: phaseTitle, verdict, summary: String(summary || '').slice(0, 600) });
}

function enter(title) {
  PHASE = title;
  phase(title);
}
const stopHere = (title) => STOP_AFTER !== '' && STOP_AFTER === title.toLowerCase();

// Inputs every role sees: the context plus what earlier phases produced.
const inputs = (extra) => ({
  ...C,
  known_issues: R.known_issues,
  verified_work_packages: R.done,
  ...(extra || {}),
});

function rolePrompt(role, sub, ins, attempt) {
  const writes = role === 'intake'
    ? 'No RUN_DIR exists yet: change nothing; every check you run is read-only. Never push, never post on GitHub.'
    : `Write artifacts only under RUN_DIR (code changes only in the
task worktree named in the inputs). Never push, never post on GitHub. The exceptions are Petra's own repository
only: a scan's daily-report issue (scripts/post_queue.py) and the curator's knowledge pull request
(scripts/propose_knowledge.py).
Framework code runs from the tree under test, the task worktree (or RUN_DIR/base for a baseline at the
base commit): put it first on PYTHONPATH (sglang: <tree>/python) for every server, test and benchmark.
Use only the GPUs in gpu_ids: export HIP_VISIBLE_DEVICES=<gpu_ids> for every server, test and
benchmark. Touch only the processes, servers and containers this run started (knowledge/guardrails.md).
As root in the container, give back what you write under /home: after every git write and before you
return, run ${PETRA}/scripts/restore_owner.sh on RUN_DIR and on the worktree's .git
(knowledge/env_hygiene.md).`;
  const retry = attempt > 1 ? `
This is attempt ${attempt}: an earlier attempt of this call failed and may have left work behind —
commits, files in RUN_DIR, servers or processes it started. Check first (git status and the last
commits of the worktree, RUN_DIR, the run's process records), then continue from that state or clean it
up; never commit the same change twice or start a second server.` : '';
  return `You are the ${role}. PHASE=${sub}. MODE=${ins.mode || 'undecided'}.
First Read ${PETRA}/roles/${role}.md and follow its instructions for PHASE=${sub}.
Read ${PETRA}/knowledge/guardrails.md; its rules override anything else. Read every other knowledge
file the role names under ${PETRA}/knowledge/ and fill the templates it names under ${PETRA}/templates/.
Do all filesystem and shell work yourself. ${writes}${retry}

## Inputs
${cfg(ins)}

Return ONLY the structured JSON the role file specifies for PHASE=${sub} (a StructuredOutput tool is forced).`;
}

function withTimeout(p, ms) {
  if (typeof setTimeout !== 'function' || !(ms > 0)) return p;
  let to;
  const guard = new Promise((resolve) => {
    to = setTimeout(() => resolve(TIMED_OUT), ms);
  });
  const done = (v) => {
    if (typeof clearTimeout === 'function') clearTimeout(to);
    return v;
  };
  return Promise.race([p.then(done, (e) => { done(null); throw e; }), guard]);
}

// One agent call; resolves null (never throws) so every caller decides what a missing answer means
// for its gate. A failed attempt is retried and the retry is told to check what it left behind. A
// timeout is not retried: the timed-out agent cannot be cancelled and may still be running, so a
// retry would run the role twice at once (GEAK's agentT makes the same choice).
async function call(role, sub, ins, schema, label, opts) {
  const lbl = label || `${role}:${sub}`;
  const ms = timeoutFor(role);
  for (let attempt = 1; attempt <= AGENT_RETRIES; attempt++) {
    try {
      const r = await withTimeout(agent(rolePrompt(role, sub, ins, attempt),
        { label: lbl, phase: PHASE, schema, ...(opts || {}) }), ms);
      if (r === TIMED_OUT) {
        const min = Math.round(ms / 60000);
        log(`  [petra] ${lbl} timed out after ${min} min; not retried`);
        ATTENTION.push({ call: lbl, issue: `timed out after ${min} min and may still be running: check its servers and GPUs before reusing them` });
        return null;
      }
      if (r) return r;
      log(`  [petra] ${lbl} returned nothing (attempt ${attempt}/${AGENT_RETRIES})`);
    } catch (e) {
      log(`  [petra] ${lbl} failed (attempt ${attempt}/${AGENT_RETRIES}): ` +
        String(e && e.message ? e.message : e).slice(0, 200));
    }
  }
  return null;
}

// Schemas of the phases after Intake (the helpers are defined above).
const WP = S({
  id: str,
  goal: str,
  kind: { type: 'string', enum: ['framework', 'kernel', 'test', 'docs', 'apply_pr'] },
  files: strs,
  test: str,
  depends_on: strs,
}, ['id', 'goal', 'test']);
const WPS = arr(WP);

const LOCK = { type: 'string', enum: ['acquired', 'busy'] }; // the machine's run lock (scripts/run_lock.py)
const SETUP = S({
  lock: LOCK,
  run_dir: str,
  baseline_status: { type: 'string', enum: ['pass', 'fail', 'skip'] },
  baseline: str,
  branch: str,
  worktree: str,
  gpu_ids: str, // the GPU set every later role uses
  notes: str,
}, ['lock', 'run_dir', 'baseline_status', 'gpu_ids']);
const SPEC = S({ spec_path: str, gates_measurable: bool, perf_claim: str, skill: str, notes: str },
  ['spec_path', 'gates_measurable']);
const RECON = S({
  design_path: str,
  subsystems: arr(S({ name: str, files: strs, hook: str }, ['name'])),
  unmapped: strs,
  gap_type: str,
  level: { type: 'string', enum: ['L1', 'L2', 'L3'] },
  needs_kernel: bool,
  summary: str,
}, ['design_path', 'unmapped', 'level']);
const DESIGN = S({
  design_path: str,
  work_packages: WPS,
  gate_ok: bool,
  needs_human_review: bool,
  perf_claim: str, // required, '' for none: a resumed run measures exactly this claim
  summary: str,
}, ['work_packages', 'gate_ok', 'perf_claim']);
const TRIAGE = S({
  priority: { type: 'string', enum: ['P0', 'P1', 'P2'] },
  category: {
    type: 'string',
    enum: ['wrong result', 'crash', 'startup or build failure', 'performance', 'feature request', 'CI', 'tool'],
  },
  action: { type: 'string', enum: ['reproduce', 'push_existing_pr', 'close_fixed', 'needs_info', 'not_amd', 'plan'] },
  reason: str,
  existing_prs: strs,
  triage_path: str,
  reply_draft_path: str,
}, ['priority', 'category', 'action', 'triage_path']);
const REPRO = S({ reproduced: bool, repro_cmd: str, perf_claim: str, evidence: str },
  ['reproduced', 'repro_cmd', 'evidence']);
const DIAG = S({
  verdict: { type: 'string', enum: ['fix_needed', 'baseline_bug', 'not_amd_side', 'inconclusive'] },
  root_cause: str,
  work_packages: WPS,
  known_issue: obj,
  summary: str,
}, ['verdict', 'root_cause']);
const CLASSIFY = S({
  failure_class: { type: 'string', enum: ['code_regression', 'dependency_bump', 'test_bug', 'flaky', 'infrastructure'] },
  failing_test_cmd: str,
  window: str,
  evidence: str,
  triage_path: str,
}, ['failure_class', 'failing_test_cmd', 'evidence', 'triage_path']);
const BISECT = S({ culprit: str, confirmed: bool, work_packages: WPS, evidence: str }, ['culprit', 'confirmed']);
const PROFILE = S({
  analysis_path: str,
  path_ok: bool,
  path_evidence: str,
  metrics: obj,
  opportunities: arr(S({
    id: str,
    kind: str,
    where: str,
    evidence: str,
    upper_bound_pct: num,
    owner: { type: 'string', enum: ['petra', 'kernel_workflow', 'hyperloom'] },
  }, ['id', 'kind', 'owner'])),
}, ['analysis_path', 'path_ok', 'opportunities']);
const PERF_PLAN = S({
  work_packages: WPS,
  handoffs: arr(S({
    id: str,
    owner: { type: 'string', enum: ['kernel_workflow', 'hyperloom'] },
    spec_path: str,
  }, ['id', 'owner'])),
  perf_claim: str,
  gate_ok: bool,
}, ['work_packages', 'gate_ok']);
const IMPL = S({
  wp: str,
  status: { type: 'string', enum: ['done', 'blocked'] },
  commit: str,
  unit_test_cmd: str,
  files_changed: strs,
  kernel_handoff: { type: ['object', 'null'] },
  notes: str,
}, ['wp', 'status']);
const UNIT = S({
  wp: str,
  unit_pass: bool,
  feature_off_unchanged: bool,
  fails_without_change: { type: 'string', enum: ['parent', 'mutant', 'no', 'n/a'] },
  failure_summary: str,
  evidence: str,
}, ['wp', 'unit_pass', 'feature_off_unchanged', 'fails_without_change']);
const ROLLBACK = S({ wp: str, reset_to: str, clean: bool }, ['reset_to', 'clean']);
const VERIFY = S({
  all_pass: bool,
  gates: obj,
  failures: arr(S({ gate: str, failure_class: str, counts: str, evidence: str }, ['gate'])),
  ledger_path: str,
  summary: str,
}, ['all_pass', 'failures']);
const INVESTIGATE = S({
  verdict: { type: 'string', enum: ['fix_needed', 'baseline_bug', 'kernel_regression', 'inconclusive'] },
  work_packages: WPS,
  known_issue: obj,
  kernel_handoffs: strs, // kernel_regression: the integrated hand-offs whose kernels cause the failure
  counterexample: str,   // kernel_regression: the failing case, given to the kernel back end as a test
  summary: str,
}, ['verdict']);
const PERF = S({
  claim_reproduced: bool,
  held_out_ok: bool,
  guards_ok: bool,
  workload_unchanged: bool,
  path_ok: bool,
  results: arr(),
  summary: str,
}, ['claim_reproduced', 'held_out_ok', 'guards_ok', 'workload_unchanged', 'path_ok']);
const REVIEW = S({
  verdict: { type: 'string', enum: ['approve', 'changes_requested', 'blocked'] },
  findings: arr(S({
    severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
    where: str,
    issue: str,
    evidence: str,
    hack: str, // knowledge/reward_hacks.md id, or "new"
  }, ['severity', 'issue'])),
  work_packages: WPS,
  review_path: str,
  summary: str,
}, ['verdict', 'findings', 'review_path']);
const PR = S({
  branch: str,
  title: str,
  commits: strs,
  lint_pass: bool,
  feature_off_final: bool,
  content_unchanged: bool, // the branch's tree is the one Verify and Review passed
  merges_cleanly: bool,
  pr_body_path: str,
  push_command: str,
  work_packages: WPS, // what the branch still lacks; implemented, verified and reviewed like a finding
}, ['branch', 'lint_pass', 'feature_off_final', 'content_unchanged', 'pr_body_path']);
const K_PACKAGE = S({
  task_dir: str,
  mode: { type: 'string', enum: ['optimize', 'author'] },
  target_language: str,
  op_spec: obj,
  workload_spec_path: str,
  task: str,
  notes: str,
}, ['task_dir', 'mode']);
const K_RUN = S({ exit_code: num, result_path: str, notes: str }, ['exit_code']);
const K_COLLECT = S({
  status: { type: 'string', enum: ['improved', 'no_gain', 'failed'] },
  speedup: num,
  evidence: str,
  integrate_wp: { type: ['object', 'null'], properties: WP.properties, required: WP.required },
  notes: str,
}, ['status']);
const REPORT = S({ report_path: str, summary: str }, ['report_path']);
const LEARN = S({ updates: arr(S({ file: str, change: str }, ['file'])), skill_status: str, pr_url: str, notes: str },
  ['updates']);
const COLLECT = S({ lock: { type: 'string', enum: ['acquired', 'busy', 'skipped'] }, run_dir: str, candidates_path: str,
  counts: obj, recent: obj, notes: str }, ['lock', 'run_dir', 'candidates_path']);
const DISPATCH = S({
  queue_path: str,
  top: arr(S({ rank: num, task: str, type: str, level: str, priority: str, source: str }, ['task'])),
  matrix_changes: num,
}, ['queue_path', 'top']);

// ---------------------------------------------------------------------------
// Shared stages
// ---------------------------------------------------------------------------
async function finish(status, at) {
  R.status = status;
  R.stopped_at = at || '';
  if (C.run_dir) {
    enter('Report');
    const rep = await call('director', 'report',
      inputs({ status, stopped_at: at || '', phases: R.phases, handoffs: R.handoffs, attention: R.attention }), REPORT);
    if (rep) {
      R.report_path = rep.report_path;
      R.summary = rep.summary || '';
    }
    const learn = await call('curator', 'learn',
      inputs({ status, report_path: R.report_path, phases: R.phases }), LEARN);
    if (learn) {
      R.knowledge_updates = learn.updates || [];
      R.knowledge_pr = learn.pr_url || '';
    }
  }
  R.run_dir = C.run_dir;
  log(`[petra] mode=${MODE} status=${status}${at ? ` at ${at}` : ''}` +
    `${R.report_path ? ` report=${R.report_path}` : ''}${R.attention.length ? ` attention=${R.attention.length}` : ''}`);
  return R;
}

// A rollback that did not leave the worktree clean is recorded for a human; returns the note suffix.
function rolledBack(rb, wpId) {
  const clean = !!rb && rb.clean === true;
  if (!clean) {
    R.attention.push({ wp: wpId, worktree: C.worktree,
      issue: rb ? `rollback to ${rb.reset_to} left the worktree unclean` : 'the rollback returned nothing' });
  }
  return rb ? ` (reset to ${rb.reset_to}${clean ? '' : ', worktree not clean'})` : ' (rollback returned nothing)';
}

// Setup, then the stop_after check: a finished run record when the run ends here, else null.
async function start(requireBaseline) {
  const s = await setup(requireBaseline);
  if (s === 'busy') return finish('busy', 'Setup');
  if (!s) return finish('blocked', 'Setup');
  if (stopHere('Setup')) return finish('stopped', 'Setup');
  return null;
}

// true, false, or 'busy' when another Petra task holds the machine (nothing was created then).
async function setup(requireBaseline) {
  enter('Setup');
  const s = await call('director', 'setup', inputs({ require_baseline: requireBaseline }), SETUP);
  if (s && s.lock === 'busy') {
    note('Setup', 'busy', `another Petra task holds this machine${s.notes ? `: ${s.notes}` : ''}`);
    return 'busy';
  }
  if (!s || !s.run_dir) {
    note('Setup', 'fail', 'the director returned no run directory');
    return false;
  }
  // GPUs the user gave win; otherwise every later role uses the set Setup pinned.
  Object.assign(C, { run_dir: s.run_dir, branch: s.branch || C.branch, worktree: s.worktree || C.worktree,
    gpu_ids: String(C.gpu_ids || s.gpu_ids || '').trim() });
  if (!C.gpu_ids) {
    note('Setup', 'fail', 'no GPU set pinned (gpu_ids)');
    return false;
  }
  const ok = s.baseline_status === 'pass' || (!requireBaseline && s.baseline_status === 'skip');
  note('Setup', ok ? 'pass' : 'fail',
    `baseline ${s.baseline_status}${s.baseline ? `: ${s.baseline}` : ''}${s.notes ? `; ${s.notes}` : ''}`);
  return ok;
}

// One work package at a time: implement, then an independent unit + feature-off
// gate; failed rounds feed the test engineer's findings back; after the last round
// the package is rolled back to the last verified commit and the task stops.
async function implementAll(wps) {
  enter('Implement');
  const list = Array.isArray(wps) ? wps : [];
  if (list.length === 0) {
    note('Implement', 'fail', 'no work packages');
    return { ok: false, reason: 'no work packages' };
  }
  if (R.done.length + list.length > MAX_WPS) {
    note('Implement', 'fail', `${R.done.length + list.length} work packages exceed args.max_work_packages=${MAX_WPS}`);
    return { ok: false, reason: 'work-package budget exceeded' };
  }
  for (const wp of list) {
    const known = new Set(R.done.map((d) => d.wp));
    const missing = (wp.depends_on || []).filter((d) => !known.has(d));
    if (missing.length) log(`  [petra] ${wp.id} depends on unverified ${missing.join(', ')}; order follows the design`);
    let feedback = '';
    let passed = false;
    for (let round = 0; round <= MAX_FIX_ROUNDS && !passed; round++) {
      const im = await call('implementer', 'implement',
        inputs({ work_package: wp, round, feedback }), IMPL, `implementer:${wp.id}#${round}`);
      if (!im) {
        feedback = 'the implementer returned nothing';
        continue;
      }
      if (im.status === 'blocked') {
        feedback = im.notes || 'the implementer reported the work package blocked';
        break;
      }
      if (!String(im.commit || '').trim()) {
        feedback = 'the implementer reported done without a commit';
        continue;
      }
      if (im.kernel_handoff && !R.handoffs.some((h) => h.id === `K-${wp.id}`)) {
        R.handoffs.push({ id: `K-${wp.id}`, wp: wp.id, owner: 'kernel_workflow', source: 'implement', ...im.kernel_handoff });
      }
      const ut = await call('test_engineer', 'unit',
        inputs({ work_package: wp, commit: im.commit, unit_test_cmd: im.unit_test_cmd || wp.test }),
        UNIT, `test_engineer:${wp.id}#${round}`);
      // A unit test proves something only if it can fail: on the parent commit when the package changes
      // behaviour, on a copy of the change broken in one way when it keeps behaviour (a performance
      // change, a kernel swap, a refactor). Only a docs package has nothing to fail.
      const bites = !!ut && (['parent', 'mutant'].includes(ut.fails_without_change)
        || (ut.fails_without_change === 'n/a' && wp.kind === 'docs'));
      if (ut && ut.unit_pass === true && ut.feature_off_unchanged === true && bites) {
        passed = true;
        R.done.push({ wp: wp.id, commit: im.commit, evidence: ut.evidence || '' });
      } else if (!ut) {
        feedback = 'the test engineer returned nothing';
      } else if (ut.unit_pass === true && ut.feature_off_unchanged === true) {
        feedback = `the unit test cannot fail (fails_without_change=${ut.fails_without_change}); make it fail on the parent `
          + `commit, or on a copy of the change broken in one way when the change keeps behaviour`
          + `${ut.failure_summary ? `: ${ut.failure_summary}` : ''}`;
      } else {
        feedback = ut.failure_summary || 'the unit or feature-off gate failed';
      }
    }
    if (!passed) {
      const rb = await call('implementer', 'rollback', inputs({ work_package: wp, reason: feedback }),
        ROLLBACK, `implementer:rollback:${wp.id}`);
      note('Implement', 'fail', `${wp.id}: ${feedback}${rolledBack(rb, wp.id)}`);
      return { ok: false, failed_wp: wp.id, reason: feedback };
    }
  }
  note('Implement', 'pass', `verified: ${R.done.map((d) => d.wp).join(', ')}`);
  return { ok: true };
}

// Verify against the same-pattern baseline; a failure goes to the investigator,
// whose verdict decides: fix work packages (implemented, then re-verified), a
// baseline bug (recorded; the gate is re-judged on what remains) or a stop.
async function verifyLoop(extraGates) {
  for (let round = 0; ; round++) {
    enter('Verify');
    const v = await call('verify_engineer', 'verify', inputs({ extra_gates: extraGates || [], round }),
      VERIFY, `verify_engineer#${round}`);
    if (!v) {
      note('Verify', 'fail', 'the verify engineer returned nothing');
      return { ok: false, reason: 'no verification result' };
    }
    if (v.ledger_path) C.ledger_path = v.ledger_path;
    if (v.all_pass === true) {
      note('Verify', 'pass', v.summary || 'all gates pass');
      return { ok: true };
    }
    const failing = (v.failures || []).map((f) => `${f.gate}${f.failure_class ? `:${f.failure_class}` : ''}`).join(', ');
    note('Verify', 'fail', failing || v.summary || 'gates failed');
    if (round >= MAX_INVESTIGATE) return { ok: false, reason: `investigation budget exhausted (${failing})` };

    enter('Investigate');
    const integratedKernels = R.handoffs.filter((h) => h.status === 'integrated')
      .map((h) => ({ handoff: h.id, wp: h.integrated_wp, commit: h.commit }));
    const inv = await call('investigator', 'investigate',
      inputs({ failures: v.failures || [], round, integrated_kernels: integratedKernels }),
      INVESTIGATE, `investigator#${round}`);
    if (!inv) {
      note('Investigate', 'fail', 'the investigator returned nothing');
      return { ok: false, reason: 'no investigation result' };
    }
    note('Investigate', inv.verdict, inv.summary || '');
    if (inv.verdict === 'baseline_bug') {
      if (inv.known_issue) R.known_issues.push(inv.known_issue);
      continue;
    }
    if (inv.verdict === 'kernel_regression') {
      const back = await rejectKernels(inv.kernel_handoffs || [], inv.counterexample || inv.summary || '');
      if (!back.ok) return { ok: false, reason: back.reason };
      continue;
    }
    if (inv.verdict === 'fix_needed' && Array.isArray(inv.work_packages) && inv.work_packages.length) {
      const fix = await implementAll(inv.work_packages);
      if (!fix.ok) return { ok: false, reason: `fix ${fix.failed_wp || ''} failed: ${fix.reason}` };
      await kernelStage(); // hand-offs a fix raised
      continue;
    }
    return { ok: false, reason: 'investigation inconclusive' };
  }
}

// An integrated kernel that fails Petra's gates goes back to the functional kernel (its commit is
// reverted). With a back end it is handed back once more, the failing case added to its tests, and
// integrated again only if the back end passes it; otherwise it ends `rejected`.
async function rejectKernels(ids, counterexample) {
  const hs = R.handoffs.filter((h) => ids.includes(h.id) && h.status === 'integrated');
  if (!hs.length) {
    note('Investigate', 'fail', `kernel_regression names no integrated kernel (${ids.join(', ') || 'none'})`);
    return { ok: false, reason: 'kernel_regression without an integrated kernel' };
  }
  for (const h of hs) {
    const rb = await call('implementer', 'rollback', inputs({
      work_package: { id: h.integrated_wp, goal: `back to the functional kernel of ${h.id}`, test: '' },
      revert: h.commit, reason: `the integrated kernel fails Petra's gates: ${counterexample}`,
    }), ROLLBACK, `implementer:revert:${h.id}`);
    const suffix = rolledBack(rb, h.integrated_wp);
    if (!rb || rb.clean !== true) {
      note('Investigate', 'fail', `${h.id}: could not go back to the functional kernel${suffix}`);
      return { ok: false, reason: `revert of ${h.id} failed` };
    }
    R.done = R.done.filter((d) => d.wp !== h.integrated_wp);
    h.counterexamples = [...(h.counterexamples || []), counterexample];
    const retry = (h.retries || 0) < 1;
    h.status = retry ? undefined : 'rejected'; // undefined: pending again for the Kernel stage
    if (retry) h.retries = (h.retries || 0) + 1;
    note('Investigate', 'kernel_rejected', `${h.id}: back to the functional kernel${suffix}`
      + `${retry ? '; handed back once with the failing case' : '; rejected after its retry'}`);
  }
  await kernelStage();
  return { ok: true };
}

async function performance(claim) {
  enter('Performance');
  const p = await call('perf_engineer', 'perf_eval', inputs({ claim: claim || '' }), PERF);
  // A measurement counts only on the fixed workload and on the path the task targets; a gain counts
  // only if it also holds at the held-out operating point nobody tuned on.
  const trusted = !!p && p.workload_unchanged === true && p.path_ok === true;
  const reproduced = trusted && p.claim_reproduced === true && p.held_out_ok === true;
  const ok = trusted && p.guards_ok === true && (!claim || reproduced);
  const why = !p ? 'the performance engineer returned nothing'
    : !trusted ? `not trusted: ${p.workload_unchanged !== true ? 'workload changed' : 'the run left the intended path'}; ${p.summary || ''}`
      : claim && p.claim_reproduced === true && p.held_out_ok !== true
        ? `the gain does not hold at the held-out operating point; ${p.summary || ''}`
        : (p.summary || '');
  note('Performance', ok ? 'pass' : 'fail', why);
  return { ok, trusted, claimed: !!claim, reproduced };
}

// An independent review of the diff and its evidence. Requested changes come back as work packages:
// implemented, verified again (and measured again when the task measures), then reviewed again.
async function reviewLoop(extraGates, perfClaim, runPerf) {
  for (let round = 0; ; round++) {
    enter('Review');
    const rv = await call('reviewer', 'review', inputs({ round, extra_gates: extraGates || [], claim: perfClaim || '' }),
      REVIEW, `reviewer#${round}`, REVIEW_MODEL ? { model: REVIEW_MODEL } : undefined);
    if (!rv) {
      note('Review', 'fail', 'the reviewer returned nothing');
      return { ok: false, at: 'Review' };
    }
    if (rv.review_path) C.review_path = rv.review_path;
    const findings = rv.findings || [];
    const count = (s) => findings.filter((f) => f.severity === s).length;
    note('Review', rv.verdict, `${count('blocker')} blocker, ${count('major')} major, ${count('minor')} minor` +
      `${rv.summary ? `; ${rv.summary}` : ''}`);
    if (rv.verdict === 'approve') {
      if (count('blocker') === 0) return { ok: true };
      note('Review', 'fail', 'an approval with a blocker finding is not an approval');
      return { ok: false, at: 'Review' };
    }
    if (rv.verdict === 'blocked') return { ok: false, at: 'Review' };
    const wps = rv.work_packages || [];
    if (!wps.length || round >= MAX_REVIEW) {
      note('Review', 'fail', wps.length ? `review budget exhausted (max_review_rounds=${MAX_REVIEW})`
        : 'changes requested without work packages');
      return { ok: false, at: 'Review' };
    }
    const fix = await implementAll(wps);
    if (!fix.ok) return { ok: false, at: 'Implement' };
    await kernelStage(); // hand-offs a requested change raised
    const ver = await verifyLoop(extraGates);
    if (!ver.ok) return { ok: false, at: 'Verify' };
    if (runPerf && !(await performance(perfClaim)).ok) return { ok: false, at: 'Performance' };
  }
}

// The PR engineer changes no code: the branch it hands over must be the tree Verify and Review passed.
// What it finds missing comes back as work packages.
async function preparePR(round) {
  enter('PR');
  const pr = await call('pr_engineer', 'pr', inputs({ round }), PR, `pr_engineer#${round}`);
  const ok = !!pr && pr.lint_pass === true && pr.feature_off_final === true && pr.content_unchanged === true
    && !!pr.pr_body_path;
  if (pr) {
    if (pr.branch) C.branch = pr.branch;
    C.pr_body_path = pr.pr_body_path || '';
    R.pr = { title: pr.title || '', branch: pr.branch, pr_body_path: pr.pr_body_path, push_command: pr.push_command || '',
      merges_cleanly: pr.merges_cleanly !== false };
  }
  note('PR', ok ? 'pass' : 'fail', !pr ? 'the PR engineer returned nothing'
    : `${pr.title || pr.branch}${pr.content_unchanged !== true ? '; the branch no longer matches what was verified' : ''}`
      + `${pr.merges_cleanly === false ? '; conflicts with main, reported in the PR body' : ''}`);
  return { ok, wps: !pr || ok || pr.content_unchanged !== true ? [] : (pr.work_packages || []) };
}

// What a back end returned, trimmed to the fields the liaison needs (GEAK lanes also return
// their agent timelines and large records).
function backendSummary(r) {
  if (r == null) return null;
  if (typeof r !== 'object') return String(r).slice(0, 2000);
  const keep = ['validation_status', 'final_speedup', 'final_weighted', 'final_geomean', 'final_patch',
    'eval_dir', 'authored', 'note', 'error'];
  const out = {};
  for (const k of keep) if (r[k] != null) out[k] = r[k];
  if (r.winner) out.winner = typeof r.winner === 'object' ? { source: r.winner.source, language: r.winner.language } : r.winner;
  return out;
}

// Kernel hand-offs go to the selected back end. A gain comes back as a work package that the
// implementer integrates and the test engineer re-verifies; the later Verify and Performance gates
// judge it with everything else. A back end that fails or finds no gain never blocks the task:
// the functional kernel stays. Runs again after every fix loop, for hand-offs raised there and for a
// kernel handed back after it failed Verify (rejectKernels).
async function kernelStage() {
  const pending = R.handoffs.filter((h) => h.owner === 'kernel_workflow' && !h.status);
  if (!pending.length) return { integrated: 0 };
  if (KERNEL_BACKEND === 'none') {
    for (const h of pending) h.status = 'recorded';
    note('Kernel', 'recorded', `${pending.length} kernel hand-off(s) recorded (kernel_backend=none)`);
    return { integrated: 0 };
  }
  let integrated = 0;
  for (const h of pending) {
    if (PHASE !== 'Kernel') enter('Kernel');
    const pkg = await call('kernel_liaison', 'package', inputs({ handoff: h }), K_PACKAGE, `kernel_liaison:package:${h.id}`);
    if (!pkg) {
      h.status = 'failed';
      h.reason = 'no task package';
      continue;
    }
    let result = null;
    if (KERNEL_BACKEND === 'geak') {
      const laneArgs = {
        kernel_path: pkg.task_dir,
        workflow_dir: `${KERNEL_BACKEND_DIR}/kernel_workflow`,
        mode: pkg.mode,
        budget: C.kernel_budget,
        gpu_ids: C.gpu_ids,
        task: pkg.task || h.reason || '',
        exp_root: `${C.run_dir}/kernel`,
        apply_to_original: 'false',
        ...(pkg.target_language ? { target_language: pkg.target_language } : {}),
        ...(pkg.op_spec ? { op_spec: pkg.op_spec } : {}),
        ...(pkg.workload_spec_path ? { workload_spec_path: pkg.workload_spec_path } : {}),
      };
      try {
        result = backendSummary(await workflow({ scriptPath: `${KERNEL_BACKEND_DIR}/kernel_workflow/kernel_lane.js` }, laneArgs));
      } catch (e) {
        result = { error: String(e && e.message ? e.message : e).slice(0, 400) };
      }
    } else {
      result = await call('kernel_liaison', 'run', inputs({ handoff: h, task_dir: pkg.task_dir }), K_RUN,
        `kernel_liaison:run:${h.id}`) || { error: 'the command back end did not run' };
    }
    const res = await call('kernel_liaison', 'collect', inputs({ handoff: h, task_dir: pkg.task_dir, backend_result: result }),
      K_COLLECT, `kernel_liaison:collect:${h.id}`);
    h.status = res ? res.status : 'failed';
    h.result = res ? { speedup: res.speedup, evidence: res.evidence || '' } : result;
    if (res && res.status === 'improved' && res.integrate_wp) {
      const r = await implementAll([res.integrate_wp]);
      h.status = r.ok ? 'integrated' : 'integration_failed';
      if (r.ok) {
        integrated += 1;
        h.integrated_wp = res.integrate_wp.id;
        h.commit = (R.done.find((d) => d.wp === res.integrate_wp.id) || {}).commit || '';
      }
    }
  }
  note('Kernel', integrated ? 'integrated' : 'no_gain', pending.map((h) => `${h.id}:${h.status}`).join(', '));
  return { integrated };
}

// Implement -> Kernel -> Verify -> (Performance) -> PR, shared by every code-changing mode.
// `wps` may be empty only in perf mode when the plan is all kernel hand-offs.
async function deliver(wps, extraGates, perfClaim, runPerf) {
  if (wps.length) {
    const impl = await implementAll(wps);
    if (!impl.ok) return finish('blocked', 'Implement');
  }
  if (stopHere('Implement')) return finish('stopped', 'Implement');
  const ks = await kernelStage();
  if (!wps.length && ks.integrated === 0) return finish('no_gain', 'Kernel');
  if (stopHere('Kernel')) return finish('stopped', 'Kernel');

  const ver = await verifyLoop(extraGates);
  if (!ver.ok) return finish('blocked', 'Verify');
  if (stopHere('Verify')) return finish('stopped', 'Verify');

  if (runPerf) {
    const perf = await performance(perfClaim);
    if (!perf.ok) {
      if (perf.trusted && perf.claimed && !perf.reproduced && MODE === 'perf') {
        // A performance change without a measured win is dropped (guardrails.md).
        const rb = await call('implementer', 'rollback', inputs({ work_package: { id: 'ALL', goal: 'drop the change', test: '' },
          reason: 'no measured win' }), ROLLBACK, 'implementer:rollback:ALL');
        note('Performance', 'dropped', `no measured win${rolledBack(rb, 'ALL')}`);
        return finish('dropped', 'Performance');
      }
      return finish('blocked', 'Performance');
    }
    if (stopHere('Performance')) return finish('stopped', 'Performance');
  }

  const rev = await reviewLoop(extraGates, perfClaim, runPerf);
  if (!rev.ok) return finish('blocked', rev.at);
  if (stopHere('Review')) return finish('stopped', 'Review');

  // What the PR engineer finds missing goes back through Implement, Verify and Review, once.
  for (let round = 0; ; round++) {
    const pr = await preparePR(round);
    if (pr.ok) return finish('ready_for_review', 'PR');
    if (!pr.wps.length || round >= 1) return finish('blocked', 'PR');
    const fix = await implementAll(pr.wps);
    if (!fix.ok) return finish('blocked', 'Implement');
    await kernelStage();
    const again = await verifyLoop(extraGates);
    if (!again.ok) return finish('blocked', 'Verify');
    if (runPerf && !(await performance(perfClaim)).ok) return finish('blocked', 'Performance');
    const reviewed = await reviewLoop(extraGates, perfClaim, runPerf);
    if (!reviewed.ok) return finish('blocked', reviewed.at);
  }
}

// ---------------------------------------------------------------------------
// Modes
// ---------------------------------------------------------------------------
async function runFeature() {
  const early = await start(true);
  if (early) return early;

  // Resume after a human approved design.md (a run that stopped at Design).
  if (RESUME === 'implement') {
    C.spec_path = String(A.spec_path || `${C.run_dir}/feature_spec.md`);
    C.design_path = String(A.design_path || `${C.run_dir}/design.md`);
    enter('Design');
    const approved = await call('architect', 'design', inputs({ approved_design: true }), DESIGN);
    if (!approved || approved.gate_ok !== true || !(approved.work_packages || []).length) {
      note('Design', 'fail', approved ? (approved.summary || 'approved design has no usable work packages') : 'no design');
      return finish('blocked', 'Design');
    }
    note('Design', 'approved', `${approved.work_packages.length} work package(s) from the approved design`);
    return deliver(approved.work_packages, [], approved.perf_claim || '', true);
  }

  enter('Spec');
  const spec = await call('director', 'spec', inputs(), SPEC);
  if (!spec || spec.gates_measurable !== true) {
    note('Spec', 'fail', spec ? (spec.notes || 'acceptance criteria not measurable') : 'no spec');
    return finish('blocked', 'Spec');
  }
  C.spec_path = spec.spec_path;
  note('Spec', 'pass', `${spec.spec_path}${spec.skill ? `; skill ${spec.skill}` : ''}`);
  if (stopHere('Spec')) return finish('stopped', 'Spec');

  enter('Recon');
  const recon = await call('analyst', 'recon', inputs(), RECON);
  if (!recon || (recon.unmapped || []).length > 0) {
    note('Recon', 'fail', recon ? `unmapped: ${(recon.unmapped || []).join(', ')}` : 'no recon');
    return finish('blocked', 'Recon');
  }
  C.design_path = recon.design_path;
  C.level = recon.level;
  C.gap_type = recon.gap_type || '';
  note('Recon', 'pass', `${recon.gap_type || ''} ${recon.level}; ${recon.summary || ''}`);
  if (stopHere('Recon')) return finish('stopped', 'Recon');

  enter('Design');
  const design = await call('architect', 'design', inputs(), DESIGN);
  if (!design || design.gate_ok !== true || !(design.work_packages || []).length) {
    note('Design', 'fail', design ? (design.summary || 'design gate not met') : 'no design');
    return finish('blocked', 'Design');
  }
  if (design.design_path) C.design_path = design.design_path;
  note('Design', 'pass', `${design.work_packages.length} work package(s)${design.summary ? `; ${design.summary}` : ''}`);
  // L3 work, or a design the architect flags, waits for a human-approved design.
  if (stopHere('Design') || design.needs_human_review === true || recon.level === 'L3') {
    return finish(stopHere('Design') ? 'stopped' : 'awaiting_design_review', 'Design');
  }

  return deliver(design.work_packages, [], spec.perf_claim || '', true);
}

async function runIssue() {
  const early = await start(false);
  if (early) return early;

  enter('Triage');
  const tri = await call('issue_triager', 'triage', inputs(), TRIAGE);
  if (!tri) {
    note('Triage', 'fail', 'no triage');
    return finish('blocked', 'Triage');
  }
  Object.assign(C, { triage_path: tri.triage_path, reply_draft_path: tri.reply_draft_path || '', priority: tri.priority });
  R.priority = tri.priority;
  note('Triage', tri.action, `${tri.priority} ${tri.category || ''}: ${tri.reason || ''}`);
  if (['needs_info', 'not_amd', 'plan'].includes(tri.action)) return finish('triaged', 'Triage');
  if (stopHere('Triage')) return finish('stopped', 'Triage');

  // Every path that changes code first reproduces on main: the reproduction is the issue_repro gate,
  // also for an existing fix PR.
  enter('Reproduce');
  const expectFixed = tri.action === 'close_fixed';
  const rep = await call('issue_triager', 'reproduce', inputs({ expect_fixed: expectFixed }), REPRO);
  if (!rep) {
    note('Reproduce', 'fail', 'no reproduction result');
    return finish('blocked', 'Reproduce');
  }
  const reproCmd = String(rep.repro_cmd || '').trim();
  if (rep.reproduced && !reproCmd) {
    note('Reproduce', 'fail', 'reproduced without a repro_cmd; the issue_repro gate needs one');
    return finish('blocked', 'Reproduce');
  }
  C.repro_cmd = reproCmd;
  note('Reproduce', rep.reproduced ? 'reproduced' : 'not_reproduced', rep.evidence);
  if (!rep.reproduced) return finish(expectFixed ? 'fixed_on_main' : 'not_reproduced', 'Reproduce');
  // A performance issue is fixed when the reported number comes back; the reproduction states it.
  const runPerf = tri.category === 'performance';
  const issueClaim = runPerf ? String(rep.perf_claim || '').trim() : '';
  if (runPerf && !issueClaim) {
    note('Reproduce', 'fail', 'a performance issue reproduced without a perf_claim: the number the fix must restore');
    return finish('blocked', 'Reproduce');
  }
  if (stopHere('Reproduce')) return finish('stopped', 'Reproduce');

  const gates = [{ gate: 'issue_repro', cmd: reproCmd, expect: 'fixed' }];
  if (tri.action === 'push_existing_pr') {
    const prs = (tri.existing_prs || []).join(', ');
    const wp = { id: 'WP1', kind: 'apply_pr', goal: `apply the existing fix ${prs} and complete what verification needs`,
      test: 'the issue reproduction no longer fails; the PR\'s own tests pass', files: [], depends_on: [] };
    return deliver([wp], gates, issueClaim, runPerf);
  }

  enter('Diagnose');
  const dg = await call('investigator', 'diagnose', inputs(), DIAG);
  if (!dg) {
    note('Diagnose', 'fail', 'no diagnosis');
    return finish('blocked', 'Diagnose');
  }
  note('Diagnose', dg.verdict, dg.root_cause);
  if (dg.verdict === 'baseline_bug' && dg.known_issue) R.known_issues.push(dg.known_issue);
  if (dg.verdict !== 'fix_needed' || !(dg.work_packages || []).length) return finish('diagnosed', 'Diagnose');
  if (stopHere('Diagnose')) return finish('stopped', 'Diagnose');

  return deliver(dg.work_packages, gates, issueClaim, runPerf);
}

async function runCi() {
  const early = await start(false);
  if (early) return early;

  enter('Classify');
  const cl = await call('ci_guardian', 'classify', inputs(), CLASSIFY);
  if (!cl) {
    note('Classify', 'fail', 'no classification');
    return finish('blocked', 'Classify');
  }
  const failingCmd = String(cl.failing_test_cmd || '').trim();
  const handOver = cl.failure_class === 'infrastructure' || cl.failure_class === 'flaky';
  Object.assign(C, { triage_path: cl.triage_path, failing_test_cmd: failingCmd, failure_class: cl.failure_class });
  if (!handOver && !failingCmd) {
    note('Classify', 'fail', `${cl.failure_class} without a failing_test_cmd; the failing_test gate needs one`);
    return finish('blocked', 'Classify');
  }
  note('Classify', cl.failure_class, cl.evidence);
  if (handOver) return finish('handed_off', 'Classify');
  if (stopHere('Classify')) return finish('stopped', 'Classify');

  enter('Bisect');
  const bi = await call('ci_guardian', 'bisect', inputs(), BISECT);
  if (!bi || bi.confirmed !== true || !(bi.work_packages || []).length) {
    note('Bisect', 'fail', bi ? `culprit ${bi.culprit} not confirmed or no fix planned` : 'no bisect result');
    return finish('blocked', 'Bisect');
  }
  C.culprit = bi.culprit;
  note('Bisect', 'pass', `culprit ${bi.culprit}`);
  if (stopHere('Bisect')) return finish('stopped', 'Bisect');

  return deliver(bi.work_packages, [{ gate: 'failing_test', cmd: failingCmd, expect: 'pass on every lane it failed on' }],
    '', false);
}

async function runPerf() {
  const early = await start(true);
  if (early) return early;

  enter('Profile');
  const pf = await call('perf_engineer', 'profile', inputs(), PROFILE);
  if (!pf) {
    note('Profile', 'fail', 'no profile');
    return finish('blocked', 'Profile');
  }
  if (pf.path_ok !== true) {
    note('Profile', 'fail', `the profiled run did not take the intended path: ${pf.path_evidence || 'no evidence given'}`);
    return finish('blocked', 'Profile');
  }
  C.analysis_path = pf.analysis_path;
  const opps = pf.opportunities || [];
  note('Profile', 'pass', `${opps.length} opportunit${opps.length === 1 ? 'y' : 'ies'}: ` +
    opps.map((o) => `${o.id}:${o.kind}(${o.owner})`).join(', '));
  if (stopHere('Profile')) return finish('stopped', 'Profile');

  enter('Plan');
  const applyPrs = Array.isArray(A.apply_prs) ? A.apply_prs : (A.apply_prs ? [String(A.apply_prs)] : []);
  const plan = await call('architect', 'perf_plan', inputs({ opportunities: opps, apply_prs: applyPrs }), PERF_PLAN);
  if (!plan || plan.gate_ok !== true) {
    note('Plan', 'fail', 'plan gate not met');
    return finish('blocked', 'Plan');
  }
  for (const h of plan.handoffs || []) {
    // Kernel hand-offs wait for the Kernel stage; other owners (Hyperloom) are recorded.
    R.handoffs.push(h.owner === 'kernel_workflow' ? { ...h, source: 'plan' } : { ...h, source: 'plan', status: 'recorded' });
  }
  const kernelHandoffs = R.handoffs.filter((h) => h.owner === 'kernel_workflow').length;
  if (!(plan.work_packages || []).length) {
    if (kernelHandoffs && KERNEL_BACKEND !== 'none') {
      note('Plan', 'kernel_only', `${kernelHandoffs} kernel hand-off(s) for kernel_backend=${KERNEL_BACKEND}`);
      return deliver([], [], plan.perf_claim || 'the planned gain', true);
    }
    note('Plan', 'no_work', `${(plan.handoffs || []).length} hand-off(s), nothing for Petra`);
    for (const h of R.handoffs) if (!h.status) h.status = 'recorded';
    return finish('handed_off', 'Plan');
  }
  note('Plan', 'pass', `${plan.work_packages.length} work package(s); claim: ${plan.perf_claim || 'none'}`);
  if (stopHere('Plan')) return finish('stopped', 'Plan');

  return deliver(plan.work_packages, [], plan.perf_claim || 'the planned gain', true);
}

async function runScan() {
  enter('Collect');
  const sources = Array.isArray(A.sources) && A.sources.length ? A.sources : ['ci', 'issues', 'upstream'];
  const rescan = A.rescan === true || String(A.rescan).toLowerCase() === 'true';
  const col = await call('scout', 'collect', inputs({ sources, since: String(A.since || ''), rescan,
    upstream_repos: Array.isArray(A.upstream_repos) ? A.upstream_repos : [] }), COLLECT);
  // One report a day: a scan from the last 24 hours makes the run ask before it starts another.
  if (col && col.lock === 'skipped' && !rescan) {
    const r = col.recent || {};
    const when = r.at || 'the last 24 hours';
    const where = r.url || r.run_dir || 'this container';
    note('Collect', 'needs_input', `a scan from ${when} exists: ${where}`);
    Object.assign(R, { status: 'needs_input', stopped_at: 'Collect', recent: r,
      questions: [{ field: 'rescan', question: `A daily report from ${when} exists (${where}). Scan again anyway?`,
        why: 'one report a day is enough: another scan repeats the same API calls and agent work', options: [true, false] }],
      next: 'to scan anyway, run petra.js again with the same arguments plus answers={"rescan": true}' });
    log(`[petra] mode=scan status=needs_input: a scan from ${when} exists (${where})`);
    return R;
  }
  if (col && col.lock === 'busy') {
    note('Collect', 'busy', `another Petra task holds this machine${col.notes ? `: ${col.notes}` : ''}`);
    return finish('busy', 'Collect');
  }
  if (!col || !col.run_dir) {
    note('Collect', 'fail', 'no candidates');
    return finish('blocked', 'Collect');
  }
  C.run_dir = col.run_dir;
  C.candidates_path = col.candidates_path;
  note('Collect', 'pass', JSON.stringify(col.counts || {}));
  if (stopHere('Collect')) return finish('stopped', 'Collect');

  enter('Dispatch');
  const dp = await call('dispatcher', 'dispatch', inputs(), DISPATCH);
  if (!dp) {
    note('Dispatch', 'fail', 'no ranking');
    return finish('blocked', 'Dispatch');
  }
  C.queue_path = dp.queue_path;
  R.queue = (dp.top || []).slice(0, 20);
  note('Dispatch', 'pass', `${(dp.top || []).length} ranked; ${dp.matrix_changes || 0} matrix change(s)`);
  return finish('queued', 'Dispatch');
}

const RUNNERS = { feature: runFeature, issue: runIssue, ci: runCi, perf: runPerf, scan: runScan };
log(`[petra] mode=${MODE} petra_dir=${PETRA} framework=${C.framework}${C.framework_dir ? ` (${C.framework_dir})` : ''}`);
return await RUNNERS[MODE]();
