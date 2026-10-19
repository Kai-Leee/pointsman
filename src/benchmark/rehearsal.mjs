// Record-based zero-cost rehearsal (R20261018-DESIGN-SELECTION, proposal B). Only the two paid boundaries are
// doubled: Claude inference and the Jev POST. Docker, the task image, readiness and public checks, the runner,
// partial repair and budget.mjs settlement (on a ledger copy) run for real. Doubles answer from recorded runs:
// Jev answers and model IDs from calls/jev-*.response.json, worker files from a recorded passing candidate or the
// task's public reference control. Nothing here may reach a paid endpoint.
import {copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync} from 'node:fs';
import {basename, dirname, join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {processResult} from './docker.mjs';

const read = path => JSON.parse(readFileSync(path, 'utf8'));
const raw = (stdout, exit_code = 0) => ({stdout, stderr: '', exit_code, outcome_uncertain: false});
const completion = (response, model) => raw(JSON.stringify({type: 'result', subtype: 'success', is_error: false,
  modelUsage: {[model]: {}}, usage: {input_tokens: 20, output_tokens: 5, cache_read_input_tokens: 0, cache_creation_input_tokens: 0},
  total_cost_usd: 0, structured_output: response, result: 'rehearsal'}) + '\n');
export const UNKNOWN_MODEL_BUILD = 'typesafe/jev-9.99-20991231';
const isClaude = command => basename(String(command)) === 'claude';

/** Recorded Jev decisions: question id -> answer, and every distinct model id the provider actually returned. */
export function loadRecordedJev(runDirectories) {
  const answers = new Map(), models = new Set();
  for (const runDirectory of runDirectories) {
    const calls = join(runDirectory, 'calls');
    if (!existsSync(calls)) continue;
    for (const name of readdirSync(calls).filter(name => /^jev-\d+\.response\.json$/.test(name)).sort()) {
      const response = read(join(calls, name));
      if (typeof response.model === 'string') models.add(response.model);
      for (const [id, answer] of Object.entries(response.answers ?? {})) answers.set(id, answer);
    }
  }
  return {answers, models: [...models].sort()};
}

/** The dated build the provider currently serves: the highest jev-X.Y[.Z] on the free model list, mapped to its
 * typesafe/jev-X.Y-YYYYMMDD entry in the settlement contract (latest date). Null when no Jev version is listed;
 * REHEARSAL_SERVED_MODEL_UNKNOWN when a listed version has no dated build to replay. */
export function servedDatedBuild(listedNames, settlementIds) {
  const version = name => /^jev-(\d+)\.(\d+)(?:\.\d+)?$/.exec(name)?.slice(1).map(Number);
  const top = listedNames.map(version).filter(Boolean).sort((a, b) => b[0] - a[0] || b[1] - a[1])[0];
  if (!top) return null;
  const dated = settlementIds.map(id => [id, /^typesafe\/jev-(\d+)\.(\d+)-(\d{8})$/.exec(id)])
    .filter(([, m]) => m && Number(m[1]) === top[0] && Number(m[2]) === top[1]).sort((a, b) => b[1][3].localeCompare(a[1][3]));
  if (!dated.length) throw Object.assign(new Error('REHEARSAL_SERVED_MODEL_UNKNOWN'), {code: 'REHEARSAL_SERVED_MODEL_UNKNOWN', version: top.join('.')});
  return dated[0][0];
}

/** Adapters for runAdaptiveArm. `fault` is one of null, 'readiness_failure' (first worker writes unparsable files), 'missing_output'
 * (first worker writes nothing), 'unknown_model_build'.
 * `freeClient` may serve only free GETs (listCredits); decide() always stays doubled. */
export function rehearsalAdapters({recorded, referenceRoots, fault = null, log = [], freeClient = null, servedModel = null}) {
  let modelIndex = 0, firstWorker = true;
  // Every Jev answer reports the currently served dated build when known, so admission and settlement see it on each call.
  const models = fault === 'unknown_model_build' ? [UNKNOWN_MODEL_BUILD] : servedModel ? [servedModel]
    : recorded.models.length ? recorded.models : ['typesafe-ai/jev'];
  const answerFor = (id, question) => {
    const keys = Object.keys(question.criteria ?? {});
    const prior = recorded.answers.get(id);
    if (prior?.type === 'choice' && keys.includes(prior.choice)) return prior;
    return {type: 'choice', choice: keys[0], confidence: 0.8};
  };
  const jevClient = {
    listModels: async () => ({models: [{name: 'jev-latest'}]}),
    // Balance lookup is a free GET: use the real account (catches frozen or low balances) when a client is given.
    listCredits: async (...args) => freeClient ? freeClient.listCredits(...args) : ({}),
    decide: async body => {
      const model = models[modelIndex++ % models.length];
      const input_tokens = Math.min(65536, Math.ceil(JSON.stringify(body).length / 4));
      log.push({boundary: 'jev', model, questions: Object.keys(body.questions ?? {}).length});
      return {model, answers: Object.fromEntries(Object.entries(body.questions ?? {}).map(([id, q]) => [id, answerFor(id, q)])),
        usage: {input_tokens, output_tokens: 100, cost: null},
        billing: {runId: `rehearsal-${randomUUID()}`, mode: 'tokens', paidInputTokensUsed: String(input_tokens), modelMultiplier: '1', creditsCharged: '0'},
        receipt: {method: 'POST', destination: 'https://jev-ai.pro/api/v1/systemone', status: 200, durationMs: 1, automaticRetries: 0}};
    }};
  const writeWorker = (prompt, args) => {
    const mcp = read(args[args.indexOf('--mcp-config') + 1]), transport = read(mcp.mcpServers.artifact_worker.args.at(-1));
    const first = firstWorker, skip = fault === 'missing_output' && first, broken = fault === 'readiness_failure' && first;
    firstWorker = false;
    // A repair prompt's packet names its writable files; the transport is what a real worker's write_file would admit.
    for (const path of prompt.artifact_repair?.allowed_write_paths ?? prompt.task?.write_scope ?? []) {
      const source = referenceRoots.map(root => join(root, path)).find(file => existsSync(file) && statSync(file).isFile());
      const denied = !transport.allowedPaths.includes(path);
      log.push({boundary: 'claude_worker', task: prompt.task.id, operation: prompt.operation ?? null, path,
        source: denied ? 'denied_by_transport' : skip ? 'skipped_fault' : broken ? 'broken_fault' : source ?? 'unmapped'});
      if (skip || denied) continue;
      mkdirSync(dirname(join(transport.root, path)), {recursive: true});
      if (broken) writeFileSync(join(transport.root, path), '(((\n'); // fails ast/toml/bash -n readiness parsing
      else if (source) copyFileSync(source, join(transport.root, path)); else writeFileSync(join(transport.root, path), '');
    }
  };
  const runCommand = async (command, args, options = {}) => {
    if (!isClaude(command)) return processResult(command, args, options);
    // Free CLI introspection stays real; inference never leaves the double.
    if (args.includes('--version') || args[0] === 'auth') return processResult(command, args, options);
    const prompt = JSON.parse(options.input), model = args[args.indexOf('--model') + 1] || 'claude';
    let response;
    if (prompt.task?.startsWith?.('Compare the implementation')) response = {rehearsal: 'review'};
    else if (prompt.questions) response = {answers: Object.fromEntries(Object.entries(prompt.questions).map(([id, q]) => [id, answerFor(id, q)]))};
    else { writeWorker(prompt, args); response = {rehearsal: 'worker completed'}; }
    const result = completion(response, model);
    options.onStdout?.(result.stdout);
    return result;
  };
  return {runCommand, jevClientFactory: () => jevClient, jevConfig: {}};
}

/** Point the manifest's ledger at a copy so real settlement code runs without touching the shared ledger. */
export function rehearsalManifest(manifest, ledgerCopyPath) {
  return {...manifest, jev_budget: {...manifest.jev_budget, ledger_path: ledgerCopyPath}};
}

/** Spend gate: a paid run needs a passing rehearsal of the same clean tree, manifest and image, under 24 h old,
 * on a commit that descends from the main line. `current` holds the values observed now. */
export function assertRehearsal(report, current, {maxAgeMs = 24 * 3600 * 1000, now = Date.now()} = {}) {
  const fail = code => { throw Object.assign(new Error(code), {code, outcome_uncertain: false}); };
  if (!report || report.schema_version !== 'rehearsal/v1') fail('REHEARSAL_REQUIRED');
  if (report.passed !== true || !report.rows?.length || !report.rows.every(row => row.matched)) fail('REHEARSAL_NOT_PASSED');
  if (!(now - Date.parse(report.created_at) <= maxAgeMs)) fail('REHEARSAL_STALE');
  if (!current.clean || report.clean !== true || report.git_tree !== current.git_tree || report.manifest_sha256 !== current.manifest_sha256
      || report.image_id !== current.image_id) fail('REHEARSAL_MISMATCH');
  if (current.mainline_ancestor !== true) fail('SOURCE_NOT_ON_MAINLINE');
  return true;
}

export function writeJson(path, value) { mkdirSync(dirname(path), {recursive: true}); writeFileSync(path, JSON.stringify(value, null, 2) + '\n'); }
