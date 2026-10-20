import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync, readFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {checkInterfaceContract, runInterfaceFirst, validateInterfaceFirstBinding, INTERFACE_FIRST_CONTRACT} from '../src/benchmark/adaptive-interface-first.mjs';
import {createHash} from 'node:crypto';

const ROOT = resolve(import.meta.dirname, '..');
const plan = {tasks: [
  {id: 'n1', kind: 'implementation', write_scope: ['pkg/a.py', 'pyproject.toml'], requirement_ids: ['R1']},
  {id: 'n2', kind: 'implementation', write_scope: ['pkg/b.py'], requirement_ids: ['R2']},
  {id: 'verify', kind: 'verification', write_scope: [], requirement_ids: []}]};
const file = (path, imports = []) => ({path, purpose: 'x', exports: [{name: 'f', kind: 'function', signature: 'f()'}], imports});
const stream = (output, {model = 'claude-opus-5-5', error = false} = {}) => ({exit_code: 0, outcome_uncertain: false, stderr: '',
  stdout: JSON.stringify({type: 'result', subtype: error ? 'error' : 'success', is_error: error, modelUsage: {[model]: {}},
    usage: {input_tokens: 10, output_tokens: 5, cache_read_input_tokens: 0, cache_creation_input_tokens: 0},
    total_cost_usd: 0.25, structured_output: output, result: 'ok'}) + '\n'});
const run = async (t, output, options) => {
  const out = mkdtempSync(join(tmpdir(), 'iface-')); t.after(() => rmSync(out, {recursive: true, force: true}));
  let sent;
  const summary = await runInterfaceFirst({rootDir: ROOT, manifest: {interface_first: {contract: INTERFACE_FIRST_CONTRACT}},
    input: {source: 'spec', requirement_descriptions: [{id: 'R1', text: 'r'}]}, catalog: {units: [{id: 'u', title: 't', interface: 'i'}]},
    plan, outDirectory: out, runCommand: async (command, args, opts) => { sent = {command, args, input: JSON.parse(opts.input)}; return stream(output, options); }});
  return {summary, sent, out};
};

test('only owned paths and owned import sources are accepted', () => {
  assert.equal(checkInterfaceContract({files: [file('pkg/a.py'), file('pkg/b.py', [{from: 'pkg/a.py', names: ['f'], load_time: true}])]}, plan), null);
  assert.equal(checkInterfaceContract({files: []}, plan), 'ADAPTIVE_INTERFACE_FIRST_EMPTY');
  assert.equal(checkInterfaceContract({files: [file('pkg/a.py'), file('pkg/a.py')]}, plan), 'ADAPTIVE_INTERFACE_FIRST_DUPLICATE_PATH');
  assert.equal(checkInterfaceContract({files: [file('pkg/c.py')]}, plan), 'ADAPTIVE_INTERFACE_FIRST_PATH_UNOWNED');
  assert.equal(checkInterfaceContract({files: [file('pkg/a.py', [{from: 'other/x.py', names: [], load_time: true}])]}, plan), 'ADAPTIVE_INTERFACE_FIRST_IMPORT_UNOWNED');
});

test('a valid contract is used; the call has no tools and sends only public inputs', async t => {
  const {summary, sent, out} = await run(t, {files: [file('pkg/a.py')], shared_rules: []});
  assert.equal(summary.used, true);
  assert.equal(summary.api_equivalent_usd, 0.25);
  assert.equal(sent.args[sent.args.indexOf('--tools') + 1], '');
  assert.deepEqual(Object.keys(sent.input).sort(), ['interface_catalog', 'public_source', 'requirement_descriptions', 'stage', 'task', 'tasks']);
  assert.deepEqual(sent.input.tasks.map(task => task.id), ['n1', 'n2']);
  assert.equal(JSON.parse(readFileSync(join(out, 'summary.json'), 'utf8')).used, true);
});

test('an unusable or failed contract is recorded and not used', async t => {
  assert.equal((await run(t, {files: [file('elsewhere.py')], shared_rules: []})).summary.reason, 'ADAPTIVE_INTERFACE_FIRST_PATH_UNOWNED');
  const failed = (await run(t, null, {error: true})).summary;
  assert.equal(failed.used, false);
  assert.equal(failed.contract, null);
});

test('manifest binding requires the exact contract hash', () => {
  const sha256 = createHash('sha256').update(readFileSync(join(ROOT, INTERFACE_FIRST_CONTRACT))).digest('hex');
  const binding = {policy: 'interface-contract-v1', contract: INTERFACE_FIRST_CONTRACT, sha256};
  assert.doesNotThrow(() => validateInterfaceFirstBinding({interface_first: binding}, ROOT));
  assert.throws(() => validateInterfaceFirstBinding({interface_first: {...binding, sha256: '0'.repeat(64)}}, ROOT), {code: 'ADAPTIVE_INTERFACE_FIRST_BINDING'});
  assert.throws(() => validateInterfaceFirstBinding({interface_first: {...binding, extra: 1}}, ROOT), {code: 'ADAPTIVE_INTERFACE_FIRST_BINDING'});
});
