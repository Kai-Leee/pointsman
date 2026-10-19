import {accessSync, constants, readdirSync, realpathSync, statSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {homedir} from 'node:os';
import {basename, delimiter, dirname, isAbsolute, join} from 'node:path';

// Kept out of the source-pinned runner files: callers opt in at the script entry point.
const APP_CLI_ROOT = join(homedir(), 'Library', 'Application Support', 'Claude', 'claude-code');
const unavailable = reason => Object.assign(new Error('CLAUDE_CLI_UNAVAILABLE'), {reason});
// statSync follows the link, so a dangling symlink throws here and is never used.
function executable(path) {
  try { if (!statSync(path).isFile()) return false; accessSync(path, constants.X_OK); return true; } catch { return false; }
}

// Prefer an explicit override, then the newest Claude-app build, then a live `claude` on PATH.
export function resolveClaudeCli({env = process.env, appRoot = APP_CLI_ROOT} = {}) {
  if (env.JEV_CLAUDE_CLI !== undefined) {
    if (!isAbsolute(env.JEV_CLAUDE_CLI) || !executable(env.JEV_CLAUDE_CLI)) throw unavailable('JEV_CLAUDE_CLI_INVALID');
    return {path: env.JEV_CLAUDE_CLI, version_dir: null, source: 'env'};
  }
  let versions = [];
  try { versions = readdirSync(appRoot).filter(name => /^\d+\.\d+\.\d+$/.test(name)); } catch {}
  const semver = name => name.split('.').map(Number);
  versions.sort((a, b) => { const x = semver(a), y = semver(b); return y[0] - x[0] || y[1] - x[1] || y[2] - x[2]; });
  for (const version of versions) {
    const versionDir = join(appRoot, version);
    let builds = [];
    try { builds = readdirSync(versionDir).filter(name => !name.startsWith('.'))
      .map(name => join(versionDir, name, 'claude.app', 'Contents', 'MacOS', 'claude')).filter(executable); } catch {}
    if (builds.length > 1) throw unavailable('AMBIGUOUS_APP_BUILDS');
    if (builds.length === 1) return {path: builds[0], version_dir: versionDir, source: 'app'};
  }
  for (const dir of (env.PATH ?? '').split(delimiter)) {
    const candidate = dir && join(dir, 'claude');
    if (candidate && isAbsolute(candidate) && executable(candidate)) return {path: realpathSync(candidate), version_dir: null, source: 'path'};
  }
  throw unavailable('NO_CANDIDATE');
}

// Put the resolved CLI first on env.PATH so existing bare `claude` spawns reach it; --version is a free local call.
export function useAppClaudeCli({env = process.env, appRoot} = {}) {
  const {path, source} = resolveClaudeCli({env, appRoot});
  if (basename(path) !== 'claude') throw unavailable('NOT_NAMED_CLAUDE');
  env.PATH = [dirname(path), env.PATH].filter(Boolean).join(delimiter);
  let version;
  try { version = execFileSync(path, ['--version'], {env, encoding: 'utf8', timeout: 30000}).trim().slice(0, 160); }
  catch { throw unavailable('VERSION_FAILED'); }
  return {path, source, version};
}
