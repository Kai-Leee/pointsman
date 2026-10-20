// Pointsman plan tools: check a task plan before workers start, find links the plan misses,
// estimate time and cost from recorded runs, and decide when Jev decomposition is not worth it.
// A plan is { tasks: [{ id, profile, writes: [path], inputs: [artifactId], outputs: [artifactId], requirements: [id] }], requirements?: [id] }.
import { readFileSync } from 'node:fs';
import { dirname, join, normalize } from 'node:path';

export const RATES = JSON.parse(readFileSync(new URL('./rates.v1.json', import.meta.url), 'utf8'));
const list = (value) => (Array.isArray(value) ? value : []);
const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b), mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

/** Structural check. Returns { order, predecessors, errors }; errors is empty for a runnable plan. */
export function validatePlan(plan) {
  const errors = [], tasks = list(plan?.tasks), ids = new Set();
  for (const task of tasks) {
    if (typeof task?.id !== 'string' || !task.id) errors.push({ code: 'PLAN_TASK_ID_INVALID' });
    else if (ids.has(task.id)) errors.push({ code: 'PLAN_DUPLICATE_TASK', task: task.id });
    else ids.add(task.id);
  }
  const writer = new Map(), producer = new Map();
  for (const task of tasks) {
    for (const path of list(task.writes)) {
      if (writer.has(path)) errors.push({ code: 'PLAN_WRITE_OVERLAP', path, tasks: [writer.get(path), task.id] });
      else writer.set(path, task.id);
    }
    for (const artifact of list(task.outputs)) {
      if (producer.has(artifact)) errors.push({ code: 'PLAN_DUPLICATE_PRODUCER', artifact, tasks: [producer.get(artifact), task.id] });
      else producer.set(artifact, task.id);
    }
  }
  const predecessors = {};
  for (const task of tasks) {
    const before = new Set();
    for (const artifact of list(task.inputs)) {
      const from = producer.get(artifact);
      if (!from) errors.push({ code: 'PLAN_INPUT_WITHOUT_PRODUCER', task: task.id, artifact });
      else if (from !== task.id) before.add(from);
    }
    predecessors[task.id] = [...before];
  }
  for (const requirement of list(plan?.requirements)) {
    if (!tasks.some((task) => list(task.requirements).includes(requirement))) errors.push({ code: 'PLAN_REQUIREMENT_UNOWNED', requirement });
  }
  // Kahn's algorithm: whatever is left after removing ready tasks sits on a cycle.
  const indegree = new Map(tasks.map((task) => [task.id, predecessors[task.id]?.length ?? 0])), order = [];
  const ready = tasks.filter((task) => indegree.get(task.id) === 0).map((task) => task.id);
  while (ready.length) {
    const id = ready.shift();
    order.push(id);
    for (const task of tasks) {
      if (!predecessors[task.id]?.includes(id)) continue;
      indegree.set(task.id, indegree.get(task.id) - 1);
      if (indegree.get(task.id) === 0) ready.push(task.id);
    }
  }
  if (order.length < ids.size) errors.push({ code: 'PLAN_CYCLE', tasks: [...ids].filter((id) => !order.includes(id)) });
  return { order, predecessors, errors };
}

const ancestors = (id, predecessors, seen = new Set()) => {
  for (const before of predecessors[id] ?? []) if (!seen.has(before)) { seen.add(before); ancestors(before, predecessors, seen); }
  return seen;
};

// Python absolute/relative imports and JS relative imports, resolved to repository paths.
function importedPaths(file, text) {
  const found = [];
  const python = (module, dots) => {
    let base = dots ? dirname(file) : '.';
    for (let i = 1; i < dots; i += 1) base = dirname(base);
    const parts = module ? module.split('.') : [];
    const stem = join(base, ...parts);
    found.push(`${stem}.py`, join(stem, '__init__.py'));
    return stem;
  };
  // Names run to the end of the line, or across lines only inside parentheses.
  for (const match of text.matchAll(/^[ \t]*from[ \t]+(\.*)([\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n#]*)/gm)) {
    const stem = python(match[2], match[1].length);
    for (const name of match[3].replace(/[()]/g, '').split(',').map((s) => s.trim().split(/\s+/)[0]).filter((s) => /^\w+$/.test(s))) {
      found.push(join(stem, `${name}.py`), join(stem, name, '__init__.py'));
    }
  }
  for (const match of text.matchAll(/^\s*import\s+([\w.]+(?:\s*,\s*[\w.]+)*)/gm)) {
    for (const module of match[1].split(',')) python(module.trim(), 0);
  }
  for (const match of text.matchAll(/(?:from\s+|import\s*\(\s*|require\s*\(\s*)['"](\.{1,2}\/[^'"]+)['"]/g)) {
    const stem = join(dirname(file), match[1]);
    found.push(stem, `${stem}.js`, `${stem}.mjs`, `${stem}.ts`, join(stem, 'index.js'));
  }
  // shortcut: an enclosing package's __init__.py runs on every submodule import, so it is not reported as a link;
  // report it if plans start splitting package initialisation into its own task.
  const own = normalize(dirname(file));
  return found.map((path) => normalize(path))
    .filter((path) => !(path.endsWith('__init__.py') && (own + '/').startsWith(normalize(dirname(path)) + '/')));
}

/** Links the plan does not express: a task's file imports a file another task writes, and that task is not before it.
 * `readFile(path)` returns the file text or null; only files that already exist can be scanned. */
export function findMissingLinks(plan, readFile) {
  const { predecessors } = validatePlan(plan), owner = new Map(), links = [], scanned = [];
  for (const task of list(plan.tasks)) for (const path of list(task.writes)) owner.set(normalize(path), task.id);
  for (const task of list(plan.tasks)) {
    const before = ancestors(task.id, predecessors);
    for (const path of list(task.writes)) {
      const text = readFile(path);
      if (text == null) continue;
      scanned.push(path);
      for (const imported of new Set(importedPaths(path, text))) {
        const other = owner.get(imported);
        if (other && other !== task.id && !before.has(other)) links.push({ task: task.id, needs: other, file: path, imports: imported });
      }
    }
  }
  return { links, scanned };
}

/** Time and cost estimate per task (median and range of recorded samples for its profile), a slot schedule and totals.
 * Unknown profiles stay null and are reported, never counted as zero. */
export function estimatePlan(plan, { rates = RATES, slots = 2, baselineProfile = 'claude_opus55_medium' } = {}) {
  const { order, predecessors } = validatePlan(plan), warnings = [];
  const pick = (profile) => {
    const samples = rates.profiles[profile];
    if (!samples?.length) return null;
    const seconds = samples.map((s) => s.seconds), usd = samples.map((s) => s.usd);
    return { seconds: median(seconds), usd: median(usd), range: { seconds: [Math.min(...seconds), Math.max(...seconds)], usd: [Math.min(...usd), Math.max(...usd)] }, samples: samples.length };
  };
  const tasks = Object.fromEntries(list(plan.tasks).map((task) => {
    const rate = pick(task.profile);
    if (!rate) warnings.push({ code: 'PLAN_PROFILE_UNRATED', task: task.id, profile: task.profile ?? null });
    return [task.id, { profile: task.profile ?? null, ...(rate ?? { seconds: null, usd: null }) }];
  }));
  const known = Object.values(tasks).map((t) => t.seconds).filter((s) => s != null);
  const typical = known.length ? median(known) : null;
  for (const [id, t] of Object.entries(tasks)) if (typical && t.seconds > 5 * typical) warnings.push({ code: 'PLAN_TASK_SIZE_OUTLIER', task: id, seconds: t.seconds, median: typical });
  // List scheduling: among ready tasks, start the longest first on the earliest free slot.
  const finish = {}, slotFree = Array(Math.max(1, slots)).fill(0), schedule = [], pending = new Set(order);
  while (pending.size) {
    const ready = [...pending].filter((id) => predecessors[id].every((p) => p in finish));
    ready.sort((a, b) => (tasks[b].seconds ?? 0) - (tasks[a].seconds ?? 0));
    const id = ready[0], slot = slotFree.indexOf(Math.min(...slotFree));
    const start = Math.max(slotFree[slot], ...predecessors[id].map((p) => finish[p]), 0), end = start + (tasks[id].seconds ?? 0);
    schedule.push({ task: id, slot, start, end });
    finish[id] = end; slotFree[slot] = end; pending.delete(id);
  }
  const complete = known.length === Object.keys(tasks).length;
  const sum = (key) => (complete ? Object.values(tasks).reduce((total, t) => total + t[key], 0) : null);
  const sequentialSeconds = sum('seconds'), usd = sum('usd'), makespan = complete ? Math.max(0, ...schedule.map((s) => s.end)) : null;
  const baseline = pick(baselineProfile), baselineUsd = baseline ? baseline.usd * Object.keys(tasks).length : null;
  return {
    tasks, schedule, warnings, slots,
    totals: {
      makespan_seconds: makespan, sequential_seconds: sequentialSeconds, usd,
      time_saved_vs_sequential: complete && sequentialSeconds ? 1 - makespan / sequentialSeconds : null,
      usd_saved_vs_all_baseline_profile: complete && baselineUsd ? 1 - usd / baselineUsd : null,
      baseline_profile: baselineProfile,
    },
  };
}

/** Skip decomposition when it cannot pay for its fixed overhead.
 * shortcut: the threshold is the smallest recorded fixed overhead, not a measured break-even; recalibrate with paired same-task runs. */
export function shouldSkipJev({ taskCount, estimatedSeconds }, { rates = RATES } = {}) {
  const overhead = Math.min(...rates.fixed_overhead_seconds.samples.map(([before, after]) => before + after));
  if (taskCount <= 1) return { skip: true, reason: 'single_task', overhead_seconds: overhead };
  if (estimatedSeconds != null && estimatedSeconds < overhead) return { skip: true, reason: 'below_fixed_overhead', overhead_seconds: overhead };
  return { skip: false, reason: null, overhead_seconds: overhead };
}

/** Items to close out a run: plan errors, unexpressed links, size outliers, failed checks and files a review changed.
 * Repair is not automated here; the list goes to the person running the session. */
export function closingFeedback({ validation, gaps, estimate, checks = [], reviewChanged = [] }) {
  return [
    ...validation.errors.map((e) => ({ kind: 'plan', text: `${e.code}${e.task ? ` ${e.task}` : ''}${e.path ? ` ${e.path}` : ''}${e.artifact ? ` ${e.artifact}` : ''}` })),
    ...(gaps?.links ?? []).map((l) => ({ kind: 'link', text: `${l.task} imports ${l.imports} (written by ${l.needs}) without a plan link` })),
    ...estimate.warnings.map((w) => ({ kind: 'size', text: `${w.code} ${w.task}${w.profile ? ` ${w.profile}` : ''}` })),
    ...checks.filter((c) => !c.passed).map((c) => ({ kind: 'check', text: `check failed: ${c.id}` })),
    ...reviewChanged.map((path) => ({ kind: 'review', text: `spec review changed ${path}` })),
  ];
}
