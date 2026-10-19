#!/usr/bin/env node
// Record-based zero-cost rehearsal before any paid run (R20261018-DESIGN-SELECTION, proposal B).
// Usage: node scripts/rehearse.mjs --manifest <v12.json> --catalog-preparation <dir> --record <run-dir>... --reference <dir>...
//          [--faults baseline,readiness_failure,missing_output,unknown_model_build] <out-dir>
// Real: probe, Docker, task image, readiness/public checks, runner, partial repair, budget.mjs settlement on a ledger copy.
// Doubled: Claude inference and the Jev POST, answered from recorded runs. The shared ledger must not change.
import {copyFileSync, mkdirSync, readFileSync} from 'node:fs';
import {join, relative, resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {loadAdaptiveRunManifest, runAdaptiveArm} from '../src/benchmark/adaptive-dag-runner.mjs';
import {loadRecordedJev, rehearsalAdapters, rehearsalManifest, servedDatedBuild, writeJson} from '../src/benchmark/rehearsal.mjs';
import {loadSettlementModels} from '../src/benchmark/budget.mjs';
import {useAppClaudeCli} from '../src/benchmark/claude-cli.mjs';
import {createJevClient} from '../src/client.mjs';
import {loadConfig} from '../src/config.mjs';

const root = resolve(import.meta.dirname, '..');
const sha = path => createHash('sha256').update(readFileSync(path)).digest('hex');
const git = (...args) => execFileSync('git', ['-C', root, ...args], {encoding: 'utf8'}).trim();
// Expected outcome per fault row: a completed arm, or the exact fail-closed stop the fault must produce.
export const FAULTS = {
  baseline: {status: 'completed'},
  readiness_failure: {status: 'completed'}, // R20261015 partial readiness repair must recover it
  missing_output: {status: 'completed'}, // a never-produced output is repaired by its exact owner (R20261018-REHEARSAL-C)
  unknown_model_build: {stop_code: 'BUDGET_MODEL_UNSUPPORTED'},
};

const args = process.argv.slice(2), take = flag => args.flatMap((arg, i) => arg === flag ? [args[i + 1]] : []);
const out = resolve(root, args.filter((arg, i) => !arg.startsWith('--') && !args[i - 1]?.startsWith('--')).at(-1) ?? '');
const manifestPath = take('--manifest')[0], preparation = take('--catalog-preparation')[0];
const faults = (take('--faults')[0] ?? Object.keys(FAULTS).join(',')).split(',');
if (!manifestPath || !preparation || !take('--reference').length || out === root || faults.some(f => !FAULTS[f]))
  throw new Error('usage: rehearse.mjs --manifest m --catalog-preparation d --record r... --reference d... [--faults f,..] <out-dir>');

const cli = useAppClaudeCli();
const manifest = loadAdaptiveRunManifest(resolve(root, manifestPath), root);
const sharedLedger = resolve(root, manifest.jev_budget.ledger_path), sharedBefore = sha(sharedLedger);
const recorded = loadRecordedJev(take('--record').map(dir => resolve(root, dir)));
const referenceRoots = take('--reference').map(dir => resolve(root, dir));
// Free GETs only (credits); the double never forwards decide().
const real = createJevClient({apiKey: loadConfig().apiKey}), freeClient = {listCredits: () => real.listCredits()};
// The Jev double answers with the dated build served now (free GET /v1/models), not only the recorded IDs.
const listedModels = (await real.listModels()).models.map(model => model.name);
const servedModel = servedDatedBuild(listedModels, [...loadSettlementModels()]);
const rows = [];
mkdirSync(out, {recursive: true});
for (const fault of faults) {
  const directory = join(out, fault), ledgerCopy = join(out, `${fault}-ledger.json`), log = [];
  copyFileSync(sharedLedger, ledgerCopy);
  const result = await runAdaptiveArm({rootDir: root, manifest: rehearsalManifest(manifest, relative(root, ledgerCopy)), runDir: directory,
    arm: manifest.arms[0], preparationDirectory: resolve(root, preparation), spend: true,
    adapters: rehearsalAdapters({recorded, referenceRoots, fault: fault === 'baseline' ? null : fault, log, freeClient, servedModel})});
  const expect = FAULTS[fault];
  const matched = expect.status ? result.status === expect.status : result.stop_code === expect.stop_code;
  rows.push({fault, arm: manifest.arms[0], status: result.status, stop_code: result.stop_code ?? null,
    terminal_cause: result.terminal_cause ?? null, public_status: result.public_status ?? null, expected: expect, matched,
    unmapped_paths: [...new Set(log.filter(e => e.source === 'unmapped').map(e => e.path))],
    jev_models: [...new Set(log.filter(e => e.boundary === 'jev').map(e => e.model))]});
  writeJson(join(directory, 'rehearsal-log.json'), log);
}
const sharedAfter = sha(sharedLedger);
const report = {schema_version: 'rehearsal/v1', created_at: new Date().toISOString(),
  head: git('rev-parse', 'HEAD'), git_tree: git('rev-parse', 'HEAD^{tree}'), clean: git('status', '--porcelain', '--untracked-files=no') === '',
  manifest_path: manifestPath, manifest_sha256: sha(resolve(root, manifestPath)),
  image_id: JSON.parse(readFileSync(resolve(root, manifest.image_lock), 'utf8')).image_id, cli,
  recorded_models: recorded.models, listed_models: listedModels, served_model: servedModel, record_runs: take('--record'), reference_roots: take('--reference'),
  shared_ledger_sha256_before: sharedBefore, shared_ledger_sha256_after: sharedAfter, rows,
  passed: rows.every(row => row.matched) && sharedBefore === sharedAfter};
writeJson(join(out, 'rehearsal.json'), report);
console.log(JSON.stringify({passed: report.passed, rows: rows.map(r => [r.fault, r.status, r.stop_code, r.matched]),
  shared_ledger_unchanged: sharedBefore === sharedAfter}));
process.exitCode = report.passed ? 0 : 2;
