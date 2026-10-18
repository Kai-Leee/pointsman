#!/usr/bin/env node
// Explicit offline reconciliation of the one observed D086 dated-model response.
// No network, inference, balance lookup, automatic retries, or history replacement.
import {readFileSync, writeFileSync, mkdirSync, existsSync} from 'node:fs';
import {resolve, join} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {createTokenBudget, validateBudgetConfig, readTokenBudgetSnapshot} from '../src/benchmark/budget.mjs';

const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const fail = code => { throw Object.assign(new Error(code), {code}); };
const exactModel = 'typesafe/jev-1.14-20261014';
const hashRead = (path, expected) => {
  const bytes = readFileSync(resolve(path));
  if (!/^[a-f0-9]{64}$/.test(expected ?? '') || sha(bytes) !== expected) fail('D086_RECONCILIATION_HASH_MISMATCH');
  return bytes;
};

/** Pure/read-only evidence validation. The current ledger must still contain this exact blocked entry. */
export function validateD086Reconciliation(plan) {
  if (plan?.schema_version !== 'd086-response-reconciliation/v1' || !plan.attempt_id || !plan.reservation_id)
    fail('D086_RECONCILIATION_PLAN_INVALID');
  const config = validateBudgetConfig(plan.ledger_config);
  if (config.schema_version !== 'jev-token-budget/v4') fail('D086_RECONCILIATION_LEDGER_VERSION');
  const ledgerBytes = hashRead(config.ledger_path, plan.ledger_sha256), ledger = JSON.parse(ledgerBytes);
  const validatedLedger = readTokenBudgetSnapshot(config);
  if (validatedLedger.budget_id !== ledger.budget_id || !validatedLedger.pending_reservation_ids.includes(plan.reservation_id))
    fail('D086_RECONCILIATION_CURRENT_ENTRY_INVALID');
  const eventBytes = hashRead(plan.events_path, plan.events_sha256);
  const receiptBytes = hashRead(plan.provider_receipt_path, plan.provider_receipt_sha256), providerReceipt = JSON.parse(receiptBytes);
  const resultBytes = hashRead(plan.arm_result_path, plan.arm_result_sha256), result = JSON.parse(resultBytes);
  const events = eventBytes.toString('utf8').split('\n').filter(Boolean).map(line => JSON.parse(line));
  const selectOne = name => {
    const rows = events.filter(event => event.event === name && event.attempt_id === plan.attempt_id);
    if (rows.length !== 1) fail('D086_RECONCILIATION_EVENT_AMBIGUOUS');
    return rows[0];
  };
  const reserved = selectOne('budget_reserved'), started = selectOne('inference_started'), finished = selectOne('inference_finished');
  const blocked = selectOne('budget_blocked');
  if (!(events.indexOf(reserved) < events.indexOf(started) && events.indexOf(started) < events.indexOf(finished)
    && events.indexOf(finished) < events.indexOf(blocked))) fail('D086_RECONCILIATION_EVENT_ORDER_INVALID');
  if (finished.status !== 'completed' || finished.provider !== 'jev' || finished.model !== exactModel
    || finished.receipt?.status !== 200 || blocked.code !== 'BUDGET_MODEL_UNSUPPORTED' || blocked.outcome_uncertain !== true)
    fail('D086_RECONCILIATION_RESPONSE_INVALID');
  if (providerReceipt.provider !== 'jev' || providerReceipt.attempt_id !== plan.attempt_id
    || providerReceipt.code !== 'BUDGET_MODEL_UNSUPPORTED' || providerReceipt.status !== 'uncertain'
    || providerReceipt.inference_started !== true || providerReceipt.usage !== null
    || result.run_id !== finished.run_id || result.status !== 'uncertain' || result.stop_code !== 'BUDGET_MODEL_UNSUPPORTED')
    fail('D086_RECONCILIATION_TERMINAL_MISMATCH');
  if (!reserved.budget?.pending_reservation_ids?.includes(plan.reservation_id)
    || !result.budget_after?.pending_reservation_ids?.includes(plan.reservation_id))
    fail('D086_RECONCILIATION_RESERVATION_MISMATCH');
  const entries = ledger.pending?.filter(entry => entry.reservation_id === plan.reservation_id) ?? [];
  if (entries.length !== 1 || entries[0].blocked_code !== 'BUDGET_MODEL_UNSUPPORTED')
    fail('D086_RECONCILIATION_CURRENT_ENTRY_INVALID');
  const entry = entries[0];
  for (const key of ['request_id', 'run_id', 'attempt_id', 'group_id']) {
    if (entry[key] !== finished[key] || [reserved, started, blocked].some(event => event[key] !== entry[key]))
      fail('D086_RECONCILIATION_LINKAGE_MISMATCH');
  }
  const response = {model: finished.model, usage: finished.usage, billing: finished.billing, receipt: finished.receipt};
  const u = response.usage, b = response.billing, r = response.receipt;
  if (!Number.isSafeInteger(u?.input_tokens) || u.input_tokens < 0 || !Number.isSafeInteger(u?.output_tokens) || u.output_tokens < 0
    || b?.mode !== 'tokens' || b.modelMultiplier !== '1' || b.creditsCharged !== '0'
    || !/^(0|[1-9][0-9]*)$/.test(b.paidInputTokensUsed ?? '') || Number(b.paidInputTokensUsed) !== u.input_tokens
    || u.input_tokens > entry.reserved_input_tokens || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/.test(b.runId ?? '')
    || r.method !== 'POST' || r.destination !== 'https://jev-ai.pro/api/v1/systemone' || r.automaticRetries !== 0
    || !Number.isFinite(r.durationMs) || r.durationMs < 0
    || r.outcome_uncertain === true || r.outcomeUncertain === true)
    fail('D086_RECONCILIATION_BILLING_INVALID');
  return {config, ledger, ledgerBytes, entry, response, source_hashes: {
    events: plan.events_sha256, provider_receipt: plan.provider_receipt_sha256, arm_result: plan.arm_result_sha256,
    ledger_before: plan.ledger_sha256}, reservation_id: plan.reservation_id, attempt_id: plan.attempt_id};
}

/** apply=false is a no-lock, no-ledger-write preview. apply=true requires a separately reviewed plan. */
export function reconcileD086Response({plan, outDirectory, apply = false}) {
  const proof = validateD086Reconciliation(plan), out = resolve(outDirectory);
  if (existsSync(out)) fail('D086_RECONCILIATION_OUTPUT_EXISTS');
  mkdirSync(out, {mode: 0o700});
  const save = (name, value) => writeFileSync(join(out, name), typeof value === 'string' || Buffer.isBuffer(value)
    ? value : JSON.stringify(value, null, 2) + '\n', {flag: 'wx', mode: 0o600});
  const base = {schema_version: 'd086-response-reconciliation-audit/v1', model_calls: 0, network_calls: 0,
    automatic_retries: 0, reservation_id: proof.reservation_id, attempt_id: proof.attempt_id, source_hashes: proof.source_hashes,
    response_model: proof.response.model, input_tokens: proof.response.usage.input_tokens, output_tokens: proof.response.usage.output_tokens,
    actual_billed_usd: null, provider_billing_run_id: proof.response.billing.runId};
  if (!apply) { const preview = {...base, status: 'validated_not_applied', ledger_changed: false}; save('preview.json', preview); return preview; }
  let budget, applied = false;
  try {
    budget = createTokenBudget(proof.config, {requireExisting: true});
    // Revalidate under the native lock before saving or mutating any history.
    const lockedProof = validateD086Reconciliation(plan);
    save('ledger-before.json', lockedProof.ledgerBytes);
    const before = budget.snapshot();
    const after = budget.reconcile(proof.reservation_id, proof.response); applied = true;
    const afterBytes = readFileSync(proof.config.ledger_path), afterLedger = JSON.parse(afterBytes);
    save('ledger-after.json', afterBytes);
    const expected = {...lockedProof.ledger, charged_input_tokens: lockedProof.ledger.charged_input_tokens + proof.response.usage.input_tokens,
      settled_requests: lockedProof.ledger.settled_requests + 1,
      pending: lockedProof.ledger.pending.filter(entry => entry.reservation_id !== proof.reservation_id), blocked_code: null,
      last_settlement: {reservation_id: proof.reservation_id, charged_input_tokens: proof.response.usage.input_tokens,
        input_tokens: proof.response.usage.input_tokens, billing_run_id: proof.response.billing.runId}};
    if (JSON.stringify(afterLedger) !== JSON.stringify(expected)) fail('D086_RECONCILIATION_POSTCONDITION_FAILED');
    // Prove the preserved raw outcome, receipt, and event stream were not rewritten.
    hashRead(plan.events_path, plan.events_sha256); hashRead(plan.provider_receipt_path, plan.provider_receipt_sha256);
    hashRead(plan.arm_result_path, plan.arm_result_sha256);
    const audit = {...base, status: 'reconciled', ledger_changed: true, before, after,
      ledger_after_sha256: sha(afterBytes), original_result_receipt_events_unchanged: true,
      basis: 'One saved HTTP200 response settled via native reconcile. No API query, model call, retry, refund, history reset, or execution-result promotion.'};
    save('audit.json', audit); return audit;
  } catch (error) {
    save('failure.json', {...base, status: 'failed', ledger_changed: applied, code: error.code ?? 'D086_RECONCILIATION_FAILED'});
    throw error;
  } finally { budget?.close(); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const args = process.argv.slice(2), apply = args.includes('--apply'), fields = args.filter(arg => arg !== '--apply');
    if (fields.length !== 4 || fields[0] !== '--plan' || fields[2] !== '--out' || args.length !== (apply ? 5 : 4))
      fail('D086_RECONCILIATION_ARGUMENTS');
    const plan = JSON.parse(readFileSync(resolve(fields[1]), 'utf8'));
    const result = reconcileD086Response({plan, outDirectory: fields[3], apply});
    console.log(JSON.stringify({status: result.status, ledger_changed: result.ledger_changed,
      model_calls: 0, network_calls: 0, charged_input_tokens: result.input_tokens}));
  } catch (error) { console.error(JSON.stringify({status: 'failed', code: error.code ?? 'D086_RECONCILIATION_FAILED'})); process.exitCode = 1; }
}
