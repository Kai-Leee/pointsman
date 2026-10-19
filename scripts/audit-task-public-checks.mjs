// Public-check audit bound to a run manifest. d056 (openapi) manifests go to audit-dag-public-checks.mjs
// unchanged, so its bytes, and every frozen openapi control receipt that pins them, stay valid. Any other
// input (the held-out E2E-SWE tasks) is audited against its own checker root, inventory and receipts.
// Never opens hidden graders.
import {createHash, randomUUID} from 'node:crypto';
import {readFileSync, existsSync, readdirSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {publicCheckMapping} from '../src/orchestration/dag-contracts.mjs';
import * as openapi from './audit-dag-public-checks.mjs';

export const MANIFEST = openapi.MANIFEST;
const ROOT = openapi.ROOT, BASE = openapi.BASE;
const hash = input => createHash('sha256').update(input).digest('hex');
const json = path => JSON.parse(readFileSync(path, 'utf8'));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const sorted = values => [...values].sort();
const suiteOf = check => check.argv[check.argv.indexOf('--suite') + 1];
const fail = (code, message = code) => { throw Object.assign(new Error(message), {code,
  ...(['PUBLIC_CONTROL_DOCKER_CLEANUP_UNCONFIRMED', 'PUBLIC_CONTROL_OUTCOME_UNCERTAIN'].includes(code) ? {outcome_uncertain: true} : {})}); };

/** Audit options a run manifest binds: d056 inputs keep the openapi options; any other input names its own checker root. */
export const manifestAuditOptions = manifest => ({registryPath: manifest.public_registry, runnerPath: manifest.public_runner,
  ...(manifest.input !== MANIFEST ? {inputPath: manifest.input, checkerRoot: manifest.public_checker_root} : {})});
const isTask = options => options?.inputPath !== undefined && options.inputPath !== MANIFEST;

export function taskAuditConfiguration({registryPath, runnerPath, inventoryPath, inputPath, checkerRoot} = {}) {
  const inventory = checkerRoot + '/inventory.json';
  if (typeof checkerRoot !== 'string' || !checkerRoot || checkerRoot === BASE || checkerRoot.split('/').includes('..')
      || ![registryPath, runnerPath].every(path => typeof path === 'string' && path.startsWith(checkerRoot + '/') && !path.split('/').includes('..'))
      || (inventoryPath !== undefined && inventoryPath !== inventory)) fail('PUBLIC_AUDIT_CONFIGURATION_INVALID');
  return {publicGateVersion: '1', inputPath, checkerRoot, registryPath, runnerPath, inventoryPath: inventory,
    controlRunnerPath: checkerRoot + '/run_control_batch.py', controlCatalogPath: checkerRoot + '/controls/catalog.json',
    assertionContractPath: checkerRoot + '/assertions.json'};
}

function runJson(command, args, {cwd, timeout = 120_000} = {}) {
  const result = spawnSync(command, args, {cwd, encoding: 'utf8', timeout, maxBuffer: 64 * 1024 * 1024});
  if (result.error) fail(result.error.code === 'ETIMEDOUT' ? 'PUBLIC_CONTROL_OUTCOME_UNCERTAIN' : 'PUBLIC_CHECK_PROCESS_ERROR', result.error.message);
  let report;
  try { report = JSON.parse(result.stdout); } catch { fail('PUBLIC_CHECK_INVALID_JSON', result.stderr.slice(-1000)); }
  return {result, report};
}

function loadTaskInputs(root, options) {
  const configuration = taskAuditConfiguration(options);
  const manifestBytes = readFileSync(resolve(root, configuration.inputPath)), manifest = JSON.parse(manifestBytes);
  if (hash(readFileSync(resolve(root, manifest.source.path))) !== manifest.source.sha256) fail('PUBLIC_ORIGINAL_SOURCE_CHANGED');
  const inventory = json(resolve(root, configuration.inventoryPath)), registry = json(resolve(root, configuration.registryPath));
  if (inventory.public_source_sha256 !== manifest.source.sha256 || inventory.input_sha256 !== hash(manifestBytes)) fail('PUBLIC_INVENTORY_PIN_MISMATCH');
  for (const check of registry) {
    for (const path of [check.runner_ref, check.cwd, check.source_ref]) {
      if (!existsSync(resolve(root, path))) fail('PUBLIC_CHECK_PATH_MISSING', path);
    }
    if (check.source_ref !== manifest.source.path) fail('PUBLIC_CHECK_SOURCE_MISMATCH');
    if (check.runner_ref !== configuration.runnerPath || check.argv?.[1] !== configuration.runnerPath.split('/').at(-1)
        || check.version !== configuration.publicGateVersion || check.cwd !== configuration.checkerRoot) fail('PUBLIC_RUNNER_VERSION_DRIFT');
  }
  const {result, report: runnerInventory} = runJson('python3', ['-B', resolve(root, configuration.runnerPath), '--list'], {cwd: root, timeout: 10_000});
  if (result.status !== 0) fail('PUBLIC_RUNNER_INVENTORY_FAILED');
  return {manifest, inventory, registry, runnerInventory, configuration};
}

export function loadPublicAuditInputs(root = ROOT, options = {}) {
  return isTask(options) ? loadTaskInputs(root, options) : openapi.loadPublicAuditInputs(root, options);
}

/** Same row/registry/runner agreement rules as the openapi audit, with the task's own test count. */
function inspectTaskMapping({manifest, inventory, registry, runnerInventory, configuration}) {
  if (inventory?.schema_version !== 'dag-public-check-inventory/v1' || inventory.execution_target !== 'authored_local_control' || !Array.isArray(inventory.rows)
      || !Array.isArray(manifest.tests) || !Array.isArray(registry)) fail('INVALID_PUBLIC_INVENTORY');
  const tests = new Map(manifest.tests.map(test => [test.id, test]));
  if (!tests.size || tests.size !== manifest.tests.length) fail('PUBLIC_SOURCE_TEST_COUNT_CHANGED');
  const rows = new Map();
  for (const row of inventory.rows) {
    const spec = tests.get(row.test_id);
    if (!spec || rows.has(row.test_id)) fail('PUBLIC_INVENTORY_UNKNOWN_OR_DUPLICATE_ID');
    if (!same(row.requirement_ids, spec.requirement_refs) || !same(row.source_refs, spec.source_refs)
        || row.scenario !== spec.scenario) fail('PUBLIC_INVENTORY_SOURCE_DRIFT');
    if (!Array.isArray(row.check_ids) || new Set(row.check_ids).size !== row.check_ids.length) fail('INVALID_PUBLIC_INVENTORY_CHECK_IDS');
    if (!['implemented', 'blocked'].includes(row.mapping_status)) fail('INVALID_PUBLIC_INVENTORY_STATUS');
    if (row.mapping_status === 'blocked' && (row.check_ids.length || typeof row.missing_reason !== 'string' || !row.missing_reason.trim())) {
      fail('BLOCKED_PUBLIC_ID_NEEDS_EXPLICIT_REASON');
    }
    if (row.mapping_status === 'implemented' && (!row.check_ids.length || row.missing_reason !== null)) fail('IMPLEMENTED_PUBLIC_ID_NEEDS_CHECK');
    rows.set(row.test_id, row);
  }
  if (rows.size !== tests.size) fail('PUBLIC_INVENTORY_MISSING_ID');
  const checks = new Map(registry.map(check => [check.id, check]));
  for (const check of registry) {
    if (check.phase !== 'integration' || !Array.isArray(check.artifact_ids) || !check.artifact_ids.length) fail('INVALID_PUBLIC_CHECK_BOUNDARY');
    if (check.id !== 'public.' + suiteOf(check) || !same(check.test_ids, runnerInventory[suiteOf(check)])) fail('PUBLIC_RUNNER_ID_DRIFT');
    for (const id of check.test_ids) {
      if (!tests.has(id) || !rows.get(id).check_ids.includes(check.id)) fail('PUBLIC_CHECK_UNKNOWN_OR_UNINVENTORIED_ID');
    }
    const requirements = sorted(new Set(check.test_ids.flatMap(id => tests.get(id).requirement_refs)));
    if (!same(sorted(check.requirement_ids), requirements)) fail('PUBLIC_CHECK_REQUIREMENT_DRIFT');
  }
  if (!same(sorted(Object.keys(runnerInventory)), sorted(registry.map(suiteOf)))) fail('PUBLIC_RUNNER_SUITE_DRIFT');
  for (const row of rows.values()) {
    for (const id of row.check_ids) {
      if (!checks.get(id)?.test_ids.includes(row.test_id)) fail('PUBLIC_INVENTORY_UNBACKED_MAPPING');
    }
  }
  const mapping = publicCheckMapping({test_ids: [...tests.keys()], requirement_ids: manifest.obligations.map(obligation => obligation.id)}, registry);
  const missingIds = inventory.rows.filter(row => row.mapping_status === 'blocked').map(row => row.test_id);
  if (!same(sorted(mapping.missing_test_ids), sorted(missingIds))) fail('PUBLIC_MAPPING_DISAGREEMENT');
  return {schema_version: 'dag-public-check-audit/v1', status: mapping.status, mapping_only: true, product_execution_ready: false,
    source_test_count: tests.size, original_test_count: tests.size, additional_test_count: 0,
    public_gate_version: configuration.publicGateVersion, implemented_test_count: tests.size - missingIds.length,
    missing_test_count: missingIds.length, missing_test_ids: mapping.missing_test_ids, missing_requirement_ids: mapping.missing_requirement_ids,
    missing: inventory.rows.filter(row => row.mapping_status === 'blocked').map(row => ({test_id: row.test_id, reason: row.missing_reason})),
    check_count: registry.length, checks: registry.map(check => ({id: check.id, phase: check.phase, test_ids: check.test_ids})),
    blockers: [...(missingIds.length ? ['PUBLIC_CHECK_MAPPING_INCOMPLETE'] : []),
      'REAL_CANDIDATE_ENVIRONMENT_NOT_VALIDATED', 'ARTIFACT_REVISION_ADAPTER_NOT_BOUND'],
    controls: {status: 'not_run'}};
}

/** Pinned sources of a task's checks: its checker root (minus results/), this audit, the openapi audit it imports, the input and the instruction. */
function taskSourceHashes(root, {checkerRoot, inputPath}) {
  const paths = [];
  function walk(directory) {
    for (const entry of readdirSync(resolve(root, directory), {withFileTypes: true})) {
      if (entry.name === '__pycache__' || entry.name === 'results') continue;
      const path = join(directory, entry.name);
      if (entry.isSymbolicLink()) fail('PUBLIC_CHECK_SOURCE_SYMLINK', path);
      if (entry.isDirectory()) walk(path);
      else if (/\.(py|toml|sh|json)$/.test(entry.name)
        || path.startsWith(checkerRoot + '/fixtures/') || path.startsWith(checkerRoot + '/bindings/')) paths.push(path);
    }
  }
  walk(checkerRoot);
  paths.push('scripts/audit-task-public-checks.mjs', 'scripts/audit-dag-public-checks.mjs', 'src/orchestration/dag-contracts.mjs',
    inputPath, json(resolve(root, inputPath)).source.path);
  return sorted(paths).map(path => ({path, sha256: hash(readFileSync(resolve(root, path)))}));
}

export function publicSourceHashes(root = ROOT, options = {}) {
  return isTask(options) ? taskSourceHashes(root, taskAuditConfiguration(options)) : openapi.publicSourceHashes(root);
}

function validateReport(check, result, report, selectedIds) {
  if (report?.outcome_uncertain === true) fail('PUBLIC_CONTROL_OUTCOME_UNCERTAIN');
  if (!report || report.schema_version !== 'dag-public-check-evidence/v1' || report.check_id !== check.id || report.check_version !== check.version
      || report.environment_ref !== check.environment_ref || !same(report.test_ids, selectedIds)
      || report.exit_code !== result.status || report.executed !== true || report.outcome_uncertain !== false
      || report.product_certified !== false || report.artifact_revisions !== null) fail('PUBLIC_CONTROL_EVIDENCE_INVALID');
  if (!Array.isArray(report.cases) || !same(report.cases.map(row => row.test_id), selectedIds)
      || report.error !== null || report.skipped !== 0
      || report.assertions !== report.cases.reduce((sum, row) => sum + row.assertions, 0)) fail('PUBLIC_CONTROL_CASES_INVALID');
}

function validateTaskControlBatch(batch, registry, {root, requireComplete = true, configuration}) {
  if (batch?.schema_version !== 'dag-public-control-batch/v1' || !Array.isArray(batch.results)) fail('PUBLIC_CONTROL_BATCH_INVALID');
  const catalog = json(resolve(root, configuration.controlCatalogPath));
  const assertionHash = hash(readFileSync(resolve(root, configuration.assertionContractPath)));
  const normal = [], negative = [];
  for (const row of batch.results) {
    if (row.error?.type === 'TimeoutExpired') fail('PUBLIC_CONTROL_OUTCOME_UNCERTAIN', row.error.message);
    const check = registry.find(item => item.id === 'public.' + row.suite);
    if (!check) fail('PUBLIC_CONTROL_UNKNOWN_SUITE');
    const selected = row.kind === 'negative' ? check.test_ids.filter(id => row.expected_failed_ids.includes(id)) : check.test_ids;
    validateReport(check, {status: row.returncode}, row.report, selected);
    if (row.report.assertion_contract_sha256 !== assertionHash) fail('PUBLIC_CONTROL_ASSERTION_SOURCE_DRIFT');
    if (row.kind === 'normal') {
      const passed = row.returncode === 0 && row.report.status === 'passed' && row.report.scope === 'complete_suite'
        && row.report.cases.every(item => item.status === 'passed' && Number.isInteger(item.assertions) && item.assertions > 0);
      normal.push({check_id: check.id, passed, report: row.report, elapsed_seconds: row.elapsed_seconds});
    } else if (row.kind === 'negative') {
      const definition = catalog.find(control => control.suite === row.suite && control.defect === row.defect);
      if (!definition || !same(definition.expected_failed_ids, row.expected_failed_ids)) fail('PUBLIC_CONTROL_UNKNOWN_DEFECT');
      const failedIds = row.report.cases.filter(item => item.status === 'failed').map(item => item.test_id);
      const rejected = row.returncode !== 0 && row.report.status === 'failed' && row.report.scope === 'targeted_control'
        && row.expected_failed_ids.every(id => failedIds.includes(id));
      negative.push({defect: row.defect, check_id: check.id, expected_failed_ids: row.expected_failed_ids,
        failed_test_ids: failedIds, rejected, report: row.report, elapsed_seconds: row.elapsed_seconds});
    } else fail('PUBLIC_CONTROL_KIND_INVALID');
  }
  if (!same(sorted(normal.map(row => row.check_id)), sorted(registry.map(check => check.id)))) fail('PUBLIC_CONTROL_NORMAL_SET_INCOMPLETE');
  if (requireComplete && (!batch.complete_catalog || !same(sorted(negative.map(row => row.check_id + ':' + row.defect)),
    sorted(catalog.map(row => 'public.' + row.suite + ':' + row.defect))))) fail('PUBLIC_CONTROL_DEFECT_SET_INCOMPLETE');
  const environment = json(resolve(root, configuration.checkerRoot, 'environment.json'));
  if (batch.environment?.python !== environment.python || Object.entries(environment.preinstalled_dependencies)
    .some(([name, version]) => batch.environment?.dependencies?.[name] !== version)) fail('PUBLIC_CONTROL_ENVIRONMENT_DRIFT');
  return {status: normal.every(row => row.passed) && negative.every(row => row.rejected) ? 'passed' : 'failed',
    evidence_level: 'authored_local_controls_only', normal_count: normal.length, defective_count: negative.length,
    normal, negative, product_execution_ready: false};
}

function runTaskControls(registry, {root, normalOnly = false, configuration}) {
  const environment = json(resolve(root, configuration.checkerRoot, 'environment.json'));
  const before = taskSourceHashes(root, configuration);
  const name = 'heldout-public-controls-' + randomUUID();
  const arguments_ = ['create', '--name', name, '--platform', environment.platform, '--network', 'none', '--read-only', '--tmpfs', '/tmp:rw,exec,size=2g',
    '--mount', `type=bind,src=${root},dst=/checker,readonly`, '--workdir', '/checker', '--entrypoint', 'python3', environment.image_id,
    '/checker/' + configuration.controlRunnerPath, ...(normalOnly ? ['--normal-only'] : [])];
  let receipt;
  try {
    const created = spawnSync('docker', arguments_, {encoding: 'utf8', timeout: 30_000});
    if (created.status !== 0 || !/^[a-f0-9]{64}\s*$/.test(created.stdout)) fail('PUBLIC_CONTROL_DOCKER_CREATE_FAILED', created.stderr?.slice(-1500));
    const container = created.stdout.trim();
    // Every suite run installs a fresh venv under amd64 emulation; a full held-out batch took 482-927 s locally.
    const {result, report: batch} = runJson('docker', ['start', '-a', container], {timeout: 3_600_000});
    if (result.status !== 0) fail('PUBLIC_CONTROL_DOCKER_PROCESS_FAILED', result.stderr?.slice(-1000));
    const inspection = spawnSync('docker', ['inspect', container], {encoding: 'utf8', timeout: 10_000});
    if (inspection.status !== 0) fail('PUBLIC_CONTROL_DOCKER_INSPECT_FAILED');
    const actual = JSON.parse(inspection.stdout)[0];
    if (actual.Image !== environment.image_id || actual.HostConfig.NetworkMode !== 'none' || actual.HostConfig.ReadonlyRootfs !== true
        || actual.State.ExitCode !== 0 || !actual.Mounts.some(mount => mount.Destination === '/checker' && mount.RW === false)) fail('PUBLIC_CONTROL_CONTAINMENT_MISMATCH');
    if (!same(before, taskSourceHashes(root, configuration))) fail('PUBLIC_CONTROL_SOURCES_CHANGED_DURING_RUN');
    const controls = validateTaskControlBatch(batch, registry, {root, requireComplete: !normalOnly, configuration});
    receipt = {...controls, schema_version: 'dag-public-control-receipt/v2', recorded_at: new Date().toISOString(), source_hashes: before,
      public_gate_version: configuration.publicGateVersion, audit_inputs: configuration,
      container: {image_id: actual.Image, platform: environment.platform, network_mode: actual.HostConfig.NetworkMode, readonly_rootfs: actual.HostConfig.ReadonlyRootfs,
        checker_mount_readonly: true, exit_code: actual.State.ExitCode, command: arguments_}, batch, elapsed_seconds: batch.elapsed_seconds};
  } finally {
    spawnSync('docker', ['rm', '-f', name], {encoding: 'utf8', timeout: 15_000});
    const remains = spawnSync('docker', ['inspect', name], {encoding: 'utf8', timeout: 10_000});
    if (remains.status === 0 || !/no such (object|container)/i.test(remains.stderr ?? '')) fail('PUBLIC_CONTROL_DOCKER_CLEANUP_UNCONFIRMED');
    if (receipt) receipt.container.cleanup_confirmed = true;
  }
  return receipt;
}

export function verifyFrozenControlEvidence({root = ROOT, path, ...options} = {}) {
  if (!isTask(options)) return openapi.verifyFrozenControlEvidence({root, ...(path ? {path} : {}), ...options});
  const configuration = taskAuditConfiguration(options), receipt = json(resolve(root, path));
  if (receipt.schema_version !== 'dag-public-control-receipt/v2' || !same(receipt.source_hashes, taskSourceHashes(root, configuration))) fail('PUBLIC_CONTROL_FROZEN_SOURCE_DRIFT');
  if (receipt.public_gate_version !== configuration.publicGateVersion || !same(receipt.audit_inputs, configuration)) fail('PUBLIC_CONTROL_FROZEN_GATE_MISMATCH');
  const environment = json(resolve(root, configuration.checkerRoot, 'environment.json'));
  if (receipt.container?.image_id !== environment.image_id || receipt.container?.network_mode !== 'none' || receipt.container?.readonly_rootfs !== true
      || receipt.container?.checker_mount_readonly !== true || receipt.container?.cleanup_confirmed !== true || receipt.container?.exit_code !== 0) fail('PUBLIC_CONTROL_FROZEN_CONTAINMENT_INVALID');
  const verified = validateTaskControlBatch(receipt.batch, loadTaskInputs(root, configuration).registry, {root, configuration});
  if (verified.status !== 'passed' || receipt.status !== 'passed') fail('PUBLIC_CONTROL_FROZEN_FAILURE');
  return {status: 'verified', evidence_level: 'historical_authored_controls_at_exact_current_sources', path,
    receipt_sha256: hash(readFileSync(resolve(root, path))), source_count: receipt.source_hashes.length,
    normal_count: verified.normal_count, defective_count: verified.defective_count, recorded_at: receipt.recorded_at};
}

export function auditPublicChecks({root = ROOT, controls = false, defects = null, ...options} = {}) {
  if (!isTask(options)) return openapi.auditPublicChecks({root, controls, defects, ...options});
  if (defects) fail('PUBLIC_AUDIT_CONFIGURATION_INVALID');
  const inputs = loadTaskInputs(root, options), audit = inspectTaskMapping(inputs);
  audit.source_integrity = {input_path: inputs.configuration.inputPath, input_sha256: hash(readFileSync(resolve(root, inputs.configuration.inputPath))),
    public_source_sha256: inputs.manifest.source.sha256, verified: true};
  audit.audit_inputs = inputs.configuration;
  if (controls) audit.controls = runTaskControls(inputs.registry, {root, normalOnly: controls === 'normal', configuration: inputs.configuration});
  return audit;
}
