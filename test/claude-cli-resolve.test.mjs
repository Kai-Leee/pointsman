import test from 'node:test';
import assert from 'node:assert/strict';
import {chmodSync, mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {execFileSync} from 'node:child_process';
import {resolveClaudeCli, useAppClaudeCli} from '../src/benchmark/claude-cli.mjs';

function root(t) {
  const dir = mkdtempSync(join(tmpdir(), 'claude-cli-resolve-'));
  t.after(() => rmSync(dir, {recursive: true, force: true}));
  return dir;
}
function build(appRoot, version, hash, mode = 0o755) {
  const dir = join(appRoot, version, hash, 'claude.app', 'Contents', 'MacOS');
  mkdirSync(dir, {recursive: true});
  const path = join(dir, 'claude');
  writeFileSync(path, '#!/bin/sh\necho fake\n'); chmodSync(path, mode);
  return path;
}
const code = error => error.message === 'CLAUDE_CLI_UNAVAILABLE';

test('newest app build wins by semver, skipping hidden and non-executable entries', t => {
  const appRoot = join(root(t), 'app');
  build(appRoot, '2.1.9', 'aaa');
  const newest = build(appRoot, '2.1.10', 'bbb');
  build(appRoot, '9.9.9', 'ccc', 0o644);
  build(appRoot, '2.1.10', '.hidden');
  build(appRoot, '.9.9.9', 'ddd');
  assert.deepEqual(resolveClaudeCli({env: {PATH: ''}, appRoot}),
    {path: newest, version_dir: join(appRoot, '2.1.10'), source: 'app'});
});

test('JEV_CLAUDE_CLI overrides app builds and must be an absolute executable', t => {
  const dir = root(t), appRoot = join(dir, 'app');
  build(appRoot, '2.1.299', 'aaa');
  const override = build(join(dir, 'custom'), '1.0.0', 'x');
  assert.deepEqual(resolveClaudeCli({env: {JEV_CLAUDE_CLI: override}, appRoot}), {path: override, version_dir: null, source: 'env'});
  assert.throws(() => resolveClaudeCli({env: {JEV_CLAUDE_CLI: 'claude'}, appRoot}), code);
  assert.throws(() => resolveClaudeCli({env: {JEV_CLAUDE_CLI: join(dir, 'missing')}, appRoot}), code);
});

test('dangling PATH symlink is rejected; a live PATH entry after it is used', t => {
  const dir = root(t), dangling = join(dir, 'bin1'), live = join(dir, 'bin2');
  mkdirSync(dangling); mkdirSync(live);
  symlinkSync(join(dir, 'removed', 'claude'), join(dangling, 'claude'));
  const appRoot = join(dir, 'no-app');
  assert.throws(() => resolveClaudeCli({env: {PATH: dangling}, appRoot}), code);
  const target = build(join(dir, 'real'), '1.0.0', 'x');
  symlinkSync(target, join(live, 'claude'));
  assert.deepEqual(resolveClaudeCli({env: {PATH: `${dangling}:${live}`}, appRoot}), {path: realpathSync(target), version_dir: null, source: 'path'});
});

test('no candidate gives CLAUDE_CLI_UNAVAILABLE; two builds of the newest version are refused', t => {
  const dir = root(t), appRoot = join(dir, 'app');
  assert.throws(() => resolveClaudeCli({env: {PATH: join(dir, 'empty')}, appRoot}), code);
  build(appRoot, '2.1.299', 'aaa'); build(appRoot, '2.1.299', 'bbb');
  assert.throws(() => resolveClaudeCli({env: {PATH: ''}, appRoot}), error => code(error) && error.reason === 'AMBIGUOUS_APP_BUILDS');
});

test('useAppClaudeCli puts the chosen binary first so a bare claude lookup reaches it', t => {
  const dir = root(t), appRoot = join(dir, 'app'), other = join(dir, 'other');
  const chosen = build(appRoot, '2.1.299', 'aaa');
  writeFileSync(chosen, '#!/bin/sh\necho "2.1.299 (Claude Code)"\n');
  mkdirSync(other); writeFileSync(join(other, 'claude'), '#!/bin/sh\necho stale\n'); chmodSync(join(other, 'claude'), 0o755);
  const env = {PATH: `${other}:/usr/bin:/bin`};
  assert.deepEqual(useAppClaudeCli({env, appRoot}), {path: chosen, source: 'app', version: '2.1.299 (Claude Code)'});
  assert.equal(execFileSync('/bin/sh', ['-c', 'command -v claude'], {env, encoding: 'utf8'}).trim(), chosen);
  assert.throws(() => useAppClaudeCli({env: {PATH: ''}, appRoot: join(dir, 'none')}), code);
});
