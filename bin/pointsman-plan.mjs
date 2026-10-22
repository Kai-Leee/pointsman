#!/usr/bin/env node
// Check a Pointsman task plan before workers start. No network, no model calls.
// Usage: node bin/pointsman-plan.mjs --plan plan.json [--repo dir] [--slots 2] [--html view.html] [--actual actual.json] [--title text]
// Prints a JSON report; exits 2 when the plan has structural errors.
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { analyzeCoupling, closingFeedback, estimatePlan, findMissingLinks, shouldSkipJev, validatePlan } from '../src/plan/plan.mjs';
import { renderPlanView } from '../src/plan/view.mjs';

const args = process.argv.slice(2);
const option = (name) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : undefined; };
const planPath = option('--plan');
if (!planPath) { process.stderr.write('usage: pointsman-plan.mjs --plan plan.json [--repo dir] [--slots 2] [--html view.html] [--actual actual.json]\n'); process.exit(64); }
const plan = JSON.parse(readFileSync(planPath, 'utf8'));
const repo = option('--repo');
const readFile = (path) => { const full = resolve(repo ?? '.', path); return repo && existsSync(full) ? readFileSync(full, 'utf8') : null; };

const validation = validatePlan(plan);
const gaps = repo ? findMissingLinks(plan, readFile) : { links: [], scanned: [], edges: [] };
const coupling = analyzeCoupling(plan, gaps);
const estimate = estimatePlan(plan, { slots: Number(option('--slots') ?? 2) });
const skip = shouldSkipJev({ taskCount: plan.tasks?.length ?? 0, estimatedSeconds: estimate.totals.makespan_seconds });
const feedback = closingFeedback({ validation, gaps, estimate, coupling });
const report = { validation, gaps, coupling, estimate, skip, feedback };

const html = option('--html');
if (html) {
  const actual = option('--actual') ? JSON.parse(readFileSync(option('--actual'), 'utf8')) : null;
  writeFileSync(html, renderPlanView(report, { title: option('--title') ?? 'Pointsman plan', actual }));
}
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
process.exitCode = validation.errors.length ? 2 : 0;
