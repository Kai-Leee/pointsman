import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, mkdirSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {assertRehearsal, loadRecordedJev, rehearsalAdapters, UNKNOWN_MODEL_BUILD} from '../src/benchmark/rehearsal.mjs';

const now = Date.parse('2026-10-18T12:00:00Z');
const report = {schema_version: 'rehearsal/v1', created_at: '2026-10-18T06:00:00Z', passed: true, clean: true,
  git_tree: 't1', manifest_sha256: 'm1', image_id: 'i1', rows: [{fault: 'baseline', matched: true}]};
const current = {git_tree: 't1', clean: true, manifest_sha256: 'm1', image_id: 'i1', mainline_ancestor: true};

test('spend gate accepts only a fresh, passing rehearsal of the same clean tree on the main line', () => {
  assert.equal(assertRehearsal(report, current, {now}), true);
  const code = (r, c = current) => { try { assertRehearsal(r, c, {now}); } catch (e) { return e.code; } };
  assert.equal(code(null), 'REHEARSAL_REQUIRED');
  assert.equal(code({...report, passed: false}), 'REHEARSAL_NOT_PASSED');
  assert.equal(code({...report, rows: [{matched: false}]}), 'REHEARSAL_NOT_PASSED');
  assert.equal(code({...report, created_at: '2026-10-17T06:00:00Z'}), 'REHEARSAL_STALE');
  assert.equal(code(report, {...current, git_tree: 't2'}), 'REHEARSAL_MISMATCH');
  assert.equal(code(report, {...current, clean: false}), 'REHEARSAL_MISMATCH');
  assert.equal(code(report, {...current, manifest_sha256: 'm2'}), 'REHEARSAL_MISMATCH');
  assert.equal(code(report, {...current, mainline_ancestor: false}), 'SOURCE_NOT_ON_MAINLINE');
});

test('recorded Jev answers and model ids drive the Jev double; unknown_model_build swaps in an unlisted build', async () => {
  const run = mkdtempSync(join(tmpdir(), 'rehearsal-rec-'));
  mkdirSync(join(run, 'calls'));
  writeFileSync(join(run, 'calls/jev-0001.response.json'), JSON.stringify({model: 'typesafe/jev-1.14-20261014',
    answers: {q1: {type: 'choice', choice: 'b', confidence: 0.9}}}));
  const recorded = loadRecordedJev([run, join(run, 'missing')]);
  assert.deepEqual(recorded.models, ['typesafe/jev-1.14-20261014']);
  const body = {questions: {q1: {criteria: {a: 'x', b: 'y'}}, q2: {criteria: {c: 'x', d: 'y'}}}};
  const replayed = await rehearsalAdapters({recorded, referenceRoots: []}).jevClientFactory().decide(body);
  assert.equal(replayed.model, 'typesafe/jev-1.14-20261014');
  assert.equal(replayed.answers.q1.choice, 'b'); // recorded answer reused
  assert.equal(replayed.answers.q2.choice, 'c'); // unrecorded question: first allowed key
  assert.equal(replayed.billing.paidInputTokensUsed, String(replayed.usage.input_tokens));
  const unknown = await rehearsalAdapters({recorded, referenceRoots: [], fault: 'unknown_model_build'}).jevClientFactory().decide(body);
  assert.equal(unknown.model, UNKNOWN_MODEL_BUILD);
});
