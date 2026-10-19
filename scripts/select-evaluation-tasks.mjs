#!/usr/bin/env node
// Deterministic held-out task list for evaluation-protocol.v1.json `task_selection`. Reads task metadata only;
// no Docker, no model calls. Re-running with the same upstream checkout gives the same file.
// Usage: node scripts/select-evaluation-tasks.mjs [--check]
import {existsSync, readFileSync, readdirSync, statSync, writeFileSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';

const root = resolve(import.meta.dirname, '..');
const protocol = JSON.parse(readFileSync(join(root, 'docs/orchestration/contracts/evaluation-protocol.v1.json'), 'utf8'));
const rule = protocol.task_selection;

const field = (toml, key) => toml.match(new RegExp(`^${key}\\s*=\\s*"?([^"\\n]+)"?`, 'm'))?.[1];

export function select(tasks, {tiers, per_tier, seed}, exclude) {
  const population = tasks.filter(t => t.language === 'Python' && !exclude.includes(t.task));
  const sizes = population.map(t => t.spec_bytes).sort((a, b) => a - b);
  const cut = q => sizes[Math.floor(q * (sizes.length - 1))];
  const cuts = [cut(1 / 3), cut(2 / 3)];
  const tierOf = t => t.spec_bytes <= cuts[0] ? tiers[0] : t.spec_bytes <= cuts[1] ? tiers[1] : tiers[2];
  const order = t => createHash('sha256').update(`${seed}:${t.task}`).digest('hex');
  const selected = tiers.flatMap(tier => population.filter(t => tierOf(t) === tier)
    .map(t => ({...t, tier, order_sha256: order(t)}))
    .sort((a, b) => a.order_sha256 < b.order_sha256 ? -1 : 1).slice(0, per_tier));
  return {population: population.length, tier_cut_bytes: cuts, selected};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const dir = join(root, '.benchmarks/E2E-SWE/tasks');
  const tasks = readdirSync(dir).filter(name => existsSync(join(dir, name, 'task.toml'))).map(name => {
    const toml = readFileSync(join(dir, name, 'task.toml'), 'utf8');
    return {task: name, language: field(toml, 'programming_language'), category: field(toml, 'category'),
      spec_bytes: statSync(join(dir, name, 'instruction.md')).size, hidden_tests: Number(field(toml, 'test_case_count')),
      docker_image: field(toml, 'docker_image')};
  });
  const {population, tier_cut_bytes, selected} = select(tasks, rule, protocol.tuning_tasks);
  const output = {schema_version: 'evaluation-tasks/v1', protocol: protocol.id, rule, excluded_tuning_tasks: protocol.tuning_tasks,
    upstream_tasks: tasks.length, population, tier_cut_bytes,
    tasks: selected.map(({language, ...t}) => t)};
  const text = JSON.stringify(output, null, 2) + '\n', out = join(root, rule.output);
  if (process.argv.includes('--check')) {
    if (readFileSync(out, 'utf8') !== text) throw new Error('EVALUATION_TASKS_DRIFT');
    console.log('evaluation tasks unchanged');
  } else {
    writeFileSync(out, text);
    console.log(`${selected.length} tasks from ${population} Python candidates -> ${rule.output}`);
  }
}
