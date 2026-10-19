#!/usr/bin/env node
// Held-out stage-1 inputs (R20261017-EVAL-PROTOCOL). Authored atoms in benchmarks/e2e-swe/heldout/<task>/atoms.json
// become a d056-shaped obligations.json. Planning input is the public instruction.md only; tests/ and solution/ are
// never read here. No Docker, no model calls. --mock feeds the result through the real runner/planner functions offline.
// Usage: node scripts/build-heldout-obligations.mjs <task> [--check] | --mock <task>
import {createHash} from 'node:crypto';
import {existsSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

export const ROOT = resolve(import.meta.dirname, '..');
export const TASKS = ['h2', 'pycparser', 'django-modelcluster'];
const SCHEMA_VERSION = 'jev-recursive-task-test-input/v1';
const hash = value => createHash('sha256').update(value).digest('hex');
export const paths = task => {
  const dir = `benchmarks/e2e-swe/heldout/${task}`;
  return {dir, source: `.benchmarks/E2E-SWE/tasks/${task}/instruction.md`, atoms: `${dir}/atoms.json`,
    plan: `${dir}/public-checks.plan.json`, obligations: `${dir}/obligations.json`, manifest: `${dir}/v12.draft.json`,
    checker: `${dir}/public-checks`, registry: `${dir}/public-checks/registry.json`, runner: `${dir}/public-checks/run_public_checks.py`,
    inventory: `${dir}/public-checks/inventory.json`};
};
const DISCLOSURE = 'No dependency is asserted at the obligation level. An empty depends_on array is not evidence of independence; shared-file access and known interface producer/consumer facts still require sequencing or integration.';

export function sourceLines(text) {
  let position = 0;
  return (text.match(/[^\n]*\n|[^\n]+$/gu) ?? []).map(line => {
    const row = {text: line, start_byte: position, end_byte: position + Buffer.byteLength(line)};
    position = row.end_byte;
    return row;
  });
}

// Structural lines carry no requirement on their own: blank, heading, rule, fence, table separator.
function lineKinds(lines) {
  let fenced = false;
  return lines.map(({text}) => {
    const line = text.replace(/\n$/, '');
    if (/^```/.test(line)) { fenced = !fenced; return 'fence'; }
    if (fenced) return 'code';
    if (!line.trim()) return 'blank';
    if (/^#{1,6} /.test(line)) return line.startsWith('## ') ? 'section' : 'heading';
    if (/^---+$/.test(line) || /^\|[\s:|-]+\|$/.test(line)) return 'rule';
    return 'text';
  });
}

export function buildObligations(task, {sourceText, atoms}) {
  const p = paths(task), sha = hash(sourceText), lines = sourceLines(sourceText), kinds = lineKinds(lines);
  if (atoms.task !== task || atoms.source_path !== p.source || atoms.source_sha256 !== sha) throw Error('ATOMS_SOURCE_MISMATCH');
  const span = (start, end) => {
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start || end > lines.length) throw Error(`INVALID_LINES ${start}-${end}`);
    const text = lines.slice(start - 1, end).map(line => line.text).join('');
    return {text, source_ref: {path: p.source, sha256: sha, start_line: start, end_line: end},
      source_span: {start_byte: lines[start - 1].start_byte, end_byte: lines[end - 1].end_byte, sha256: hash(text)}};
  };
  // Sections: preamble plus one per level-2 heading, contiguous and covering every byte.
  const starts = [1, ...kinds.flatMap((kind, index) => kind === 'section' && index > 0 ? [index + 1] : [])];
  const sections = starts.map((start, index) => {
    const end = (starts[index + 1] ?? lines.length + 1) - 1, id = `R${String(index + 1).padStart(2, '0')}`;
    const {source_ref, source_span} = span(start, end);
    return {requirement_id: id, title: lines[start - 1].text.replace(/^#+ /, '').trim(), source_ref, source_span};
  });
  const sectionOf = line => sections.find(s => line >= s.source_ref.start_line && line <= s.source_ref.end_line);
  const ids = new Set(), covered = new Set(), primary = new Set(), issues = [];
  const obligations = atoms.atoms.map(atom => {
    const section = sectionOf(atom.lines?.[0]);
    if (!/^R\d{2}\.\d{2}$/.test(atom.id) || ids.has(atom.id)) issues.push(`bad or duplicate id ${atom.id}`);
    ids.add(atom.id);
    if (!section || !atom.id.startsWith(section.requirement_id + '.') || atom.lines[1] > section.source_ref.end_line) issues.push(`${atom.id} outside its section`);
    if (!['unit', 'integration', 'e2e'].includes(atom.scope)) issues.push(`${atom.id} scope`);
    for (const key of ['title', 'input', 'expected']) if (typeof atom[key] !== 'string' || !atom[key].trim()) issues.push(`${atom.id} ${key}`);
    if (!Array.isArray(atom.write_scope) || atom.write_scope.some(path => !/^[A-Za-z0-9_.-]+(\/[A-Za-z0-9_.-]+)*$/.test(path))) issues.push(`${atom.id} write_scope`);
    const exact = span(...atom.lines), context = (atom.context_lines ?? []).map(range => span(...range).source_ref);
    for (let line = atom.lines[0]; line <= atom.lines[1]; line++) { covered.add(line); primary.add(line); }
    for (const [start, end] of atom.context_lines ?? []) for (let line = start; line <= end; line++) covered.add(line);
    return {id: atom.id, requirement_id: atom.id.slice(0, 3), title: atom.title, ...exact, inputs: [atom.input], outputs: [atom.expected],
      write_scope: [...atom.write_scope], depends_on: [], gaps: [...(atom.gaps ?? [])], context_refs: context,
      dependency_assertion: 'unasserted', dependency_note: DISCLOSURE,
      write_scope_provenance: {kind: 'public_import_surface_paths', path: p.source, sha256: sha, requirement_id: atom.id.slice(0, 3),
        basis: 'Module or file paths named by the public instruction (dotted import path to file path); not ownership, an implementation assignment, or a design.'}};
  });
  for (const section of sections) if (!obligations.some(o => o.requirement_id === section.requirement_id)) issues.push(`section ${section.requirement_id} has no atom`);
  const uncovered = kinds.flatMap((kind, index) => ['text', 'code'].includes(kind) && !covered.has(index + 1) ? [index + 1] : []);
  if (uncovered.length) issues.push(`unclassified substantive lines ${uncovered.join(',')}`);
  const byId = new Map(obligations.map(o => [o.id, o]));
  const caseProvenance = refs => ({kind: 'authored_public_specification_case',
    examples: 'Concrete inputs are authored derivations of the public instruction, not hidden tests, prior candidate observations, or measured executions.',
    expectation_basis: 'Public instruction clauses identified by source_refs; wording is an authored acceptance paraphrase, not an additional product requirement.', source_refs: refs});
  const makeTest = (id, refs, scenario, input, expected, scope) => {
    const source_refs = refs.flatMap(ref => [byId.get(ref).source_ref, ...byId.get(ref).context_refs]);
    return {id, requirement_refs: refs, scenario, input, expected, scope, runner_ref: null, status: 'not_run', source_refs, provenance: caseProvenance(source_refs)};
  };
  const tests = atoms.atoms.map(atom => makeTest(`T.${atom.id}`, [atom.id], atom.title, atom.input, atom.expected, atom.scope));
  for (const def of atoms.integration ?? []) {
    if (!/^T\.integration\.[a-z0-9-]+$/.test(def.id) || !Array.isArray(def.refs) || def.refs.length < 2
      || new Set(def.refs).size !== def.refs.length || def.refs.some(ref => !byId.has(ref))) { issues.push(`integration ${def.id}`); continue; }
    tests.push(makeTest(def.id, def.refs, def.scenario, def.input, def.expected, 'e2e'));
  }
  if (new Set(tests.map(t => t.id)).size !== tests.length) issues.push('duplicate test id');
  if (issues.length) throw Error(`ATOMS_INVALID: ${issues.join('; ')}`);
  // Context segments: maximal runs of lines outside every atom's primary range.
  const context_segments = [];
  for (let line = 1; line <= lines.length; line++) {
    if (primary.has(line)) continue;
    let end = line;
    while (end < lines.length && !primary.has(end + 1)) end++;
    const run = kinds.slice(line - 1, end), {source_ref, source_span} = span(line, end);
    context_segments.push({kind: run.some(k => k === 'section' || k === 'heading') ? 'heading'
      : run.every(k => ['blank', 'rule', 'fence'].includes(k)) ? 'formatting' : 'context-introduction', source_ref, source_span});
    line = end;
  }
  const integrationCount = (atoms.integration ?? []).length;
  return {schema_version: SCHEMA_VERSION, goal: atoms.goal,
    source: {path: p.source, sha256: sha, text: sourceText, encoding: 'utf-8', byte_length: Buffer.byteLength(sourceText), line_count: lines.length},
    obligations, tests,
    constraints: ['Planning-only input: authored test specifications have no runner and have not executed against a product.',
      'Preserve all source obligations, constraints and test expectations; the complete frozen public instruction remains authoritative.',
      'Held-out evaluation task: authored from instruction.md only; the upstream tests/ and solution/ folders were not read.', DISCLOSURE],
    interfaces: [], artifact_interfaces: [], sections, context_segments,
    provenance: {preparation: 'Authored public-specification atoms (benchmarks/e2e-swe/heldout/<task>/atoms.json) with deterministic line/byte extraction.',
      source_inputs: [{path: p.source, sha256: sha}, {path: p.atoms, sha256: hash(JSON.stringify(atoms))}],
      shared_design: null, ownership_imported: false, task_groups_imported: false, task_dependencies_imported: false,
      hidden_material_read: false, dependency_status: DISCLOSURE,
      test_status: 'All test records are specifications only: runner_ref null, status not_run.',
      preparation_cost: 'Atoms were authored by Claude sessions from the public instruction; no provider call was made by this script and authoring cost is not measured here.',
      semantic_limit: 'Line/byte reconstruction, substantive-line coverage and test-link integrity are measured mechanically. Whether the cases detect every incorrect implementation needs executable public checks with normal/defective controls, which do not exist yet.'},
    coverage: {source: {method: 'SHA-256 and level-2-heading section byte spans reconstruct every public source byte; source.text is stored once.',
      total_lines: lines.length, total_bytes: Buffer.byteLength(sourceText), section_count: sections.length},
      declared_atoms: {count: obligations.length, requirement_count: sections.length, specification_count: tests.length, cross_atom_specification_count: integrationCount},
      semantic: {status: 'authored_public_spec_cases_not_product_verified', completeness_proven: false, executable_test_count: 0, executed_product_test_count: 0}}};
}

/** Public-check plan: every test id in exactly one suite, every suite with at least one defective control. */
export function validatePlan(plan, obligations) {
  const testIds = obligations.tests.map(t => t.id), seen = new Map(), issues = [];
  if (plan?.schema_version !== 'heldout-public-check-plan/v1' || !Array.isArray(plan.suites) || !Array.isArray(plan.defective_controls)) return {valid: false, issues: ['plan shape']};
  for (const suite of plan.suites) {
    if (!/^[a-z0-9-]+$/.test(suite.suite ?? '') || !Array.isArray(suite.test_ids) || !suite.test_ids.length
      || typeof suite.observable_behavior !== 'string' || typeof suite.case_design !== 'string') issues.push(`suite ${suite.suite}`);
    for (const id of suite.test_ids ?? []) { if (seen.has(id)) issues.push(`${id} in two suites`); seen.set(id, suite.suite); }
  }
  const unknown = [...seen.keys()].filter(id => !testIds.includes(id)), missing = testIds.filter(id => !seen.has(id));
  if (unknown.length) issues.push(`unknown test ids ${unknown.join(',')}`);
  if (missing.length) issues.push(`unmapped test ids ${missing.join(',')}`);
  const killed = new Set(), defects = new Set();
  for (const control of plan.defective_controls) {
    const key = `${control.suite}:${control.defect}`, suite = plan.suites.find(s => s.suite === control.suite);
    if (!suite || !/^[a-z0-9_]+$/.test(control.defect ?? '') || defects.has(key) || typeof control.mutation !== 'string'
      || !Array.isArray(control.expected_failed_ids) || !control.expected_failed_ids.length
      || control.expected_failed_ids.some(id => !suite.test_ids.includes(id))) issues.push(`control ${key}`);
    defects.add(key);
    for (const id of control.expected_failed_ids ?? []) killed.add(id);
  }
  for (const suite of plan.suites) if (!plan.defective_controls.some(c => c.suite === suite.suite)) issues.push(`suite ${suite.suite} has no defective control`);
  return {valid: !issues.length, issues, measured: {suites: plan.suites.length, mapped_test_ids: seen.size, test_ids: testIds.length,
    defective_controls: plan.defective_controls.length, test_ids_with_a_defect: killed.size}};
}

/** Declared public suites (one registry row per plan suite). The runner they name is a later step and may not exist yet. */
export function buildRegistry(task, obligations, plan) {
  const p = paths(task), tests = new Map(obligations.tests.map(test => [test.id, test]));
  return plan.suites.map(suite => ({id: `public.${suite.suite}`, version: '1', phase: 'integration', artifact_ids: ['candidate-source'],
    requirement_ids: [...new Set(suite.test_ids.flatMap(id => tests.get(id).requirement_refs))].sort(), test_ids: [...suite.test_ids],
    runner_ref: p.runner, argv: ['python3', 'run_public_checks.py', '--suite', suite.suite, '--binding', 'bindings/normal.json'],
    cwd: p.checker, environment_ref: `e2e-swe-public-${task}/v1`, source_ref: obligations.source.path, origin: 'public_specification'}));
}

/** One row per public test id, pinned to the exact obligations.json bytes the audit loads. */
export function buildInventory(task, obligations, registry, obligationsText) {
  const p = paths(task), suiteOf = new Map(registry.flatMap(check => check.test_ids.map(id => [id, check.id])));
  return {schema_version: 'dag-public-check-inventory/v1', execution_target: 'authored_local_control',
    public_source_sha256: obligations.source.sha256, input_sha256: hash(obligationsText),
    source_policy: 'Cases are authored from the public instruction.md only; tests/, solution/ and environment/ of the task were never read.',
    rows: obligations.tests.map(test => ({test_id: test.id, scenario: test.scenario, requirement_ids: test.requirement_refs,
      source_refs: test.source_refs, mapping_status: 'implemented', check_ids: [suiteOf.get(test.id)],
      case_refs: [`${p.checker}/cases.py#${suiteOf.get(test.id).slice('public.'.length)}:${test.id}`], missing_reason: null}))};
}

const read = path => readFileSync(join(ROOT, path), 'utf8');
const pretty = value => JSON.stringify(value, null, 2) + '\n';

export function build(task) {
  const p = paths(task), obligations = buildObligations(task, {sourceText: read(p.source), atoms: JSON.parse(read(p.atoms))});
  const planJson = existsSync(join(ROOT, p.plan)) ? JSON.parse(read(p.plan)) : null;
  const plan = planJson ? validatePlan(planJson, obligations) : {valid: false, issues: ['plan missing']};
  const registry = plan.valid ? buildRegistry(task, obligations, planJson) : null;
  return {obligations, text: pretty(obligations), plan, registryText: registry && pretty(registry),
    inventoryText: registry && pretty(buildInventory(task, obligations, registry, pretty(obligations)))};
}

/** Offline: the exact runner/planner functions the first paid stage would call, plus the manifest loader's verdict. */
export async function mock(task) {
  const p = paths(task), obligations = JSON.parse(read(p.obligations)), draft = JSON.parse(read(p.manifest));
  const runner = await import('../src/benchmark/adaptive-dag-runner.mjs'), planner = await import('../src/orchestration/adaptive-dag-planner.mjs');
  const input = runner.adaptivePublicInput(obligations);
  const prepared = planner.prepareAdaptiveCatalog({...input, limits: draft.limits});
  let loader;
  try { runner.loadAdaptiveRunManifest(join(ROOT, p.manifest), ROOT); loader = {status: 'accepted'}; }
  catch (error) { loader = {status: 'rejected', code: error.code ?? error.message}; }
  return {task, public_input: {requirements: input.requirement_ids.length, source_sha256: input.source_ref.sha256},
    catalog_preparation: {prompt_bytes: Buffer.byteLength(prepared.prompt), schema_requirement_enum: prepared.schema.properties.units.items.properties.requirement_ids.items.enum.length,
      source_sha256_matches: prepared.source_sha256 === obligations.source.sha256},
    test_requirement_mapping: {obligation_tests: obligations.tests.length},
    manifest_loader: loader, model_calls: 0, docker_calls: 0};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2), mockMode = args[0] === '--mock', task = mockMode ? args[1] : args[0];
  if (!TASKS.includes(task) || args.some(arg => arg.startsWith('--') && !['--check', '--mock'].includes(arg))) throw Error('Usage: build-heldout-obligations.mjs <task> [--check] | --mock <task>');
  if (mockMode) console.log(JSON.stringify(await mock(task), null, 2));
  else {
    const {obligations, text, plan, registryText, inventoryText} = build(task), p = paths(task);
    if (args.includes('--check')) {
      if (read(p.obligations) !== text) throw Error('HELDOUT_OBLIGATIONS_DRIFT');
      if (registryText && read(p.registry) !== registryText) throw Error('HELDOUT_REGISTRY_DRIFT');
      if (inventoryText && read(p.inventory) !== inventoryText) throw Error('HELDOUT_INVENTORY_DRIFT');
    } else {
      writeFileSync(join(ROOT, p.obligations), text);
      if (registryText) {
        mkdirSync(join(ROOT, p.checker), {recursive: true});
        writeFileSync(join(ROOT, p.registry), registryText); writeFileSync(join(ROOT, p.inventory), inventoryText);
      }
    }
    console.log(JSON.stringify({task, mode: args.includes('--check') ? 'check' : 'write', obligations: obligations.obligations.length,
      tests: obligations.tests.length, sections: obligations.sections.length, plan}));
    if (!plan.valid) process.exitCode = 2;
  }
}
