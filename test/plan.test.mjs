import { test } from 'node:test';
import assert from 'node:assert/strict';
import { analyzeCoupling, closingFeedback, estimatePlan, findMissingLinks, shouldSkipJev, validatePlan } from '../src/plan/plan.mjs';
import { renderPlanView } from '../src/plan/view.mjs';

const task = (id, extra = {}) => ({ id, profile: 'claude_sonnet55_medium', writes: [], inputs: [], outputs: [], requirements: [], ...extra });
const codes = (plan) => validatePlan(plan).errors.map((e) => e.code).sort();

test('a valid plan orders tasks by the artifacts they consume', () => {
  const plan = { tasks: [task('b', { inputs: ['A'], writes: ['b.py'] }), task('a', { outputs: ['A'], writes: ['a.py'] })] };
  const result = validatePlan(plan);
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.order, ['a', 'b']);
  assert.deepEqual(result.predecessors, { a: [], b: ['a'] });
});

test('placement errors are reported before any worker starts', () => {
  assert.deepEqual(codes({ tasks: [task('a', { writes: ['x.py'] }), task('b', { writes: ['x.py'] })] }), ['PLAN_WRITE_OVERLAP']);
  assert.deepEqual(codes({ tasks: [task('a', { inputs: ['missing'] })] }), ['PLAN_INPUT_WITHOUT_PRODUCER']);
  assert.deepEqual(codes({ tasks: [task('a', { outputs: ['A'] }), task('b', { outputs: ['A'] })] }), ['PLAN_DUPLICATE_PRODUCER']);
  assert.deepEqual(codes({ tasks: [task('a'), task('a')] }), ['PLAN_DUPLICATE_TASK']);
  assert.deepEqual(codes({ tasks: [task('a', { inputs: ['B'], outputs: ['A'] }), task('b', { inputs: ['A'], outputs: ['B'] })] }), ['PLAN_CYCLE']);
  assert.deepEqual(codes({ requirements: ['R1'], tasks: [task('a', { requirements: ['R2'] })] }), ['PLAN_REQUIREMENT_UNOWNED']);
});

test('imports of another task\'s file without a plan link are found', () => {
  const plan = { tasks: [
    task('n1', { writes: ['pkg/__init__.py', 'pkg/settings.py'] }),
    task('n2', { writes: ['pkg/connection.py'] }),
    task('n3', { writes: ['pkg/stream.py'], outputs: ['S'] }),
    task('n4', { writes: ['web/app.js'], inputs: ['S'] }),
    task('n5', { writes: ['web/util.js'] }),
  ] };
  const files = {
    'pkg/connection.py': 'from .settings import Settings\nfrom pkg.stream import Stream\nimport json\n',
    'pkg/stream.py': 'from . import settings\n',
    'web/app.js': "import { f } from './util';\n",
  };
  const { links, scanned } = findMissingLinks(plan, (path) => files[path] ?? null);
  assert.deepEqual(scanned.sort(), ['pkg/connection.py', 'pkg/stream.py', 'web/app.js']);
  assert.deepEqual(links.map((l) => `${l.task}->${l.needs}:${l.imports}`).sort(),
    ['n2->n1:pkg/settings.py', 'n2->n3:pkg/stream.py', 'n3->n1:pkg/settings.py', 'n4->n5:web/util.js']);
});

test('a linked import is not reported', () => {
  const plan = { tasks: [task('a', { writes: ['m/a.py'], outputs: ['A'] }), task('b', { writes: ['m/b.py'], inputs: ['A'] })] };
  assert.deepEqual(findMissingLinks(plan, (p) => (p === 'm/b.py' ? 'from m.a import x\n' : null)).links, []);
});

test('estimates use recorded medians, schedule two slots and never count unknown profiles as zero', () => {
  const plan = { tasks: [
    task('a', { profile: 'claude_opus55_medium', outputs: ['A'] }),
    task('b', { inputs: ['A'] }), task('c'), task('d'),
  ] };
  const estimate = estimatePlan(plan);
  assert.equal(estimate.tasks.a.seconds, 514); // median of 50, 224, 344, 684, 688, 922
  assert.equal(estimate.tasks.b.seconds, 80); // median of 44, 66, 94, 174
  const end = Object.fromEntries(estimate.schedule.map((s) => [s.task, s]));
  assert.ok(end.b.start >= end.a.end, 'b waits for a');
  assert.equal(estimate.totals.makespan_seconds, 594); // a 0-514 and b 514-594; c and d share the other slot
  assert.equal(estimate.totals.sequential_seconds, 754);
  assert.ok(estimate.totals.usd_saved_vs_all_baseline_profile > 0);
  const unknown = estimatePlan({ tasks: [task('x', { profile: 'nope' })] });
  assert.equal(unknown.totals.usd, null);
  assert.deepEqual(unknown.warnings.map((w) => w.code), ['PLAN_PROFILE_UNRATED']);
});

test('decomposition is skipped for one task or below the recorded fixed overhead', () => {
  assert.deepEqual(shouldSkipJev({ taskCount: 1, estimatedSeconds: 9999 }).reason, 'single_task');
  assert.equal(shouldSkipJev({ taskCount: 3, estimatedSeconds: 100 }).reason, 'below_fixed_overhead');
  assert.equal(shouldSkipJev({ taskCount: 3, estimatedSeconds: 2000 }).skip, false);
});

test('the view lists every task and the closing items', () => {
  const plan = { tasks: [task('a', { writes: ['x.py'] }), task('b', { writes: ['x.py'] })] };
  const validation = validatePlan(plan), estimate = estimatePlan(plan), gaps = { links: [], scanned: [] };
  const feedback = closingFeedback({ validation, gaps, estimate, checks: [{ id: 'c1', passed: false }], reviewChanged: ['x.py'] });
  assert.deepEqual(feedback.map((f) => f.kind), ['plan', 'check', 'review']);
  const html = renderPlanView({ validation, gaps, estimate, skip: shouldSkipJev({ taskCount: 2, estimatedSeconds: 1 }), feedback }, { actual: { a: { start: 0, end: 10 } } });
  for (const text of ['PLAN_WRITE_OVERLAP', 'check failed: c1', 'spec review changed x.py', '>a<', '>b<', 'actual']) assert.ok(html.includes(text), text);
});

test('a task cycle that only comes from grouping is broken by a first task with the shared files', () => {
  const plan = { tasks: [task('a', { writes: ['p/base.py', 'p/a_use.py'] }), task('b', { writes: ['p/b_base.py', 'p/b_use.py'] })] };
  const files = { 'p/a_use.py': 'from p.b_base import B\n', 'p/b_use.py': 'from .base import A\n' };
  const gaps = findMissingLinks(plan, (path) => files[path] ?? null);
  const coupling = analyzeCoupling(plan, gaps);
  assert.deepEqual(coupling.split_file_cycles, []);
  assert.deepEqual(coupling.task_cycles, [{ tasks: ['a', 'b'], foundation_files: ['p/b_base.py', 'p/base.py'], foundation_share: 0.5, resolves_with_foundation_first: true }]);
  const advice = closingFeedback({ validation: validatePlan(plan), gaps, estimate: estimatePlan(plan), coupling }).filter((f) => f.kind === 'coupling');
  assert.match(advice[0].text, /in a first task/);
});

test('files that import each other across tasks must be regrouped', () => {
  const plan = { tasks: [task('a', { writes: ['x.py'] }), task('b', { writes: ['y.py'] })] };
  const files = { 'x.py': 'import y\n', 'y.py': 'import x\n' };
  const gaps = findMissingLinks(plan, (path) => files[path] ?? null);
  const coupling = analyzeCoupling(plan, gaps);
  assert.deepEqual(coupling.split_file_cycles, [['x.py', 'y.py']]);
  const advice = closingFeedback({ validation: validatePlan(plan), gaps, estimate: estimatePlan(plan), coupling }).filter((f) => f.kind === 'coupling').map((f) => f.text);
  assert.match(advice[0], /keep together in one task: x\.py, y\.py/);
  assert.match(advice[1], /fixed interfaces/); // moving every file first would just move the whole group
});
