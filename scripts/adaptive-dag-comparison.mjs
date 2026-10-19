#!/usr/bin/env node
import {readFileSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {loadAdaptiveRunManifest, preflightAdaptiveComparison, prepareAdaptiveSharedCatalog,
  runAdaptiveArm, runAdaptiveComparison} from '../src/benchmark/adaptive-dag-runner.mjs';
import {assertRehearsal} from '../src/benchmark/rehearsal.mjs';
import {useAppClaudeCli} from '../src/benchmark/claude-cli.mjs';

const rootDir = resolve(import.meta.dirname, '..'), args = process.argv.slice(2);
const MAINLINE = process.env.JEV_MAINLINE_REF ?? 'origin/research';
try {
  useAppClaudeCli();
  let runDir, preparationDirectory, arm, rehearsalDirectory, manifestPath = 'benchmarks/e2e-swe/manifests/d066-adaptive.json';
  const flags = new Set();
  for (let index = 0; index < args.length; index++) {
    const arg = args[index];
    if (['--spend', '--probe', '--prepare-catalog'].includes(arg)) { if (flags.has(arg)) throw new Error('ADAPTIVE_ARGUMENT_INVALID'); flags.add(arg); }
    else if (['--manifest', '--catalog-preparation', '--arm', '--rehearsal'].includes(arg) && args[index + 1]) {
      const value = args[++index];
      if (arg === '--manifest') manifestPath = value;
      else if (arg === '--catalog-preparation') preparationDirectory = resolve(rootDir, value);
      else if (arg === '--rehearsal') rehearsalDirectory = resolve(rootDir, value);
      else arm = value;
    } else if (!arg.startsWith('--') && !runDir) runDir = resolve(rootDir, arg);
    else throw new Error('ADAPTIVE_ARGUMENT_INVALID');
  }
  const manifest = loadAdaptiveRunManifest(resolve(rootDir, manifestPath), rootDir), spend = flags.has('--spend');
  if (flags.has('--prepare-catalog') && manifest.catalog_reuse) throw new Error('ADAPTIVE_PREPARATION_ALREADY_PINNED');
  if (flags.has('--prepare-catalog') && (arm || preparationDirectory)) throw new Error('ADAPTIVE_ARGUMENT_INVALID');
  if (spend && (!runDir || (!flags.has('--prepare-catalog') && !preparationDirectory))) throw new Error('ADAPTIVE_ARGUMENT_INVALID');
  if (!spend && (runDir || arm || preparationDirectory || flags.has('--prepare-catalog'))) throw new Error('EXPLICIT_SPEND_REQUIRED');
  // R20261018 proposal B: every paid arm run needs a passing record-based rehearsal of this exact tree (scripts/rehearse.mjs).
  if (spend && !flags.has('--prepare-catalog')) {
    if (!rehearsalDirectory) throw Object.assign(new Error('REHEARSAL_REQUIRED'), {code: 'REHEARSAL_REQUIRED'});
    const git = (...a) => execFileSync('git', ['-C', rootDir, ...a], {encoding: 'utf8'}).trim();
    let mainlineAncestor = false;
    try { git('merge-base', '--is-ancestor', MAINLINE, 'HEAD'); mainlineAncestor = true; } catch {}
    assertRehearsal(JSON.parse(readFileSync(join(rehearsalDirectory, 'rehearsal.json'), 'utf8')), {
      git_tree: git('rev-parse', 'HEAD^{tree}'), clean: git('status', '--porcelain', '--untracked-files=no') === '',
      manifest_sha256: createHash('sha256').update(readFileSync(resolve(rootDir, manifestPath))).digest('hex'),
      image_id: JSON.parse(readFileSync(resolve(rootDir, manifest.image_lock), 'utf8')).image_id, mainline_ancestor: mainlineAncestor});
  }
  const result = !spend ? await preflightAdaptiveComparison({rootDir, manifest, probe: flags.has('--probe')})
    : flags.has('--prepare-catalog') ? await prepareAdaptiveSharedCatalog({rootDir, manifest, runDir, spend})
      : arm ? await runAdaptiveArm({rootDir, manifest, runDir, arm, preparationDirectory, spend})
        : await runAdaptiveComparison({rootDir, manifest, runDir, preparationDirectory, spend});
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  if (!['prepared', 'ready', 'inspected_no_inference', 'completed'].includes(result.status)) process.exitCode = 2;
} catch (error) {
  const code = /^[A-Z0-9_]+$/.test(error?.code ?? error?.message ?? '') ? error.code ?? error.message : 'ADAPTIVE_RUN_FAILED';
  const unknown = error?.outcome_uncertain === true || error?.outcomeUncertain === true || error?.uncertain === true || ['unknown', 'uncertain'].includes(error?.status);
  process.stderr.write(JSON.stringify({status: unknown ? 'uncertain' : 'failed', code, outcome_uncertain: unknown}) + '\n');
  process.exitCode = 1;
}
