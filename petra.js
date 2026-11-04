export const meta = {
  name: 'petra',
  description: 'Petra: the framework agent for open-source LLM inference frameworks on AMD GPUs (sglang first). ' +
    'It turns one task (an upstream feature to bring to AMD, an AMD user issue, a red AMD CI job, a system-level ' +
    'performance gap) into a verified, reviewable pull request: correct first (independent unit gates, G0-G4 against ' +
    'a same-pattern baseline, an investigation loop with controls), then fast (equal-budget G5), within the community ' +
    'rules of knowledge/guardrails.md. mode=scan collects and ranks tasks from all sources without changing code. ' +
    'Petra never pushes or posts: it prepares the branch, the PR body and the reply drafts for a human.',
  whenToUse: 'Pass args.mode (feature | issue | ci | perf | scan; there is NO natural-language mode detection), ' +
    'args.petra_dir (absolute path of the Petra checkout, required), args.task (required except for scan: an upstream ' +
    'PR or design to bring to AMD, an issue URL, a CI job or tracker cluster, or a performance goal) and ' +
    'args.framework_dir (the framework checkout to change, required except for scan). Optional: args.framework ' +
    '(default sglang), args.model_path, args.platform, args.gpu_ids, args.container, args.workload, args.exp_root, ' +
    'args.apply_prs (perf), args.sources and args.since (scan), args.stop_after (a phase title), ' +
    'args.resume_from="implement" with args.run_dir (feature: continue after a human approved design.md), ' +
    'args.kernel_backend (none | geak | command; default none records kernel hand-offs only) with ' +
    'args.kernel_backend_dir (geak: the GEAK checkout) or args.kernel_backend_command (command), args.kernel_budget, ' +
    'args.review_model (the reviewer\'s model, where the runtime takes one per call), ' +
    'args.max_fix_rounds, args.max_investigate_rounds, args.max_review_rounds, args.max_work_packages, ' +
    'args.agent_retries, args.agent_timeout_ms. mode=perf requires args.workload: the fixed benchmark every ' +
    'measurement uses.',
  phases: [
    { title: 'Setup', detail: 'director: run dir, task branch and worktree, launch scripts, baseline (not in scan)' },
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
    { title: 'Collect', detail: 'scout: upstream changes, issues, CI trackers, platform gates -> candidates [scan]' },
    { title: 'Dispatch', detail: 'dispatcher: type, level, dependencies, effort, ranking, ecosystem-matrix changes [scan]' },
    { title: 'Report', detail: 'director: final report for every outcome; curator: knowledge updates' },
  ],
};

// ---------------------------------------------------------------------------
// Arguments. Control flow (phase order, retries, gates, budgets) lives here;
// agents are called only for judgement and for the work itself, and every agent
// returns structured JSON whose gate fields this script reads.
// ---------------------------------------------------------------------------
const A = args || {};
const MODES = ['feature', 'issue', 'ci', 'perf', 'scan'];
const MODE = String(A.mode != null ? A.mode : '').trim().toLowerCase();
if (!MODES.includes(MODE)) {
  throw new Error(`args.mode must be one of ${MODES.join(' | ')} (got ${JSON.stringify(A.mode)})`);
}
const PETRA = String(A.petra_dir || '').replace(/\/+$/, '');
if (!PETRA) {
  throw new Error('args.petra_dir is required: absolute path of the Petra checkout ' +
    '(the directory containing petra.js, roles/, knowledge/ and templates/)');
}
if (MODE !== 'scan' && !A.task) throw new Error(`args.task is required for mode=${MODE}`);
if (MODE !== 'scan' && !A.framework_dir) throw new Error(`args.framework_dir is required for mode=${MODE}`);
if (MODE === 'perf' && !A.workload) {
  throw new Error('args.workload is required for mode=perf: the fixed benchmark every measurement uses ' +
    '(model, input/output lengths, concurrency, budget), fixed before any profile is read');
}

const int = (v, d) => {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n >= 0 ? n : d;
};
const MAX_FIX_ROUNDS = int(A.max_fix_rounds, 2);          // extra implement rounds per work package
const MAX_INVESTIGATE = int(A.max_investigate_rounds, 3); // verify -> investigate -> verify cycles
const MAX_REVIEW = int(A.max_review_rounds, 2);           // review -> fix -> verify -> review cycles
const REVIEW_MODEL = String(A.review_model || '').trim();
const MAX_WPS = Math.max(1, int(A.max_work_packages, 12));
const AGENT_RETRIES = Math.max(1, int(A.agent_retries, 3));
const AGENT_TIMEOUT_MS = int(A.agent_timeout_ms, 3 * 3600 * 1000);
const STOP_AFTER = String(A.stop_after || '').trim().toLowerCase();
const RESUME = String(A.resume_from || '').trim().toLowerCase();
if (RESUME && !(MODE === 'feature' && RESUME === 'implement')) {
  throw new Error('args.resume_from supports only "implement" in mode=feature (continue after an approved design)');
}
if (RESUME && !A.run_dir) throw new Error('args.resume_from needs args.run_dir (the run that stopped at Design)');
const EXP_ROOT = String(A.exp_root || `${PETRA}/exp`).replace(/\/+$/, '');

// Kernel back ends: where kernel-level work goes (tuning a kernel Petra wrote for a feature, or a
// kernel-level performance opportunity). knowledge/kernel_backends.md describes the contract.
//   none     record the hand-off package in the report and run nothing (default)
//   geak     GEAK's single-language kernel lane from the checkout args.kernel_backend_dir, nested once
//            like GEAK's own e2e_workflow does; the only place Petra uses GEAK
//   command  any other CLI, run by the kernel liaison from args.kernel_backend_command
const KERNEL_BACKENDS = ['none', 'geak', 'command'];
const KERNEL_BACKEND = String(A.kernel_backend || 'none').trim().toLowerCase();
if (!KERNEL_BACKENDS.includes(KERNEL_BACKEND)) {
  throw new Error(`args.kernel_backend must be one of ${KERNEL_BACKENDS.join(' | ')} (got ${JSON.stringify(A.kernel_backend)})`);
}
if (KERNEL_BACKEND === 'geak' && !A.kernel_backend_dir) {
  throw new Error('args.kernel_backend=geak needs args.kernel_backend_dir (the GEAK checkout providing kernel_workflow/kernel_lane.js)');
}
if (KERNEL_BACKEND === 'command' && !A.kernel_backend_command) {
  throw new Error('args.kernel_backend=command needs args.kernel_backend_command ' +
    '(a shell command with {task_dir}, {out_dir} and {gpu_ids} placeholders)');
}
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
  kernel_backend: KERNEL_BACKEND,
  kernel_backend_dir: KERNEL_BACKEND_DIR,
  kernel_backend_command: String(A.kernel_backend_command || ''),
  kernel_budget: String(Math.max(1, int(A.kernel_budget, 6))),
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
  phases: [],          // {phase, verdict, summary}
  done: [],            // verified work packages {wp, commit, evidence}
  handoffs: [],        // {id, owner: kernel_workflow | hyperloom, source, status, ...}
  known_issues: [],    // pre-existing failures proven by a same-pattern baseline control
  knowledge_updates: [],
  attention: [],       // state a human must clean up before anything else runs there
};

const cfg = (o) => Object.entries(o)
  .filter(([, v]) => v !== '' && v != null && !(Array.isArray(v) && v.length === 0))
  .map(([k, v]) => `- ${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
  .join('\n');

function note(phaseTitle, verdict, summary) {
  R.phases.push({ phase: phaseTitle, verdict, summary: String(summary || '').slice(0, 600) });
}

let PHASE = '';
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

function rolePrompt(role, sub, ins) {
  return `You are the ${role}. PHASE=${sub}. MODE=${MODE}.
First Read ${PETRA}/roles/${role}.md and follow its instructions for PHASE=${sub}.
Read ${PETRA}/knowledge/guardrails.md; its rules override anything else. Read every other knowledge
file the role names under ${PETRA}/knowledge/ and fill the templates it names under ${PETRA}/templates/.
Do all filesystem and shell work yourself. Write artifacts only under RUN_DIR (code changes only in the
task worktree named in the inputs). Never push, never post on GitHub.
As root in the container, give back what you write into checkouts another user owns: after every git
write and before you return, run ${PETRA}/scripts/restore_owner.sh on the framework's .git, the task
worktree and RUN_DIR (knowledge/env_hygiene.md).

## Inputs
${cfg(ins)}

Return ONLY the structured JSON the role file specifies for PHASE=${sub} (a StructuredOutput tool is forced).`;
}

function withTimeout(p) {
  if (typeof setTimeout !== 'function' || !(AGENT_TIMEOUT_MS > 0)) return p;
  let to;
  const guard = new Promise((resolve) => {
    to = setTimeout(() => resolve(null), AGENT_TIMEOUT_MS);
  });
  const done = (v) => {
    if (typeof clearTimeout === 'function') clearTimeout(to);
    return v;
  };
  return Promise.race([p.then(done, (e) => { done(null); throw e; }), guard]);
}

// One agent call with retries; resolves null (never throws) so every caller
// decides what a missing answer means for its gate.
async function call(role, sub, ins, schema, label, opts) {
  const lbl = label || `${role}:${sub}`;
  const prompt = rolePrompt(role, sub, ins);
  for (let attempt = 1; attempt <= AGENT_RETRIES; attempt++) {
    try {
      const r = await withTimeout(agent(prompt, { label: lbl, phase: PHASE, schema, ...(opts || {}) }));
      if (r) return r;
      log(`  [petra] ${lbl} returned nothing (attempt ${attempt}/${AGENT_RETRIES})`);
    } catch (e) {
      log(`  [petra] ${lbl} failed (attempt ${attempt}/${AGENT_RETRIES}): ` +
        String(e && e.message ? e.message : e).slice(0, 200));
    }
  }
  return null;
}

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

const WP = S({
  id: str,
  goal: str,
  kind: { type: 'string', enum: ['framework', 'kernel', 'test', 'docs', 'apply_pr'] },
  files: strs,
  test: str,
  depends_on: strs,
}, ['id', 'goal', 'test']);
const WPS = arr(WP);

const SETUP = S({
  run_dir: str,
  baseline_status: { type: 'string', enum: ['pass', 'fail', 'skip'] },
  baseline: str,
  branch: str,
  worktree: str,
  notes: str,
}, ['run_dir', 'baseline_status']);
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
  perf_claim: str,
  summary: str,
}, ['work_packages', 'gate_ok']);
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
const REPRO = S({ reproduced: bool, repro_cmd: str, evidence: str }, ['reproduced', 'repro_cmd', 'evidence']);
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
const UNIT = S({ wp: str, unit_pass: bool, feature_off_unchanged: bool, failure_summary: str, evidence: str },
  ['wp', 'unit_pass', 'feature_off_unchanged']);
const ROLLBACK = S({ wp: str, reset_to: str, clean: bool }, ['reset_to', 'clean']);
const VERIFY = S({
  all_pass: bool,
  gates: obj,
  failures: arr(S({ gate: str, failure_class: str, counts: str, evidence: str }, ['gate'])),
  ledger_path: str,
  summary: str,
}, ['all_pass', 'failures']);
const INVESTIGATE = S({
  verdict: { type: 'string', enum: ['fix_needed', 'baseline_bug', 'inconclusive'] },
  work_packages: WPS,
  known_issue: obj,
  summary: str,
}, ['verdict']);
const PERF = S({
  claim_reproduced: bool,
  guards_ok: bool,
  workload_unchanged: bool,
  path_ok: bool,
  results: arr(),
  summary: str,
}, ['claim_reproduced', 'guards_ok', 'workload_unchanged', 'path_ok']);
const REVIEW = S({
  verdict: { type: 'string', enum: ['approve', 'changes_requested', 'blocked'] },
  findings: arr(S({
    severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
    where: str,
    issue: str,
    evidence: str,
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
  upstream_synced: bool,
  pr_body_path: str,
  push_command: str,
}, ['branch', 'lint_pass', 'feature_off_final', 'pr_body_path']);
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
const LEARN = S({ updates: arr(S({ file: str, change: str }, ['file'])), skill_status: str }, ['updates']);
const COLLECT = S({ run_dir: str, candidates_path: str, counts: obj }, ['run_dir', 'candidates_path']);
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
    if (learn) R.knowledge_updates = learn.updates || [];
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

async function setup(requireBaseline) {
  enter('Setup');
  const s = await call('director', 'setup', inputs({ require_baseline: requireBaseline }), SETUP);
  if (!s || !s.run_dir) {
    note('Setup', 'fail', 'the director returned no run directory');
    return false;
  }
  Object.assign(C, { run_dir: s.run_dir, branch: s.branch || C.branch, worktree: s.worktree || C.worktree });
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
      if (ut && ut.unit_pass === true && ut.feature_off_unchanged === true) {
        passed = true;
        R.done.push({ wp: wp.id, commit: im.commit, evidence: ut.evidence || '' });
      } else {
        feedback = ut ? (ut.failure_summary || 'the unit or feature-off gate failed') : 'the test engineer returned nothing';
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
    const inv = await call('investigator', 'investigate', inputs({ failures: v.failures || [], round }),
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
    if (inv.verdict === 'fix_needed' && Array.isArray(inv.work_packages) && inv.work_packages.length) {
      const fix = await implementAll(inv.work_packages);
      if (!fix.ok) return { ok: false, reason: `fix ${fix.failed_wp || ''} failed: ${fix.reason}` };
      continue;
    }
    return { ok: false, reason: 'investigation inconclusive' };
  }
}

async function performance(claim) {
  enter('Performance');
  const p = await call('perf_engineer', 'perf_eval', inputs({ claim: claim || '' }), PERF);
  // A measurement counts only on the fixed workload and on the path the task targets.
  const trusted = !!p && p.workload_unchanged === true && p.path_ok === true;
  const ok = trusted && p.guards_ok === true && (!claim || p.claim_reproduced === true);
  const why = !p ? 'the performance engineer returned nothing'
    : !trusted ? `not trusted: ${p.workload_unchanged !== true ? 'workload changed' : 'the run left the intended path'}; ${p.summary || ''}`
      : (p.summary || '');
  note('Performance', ok ? 'pass' : 'fail', why);
  return { ok, trusted, claimed: !!claim, reproduced: trusted && p.claim_reproduced === true };
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
    const ver = await verifyLoop(extraGates);
    if (!ver.ok) return { ok: false, at: 'Verify' };
    if (runPerf && !(await performance(perfClaim)).ok) return { ok: false, at: 'Performance' };
  }
}

async function preparePR() {
  enter('PR');
  const pr = await call('pr_engineer', 'pr', inputs(), PR);
  const ok = !!pr && pr.lint_pass === true && pr.feature_off_final === true && !!pr.pr_body_path;
  if (pr) {
    if (pr.branch) C.branch = pr.branch;
    C.pr_body_path = pr.pr_body_path || '';
    R.pr = { title: pr.title || '', branch: pr.branch, pr_body_path: pr.pr_body_path, push_command: pr.push_command || '' };
  }
  note('PR', ok ? 'pass' : 'fail', pr ? (pr.title || pr.branch) : 'the PR engineer returned nothing');
  return ok;
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
// the functional kernel stays.
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
        gpu_ids: C.gpu_ids || '0',
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
      if (r.ok) integrated += 1;
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

  if (!(await preparePR())) return finish('blocked', 'PR');
  return finish('ready_for_review', 'PR');
}

// ---------------------------------------------------------------------------
// Modes
// ---------------------------------------------------------------------------
async function runFeature() {
  if (!(await setup(true))) return finish('blocked', 'Setup');
  if (stopHere('Setup')) return finish('stopped', 'Setup');

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
  if (!(await setup(false))) return finish('blocked', 'Setup');

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
  if (stopHere('Reproduce')) return finish('stopped', 'Reproduce');

  const gates = [{ gate: 'issue_repro', cmd: reproCmd, expect: 'fixed' }];
  const runPerf = tri.category === 'performance';
  if (tri.action === 'push_existing_pr') {
    const prs = (tri.existing_prs || []).join(', ');
    const wp = { id: 'WP1', kind: 'apply_pr', goal: `apply the existing fix ${prs} and complete what verification needs`,
      test: 'the issue reproduction no longer fails; the PR\'s own tests pass', files: [], depends_on: [] };
    return deliver([wp], gates, '', runPerf);
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

  return deliver(dg.work_packages, gates, '', runPerf);
}

async function runCi() {
  if (!(await setup(false))) return finish('blocked', 'Setup');

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
  if (!(await setup(true))) return finish('blocked', 'Setup');

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
  const sources = Array.isArray(A.sources) && A.sources.length ? A.sources : ['upstream', 'issues', 'ci', 'hardware'];
  const col = await call('scout', 'collect', inputs({ sources, since: String(A.since || '') }), COLLECT);
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
