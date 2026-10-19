import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {ROOT, TASKS, paths, buildObligations, validatePlan} from '../scripts/build-heldout-obligations.mjs';

// Rebuilds from the source text embedded in obligations.json, so the gitignored .benchmarks checkout is not needed.
const load = task => {
  const p = paths(task), json = path => JSON.parse(readFileSync(join(ROOT, path), 'utf8'));
  return {p, atoms: json(p.atoms), plan: json(p.plan), text: readFileSync(join(ROOT, p.obligations), 'utf8')};
};

for (const task of TASKS) {
  test(`held-out ${task}: obligations rebuild byte-for-byte and the public-check plan maps every test id`, () => {
    const {atoms, plan, text} = load(task), source = JSON.parse(text).source.text;
    const built = buildObligations(task, {sourceText: source, atoms});
    assert.equal(JSON.stringify(built, null, 2) + '\n', text);
    const result = validatePlan(plan, built);
    assert.equal(result.valid, true, result.issues.join('\n'));
    assert.equal(result.measured.mapped_test_ids, built.tests.length);
  });
}

test('held-out builder rejects an uncovered clause and an unmapped test id', () => {
  const {atoms, plan, text} = load('h2'), source = JSON.parse(text).source.text;
  const last = atoms.atoms.at(-1).id.slice(0, 3);
  const dropped = {...atoms, atoms: atoms.atoms.filter(atom => !atom.id.startsWith(last)),
    integration: atoms.integration.filter(def => def.refs.every(ref => !ref.startsWith(last)))};
  assert.throws(() => buildObligations('h2', {sourceText: source, atoms: dropped}), /has no atom; unclassified substantive lines/);
  const built = buildObligations('h2', {sourceText: source, atoms});
  const partial = {...plan, suites: plan.suites.map((suite, index) => index ? suite : {...suite, test_ids: suite.test_ids.slice(1)})};
  assert.match(validatePlan(partial, built).issues.join('\n'), /unmapped test ids/);
});
