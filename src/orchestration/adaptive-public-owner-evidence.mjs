import {createHash} from 'node:crypto';
import {lstat, readFile, realpath} from 'node:fs/promises';
import {resolve, join} from 'node:path';

const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const hash = value => createHash('sha256').update(value).digest('hex');
const digest = value => hash(JSON.stringify(canonical(value)));
const seal = value => ({...value, sha256: digest(value)});
const fail = code => { throw Object.assign(new Error(code), {code, outcome_uncertain: false}); };
const need = (value, code = 'PUBLIC_OWNER_EVIDENCE_INVALID') => { if (!value) fail(code); };
const unique = values => [...new Set(values)];
const safe = path => typeof path === 'string' && /^[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*$/.test(path)
  && !path.split('/').some(part => ['.', '..', '.git', '.env', '.agents', '.codex', '.claude'].includes(part));
export const PUBLIC_OWNER_UNION_ID = 'repair-inferred-owners+public-source';

function observations(failure) {
  const rows = [];
  for (const report of failure.public_evidence ?? []) {
    need(report.executed === true && report.outcome_uncertain === false, 'PUBLIC_OWNER_EVIDENCE_UNCERTAIN');
    if (report.status !== 'failed') continue;
    const evidence = report.evidence ?? {};
    const add = (id, type, message, traceback) => {
      if (typeof message !== 'string') return;
      const text = [message, typeof traceback === 'string' ? traceback : ''].join('\n');
      rows.push({check_id: report.check_id, test_id: id, error_type: type ?? null, message, text,
        successful_generation_observed: (evidence.candidate_invocations ?? []).some(row => row.exit_code === 0 && row.installed_cli === true),
        public_observation_sha256: digest({check_id: report.check_id, test_id: id, type, message, traceback: traceback ?? null})});
    };
    if (evidence.error) add(null, evidence.error.code, evidence.error.message, evidence.error.traceback);
    for (const testcase of evidence.cases ?? []) if (testcase.status === 'failed') {
      add(testcase.test_id ?? testcase.id, testcase.error_type, testcase.message, testcase.traceback);
    }
  }
  return rows;
}

async function sourceFile(root, path) {
  need(safe(path), 'PUBLIC_OWNER_EVIDENCE_UNSAFE_PATH');
  let cursor = root;
  for (const part of path.split('/')) {
    cursor = join(cursor, part);
    const stat = await lstat(cursor);
    need(!stat.isSymbolicLink(), 'PUBLIC_OWNER_EVIDENCE_SYMLINK');
  }
  const stat = await lstat(cursor);
  need(stat.isFile() && stat.size <= 2 * 1024 * 1024, 'PUBLIC_OWNER_EVIDENCE_SOURCE_INVALID');
  const bytes = await readFile(cursor), content = bytes.toString('utf8');
  need(Buffer.from(content).equals(bytes), 'PUBLIC_OWNER_EVIDENCE_SOURCE_ENCODING');
  return {path, sha256: hash(bytes), content};
}

/** Conservative, public-only candidate generation, not a diagnosis oracle.
 * No artifact/test/package names are prescribed. Dynamic absolute Python imports
 * are inspected only after public ModuleNotFoundError with successful generation.
 * Source traceback paths and literal missing-module imports provide direct links.
 */
export async function collectPublicOwnerEvidence({planning, failure, candidateDirectory}) {
  need(planning?.plan && planning?.catalog && failure?.outcome_uncertain === false && candidateDirectory);
  const root = await realpath(resolve(candidateDirectory));
  const rows = observations(failure), sources = [], links = [], owners = new Map();
  for (const artifact of planning.catalog.artifacts) {
    const planned = planning.plan.artifacts.find(row => row.id === artifact.id);
    const task = planning.plan.tasks.find(row => row.id === planned?.producer_task_id);
    need(task?.kind === 'implementation' && task.output_artifact_ids.includes(artifact.id), 'PUBLIC_OWNER_EVIDENCE_OWNER_BINDING');
    for (const path of artifact.paths) {
      need(safe(path) && task.write_scope.includes(path) && !owners.has(path), 'PUBLIC_OWNER_EVIDENCE_OWNER_BINDING');
      owners.set(path, {artifact_id: artifact.id, owner_task_id: task.id});
      if (!/\.py(?:\.(?:jinja|j2|jinja2))?$/.test(path)) continue;
      const source = await sourceFile(root, path); sources.push({path, sha256: source.sha256, artifact_id: artifact.id});
      for (const observation of rows) {
        const missing = observation.error_type === 'ModuleNotFoundError'
          ? /No module named ['"]([A-Za-z_][A-Za-z0-9_.]*)['"]/.exec(observation.message)?.[1] : null;
        const traceback = [...observation.text.matchAll(/File ["']([^"']+)["'], line (\d+)/g)]
          .filter(match => match[1] === path || match[1].endsWith(`/${path}`));
        for (const [index, line] of source.content.split('\n').entries()) {
          const directTrace = traceback.some(match => Number(match[2]) === index + 1);
          const imported = /^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_.]*)\b/.exec(line)?.[1];
          const literal = missing && imported && (imported === missing || imported.startsWith(`${missing}.`));
          const dynamic = missing && observation.successful_generation_observed && /\.(?:jinja|j2|jinja2)$/.test(path)
            && /^\s*(?:from|import)\s+\{\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\}(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\s|$)/.test(line);
          if (!directTrace && !literal && !dynamic) continue;
          links.push({...owners.get(path), check_id: observation.check_id, test_id: observation.test_id,
            public_observation_sha256: observation.public_observation_sha256, source: {path, sha256: source.sha256, line: index + 1, excerpt: line},
            missing_module: missing ?? null, basis: directTrace ? 'public_traceback_owned_source'
              : literal ? 'public_missing_module_literal_import' : 'public_missing_module_dynamic_template_import',
            certainty: 'repair_candidate_not_fault_proof'});
        }
      }
    }
  }
  const order = planning.plan.artifacts.map(row => row.id);
  return seal({schema_version: 'adaptive-public-owner-evidence/v1', policy: 'public-source-v1',
    binding: {plan_sha256: digest(planning.plan), catalog_sha256: digest(planning.catalog),
      public_evidence_sha256: digest(failure.public_evidence ?? []), artifact_revisions_sha256: digest(failure.artifact_revisions ?? {}),
      binding_digest: failure.binding_digest ?? null},
    observations: rows.map(({text, ...row}) => row), sources, links,
    required_artifact_ids: order.filter(id => links.some(link => link.artifact_id === id)),
    provider_calls: 0, boundary: 'Inspect all linked source candidates alongside inferred owners; links are hypotheses, never proof of fault or completion.'});
}

export function verifyPublicOwnerEvidence(evidence, {plan, failure} = {}) {
  need(evidence?.schema_version === 'adaptive-public-owner-evidence/v1', 'PUBLIC_OWNER_EVIDENCE_BINDING');
  const {sha256, ...body} = evidence;
  need(sha256 === digest(body), 'PUBLIC_OWNER_EVIDENCE_BINDING');
  if (plan) need(evidence.binding.plan_sha256 === digest(plan), 'PUBLIC_OWNER_EVIDENCE_PLAN_DRIFT');
  if (failure) need(evidence.binding.public_evidence_sha256 === digest(failure.public_evidence ?? [])
    && evidence.binding.artifact_revisions_sha256 === digest(failure.artifact_revisions ?? {})
    && evidence.binding.binding_digest === (failure.binding_digest ?? null), 'PUBLIC_OWNER_EVIDENCE_FAILURE_DRIFT');
  need(evidence.required_artifact_ids.length === unique(evidence.required_artifact_ids).length
    && evidence.required_artifact_ids.every(id => evidence.links.some(row => row.artifact_id === id)), 'PUBLIC_OWNER_EVIDENCE_COVERAGE');
  return evidence;
}

export function attachPublicOwnerEvidence(request, evidence) {
  verifyPublicOwnerEvidence(evidence);
  // The complete sealed object remains in controller records. Existing failure
  // messages are already inline: references identify them without repeating them.
  const indexes = new Map(evidence.observations.map((row, index) => [row.public_observation_sha256, index]));
  const grouped = new Map();
  for (const link of evidence.links) {
    const {check_id, test_id, public_observation_sha256, missing_module, certainty, ...sourceLink} = link;
    const key = digest(sourceLink);
    if (!grouped.has(key)) grouped.set(key, {...structuredClone(sourceLink), observation_refs: []});
    grouped.get(key).observation_refs.push(indexes.get(public_observation_sha256));
  }
  const context = {schema_version: evidence.schema_version, evidence_sha256: evidence.sha256,
    boundary: evidence.boundary, required_artifact_ids: structuredClone(evidence.required_artifact_ids),
    observation_ref_format: '[check_id, test_id]; null test_id denotes check-level error',
    observations: evidence.observations.map(row => [row.check_id, row.test_id]), source_links: [...grouped.values()]};
  return {...structuredClone(request), state: {...structuredClone(request.state), public_source_owner_evidence: context}};
}

/** Retains exact model answers and adds an explicit controller evidence closure.
 * Both existing seals are renewed, just as worker-mentioned scope expansion does.
 */
export function applyPublicOwnerEvidenceScope({candidates, analysis}, {plan, evidence, failure}) {
  verifyPublicOwnerEvidence(evidence, {plan, failure});
  if (!evidence.required_artifact_ids.length) return {candidates, analysis};
  const union = candidates.find(row => row.id === 'repair-inferred-owners+worker-mentioned')
    ?? candidates.find(row => row.id === 'repair-inferred-owners');
  // Unknown owners are retained; source evidence alone does not authorize bypassing owner inference.
  need(union && analysis.inferred_ownership && analysis.causal, 'PUBLIC_OWNER_EVIDENCE_NO_INFERRED_UNION');
  const order = plan.artifacts.map(row => row.id), selected = unique([...union.artifact_ids, ...evidence.required_artifact_ids]);
  need(selected.every(id => order.includes(id)), 'PUBLIC_OWNER_EVIDENCE_OWNER_BINDING');
  const artifact_ids = order.filter(id => selected.includes(id));
  const reads = unique([...(union.read_artifact_ids ?? []), ...analysis.causal.chains
    .filter(chain => chain.nodes.some(node => artifact_ids.includes(node.artifact_id))).flatMap(chain => chain.nodes.map(node => node.artifact_id))]);
  const expanded = {...structuredClone(union), id: PUBLIC_OWNER_UNION_ID, artifact_ids,
    task_ids: plan.tasks.filter(task => task.kind === 'implementation' && task.output_artifact_ids.some(id => artifact_ids.includes(id))).map(task => task.id),
    read_artifact_ids: order.filter(id => reads.includes(id)),
    evidence_refs: unique([...(union.evidence_refs ?? []), `public-source:${evidence.sha256}`]),
    reason: 'Inspect and repair inferred owners plus public source-linked candidates; preserve unknown attribution and rerun every public check.',
    public_source_evidence: seal({schema_version: 'adaptive-public-owner-scope-evidence/v1',
      evidence_sha256: evidence.sha256, required_artifact_ids: structuredClone(evidence.required_artifact_ids),
      context: attachPublicOwnerEvidence({state: {}}, evidence).state.public_source_owner_evidence})};
  const {sha256: prior, ...ownership} = structuredClone(analysis.inferred_ownership);
  ownership.choice_bindings[expanded.id] = digest(expanded);
  ownership.public_source_expansion = {prior_sha256: prior, candidate_id: expanded.id, evidence_sha256: evidence.sha256};
  const inferred_ownership = seal(ownership);
  const {sha256: _priorCausal, ...causal} = structuredClone(analysis.causal);
  causal.inferred_owner_scope_sha256 = inferred_ownership.sha256;
  causal.choice_bindings[expanded.id] = digest(expanded);
  return {candidates: [...candidates, expanded], analysis: {...analysis, inferred_ownership, causal: seal(causal)}};
}

export function assertPublicOwnerEvidenceCoverage(candidate, evidence) {
  verifyPublicOwnerEvidence(evidence);
  need(evidence.required_artifact_ids.every(id => candidate?.artifact_ids?.includes(id)), 'PUBLIC_OWNER_EVIDENCE_OWNER_OMITTED');
  return candidate;
}

export function selectPublicOwnerEvidenceScope({candidates}) {
  const candidate = candidates.find(row => row.id === PUBLIC_OWNER_UNION_ID);
  if (!candidate) return null;
  const {sha256, ...proof} = candidate.public_source_evidence ?? {};
  need(proof.schema_version === 'adaptive-public-owner-scope-evidence/v1' && sha256 === digest(proof), 'PUBLIC_OWNER_EVIDENCE_BINDING');
  need(proof.required_artifact_ids.every(id => candidate.artifact_ids.includes(id)), 'PUBLIC_OWNER_EVIDENCE_OWNER_OMITTED');
  return {status: 'selected', candidate: structuredClone(candidate), candidate_id: candidate.id,
    action: 'fresh_repair_scope_selected', outcome_uncertain: false, dispatch_allowed: false, automatic_retries: 0,
    selection_basis: {policy: 'public-source-v1', evidence_sha256: candidate.public_source_evidence.evidence_sha256,
      boundary: 'Model choices retained; public source candidates joined by deterministic coverage rule.'},
    stats: {provider_calls: 0, provider_questions: 0, local_questions: 1}};
}
