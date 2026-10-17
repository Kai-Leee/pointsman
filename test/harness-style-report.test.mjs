import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {collectArms, mergeArms, scoreRun, sd, summarize, wilson} from '../scripts/harness-style-report.mjs';
import {select} from '../scripts/select-evaluation-tasks.mjs';

const arm = (run, name, fields, passed, failed = []) => {
  const dir = join(run, name);
  mkdirSync(join(dir, 'grade', 'verifier'), {recursive: true});
  writeFileSync(join(dir, 'result.json'), JSON.stringify({schema_version: 'adaptive-arm-result/v1', arm: name, ...fields}));
  if (passed === null) return;
  writeFileSync(join(dir, 'independent-evaluation.json'), JSON.stringify({summary: {tests: 4, passed}, model_calls: 0, product_success: passed === 4}));
  writeFileSync(join(dir, 'grade', 'result.json'), JSON.stringify({task_id: 'openapi_python_client'}));
  const tests = ['TestA::t1', 'TestB::t2', 'TestB::t3', 'TestC::t4']
    .map(name => ({name: `t.py::${name}`, status: failed.includes(name) ? 'failed' : 'passed'}));
  writeFileSync(join(dir, 'grade', 'verifier', 'ctrf.json'), JSON.stringify({results: {tests}}));
};

function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'harness-report-'));
  arm(join(root, 'dx-comparison-01'), 'claude_all', {status: 'completed', product_success: true}, 4);
  arm(join(root, 'dx-comparison-01'), 'jev_all', {status: 'failed', stop_code: 'HTTP_ERROR', product_success: false}, 2, ['TestB::t2', 'TestB::t3']);
  arm(join(root, 'dx-comparison-02'), 'claude_all', {status: 'completed', product_success: false}, 3, ['TestB::t2']);
  arm(join(root, 'dx-comparison-02'), 'jev_all', {status: 'completed', product_success: false}, 3, ['TestC::t4']);
  arm(join(root, 'dx-comparison-03'), 'jev_all', {status: 'failed', stop_code: 'BUDGET_LOCKED'}, null);
  writeFileSync(join(root, 'dx-comparison-01', 'result.json'), JSON.stringify({schema_version: 'adaptive-comparison-result/v2'}));
  return root;
}

const pct = a => a.independent ? {score: 100 * a.independent.passed / a.independent.tests, reason: 'graded'} : {score: null, reason: 'ungraded'};

test('collects only arm results and keeps grading detail', () => {
  const arms = collectArms(fixture());
  assert.deepEqual(arms.map(a => a.id), ['dx-comparison-01/claude_all', 'dx-comparison-01/jev_all',
    'dx-comparison-02/claude_all', 'dx-comparison-02/jev_all', 'dx-comparison-03/jev_all']);
  assert.equal(arms[1].condition, 'dx-comparison/jev_all');
  assert.deepEqual(arms[1].failedClasses, ['TestB', 'TestB']);
  assert.equal(arms[4].independent, null);
});

test('condition stats, paired win rate and failure dimensions', () => {
  const report = summarize(collectArms(fixture()), pct);
  const jev = report.by_condition.find(c => c.condition === 'dx-comparison/jev_all');
  assert.deepEqual([jev.runs, jev.counted, jev.resolved, jev.mean, jev.sd], [3, 2, '0/2', 62.5, 17.7]);
  assert.deepEqual(jev.excluded, ['dx-comparison-03/jev_all: ungraded']);
  assert.deepEqual(report.pairs.map(p => [p.pair, p.wins, p.ties, p.losses]), [['claude_all vs jev_all', 1, 1, 0]]);
  // A class counts once per run even when several of its tests fail.
  assert.deepEqual(report.dimensions.map(d => [d.test_class, d.failed_runs]), [['TestB', 2], ['TestC', 1]]);
});

test('sample SD matches the Harness published case scores', () => {
  // summary-15cases.json case_results[].baseline
  const baseline = [52, 48, 46, 62, 52, 58, 52, 49, 50, 50, 44, 49, 46, 44, 40];
  assert.equal(Math.round(sd(baseline) * 100) / 100, 5.51);
  assert.equal(sd([7]), null);
});

test('scoreRun keeps graded arms on the 0-100 independent scale', () => {
  const [graded] = collectArms(fixture());
  assert.equal(scoreRun(graded).score, 100);
});

test('scoreRun follows the protocol inclusion rule for ungraded arms', () => {
  const ungraded = stop_code => scoreRun({independent: null, status: 'failed', stop_code});
  assert.deepEqual(ungraded('ADAPTIVE_ARM_TOKEN_LIMIT'), {score: 0, reason: 'ungraded system stop ADAPTIVE_ARM_TOKEN_LIMIT'});
  assert.equal(ungraded('BUDGET_LOCKED').score, null);
  assert.equal(ungraded('ADAPTIVE_CANCELLED').score, null);
  assert.match(ungraded('SOMETHING_NEW').reason, /^unclassified/);
  // A graded arm counts with its grade even when it stopped with an error.
  assert.equal(scoreRun({independent: {passed: 1, tests: 4}, stop_code: 'BUDGET_LOCKED'}).score, 25);
});

test('planned arms without a result file are listed, not dropped', () => {
  const root = fixture();
  writeFileSync(join(root, 'dx-comparison-03', 'protocol.json'), JSON.stringify({arms: ['jev_all', 'claude_all']}));
  const report = summarize(collectArms(root));
  const missing = report.arms.find(a => a.id === 'dx-comparison-03/claude_all');
  assert.equal(missing.stop_code, 'NO_ARM_RESULT');
  assert.equal(missing.score, null);
  assert.match(report.credibility.find(c => c.id === 'C07').observed, /^6 arms = 4 counted \+ 2 excluded/);
});

test('an unclassified stop code fails C07', () => {
  const root = fixture();
  arm(join(root, 'dx-comparison-04'), 'jev_all', {status: 'failed', stop_code: 'SOMETHING_NEW'}, null);
  const c07 = summarize(collectArms(root)).credibility.find(c => c.id === 'C07');
  assert.equal(c07.jev, 'no');
  assert.match(c07.observed, /1 unclassified$/);
});

test('the same run folder passed twice is rejected', () => {
  const root = fixture();
  assert.throws(() => mergeArms([collectArms(root), collectArms(root)]), /DUPLICATE_ARM dx-comparison-01\/claude_all/);
  assert.equal(mergeArms([collectArms(root)]).length, 5);
});

test('task selection excludes tuning tasks and fills each tier deterministically', () => {
  const tasks = Array.from({length: 12}, (_, i) => ({task: `t${i}`, language: i === 11 ? 'Go' : 'Python', spec_bytes: 1000 * (i + 1)}));
  const rule = {tiers: ['basic', 'advanced', 'expert'], per_tier: 2, seed: 's'};
  const a = select(tasks, rule, ['t0']), b = select(tasks, rule, ['t0']);
  assert.equal(a.population, 10);
  assert.deepEqual(a.selected.map(t => t.task), b.selected.map(t => t.task));
  assert.deepEqual(a.selected.map(t => t.tier), ['basic', 'basic', 'advanced', 'advanced', 'expert', 'expert']);
  assert.ok(a.selected.every(t => t.task !== 't0' && t.task !== 't11'));
});

test('Wilson interval and credibility checklist', () => {
  assert.equal(wilson(0, 0), null);
  assert.deepEqual(wilson(5, 7).map(x => Math.round(x * 1000) / 1000), [0.359, 0.918]);
  const report = summarize(collectArms(fixture()));
  const item = id => report.credibility.find(c => c.id === id);
  assert.equal(report.credibility.length, 14);
  assert.equal(item('C02').jev, 'yes');
  assert.equal(item('C06').jev, 'no'); // 2 counted runs per condition
  assert.equal(item('C12').jev, 'no'); // the only task is the tuning task
  assert.equal(item('C14').jev, 'no');
  assert.match(item('C07').observed, /^5 arms = 4 counted \+ 1 excluded/);
});
