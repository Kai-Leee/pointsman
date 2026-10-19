import test from 'node:test';
import assert from 'node:assert/strict';
import { copyFileSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createTokenBudget, JEV_SETTLEMENT_MODELS, JEV_SETTLEMENT_MODELS_CONTRACT, loadSettlementModels } from '../src/benchmark/budget.mjs';
import { createJevClient } from '../src/client.mjs';
import { MODELS_URL } from '../src/config.mjs';
import { DOCS_URL, getOnly, runModelCheck } from '../scripts/jev-model-check.mjs';

const NEW_BUILD = 'typesafe/jev-1.15-20261101';
const RATES = [['Jev', 1], ['Jev 1.15', 1], ['Jev 1.14', 1], ['Jev 1.13', 1], ['Clef', 6]];
const page = (body, rows = RATES) => `<html><body><section class="jev-model-rates"><table>${
  rows.map(([name, rate]) => `<tr><td>${name}</td><td>${rate}×</td><td>${rate}</td></tr>`).join('')}</table></section><p>${body}</p></body></html>`;
const temp = t => { const directory = mkdtempSync(join(tmpdir(), 'jev-model-check-')); t.after(() => rmSync(directory, { recursive: true, force: true })); return directory; };

function fixture(t, html, listed = ['jev-latest', 'jev-1.14.0']) {
  const directory = temp(t);
  const contractPath = join(directory, 'contract.json');
  copyFileSync(fileURLToPath(JEV_SETTLEMENT_MODELS_CONTRACT), contractPath);
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    calls.push({ url, method: init.method ?? 'GET', authorization: init.headers?.Authorization ?? null });
    if (url === MODELS_URL) return new Response(JSON.stringify({ models: listed.map(name => ({ name })) }), { status: 200 });
    if (url === DOCS_URL) return new Response(html, { status: 200 });
    return new Response('not found', { status: 404 });
  };
  // The real client over a fake transport, so a stray decide() POST would be visible in calls.
  const client = createJevClient({ apiKey: 'test-key-not-real', fetchImpl });
  const run = (update, options = {}) => runModelCheck({ client, fetchImpl, contractPath, evidenceRoot: join(directory, 'runs'), update,
    now: new Date('2026-11-02T00:00:00Z'), ...options });
  return { directory, contractPath, calls, run, contract: () => JSON.parse(readFileSync(contractPath, 'utf8')) };
}

test('settlement contract keeps exact-match semantics: aliases and future builds are rejected', t => {
  assert.deepEqual([...JEV_SETTLEMENT_MODELS], ['jev-1.13.0', 'typesafe/jev-1.13-20260917', 'typesafe-ai/jev', 'typesafe/jev-1.14-20261014']);
  const response = model => ({ model, usage: { input_tokens: 100, output_tokens: 1 },
    billing: { mode: 'tokens', modelMultiplier: '1', creditsCharged: '0', paidInputTokensUsed: '100', runId: 'provider-run-1' },
    receipt: { method: 'POST', destination: 'https://jev-ai.pro/api/v1/systemone', status: 200, automaticRetries: 0, durationMs: 5 } });
  const balances = { paidInputTokensRemaining: 60_000_000, tokensReserved: 0, tokenDebt: 0, spending_frozen: false };
  const linkage = { request_id: 'request-1', run_id: 'run', attempt_id: 'attempt-1', group_id: 'group' };
  const open = () => { const budget = createTokenBudget({ schema_version: 'jev-token-budget/v1', ledger_path: join(temp(t), 'ledger.json'),
    max_usd: 1, usd_per_million_input_tokens: 0.6, reserve_input_tokens: 65536 }); t.after(() => { try { budget.close(); } catch {} }); return budget; };
  for (const model of ['jev-latest', 'jev-preview', 'jev-1.14.0', 'typesafe/jev-1.14', 'typesafe/jev-latest',
    'typesafe/jev-1.14-20261101', 'typesafe/jev-1.14-20261014-extra', 'typesafe/jev-1.14-2026101', NEW_BUILD]) {
    const budget = open();
    assert.throws(() => budget.settle(budget.reserve(linkage, balances), response(model)), { code: 'BUDGET_MODEL_UNSUPPORTED' }, model);
  }
  const budget = open();
  budget.settle(budget.reserve(linkage, balances), response('typesafe/jev-1.14-20261014'));
  assert.equal(budget.snapshot().charged_input_tokens, 100);
});

test('contract loader rejects non-1x multipliers, unknown kinds, non-exact matching, duplicates and missing evidence', t => {
  const directory = temp(t), base = JSON.parse(readFileSync(JEV_SETTLEMENT_MODELS_CONTRACT, 'utf8'));
  for (const mutate of [v => { v.models[0].multiplier = 3; }, v => { v.models[0].kind = 'alias'; }, v => { v.models.push(v.models[0]); },
    v => { v.matching = 'prefix'; }, v => { delete v.models[3].evidence_note; }, v => { v.models[1].evidence_sha256 = 'abc'; }]) {
    const value = structuredClone(base); mutate(value);
    const path = join(directory, 'bad.json'); writeFileSync(path, JSON.stringify(value));
    assert.throws(() => loadSettlementModels(path), /JEV_SETTLEMENT_MODELS_CONTRACT_INVALID/);
  }
});

test('a dated build in the docs that is missing from the contract makes the check exit 3 without changing anything', async t => {
  const fx = fixture(t, page(`Pin <code>${NEW_BUILD}</code> or typesafe/jev-1.13-20260917.`));
  const before = readFileSync(fx.contractPath);
  const { exitCode, report } = await fx.run(false);
  assert.equal(exitCode, 3);
  assert.deepEqual(report.missing_from_contract, [NEW_BUILD]);
  assert.deepEqual(report.docs_dated_builds.map(b => [b.model_id, b.multiplier]), [[NEW_BUILD, 1], ['typesafe/jev-1.13-20260917', 1]]);
  assert.deepEqual(report.listed_models, ['jev-latest', 'jev-1.14.0']);
  assert.deepEqual(report.listed_not_in_contract, ['jev-latest', 'jev-1.14.0']);
  assert.deepEqual(readFileSync(fx.contractPath), before);
  assert.throws(() => readdirSync(join(fx.directory, 'runs')), { code: 'ENOENT' });
});

test('nothing missing exits 0', async t => {
  const fx = fixture(t, page('Aliases: typesafe/jev-1.13-20260917 → jev-1.13.0.'));
  const { exitCode, report } = await fx.run(false);
  assert.equal(exitCode, 0);
  assert.deepEqual(report.missing_from_contract, []);
});

test('--update appends the exact dated build with saved docs evidence and its sha256', async t => {
  const html = page(`Pin <code>${NEW_BUILD}</code>.`);
  const fx = fixture(t, html);
  const { exitCode, report } = await fx.run(true);
  assert.equal(exitCode, 0);
  assert.deepEqual(report.added, [NEW_BUILD]);
  const digest = createHash('sha256').update(html).digest('hex');
  const entry = fx.contract().models.at(-1);
  assert.deepEqual({ ...entry, evidence_note: undefined }, { model_id: NEW_BUILD, kind: 'dated_build', multiplier: 1, verified_at: '2026-11-02',
    evidence_url: `${DOCS_URL}#models`, evidence_sha256: digest, evidence_note: undefined });
  const evidenceDir = join(fx.directory, 'runs', 'jev-model-check-2026-11-02');
  const saved = readdirSync(evidenceDir).find(name => name.endsWith('.html'));
  assert.equal(createHash('sha256').update(readFileSync(join(evidenceDir, saved))).digest('hex'), digest);
  assert.match(readFileSync(join(evidenceDir, `${saved}.sha256`), 'utf8'), new RegExp(`^${digest} `));
  assert.ok(loadSettlementModels(fx.contractPath).includes(NEW_BUILD));
  assert.equal((await fx.run(false)).exitCode, 0);
});

test('an ambiguous or incomplete docs page refuses to update', async t => {
  for (const [html, reason] of [
    [page(`Pin ${NEW_BUILD}.`, [['Jev 1.15', 1], ['Jev 1.15', 2]]), 'MULTIPLIER_AMBIGUOUS'],
    [page(`Pin ${NEW_BUILD}.`, [['Jev 1.13', 1]]), 'MULTIPLIER_NOT_FOUND'],
    [page(`Pin ${NEW_BUILD}.`, [['Jev 1.15', 3]]), 'MULTIPLIER_UNSUPPORTED'],
  ]) {
    const fx = fixture(t, html), before = readFileSync(fx.contractPath);
    const { exitCode, report } = await fx.run(true);
    assert.equal(exitCode, 3, reason);
    assert.equal(report.refused[0].reason, reason);
    assert.deepEqual(report.added, []);
    assert.deepEqual(readFileSync(fx.contractPath), before);
  }
  // Undated or malformed names are never treated as dated builds.
  const fx = fixture(t, page('Use jev-1.15.0, typesafe/jev-1.15, typesafe/jev-1.15-2026110 or typesafe/jev-1.15-20261101-rc.'));
  const { exitCode, report } = await fx.run(true);
  assert.equal(exitCode, 0);
  assert.deepEqual(report.docs_dated_builds, []);
});

test('the check makes only GET requests, never a POST, and never sends the key to the docs page', async t => {
  const fx = fixture(t, page(`Pin ${NEW_BUILD}.`));
  await fx.run(true);
  assert.deepEqual(fx.calls.map(call => `${call.method} ${call.url}`), [`GET ${MODELS_URL}`, `GET ${DOCS_URL}`]);
  assert.equal(fx.calls[1].authorization, null);
  const reached = [];
  await assert.rejects(getOnly(async url => { reached.push(url); })('https://jev-ai.pro/api/v1/systemone', { method: 'POST' }), { code: 'NON_GET_REFUSED' });
  assert.deepEqual(reached, []);
});

test('a listed Jev version without a same-version contract entry exits 3; moving aliases never need coverage', async t => {
  const docs = page('Aliases: typesafe/jev-1.13-20260917 → jev-1.13.0.');
  for (const [listed, exitCode, uncovered] of [
    [['jev-latest', 'jev-1.15.0', 'jev-1.14.0'], 3, ['jev-1.15.0']],
    [['jev-1.15'], 3, ['jev-1.15']],
    [['jev-1.14.0', 'jev-1.13.0', 'clef'], 0, []],
    [['jev-preview'], 0, []],
  ]) {
    const fx = fixture(t, docs, listed);
    const { exitCode: code, report } = await fx.run(false);
    assert.equal(code, exitCode, listed.join());
    assert.deepEqual(report.listed_versions_without_contract_entry, uncovered);
    if (exitCode === 3) assert.match(report.message, /first paid response.*fail-closed.*reconcile-d086-response\.mjs/);
  }
  // Coverage never relaxes settlement: jev-1.14.0 itself stays unsettleable.
  assert.equal(JEV_SETTLEMENT_MODELS.includes('jev-1.14.0'), false);
});

test('a settlement model of a listed version that token admission does not accept exits 3 (the openapi-partial-repair-01 gap)', async t => {
  const docs = page('Aliases: typesafe/jev-1.13-20260917 → jev-1.13.0.');
  const v4 = 'docs/orchestration/contracts/jev-token-admission.v4.json';
  // Admission v4 accepts only 1.13 labels, so a listed 1.14 with a settlement entry must block before any paid run.
  const blocked = await fixture(t, docs, ['jev-latest', 'jev-1.14.0', 'jev-1.13.0']).run(false, { admissionContract: v4 });
  assert.equal(blocked.exitCode, 3);
  assert.deepEqual(blocked.report.settlement_models_not_admitted, ['typesafe/jev-1.14-20261014']);
  assert.match(blocked.report.message, /token-admission policy does not accept a settlement model/);
  // Only listed versions count: with 1.14 unlisted, v4 covers every reachable settlement model.
  assert.equal((await fixture(t, docs, ['jev-latest', 'jev-1.13.0']).run(false, { admissionContract: v4 })).exitCode, 0);
  // The default (v5) admits the 1.14 build.
  const ok = await fixture(t, docs, ['jev-latest', 'jev-1.14.0', 'jev-1.13.0']).run(false);
  assert.equal(ok.exitCode, 0); assert.deepEqual(ok.report.settlement_models_not_admitted, []);
  assert.equal(ok.report.admission_policy_id, 'r20261019-jev114-observed-build-v5');
  await assert.rejects(fixture(t, docs).run(false, { admissionContract: 'docs/orchestration/contracts/jev-token-admission.v3.json' }),
    { code: 'ADMISSION_CONTRACT_UNKNOWN' });
});
