import {mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {join} from 'node:path';
import {processResult} from './docker.mjs';
import {providerOutcome} from './runner.mjs';
import {claudeEnvironment} from './claude-env.mjs';

// R20261020-INTERFACE-FIRST: before any leaf task runs, one structured call writes the package's interface contract
// from public inputs only. Leaf workers and repair workers then receive it. It never fails the run: an unusable
// contract is recorded and the run continues without it.
export const INTERFACE_FIRST_CONTRACT = 'docs/orchestration/contracts/adaptive-interface-first.v1.json';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const fail = code => { throw Object.assign(new Error(code), {code, outcome_uncertain: false}); };

export function loadInterfaceFirstContract(rootDir, path = INTERFACE_FIRST_CONTRACT) {
  const raw = readFileSync(join(rootDir, path)), contract = JSON.parse(raw);
  if (contract.schema_version !== 'adaptive-interface-first/v1' || contract.policy !== 'interface-contract-v1') fail('ADAPTIVE_INTERFACE_FIRST_CONTRACT_INVALID');
  return {...contract, source: {path, sha256: sha(raw)}};
}

/** Manifest binding: {policy, contract, sha256}, v12 only. */
export function validateInterfaceFirstBinding(value, rootDir) {
  const binding = value.interface_first;
  if (binding === undefined) return;
  if (!binding || binding.policy !== 'interface-contract-v1' || binding.contract !== INTERFACE_FIRST_CONTRACT
    || Object.keys(binding).sort().join() !== 'contract,policy,sha256'
    || binding.sha256 !== sha(readFileSync(join(rootDir, binding.contract)))) fail('ADAPTIVE_INTERFACE_FIRST_BINDING');
}

/** Every described file must be a path some implementation task owns; one entry per path. Import sources are not
 * checked: the model may name them as module paths (h2.errors) and external packages (hpack) are owned by no task. */
export function checkInterfaceContract(contract, plan) {
  const owned = new Set(plan.tasks.filter(task => task.kind === 'implementation').flatMap(task => task.write_scope));
  const paths = contract?.files?.map(file => file.path) ?? [];
  if (!paths.length) return 'ADAPTIVE_INTERFACE_FIRST_EMPTY';
  if (new Set(paths).size !== paths.length) return 'ADAPTIVE_INTERFACE_FIRST_DUPLICATE_PATH';
  if (paths.some(path => !owned.has(path))) return 'ADAPTIVE_INTERFACE_FIRST_PATH_UNOWNED';
  return null;
}

export async function runInterfaceFirst({rootDir, manifest, input, catalog, plan, outDirectory, runCommand = processResult,
  record = async () => {}, remaining = () => Infinity}) {
  const contract = loadInterfaceFirstContract(rootDir, manifest.interface_first.contract);
  mkdirSync(outDirectory, {recursive: true});
  const save = (name, data) => writeFileSync(join(outDirectory, name), typeof data === 'string' ? data : JSON.stringify(data, null, 2) + '\n', {flag: 'wx'});
  const tasks = plan.tasks.filter(task => task.kind === 'implementation')
    .map(task => ({id: task.id, write_scope: task.write_scope, requirement_ids: task.requirement_ids}));
  // `stage` lets the zero-cost rehearsal double recognise this call; no tools, no repository access.
  const prompt = JSON.stringify({stage: 'interface_first', task: contract.task, public_source: input.source,
    requirement_descriptions: input.requirement_descriptions,
    interface_catalog: catalog.units.map(({id, title, interface: text}) => ({id, title, interface: text})), tasks});
  const args = ['--print', '--model', contract.model, '--effort', contract.effort, '--tools', '', '--strict-mcp-config',
    '--mcp-config', '{"mcpServers":{}}', '--setting-sources', '', '--disable-slash-commands', '--no-chrome', '--permission-mode', 'dontAsk',
    '--permission-prompts', 'none', '--no-session-persistence', '--output-format', 'stream-json', '--verbose',
    '--json-schema', JSON.stringify(contract.output_schema), '--system-prompt', contract.system];
  await record({event: 'adaptive_interface_first_started', contract_source: contract.source, tasks: tasks.length});
  const began = performance.now(), workspace = mkdtempSync(join(tmpdir(), 'jev-interface-first-'));
  let raw = null, summary;
  try {
    raw = await runCommand('claude', args, {cwd: workspace, env: claudeEnvironment(process.env), input: prompt,
      timeoutMs: Math.min(contract.timeout_ms, remaining()), maxBytes: 16 * 1024 * 1024, killProcessTree: true});
    const outcome = providerOutcome(raw, contract.model), produced = outcome.completion?.structured_output ?? null;
    const invalid = outcome.status === 'completed' ? checkInterfaceContract(produced, plan) : `ADAPTIVE_INTERFACE_FIRST_${outcome.status.toUpperCase()}`;
    summary = {schema_version: 'adaptive-interface-first-result/v1', contract_source: contract.source, status: outcome.status,
      used: !invalid, reason: invalid, wall_ms: performance.now() - began, usage: outcome.completion?.usage ?? null,
      api_equivalent_usd: outcome.completion?.total_cost_usd ?? null, models: outcome.models,
      outcome_uncertain: outcome.status === 'uncertain', automatic_retries: 0,
      files: produced?.files?.length ?? 0, exports: produced?.files?.reduce((n, file) => n + file.exports.length, 0) ?? 0,
      contract: invalid ? null : produced, worker_rule: contract.worker_rule};
  } catch (error) {
    summary = {schema_version: 'adaptive-interface-first-result/v1', contract_source: contract.source, status: 'failed', used: false,
      reason: /^[A-Z0-9_]{1,100}$/.test(error?.code ?? '') ? error.code : 'ADAPTIVE_INTERFACE_FIRST_FAILED',
      wall_ms: performance.now() - began, usage: null, api_equivalent_usd: null, outcome_uncertain: error?.outcome_uncertain === true,
      automatic_retries: 0, files: 0, exports: 0, contract: null, worker_rule: contract.worker_rule};
  } finally {
    save('interface.stream.jsonl', raw?.stdout ?? '');
    rmSync(workspace, {recursive: true, force: true});
  }
  save('summary.json', summary);
  await record({event: 'adaptive_interface_first_completed', used: summary.used, reason: summary.reason, files: summary.files,
    exports: summary.exports, wall_ms: summary.wall_ms, api_equivalent_usd: summary.api_equivalent_usd});
  return summary;
}
