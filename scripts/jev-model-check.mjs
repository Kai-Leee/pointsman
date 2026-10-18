#!/usr/bin/env node
// Pre-experiment Jev model check. FREE GETs only: GET /v1/models and the public docs page.
// Never POSTs, never prints the key or Authorization header, never touches the budget ledger.
// Exit 0: nothing missing. Exit 3: a documented dated build, or a listed jev-X.Y[.Z] version, has no contract entry.
// Exit 2: check failed. --update appends only dated builds whose exact ID and multiplier the docs give.
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createJevClient } from '../src/client.mjs';
import { loadConfig } from '../src/config.mjs';
import { JEV_SETTLEMENT_MODELS_CONTRACT, loadSettlementModels } from '../src/benchmark/budget.mjs';

export const DOCS_URL = 'https://jev-ai.pro/docs';
const ROOT = fileURLToPath(new URL('..', import.meta.url));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');

// Any non-GET request is refused before it reaches the network.
export const getOnly = fetchImpl => (url, init = {}) => (init.method ?? 'GET') === 'GET'
  ? fetchImpl(url, init) : Promise.reject(Object.assign(new Error('NON_GET_REFUSED'), { code: 'NON_GET_REFUSED' }));

const pageText = html => html.replace(/<[^>]*>/g, ' ').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/\s+/g, ' ');

/** Dated builds named in the docs, each with its multiplier only when exactly one rate row gives it. */
export function parseDocs(html) {
  const text = pageText(html);
  const ids = [...new Set([...text.matchAll(/\btypesafe\/jev-(\d+\.\d+)-(\d{8})(?![\w\/-]|\.\w)/g)].map(m => m[0]))];
  return ids.map(model_id => {
    const version = model_id.match(/jev-(\d+\.\d+)-/)[1];
    const rates = [...text.matchAll(new RegExp(`\\bJev ${version.replace('.', '\\.')} (\\d+(?:\\.\\d+)?)×`, 'g'))].map(m => Number(m[1]));
    const distinct = [...new Set(rates)];
    return { model_id, version, multiplier: distinct.length === 1 ? distinct[0] : null,
      reason: distinct.length === 1 ? null : distinct.length ? 'MULTIPLIER_AMBIGUOUS' : 'MULTIPLIER_NOT_FOUND' };
  });
}

export async function runModelCheck({ client, fetchImpl, contractPath = JEV_SETTLEMENT_MODELS_CONTRACT,
  evidenceRoot = join(ROOT, 'benchmark-runs'), update = false, now = new Date() }) {
  const get = getOnly(fetchImpl);
  const listed = (await client.listModels()).models.map(model => model.name);
  let response;
  try { response = await get(DOCS_URL, { method: 'GET', redirect: 'error', signal: AbortSignal.timeout(30000) }); }
  catch { throw Object.assign(new Error('DOCS_FETCH_FAILED'), { code: 'DOCS_FETCH_FAILED' }); }
  if (!response.ok) throw Object.assign(new Error('DOCS_FETCH_FAILED'), { code: 'DOCS_FETCH_FAILED', status: response.status });
  const bytes = Buffer.from(await response.arrayBuffer());
  const docs = parseDocs(bytes.toString('utf8'));
  const known = new Set(loadSettlementModels(contractPath));
  const missing = docs.filter(build => !known.has(build.model_id));
  const added = [], refused = [];
  if (update && missing.length) {
    for (const build of missing) {
      if (build.multiplier === null) refused.push({ model_id: build.model_id, reason: build.reason });
      // The ledger valuation assumes 1x; budget.mjs rejects any other multiplier in the contract.
      else if (build.multiplier !== 1) refused.push({ model_id: build.model_id, reason: 'MULTIPLIER_UNSUPPORTED', multiplier: build.multiplier });
      else added.push(build);
    }
    if (added.length) {
      const digest = sha256(bytes), date = now.toISOString().slice(0, 10);
      const directory = join(evidenceRoot, `jev-model-check-${date}`);
      const evidencePath = join(directory, `docs-${digest.slice(0, 12)}.html`);
      mkdirSync(directory, { recursive: true });
      writeFileSync(evidencePath, bytes);
      writeFileSync(`${evidencePath}.sha256`, `${digest}  ${DOCS_URL}\n`);
      const contract = JSON.parse(readFileSync(contractPath, 'utf8'));
      for (const build of added) contract.models.push({ model_id: build.model_id, kind: 'dated_build', multiplier: build.multiplier,
        verified_at: date, evidence_url: `${DOCS_URL}#models`, evidence_sha256: digest,
        evidence_note: `Added by scripts/jev-model-check.mjs --update from saved docs ${relative(ROOT, evidencePath)}.` });
      const target = contractPath instanceof URL ? fileURLToPath(contractPath) : contractPath;
      writeFileSync(`${target}.tmp`, `${JSON.stringify(contract, null, 2)}\n`);
      renameSync(`${target}.tmp`, target);
      loadSettlementModels(contractPath); // fail loudly if the written contract would not load
    }
  }
  const stillMissing = missing.filter(build => !added.includes(build));
  // A listed pinned version jev-X.Y[.Z] needs a dated_build or legacy_id entry for the same X.Y.
  // Moving aliases (jev-latest, jev-preview) are reported but neither need nor give coverage.
  const entries = JSON.parse(readFileSync(contractPath, 'utf8')).models;
  const covered = version => entries.some(({ model_id, kind }) => (kind === 'dated_build' || kind === 'legacy_id')
    && (model_id.match(/^typesafe\/jev-(\d+\.\d+)-\d{8}$/) ?? model_id.match(/^jev-(\d+\.\d+)(?:\.\d+)?$/))?.[1] === version);
  const uncovered = listed.filter(name => /^jev-\d+\.\d+(?:\.\d+)?$/.test(name) && !covered(name.match(/^jev-(\d+\.\d+)/)[1]));
  const exitCode = stillMissing.length || uncovered.length ? 3 : 0;
  return {
    exitCode,
    report: { listed_models: listed, listed_not_in_contract: listed.filter(name => !known.has(name)),
      listed_versions_without_contract_entry: uncovered,
      docs_url: DOCS_URL, docs_sha256: sha256(bytes), docs_dated_builds: docs,
      missing_from_contract: stillMissing.map(build => build.model_id), added: added.map(build => build.model_id), refused,
      ...(exitCode === 3 ? { message: 'Settlement contract does not cover every listed Jev version or documented dated build; do not start a paid run. '
        + 'A dated build is learned only from the first paid response (response.model); that response stays fail-closed '
        + '(BUDGET_MODEL_UNSUPPORTED) and is reconciled offline with scripts/reconcile-d086-response.mjs. '
        + '--update adds only exact dated IDs proven by saved docs evidence.' } : {}) },
  };
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? '').href) {
  try {
    const fetchImpl = getOnly(globalThis.fetch);
    const client = createJevClient({ apiKey: loadConfig().apiKey, fetchImpl });
    const { exitCode, report } = await runModelCheck({ client, fetchImpl, update: process.argv.includes('--update') });
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = exitCode;
  } catch (error) {
    // Print only the code: transport errors may carry request details.
    console.error(JSON.stringify({ error: error?.code ?? 'CHECK_FAILED', status: error?.status ?? null }));
    process.exitCode = 2;
  }
}
