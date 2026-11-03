// Dry run of petra.js on GEAK's workflow runtime with a scripted fake backend:
// no GPU, no network, no model. Each scenario scripts what the roles answer and
// asserts the phases Petra walks through, the roles it calls and the final status.
//
//   GEAK_HOME=/path/to/GEAK node tests/dry_run.mjs
//
// GEAK_HOME defaults to ../geak/GEAK next to this checkout.
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { existsSync, readFileSync, mkdirSync, writeFileSync } from 'node:fs';

const PETRA = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const GEAK_HOME = process.env.GEAK_HOME || path.resolve(PETRA, '..', 'geak', 'GEAK');
const ENGINE = path.join(GEAK_HOME, 'interface', 'runtime', 'engine', 'run_workflow.mjs');
if (!existsSync(ENGINE)) {
  console.error(`GEAK runtime not found at ${ENGINE}; set GEAK_HOME`);
  process.exit(2);
}
const { createRuntime } = await import(pathToFileURL(ENGINE).href);
const SCRIPT = path.join(PETRA, 'petra.js');
const RUN = '/tmp/petra_dry_run';

// A stand-in for GEAK's kernel_lane.js: echoes the arguments Petra passed (in `note`, a field Petra
// keeps) and fails when the steer says FAIL.
const FAKE_GEAK = '/tmp/petra_dry_run_geak';
mkdirSync(path.join(FAKE_GEAK, 'kernel_workflow'), { recursive: true });
writeFileSync(path.join(FAKE_GEAK, 'kernel_workflow', 'kernel_lane.js'), `export const meta = { name: 'fake-kernel-lane', description: 'dry-run stub', phases: [] };
if (String(args.task || '').includes('FAIL')) throw new Error('lane failed');
return { validation_status: 'pass', final_speedup: 1.37, final_patch: args.exp_root + '/best.diff', eval_dir: args.exp_root + '/eval',
  note: JSON.stringify({ kernel_path: args.kernel_path, workflow_dir: args.workflow_dir, mode: args.mode, budget: args.budget,
    gpu_ids: args.gpu_ids, apply_to_original: args.apply_to_original }),
  agent_timeline: { events: ['large record Petra must not forward'] } };
`);

const WP = (id, extra) => ({ id, goal: `goal of ${id}`, kind: 'framework', files: ['x.py'], test: `test ${id}`, depends_on: [], ...(extra || {}) });

// Answers every role gives unless a scenario overrides them.
const DEFAULTS = {
  'director:setup': () => ({ run_dir: RUN, baseline: 'PASS - 3/3 runs within spread', branch: 'petra/task', worktree: `${RUN}/wt` }),
  'director:spec': () => ({ spec_path: `${RUN}/feature_spec.md`, gates_measurable: true, perf_claim: '+20% output tok/s at equal HBM' }),
  'director:report': () => ({ report_path: `${RUN}/report.md`, summary: 'done' }),
  'analyst:recon': () => ({ design_path: `${RUN}/design.md`, subsystems: [{ name: 'scheduler', files: ['a.py'], hook: 'h' }], unmapped: [], gap_type: 'framework-only', level: 'L1' }),
  'architect:design': () => ({ design_path: `${RUN}/design.md`, work_packages: [WP('WP1'), WP('WP2', { depends_on: ['WP1'] })], gate_ok: true, needs_human_review: false, perf_claim: '+20% output tok/s at equal HBM' }),
  'architect:perf_plan': () => ({ work_packages: [WP('WP1')], handoffs: [{ id: 'O2', owner: 'kernel_workflow', spec_path: `${RUN}/op_spec.md` }], perf_claim: '-5% TPOT', gate_ok: true }),
  'implementer:implement': (ins) => ({ wp: ins.work_package.id, status: 'done', commit: `c_${ins.work_package.id}`, unit_test_cmd: 'pytest -q t.py', files_changed: ['x.py'], kernel_handoff: null }),
  'implementer:rollback': () => ({ wp: 'x', reset_to: 'base', clean: true }),
  'test_engineer:unit': (ins) => ({ wp: ins.work_package.id, unit_pass: true, feature_off_unchanged: true, evidence: 'ok' }),
  'verify_engineer:verify': () => ({ all_pass: true, gates: { G0: 'pass', G2: 'pass' }, failures: [], ledger_path: `${RUN}/experiment_ledger.md` }),
  'investigator:investigate': () => ({ verdict: 'fix_needed', work_packages: [WP('FIX1')], summary: 'race in hook' }),
  'investigator:diagnose': () => ({ verdict: 'fix_needed', root_cause: 'stale import', work_packages: [WP('WP1')] }),
  'perf_engineer:perf_eval': () => ({ claim_reproduced: true, guards_ok: true, results: [], summary: '+22%' }),
  'perf_engineer:profile': () => ({ analysis_path: `${RUN}/perf_analysis.md`, metrics: { gpu_busy: 0.71 }, opportunities: [
    { id: 'O1', kind: 'host_sync', where: 'aiter_backend.py', evidence: 'trace', upper_bound_pct: 4, owner: 'petra' },
    { id: 'O2', kind: 'kernel', where: 'moe', evidence: 'trace', upper_bound_pct: 9, owner: 'kernel_workflow' }] }),
  'pr_engineer:pr': () => ({ branch: 'petra/task', title: '[Fix] [AMD] scope: thing', commits: ['c_WP1'], lint_pass: true, feature_off_final: true, upstream_synced: true, pr_body_path: `${RUN}/pr_body.md`, push_command: 'git push origin petra/task' }),
  'curator:learn': () => ({ updates: [{ file: 'knowledge/known_issues.md', change: 'none' }], skill_status: 'draft' }),
  'issue_triager:triage': () => ({ priority: 'P0', category: 'crash', action: 'reproduce', reason: 'default config crash', existing_prs: [], triage_path: `${RUN}/issue_triage.md`, reply_draft_path: `${RUN}/reply.md` }),
  'issue_triager:reproduce': () => ({ reproduced: true, repro_cmd: 'bash repro.sh', evidence: 'segfault 3/3' }),
  'ci_guardian:classify': () => ({ failure_class: 'code_regression', failing_test_cmd: 'pytest test_x.py', window: 'a..b', evidence: 'new regression since 10-21', triage_path: `${RUN}/ci_triage.md` }),
  'ci_guardian:bisect': () => ({ culprit: 'deadbeef', confirmed: true, work_packages: [WP('WP1')], evidence: 'fails at culprit, passes at parent' }),
  'scout:collect': () => ({ run_dir: RUN, candidates_path: `${RUN}/candidates.json`, counts: { upstream: 3, issues: 32, ci: 76, hardware: 5 } }),
  'dispatcher:dispatch': () => ({ queue_path: `${RUN}/task_queue.md`, top: [{ rank: 1, task: 'GLM-5.3 DCP crash', type: 'bug', level: 'L1', priority: 'P0', source: 'issues' }], matrix_changes: 2 }),
  'kernel_liaison:package': (ins) => ({ task_dir: `${RUN}/kernel/${ins.handoff.id}/task`, mode: 'optimize', target_language: 'hip',
    op_spec: { op_kind: 'swap_in' }, task: ins.handoff.reason === 'FAIL' ? 'FAIL on purpose' : 'decode, M <= 64' }),
  'kernel_liaison:run': () => ({ exit_code: 0, result_path: `${RUN}/kernel/out/result.json` }),
  'kernel_liaison:collect': (ins) => ((ins.backend_result || {}).error
    ? { status: 'failed', notes: ins.backend_result.error }
    : { status: 'improved', speedup: 1.37, evidence: 'eval dir', integrate_wp: WP(`K-${ins.handoff.id}`, { kind: 'kernel' }) }),
};

// The implementer hands WP1's kernel over (reason FAIL makes the fake back end throw).
const withKernelHandoff = (reason) => ({
  'implementer:implement': (ins) => ({ wp: ins.work_package.id, status: 'done', commit: `c_${ins.work_package.id}`, unit_test_cmd: 'pytest -q t.py',
    kernel_handoff: ins.work_package.id === 'WP1'
      ? { op_spec_path: `${RUN}/handoffs/K-WP1/op_spec.md`, reference_path: `${RUN}/handoffs/K-WP1/ref.py`, test_cmd: 'pytest k.py', plug_in: 'x.py:f', reason }
      : null }),
});

const ROLE_RE = /You are the ([a-z_]+)\. PHASE=([a-z_]+)\./;

function parseInputs(prompt) {
  const out = {};
  const block = prompt.split('## Inputs\n')[1] || '';
  for (const line of block.split('\n')) {
    const m = /^- ([a-z_]+): (.*)$/.exec(line);
    if (!m) continue;
    try { out[m[1]] = JSON.parse(m[2]); } catch { out[m[1]] = m[2]; }
  }
  return out;
}

function makeBackend(overrides) {
  const calls = [];
  const counts = {};
  const b = { name: 'fake' };
  b.runAgent = async ({ prompt }) => {
    const m = ROLE_RE.exec(prompt);
    if (!m) throw new Error('prompt without role header');
    const key = `${m[1]}:${m[2]}`;
    const n = (counts[key] = (counts[key] || 0) + 1);
    const ins = parseInputs(prompt);
    calls.push({ key, n, ins });
    const f = (overrides && overrides[key]) || DEFAULTS[key];
    if (!f) throw new Error(`no scripted answer for ${key}`);
    const ans = f(ins, n);
    return { text: JSON.stringify(ans) };
  };
  return { backend: b, calls };
}

async function run(args, overrides) {
  const phases = [];
  const { backend, calls } = makeBackend(overrides);
  const rt = createRuntime({
    backend,
    concurrency: 2,
    schemaRetries: 0,
    log: (msg) => {
      const m = /=== PHASE: (.*) ===/.exec(msg);
      if (m) phases.push(m[1]);
    },
  });
  const result = await rt.runScript(SCRIPT, { petra_dir: PETRA, framework_dir: '/tmp/sglang', agent_retries: 1, ...args }, 0);
  return { result, phases, calls, keys: calls.map((c) => c.key) };
}

let failed = 0;
let passed = 0;
function check(cond, msg) {
  if (cond) passed++;
  else { failed++; console.error(`  FAIL: ${msg}`); }
}
const eqList = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const scenarios = [
  ['feature: straight path to a reviewable PR', async () => {
    const r = await run({ mode: 'feature', task: 'port HiSparse V2 to DeepSeek-V4.1' });
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(eqList(r.phases, ['Setup', 'Spec', 'Recon', 'Design', 'Implement', 'Verify', 'Performance', 'PR', 'Report']), `phases ${r.phases}`);
    check(r.result.done.map((d) => d.wp).join() === 'WP1,WP2', `done ${JSON.stringify(r.result.done)}`);
    check(r.result.pr && r.result.pr.push_command === 'git push origin petra/task', 'push command surfaced, not executed');
    check(r.keys.filter((k) => k === 'curator:learn').length === 1, 'curator runs once');
  }],
  ['feature: unit gate fails once, feedback reaches the second round', async () => {
    const r = await run({ mode: 'feature', task: 't' }, {
      'test_engineer:unit': (ins, n) => (n === 1
        ? { wp: ins.work_package.id, unit_pass: false, feature_off_unchanged: true, failure_summary: 'case 7 mismatches the reference' }
        : { wp: ins.work_package.id, unit_pass: true, feature_off_unchanged: true }),
    });
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    const second = r.calls.filter((c) => c.key === 'implementer:implement')[1];
    check(second && second.ins.feedback === 'case 7 mismatches the reference', 'feedback passed to round 1');
  }],
  ['feature: verify fails, investigation finds a fix, re-verify passes', async () => {
    const r = await run({ mode: 'feature', task: 't' }, {
      'verify_engineer:verify': (ins, n) => (n === 1
        ? { all_pass: false, failures: [{ gate: 'G4', failure_class: 'catastrophic collapse', counts: '3/4 runs' }] }
        : { all_pass: true, failures: [] }),
    });
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(eqList(r.phases.slice(4, 9), ['Implement', 'Verify', 'Investigate', 'Implement', 'Verify']), `phases ${r.phases}`);
    check(r.result.done.map((d) => d.wp).join() === 'WP1,WP2,FIX1', `done ${JSON.stringify(r.result.done)}`);
  }],
  ['feature: baseline bug is recorded and the gate is re-judged', async () => {
    const r = await run({ mode: 'feature', task: 't' }, {
      'verify_engineer:verify': (ins, n) => (n === 1
        ? { all_pass: false, failures: [{ gate: 'G4', failure_class: 'catastrophic collapse' }] }
        : { all_pass: (ins.known_issues || []).length === 1, failures: [] }),
      'investigator:investigate': () => ({ verdict: 'baseline_bug', known_issue: { id: 'KI-002', title: 'whole-batch collapse' }, summary: 'same-pattern baseline fails the same way' }),
    });
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(r.result.known_issues.length === 1 && r.result.known_issues[0].id === 'KI-002', 'known issue recorded and passed to verify');
  }],
  ['feature: investigation budget is bounded', async () => {
    const r = await run({ mode: 'feature', task: 't', max_investigate_rounds: 2 }, {
      'verify_engineer:verify': () => ({ all_pass: false, failures: [{ gate: 'G3' }] }),
      'investigator:investigate': () => ({ verdict: 'baseline_bug', known_issue: { id: 'KI-x' } }),
    });
    check(r.result.status === 'blocked' && r.result.stopped_at === 'Verify', `status ${r.result.status} at ${r.result.stopped_at}`);
    check(r.keys.filter((k) => k === 'verify_engineer:verify').length === 3, 'verify runs max_investigate_rounds + 1 times');
  }],
  ['feature: L3 waits for a human-approved design', async () => {
    const r = await run({ mode: 'feature', task: 't' }, {
      'analyst:recon': () => ({ design_path: `${RUN}/design.md`, unmapped: [], level: 'L3', gap_type: 'framework-only' }),
    });
    check(r.result.status === 'awaiting_design_review' && r.result.stopped_at === 'Design', `status ${r.result.status}`);
    check(!r.keys.includes('implementer:implement'), 'no implementation before review');
  }],
  ['feature: stop_after Design', async () => {
    const r = await run({ mode: 'feature', task: 't', stop_after: 'Design' });
    check(r.result.status === 'stopped' && r.result.stopped_at === 'Design', `status ${r.result.status}`);
  }],
  ['feature: resume_from implement after review', async () => {
    const r = await run({ mode: 'feature', task: 't', resume_from: 'implement', run_dir: RUN });
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(!r.keys.includes('director:spec') && !r.keys.includes('analyst:recon'), 'spec and recon skipped');
    const d = r.calls.find((c) => c.key === 'architect:design');
    check(d && d.ins.approved_design === true, 'architect told the design is approved');
  }],
  ['feature: a work package that never passes is rolled back', async () => {
    const r = await run({ mode: 'feature', task: 't', max_fix_rounds: 1 }, {
      'test_engineer:unit': (ins) => ({ wp: ins.work_package.id, unit_pass: false, feature_off_unchanged: true, failure_summary: 'still wrong' }),
    });
    check(r.result.status === 'blocked' && r.result.stopped_at === 'Implement', `status ${r.result.status}`);
    check(r.keys.filter((k) => k === 'implementer:implement').length === 2, 'max_fix_rounds + 1 attempts');
    check(r.keys.includes('implementer:rollback'), 'rollback called');
    check(!r.keys.includes('verify_engineer:verify'), 'no verification of a failed package');
  }],
  ['feature: baseline that does not reproduce blocks at Setup', async () => {
    const r = await run({ mode: 'feature', task: 't' }, {
      'director:setup': () => ({ run_dir: RUN, baseline: 'FAIL - spread 9% > 2%' }),
    });
    check(r.result.status === 'blocked' && r.result.stopped_at === 'Setup', `status ${r.result.status}`);
    check(r.keys.includes('director:report'), 'blocked runs still get a report');
  }],
  ['issue: reproduce, diagnose, fix, verify with the reproduction as a gate', async () => {
    const r = await run({ mode: 'issue', task: 'https://github.com/sgl-project/sglang/issues/38849' });
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(eqList(r.phases, ['Setup', 'Triage', 'Reproduce', 'Diagnose', 'Implement', 'Verify', 'PR', 'Report']), `phases ${r.phases}`);
    const v = r.calls.find((c) => c.key === 'verify_engineer:verify');
    check(v && JSON.stringify(v.ins.extra_gates).includes('issue_repro'), 'issue_repro gate passed to verify');
    check(r.result.priority === 'P0', 'priority recorded');
  }],
  ['issue: needs_info ends at triage with a reply draft', async () => {
    const r = await run({ mode: 'issue', task: 'i' }, {
      'issue_triager:triage': () => ({ priority: 'P1', action: 'needs_info', triage_path: `${RUN}/t.md`, reply_draft_path: `${RUN}/reply.md` }),
    });
    check(r.result.status === 'triaged' && r.result.stopped_at === 'Triage', `status ${r.result.status}`);
  }],
  ['issue: close_fixed that no longer reproduces', async () => {
    const r = await run({ mode: 'issue', task: 'i' }, {
      'issue_triager:triage': () => ({ priority: 'P2', action: 'close_fixed', triage_path: `${RUN}/t.md` }),
      'issue_triager:reproduce': (ins) => ({ reproduced: false, evidence: `expect_fixed=${ins.expect_fixed}; clean 3/3` }),
    });
    check(r.result.status === 'fixed_on_main', `status ${r.result.status}`);
  }],
  ['issue: push an existing PR', async () => {
    const r = await run({ mode: 'issue', task: 'i' }, {
      'issue_triager:triage': () => ({ priority: 'P1', action: 'push_existing_pr', existing_prs: ['#40872'], triage_path: `${RUN}/t.md` }),
    });
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    const im = r.calls.find((c) => c.key === 'implementer:implement');
    check(im && im.ins.work_package.kind === 'apply_pr' && im.ins.work_package.goal.includes('#40872'), 'apply_pr work package');
  }],
  ['ci: infrastructure is handed over', async () => {
    const r = await run({ mode: 'ci', task: 'tracker #45847 cluster NIXL' }, {
      'ci_guardian:classify': () => ({ failure_class: 'infrastructure', evidence: 'UCX interface errno 19', triage_path: `${RUN}/ci.md` }),
    });
    check(r.result.status === 'handed_off', `status ${r.result.status}`);
    check(!r.keys.includes('ci_guardian:bisect'), 'no bisect for infrastructure');
  }],
  ['ci: code regression to a fix PR', async () => {
    const r = await run({ mode: 'ci', task: 'tracker cluster _check ImportError' });
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(eqList(r.phases, ['Setup', 'Classify', 'Bisect', 'Implement', 'Verify', 'PR', 'Report']), `phases ${r.phases}`);
    const v = r.calls.find((c) => c.key === 'verify_engineer:verify');
    check(v && JSON.stringify(v.ins.extra_gates).includes('failing_test'), 'failing_test gate passed to verify');
  }],
  ['ci: unconfirmed culprit blocks', async () => {
    const r = await run({ mode: 'ci', task: 'c' }, {
      'ci_guardian:bisect': () => ({ culprit: 'maybe', confirmed: false, work_packages: [WP('WP1')] }),
    });
    check(r.result.status === 'blocked' && r.result.stopped_at === 'Bisect', `status ${r.result.status}`);
  }],
  ['perf: no measured win drops the change', async () => {
    const r = await run({ mode: 'perf', task: 'DeepSeek-V4.1 decode on MI355X' }, {
      'perf_engineer:perf_eval': () => ({ claim_reproduced: false, guards_ok: true, summary: '-0.3% within noise' }),
    });
    check(r.result.status === 'dropped' && r.result.stopped_at === 'Performance', `status ${r.result.status}`);
    check(r.keys.includes('implementer:rollback'), 'change rolled back');
    check(r.result.handoffs.some((h) => h.owner === 'kernel_workflow'), 'kernel opportunity handed off');
  }],
  ['perf: measured win to a PR', async () => {
    const r = await run({ mode: 'perf', task: 'p', apply_prs: ['#46329'] });
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(eqList(r.phases, ['Setup', 'Profile', 'Plan', 'Implement', 'Verify', 'Performance', 'PR', 'Report']), `phases ${r.phases}`);
    const p = r.calls.find((c) => c.key === 'architect:perf_plan');
    check(p && eqList(p.ins.apply_prs, ['#46329']), 'apply_prs reach the planner');
  }],
  ['perf: only kernel-level opportunities are handed off', async () => {
    const r = await run({ mode: 'perf', task: 'p' }, {
      'architect:perf_plan': () => ({ work_packages: [], handoffs: [{ id: 'O2', owner: 'kernel_workflow' }], gate_ok: true }),
    });
    check(r.result.status === 'handed_off' && r.result.stopped_at === 'Plan', `status ${r.result.status}`);
  }],
  ['scan: collect and dispatch without code changes', async () => {
    const r = await run({ mode: 'scan', framework_dir: '' });
    check(r.result.status === 'queued', `status ${r.result.status}`);
    check(eqList(r.phases, ['Collect', 'Dispatch', 'Report']), `phases ${r.phases}`);
    check(!r.keys.some((k) => k.startsWith('implementer')), 'no implementer in scan');
    check(r.result.queue && r.result.queue[0].priority === 'P0', 'queue surfaced');
  }],
  ['kernel: the default back end records hand-offs and runs nothing', async () => {
    const r = await run({ mode: 'feature', task: 't' }, withKernelHandoff('decode hot path'));
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(r.result.handoffs.length === 1 && r.result.handoffs[0].status === 'recorded', `handoffs ${JSON.stringify(r.result.handoffs)}`);
    check(!r.keys.some((k) => k.startsWith('kernel_liaison')) && !r.phases.includes('Kernel'), 'no liaison, no Kernel phase');
  }],
  ['kernel: the geak back end runs GEAK kernel_lane and the gain is integrated', async () => {
    const r = await run({ mode: 'feature', task: 't', kernel_backend: 'geak', geak_home: FAKE_GEAK, gpu_ids: '3' }, withKernelHandoff('decode hot path'));
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(eqList(r.phases.slice(4, 8), ['Implement', 'Kernel', 'Implement', 'Verify']), `phases ${r.phases}`);
    const h = r.result.handoffs[0];
    check(h && h.id === 'K-WP1' && h.status === 'integrated', `handoff ${JSON.stringify(h)}`);
    const col = r.calls.find((c) => c.key === 'kernel_liaison:collect');
    const lane = col ? JSON.parse(col.ins.backend_result.note) : {};
    check(lane.kernel_path === `${RUN}/kernel/K-WP1/task` && lane.workflow_dir === `${FAKE_GEAK}/kernel_workflow`, `lane args ${JSON.stringify(lane)}`);
    check(lane.apply_to_original === 'false' && lane.gpu_ids === '3' && lane.mode === 'optimize' && lane.budget === '6', 'lane never writes into the framework; GPUs, mode, budget passed');
    check(col && col.ins.backend_result.agent_timeline === undefined, 'back-end result trimmed before the liaison sees it');
    check(r.result.done.map((d) => d.wp).includes('K-K-WP1'), 'integration package verified by the test engineer');
  }],
  ['kernel: a failing back end does not block the task', async () => {
    const r = await run({ mode: 'feature', task: 't', kernel_backend: 'geak', geak_home: FAKE_GEAK }, withKernelHandoff('FAIL'));
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(r.result.handoffs[0].status === 'failed', `handoff ${JSON.stringify(r.result.handoffs[0])}`);
    check(!r.result.done.some((d) => d.wp.startsWith('K-')), 'nothing integrated');
  }],
  ['kernel: a command back end runs through the liaison', async () => {
    const r = await run({ mode: 'feature', task: 't', kernel_backend: 'command', kernel_backend_command: 'my-kernel-agent --task {task_dir} --out {out_dir} --gpus {gpu_ids}' },
      withKernelHandoff('decode hot path'));
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    const runCall = r.calls.find((c) => c.key === 'kernel_liaison:run');
    check(runCall && runCall.ins.kernel_backend_command.includes('{task_dir}'), 'command reaches the liaison');
    check(r.result.handoffs[0].status === 'integrated', 'gain integrated');
  }],
  ['kernel: a perf plan with only kernel hand-offs runs on the selected back end', async () => {
    const plan = { 'architect:perf_plan': () => ({ work_packages: [], handoffs: [{ id: 'O2', owner: 'kernel_workflow', spec_path: `${RUN}/handoffs/O2/op_spec.md` },
      { id: 'O3', owner: 'hyperloom' }], perf_claim: '-6% TPOT', gate_ok: true }) };
    const r = await run({ mode: 'perf', task: 'p', kernel_backend: 'geak', geak_home: FAKE_GEAK }, plan);
    check(r.result.status === 'ready_for_review', `status ${r.result.status}`);
    check(eqList(r.phases, ['Setup', 'Profile', 'Plan', 'Kernel', 'Implement', 'Verify', 'Performance', 'PR', 'Report']), `phases ${r.phases}`);
    const byId = Object.fromEntries(r.result.handoffs.map((h) => [h.id, h.status]));
    check(byId.O2 === 'integrated' && byId.O3 === 'recorded', `statuses ${JSON.stringify(byId)}`);
    const none = await run({ mode: 'perf', task: 'p', kernel_backend: 'geak', geak_home: FAKE_GEAK },
      { ...plan, 'kernel_liaison:collect': () => ({ status: 'no_gain', speedup: 1.01, integrate_wp: null }) });
    check(none.result.status === 'no_gain' && none.result.stopped_at === 'Kernel', `no gain: ${none.result.status}`);
  }],
  ['kernel: back-end arguments are validated', async () => {
    let msg = '';
    try { await run({ mode: 'feature', task: 't', kernel_backend: 'triton-magic' }); } catch (e) { msg = e.message; }
    check(msg.includes('args.kernel_backend must be one of'), `unknown back end: ${msg}`);
    msg = '';
    try { await run({ mode: 'feature', task: 't', kernel_backend: 'geak' }); } catch (e) { msg = e.message; }
    check(msg.includes('needs args.geak_home'), `geak without home: ${msg}`);
    msg = '';
    try { await run({ mode: 'feature', task: 't', kernel_backend: 'command' }); } catch (e) { msg = e.message; }
    check(msg.includes('needs args.kernel_backend_command'), `command without command: ${msg}`);
  }],
  ['roles: every role and PHASE petra.js calls is documented', async () => {
    const src = readFileSync(SCRIPT, 'utf8');
    const sites = [...src.matchAll(/call\('([a-z_]+)', '([a-z_]+)'/g)].map((m) => [m[1], m[2]]);
    check(sites.length >= 20, `found ${sites.length} call sites`);
    for (const [role, ph] of sites) {
      const f = path.join(PETRA, 'roles', `${role}.md`);
      const doc = existsSync(f) ? readFileSync(f, 'utf8') : '';
      check(doc.includes(`## PHASE=${ph}`), `roles/${role}.md documents PHASE=${ph}`);
      check(DEFAULTS[`${role}:${ph}`] !== undefined, `dry run scripts an answer for ${role}:${ph}`);
    }
  }],
  ['schemas: a malformed answer is rejected and the run stops cleanly', async () => {
    const r = await run({ mode: 'issue', task: 'i' }, {
      'issue_triager:triage': () => ({ priority: 'P5', action: 'maybe', triage_path: `${RUN}/t.md` }),
    });
    check(r.result.status === 'blocked' && r.result.stopped_at === 'Triage', `status ${r.result.status}`);
  }],
  ['arguments: bad mode and missing task are rejected', async () => {
    let msg = '';
    try { await run({ mode: 'magic', task: 't' }); } catch (e) { msg = e.message; }
    check(msg.includes('args.mode must be one of'), `bad mode: ${msg}`);
    msg = '';
    try { await run({ mode: 'issue' }); } catch (e) { msg = e.message; }
    check(msg.includes('args.task is required'), `missing task: ${msg}`);
    msg = '';
    try { await run({ mode: 'issue', task: 't', resume_from: 'implement', run_dir: RUN }); } catch (e) { msg = e.message; }
    check(msg.includes('resume_from supports only'), `resume outside feature: ${msg}`);
  }],
];

for (const [name, fn] of scenarios) {
  const before = failed;
  try {
    await fn();
  } catch (e) {
    failed++;
    console.error(`  FAIL: threw ${e && e.stack ? e.stack : e}`);
  }
  console.log(`${failed === before ? 'ok  ' : 'FAIL'} ${name}`);
}
console.log(`\n${passed} checks passed, ${failed} failed.`);
process.exit(failed ? 1 : 0);
