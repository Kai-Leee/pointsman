#!/usr/bin/env node
// Harness-comparable summary over execution-graded adaptive arms, scored by evaluation-protocol.v1.json.
// Reads existing run files only: no model calls, no Docker, no writes into benchmark-runs.
// revfactory/claude-code-harness reports an LLM-judged 0-100 score, a paired win rate and an across-case SD.
// Here the 0-100 score is the independent hidden-test pass percentage. That is a diagnostic: the benchmark
// score itself is binary `resolved` (grade/result.json partial_pass_fraction_is_benchmark_score=false).
// Usage: node scripts/harness-style-report.mjs [runs-dir ...] [--json <out.json>]
import {existsSync, readFileSync, readdirSync, writeFileSync} from 'node:fs';
import {basename, dirname, join, relative, resolve, sep} from 'node:path';
import {pathToFileURL} from 'node:url';

const read = path => JSON.parse(readFileSync(path, 'utf8'));
export const PROTOCOL = read(new URL('../docs/orchestration/contracts/evaluation-protocol.v1.json', import.meta.url));
export const HARNESS_REFERENCE = {
  source: 'revfactory/claude-code-harness experiments/reports/summary-15cases.json (author self-measured)',
  cases: 15, runs_per_case_per_condition: 1, judge: 'LLM rubric, 10 dimensions x 0-10, not blind',
  baseline_mean: 49.5, harness_mean: 79.3, win_rate: '15/15', baseline_sd: 5.3, harness_sd: 3.6,
};

const ARM_SCHEMAS = ['adaptive-arm-result/v1', 'codex-e2e-arm/v1'];
// ponytail: kind from directory naming, add an explicit field to arm results if names stop following it.
const kindOf = run => /repair|same-source|focused/.test(run) ? 'repair' : 'full';

export function collectArms(runsDir) {
  const arms = [];
  for (const path of readdirSync(runsDir, {recursive: true})) {
    if (!path.endsWith(`${sep}result.json`) && path !== 'result.json') continue;
    // Depth 4 covers run/cohort/<arm>/result.json (D086) and run/pair/<arm>/result.json (Codex E2E).
    if (path.split(sep).length > 4) continue;
    const file = join(runsDir, path), dir = dirname(file);
    let result;
    try { result = read(file); } catch { continue; }
    if (!ARM_SCHEMAS.includes(result.schema_version)) continue;
    result.arm ??= basename(dir);
    const id = relative(runsDir, dir), run = id.split(sep)[0];
    const evaluation = existsSync(join(dir, 'independent-evaluation.json')) ? read(join(dir, 'independent-evaluation.json')) : null;
    const grade = existsSync(join(dir, 'grade', 'result.json')) ? read(join(dir, 'grade', 'result.json')) : null;
    const ctrf = join(dir, 'grade', 'verifier', 'ctrf.json');
    const failedClasses = existsSync(ctrf)
      ? read(ctrf).results.tests.filter(t => t.status !== 'passed').map(t => t.name.split('::')[1] ?? t.name)
      : null;
    arms.push({
      id, run, arm: result.arm, condition: `${run.replace(/-\d+$/, '')}/${result.arm}`, kind: kindOf(run),
      task: grade?.task_id ?? null, status: result.status, stop_code: result.stop_code ?? null,
      uncertain: result.outcome_uncertain === true, public_status: result.public_status ?? null,
      wall_ms: result.wall_ms ?? null,
      // The arm result can say null while the later independent grade has the answer (d067/d071 jev_all).
      product_success: evaluation?.product_success ?? result.product_success ?? null,
      independent: evaluation?.summary ? {passed: evaluation.summary.passed, tests: evaluation.summary.tests} : null,
      grader_model_calls: evaluation?.model_calls ?? null,
      candidate_retained: evaluation ? Boolean(result.candidate_path && existsSync(result.candidate_path)) : null,
      failedClasses,
    });
  }
  // Planned arms that never wrote a result (protocol.json arms[]) are listed too, or C07 would be vacuous.
  for (const run of readdirSync(runsDir)) {
    const file = join(runsDir, run, 'protocol.json');
    let planned;
    try { planned = read(file).arms; } catch { continue; }
    if (!Array.isArray(planned)) continue;
    for (const arm of planned) {
      if (existsSync(join(runsDir, run, arm, 'result.json'))) continue;
      arms.push({id: join(run, arm), run, arm, condition: `${run.replace(/-\d+$/, '')}/${arm}`, kind: kindOf(run), task: null,
        status: 'no_arm_result', stop_code: 'NO_ARM_RESULT', uncertain: false, public_status: null, wall_ms: null,
        product_success: null, independent: null, grader_model_calls: null, candidate_retained: null, failedClasses: null});
    }
  }
  return arms.sort((a, b) => a.id < b.id ? -1 : 1);
}

// A worktree can hold a clone of another benchmark-runs; counting it twice would inflate repeats (C06) and pairs.
export function mergeArms(lists) {
  const seen = new Set();
  for (const arm of lists.flat()) {
    if (seen.has(arm.id)) throw new Error(`DUPLICATE_ARM ${arm.id}: pass each benchmark-runs folder once, not a clone`);
    seen.add(arm.id);
  }
  return lists.flat().sort((a, b) => a.id < b.id ? -1 : 1);
}

// Inclusion follows PROTOCOL.inclusion: graded arms count with their grade, system stops count as 0,
// infrastructure and user stops are excluded with a reason.
export function scoreRun(arm, codes = PROTOCOL.inclusion.ungraded_stop_codes) {
  if (arm.independent) return {score: 100 * arm.independent.passed / arm.independent.tests, reason: 'graded'};
  if (codes.system_failure_counted_as_zero.includes(arm.stop_code)) return {score: 0, reason: `ungraded system stop ${arm.stop_code}`};
  if (codes.excluded_infrastructure.includes(arm.stop_code)) return {score: null, reason: `infrastructure stop ${arm.stop_code}`};
  if (codes.excluded_user_or_uncertain.includes(arm.stop_code)) return {score: null, reason: `user or uncertain stop ${arm.stop_code}`};
  if (codes.excluded_not_started.includes(arm.stop_code)) return {score: null, reason: 'planned arm without arm result; cause only in STATE/decision record'};
  return {score: null, reason: `unclassified ${arm.status}/${arm.stop_code ?? 'no stop code'}`};
}

const mean = xs => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
export const sd = xs => {
  if (xs.length < 2) return null;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1));
};
// Wilson 95% score interval for k successes out of n.
export function wilson(k, n, z = 1.96) {
  if (!n) return null;
  const p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d;
  return [Math.max(0, c - h), Math.min(1, c + h)];
}
const round = x => x === null ? null : Math.round(x * 10) / 10;

function credibility(arms, scored, byCondition, pairs) {
  const graded = arms.filter(a => a.independent), counted = scored.filter(a => a.score !== null);
  const tasks = [...new Set(graded.map(a => a.task).filter(Boolean))];
  const compared = byCondition.filter(c => c.counted > 0);
  const unclassified = scored.filter(a => a.reason.startsWith('unclassified')).length;
  const auto = {
    execution_graded: [`${counted.filter(a => a.independent).length}/${counted.length} counted arms graded by hidden tests`,
      counted.every(a => a.independent || a.score === 0)],
    grader_model_calls_zero: [`${graded.filter(a => a.grader_model_calls === 0).length}/${graded.length} grades with 0 model calls`,
      graded.every(a => a.grader_model_calls === 0)],
    repeats_at_least_3: [`${compared.filter(c => c.counted >= 3).length}/${compared.length} conditions with >=3 counted runs`,
      compared.every(c => c.counted >= 3)],
    // Every arm carries a reason, so pass only when none is unclassified (protocol: unclassified blocks citation).
    intention_to_treat: [`${arms.length} arms = ${counted.length} counted + ${arms.length - counted.length} excluded with reason, ${unclassified} unclassified`,
      unclassified === 0],
    artifacts_retained: [`${graded.filter(a => a.candidate_retained).length}/${graded.length} graded candidates on disk`,
      graded.every(a => a.candidate_retained)],
    paired_runs: [`${pairs.reduce((n, p) => n + p.wins + p.ties + p.losses, 0)} same-run pairs`, pairs.length > 0],
    interval_reported: ['Wilson 95% interval per condition', true],
    distinct_tasks: [`${tasks.length} graded task(s): ${tasks.join(', ')}`, tasks.length >= 9],
    held_out_tasks: [`${tasks.filter(t => !PROTOCOL.tuning_tasks.includes(t)).length}/${tasks.length} graded tasks outside tuning_tasks`,
      tasks.length > 0 && tasks.every(t => !PROTOCOL.tuning_tasks.includes(t))],
  };
  return PROTOCOL.credibility_checklist.map(item => {
    const [observed, pass] = item.auto ? auto[item.auto] : [item.jev.evidence, item.jev.status === 'yes'];
    return {id: item.id, criterion: item.criterion, harness: item.harness.status, jev: pass ? 'yes' : 'no', observed};
  });
}

export function summarize(arms, score = scoreRun) {
  const scored = arms.map(arm => ({...arm, ...score(arm)}));
  const conditions = {};
  for (const arm of scored) {
    const c = conditions[arm.condition] ??= {kind: arm.kind, runs: 0, counted: [], resolved: 0, excluded: []};
    c.runs++;
    if (arm.score === null) { c.excluded.push(`${arm.id}: ${arm.reason}`); continue; }
    c.counted.push(arm.score);
    if (arm.product_success === true) c.resolved++;
  }
  const byCondition = Object.entries(conditions).map(([condition, c]) => ({
    condition, kind: c.kind, runs: c.runs, counted: c.counted.length, resolved: `${c.resolved}/${c.counted.length}`,
    resolved_ci95: wilson(c.resolved, c.counted.length)?.map(x => round(100 * x)) ?? null,
    mean: round(mean(c.counted)), sd: round(sd(c.counted)),
    min: c.counted.length ? Math.min(...c.counted) : null, max: c.counted.length ? Math.max(...c.counted) : null,
    excluded: c.excluded,
  }));

  // Paired win rate: arms of the same run share task, preparation and time window (Harness pairs by case).
  const pairs = {};
  const byRun = Object.groupBy(scored.filter(a => a.score !== null), a => a.run);
  for (const [run, group] of Object.entries(byRun)) {
    const sorted = group.toSorted((a, b) => a.arm < b.arm ? -1 : 1);
    for (let i = 0; i < sorted.length; i++) for (let j = i + 1; j < sorted.length; j++) {
      const [a, b] = [sorted[i], sorted[j]], key = `${a.arm} vs ${b.arm}`;
      const p = pairs[key] ??= {pair: key, wins: 0, ties: 0, losses: 0, runs: []};
      p[a.score > b.score ? 'wins' : a.score < b.score ? 'losses' : 'ties']++;
      p.runs.push(`${run}: ${a.score.toFixed(1)} vs ${b.score.toFixed(1)}`);
    }
  }

  // Execution-based dimensions: hidden-test classes instead of LLM rubric dimensions.
  const graded = arms.filter(a => a.failedClasses);
  const failRuns = {};
  for (const arm of graded) for (const cls of new Set(arm.failedClasses)) failRuns[cls] = (failRuns[cls] ?? 0) + 1;
  const dimensions = Object.entries(failRuns).map(([test_class, runs]) => ({test_class, failed_runs: runs, graded_runs: graded.length}))
    .sort((a, b) => b.failed_runs - a.failed_runs || (a.test_class < b.test_class ? -1 : 1));

  const pairList = Object.values(pairs);
  return {protocol: PROTOCOL.id, harness_reference: HARNESS_REFERENCE, arms_found: arms.length, graded: graded.length,
    by_condition: byCondition, pairs: pairList, dimensions,
    credibility: credibility(arms, scored, byCondition, pairList), arms: scored};
}

export function toMarkdown(report) {
  const rows = (head, list, cells) => [`| ${head.join(' | ')} |`, `| ${head.map(() => '---').join(' | ')} |`,
    ...list.map(x => `| ${cells(x).map(v => v ?? '—').join(' | ')} |`)].join('\n');
  const h = report.harness_reference;
  return [
    `# Harness-style report (${report.protocol})`, '',
    `Arms found ${report.arms_found}, independently graded ${report.graded}.`,
    `Harness reference (${h.source}): ${h.cases} cases x ${h.runs_per_case_per_condition} run, ${h.judge}; ` +
      `mean ${h.baseline_mean} → ${h.harness_mean}, win ${h.win_rate}, SD ${h.baseline_sd} → ${h.harness_sd}.`, '',
    '## Credibility checklist', '',
    rows(['id', 'criterion', 'Harness', 'Jev', 'observed'], report.credibility, c => [c.id, c.criterion, c.harness, c.jev, c.observed]), '',
    '## By condition (score = independent pass %, resolved = binary benchmark result)', '',
    rows(['condition', 'kind', 'runs', 'counted', 'resolved', 'resolved 95% CI', 'mean', 'SD', 'min', 'max'], report.by_condition,
      c => [c.condition, c.kind, c.runs, c.counted, c.resolved, c.resolved_ci95 && `${c.resolved_ci95[0]}–${c.resolved_ci95[1]}%`,
        c.mean, c.sd, c.min?.toFixed(1), c.max?.toFixed(1)]), '',
    '## Paired win rate (arms of the same run)', '',
    rows(['pair', 'wins', 'ties', 'losses', 'runs'], report.pairs, p => [p.pair, p.wins, p.ties, p.losses, p.runs.join('; ')]), '',
    '## Failure dimensions (hidden-test classes, graded arms)', '',
    rows(['test class', 'failed arms'], report.dimensions, d => [d.test_class, `${d.failed_runs}/${d.graded_runs}`]), '',
    '## Excluded arms', '',
    ...report.by_condition.flatMap(c => c.excluded.map(e => `- ${e}`)), '',
  ].join('\n');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2), flag = args.indexOf('--json');
  const jsonOut = flag >= 0 ? args.splice(flag, 2)[1] : null;
  // Several run folders (e.g. sibling worktrees) can be aggregated; arm ids keep their run-relative path.
  const report = summarize(mergeArms((args.length ? args : ['benchmark-runs']).map(dir => collectArms(resolve(dir)))));
  if (jsonOut) writeFileSync(jsonOut, JSON.stringify(report, null, 2) + '\n');
  process.stdout.write(toMarkdown(report));
}
