import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {loadAdaptiveRunManifest, loadAdaptiveSharedPreparation} from '../src/benchmark/adaptive-dag-runner.mjs';
import {ROOT, TASKS, paths} from '../scripts/build-heldout-obligations.mjs';

// The loader's only benchmark-runs/ read is the model account probe; a synthetic receipt in a temp root replaces it,
// so the gitignored benchmark-runs/ folder (and the shared ledger in it) is never opened.
const PROBE = 'benchmark-runs/d071-model-probes-01/result.json';
const OPENAPI = 'benchmarks/e2e-swe/manifests/d083-repair-fixes.json';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const json = path => JSON.parse(readFileSync(join(ROOT, path), 'utf8'));

function tempRoot(t) {
  const root = mkdtempSync(join(tmpdir(), 'heldout-loader-'));
  t.after(() => rmSync(root, {recursive: true, force: true}));
  for (const name of ['docs', 'benchmarks']) symlinkSync(join(ROOT, name), join(root, name));
  const models = ['claude-fable-5-1', 'claude-haiku-5-5', 'claude-opus-5-5', 'claude-sonnet-5-5'];
  const probe = Buffer.from(JSON.stringify({schema_version: 'd071-model-account-probes/v1', cli_version: json(OPENAPI).profile_policy.cli_version,
    receipts: models.map(model => ({requested_model: model, status: 'completed', model_identity_verified: true}))}));
  mkdirSync(join(root, 'benchmark-runs/d071-model-probes-01'), {recursive: true});
  writeFileSync(join(root, PROBE), probe);
  const load = (manifestPath, change = value => value) => {
    const value = change(structuredClone(json(manifestPath)));
    value.profile_policy.account_probe_sha256 = sha(probe);
    const path = join(root, 'manifest.json');
    writeFileSync(path, JSON.stringify(value));
    return loadAdaptiveRunManifest(path, root);
  };
  return {root, load};
}

const pointAt = (task, value) => {
  const p = paths(task);
  return {...value, public_checker_root: p.checker, public_registry: p.registry, public_runner: p.runner,
    public_environment_ref: `e2e-swe-public-${task}/v1`};
};

test('held-out v12 drafts load against their own registries before any catalog is prepared', t => {
  const {root, load} = tempRoot(t);
  for (const task of TASKS) {
    const manifest = load(paths(task).manifest);
    assert.equal(manifest.input, paths(task).obligations);
    assert.equal(manifest.catalog_reuse.result_sha256, null);
    // No arm may start on an unpinned catalog, whatever preparation directory is offered.
    assert.throws(() => loadAdaptiveSharedPreparation({rootDir: root, manifest, preparationDirectory: join(root, 'missing')}),
      {code: 'ADAPTIVE_CATALOG_REUSE_UNPINNED'});
  }
});

test('a held-out manifest pointed at another task\'s public registry is rejected', t => {
  const {load} = tempRoot(t);
  const openapi = value => ({...value, public_checker_root: 'benchmarks/e2e-swe/public-checks',
    public_registry: 'benchmarks/e2e-swe/public-checks/registry.v4.json',
    public_runner: 'benchmarks/e2e-swe/public-checks/run_public_checks_v4.py', public_environment_ref: 'e2e-swe-public-python/v2'});
  // Before R20261017-EVAL-PROTOCOL this combination loaded and would have run 93 openapi checks on an h2 candidate.
  assert.throws(() => load(paths('h2').manifest, openapi), {code: 'ADAPTIVE_PUBLIC_REGISTRY_BINDING'});
  assert.throws(() => load(paths('h2').manifest, value => pointAt('pycparser', value)), {code: 'ADAPTIVE_PUBLIC_REGISTRY_BINDING'});
  // R20261015 partial readiness repair is a v12-only opt-in with one allowed value.
  assert.equal(load(paths('h2').manifest, value => ({...value, partial_repair: 'local-readiness-v1'})).partial_repair, 'local-readiness-v1');
  assert.throws(() => load(paths('h2').manifest, value => ({...value, partial_repair: 'other'})), {code: 'ADAPTIVE_PARTIAL_REPAIR_BINDING'});
  // R20261019 token admission: v4 or the jev-1.14 v5 contract only.
  const admission = contract => value => ({...value, repair_policy: {...value.repair_policy, token_admission_contract: contract}});
  for (const version of ['v4', 'v5']) assert.equal(load(paths('h2').manifest, admission(`docs/orchestration/contracts/jev-token-admission.${version}.json`))
    .repair_policy.token_admission_contract, `docs/orchestration/contracts/jev-token-admission.${version}.json`);
  assert.throws(() => load(paths('h2').manifest, admission('docs/orchestration/contracts/jev-token-admission.v3.json')), {code: 'ADAPTIVE_MANIFEST_INVALID'});
  // A registry outside the manifest's own checker root fails the path rule.
  assert.throws(() => load(paths('h2').manifest, value => ({...value, public_registry: paths('pycparser').registry})),
    {code: 'ADAPTIVE_MANIFEST_INVALID'});
});

test('openapi manifests keep the exact registry.v4 gate and still require a pinned catalog', t => {
  const {load} = tempRoot(t);
  assert.equal(load(OPENAPI).public_registry, 'benchmarks/e2e-swe/public-checks/registry.v4.json');
  assert.throws(() => load(OPENAPI, value => pointAt('h2', value)), {code: 'ADAPTIVE_MANIFEST_INVALID'});
  assert.throws(() => load(OPENAPI, value => ({...value, catalog_reuse: {...value.catalog_reuse, result_sha256: null,
    catalog_file_sha256: null, source_pins_sha256: null, prepared_request_sha256: null, provider_request_sha256: null,
    original_manifest_sha256: null}})), {code: 'ADAPTIVE_MANIFEST_INVALID'});
});
