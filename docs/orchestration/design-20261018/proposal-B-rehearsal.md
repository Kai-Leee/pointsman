# Design B: zero-cost full rehearsal before every paid run

Paths are relative to the heldout worktree.

## 1. Diagnosis

`runAdaptiveArm` already accepts `adapters` (src/benchmark/adaptive-dag-runner.mjs:1031): `runCommand` (:336), `jevClientFactory` (:490) and `openBudget` (:477). The mock-arm tests use them in a way that skips the real code. test/d080-defaults-mock-arm.test.mjs:44-90 also fakes `docker` and reports every check as `passed`. It uses a fixture ledger (:28), hard-codes the model `jev-1.13.0` (:41), and never makes a leaf fail. Each of defects 1-7 sits in exactly what these fakes replace or skip: the environment, the ledger, the provider identity, partial execution and the task. So a paid run was the first place where real values met real code. Nothing that runs before spending required the fixes, so they stayed on side branches.

## 2. Design

**Rule.** A paid `--spend` needs a passing rehearsal for the same commit tree, manifest, image, CLI version and ledger shape. The rehearsal fakes only the two paid boundaries: Claude inference and the Jev POST. Everything else is real: Docker, the task image, readiness, public checks, budget.mjs, the transmission preflight, repair and spec review.

**Components:**

- **`src/benchmark/rehearsal.mjs` (new).** It takes over the doubles now inlined in the d079 and d080 mock-arm tests. Those tests import them from here, so the copies are deleted.
  - **`claudeDouble`**
    - It handles `command === 'claude'` only. Everything else goes to the real `processResult`, so `docker` and `python3` really run.
    - Workers write the **public reference control** files for their `write_scope`, taken from `benchmarks/e2e-swe/heldout/<task>/public-checks/controls/reference/`.
    - It can apply a patch from `controls/defects.json` to force a public failure.
    - A path that has no reference file gets an empty file and is listed in `unmapped_paths`.
  - **`jevDouble`**
    - It answers with the first allowed key, or with the key the fault row scripts.
    - It returns the model ID that the **live probe** observed, not a constant.
    - It applies the `scripts/validate-jev-input.mjs` logic and the provider's official limits to every request. A request that would exceed them fails the rehearsal as `WOULD_HTTP_400`.
  - **Ledger.** The real ledger is copied into the rehearsal directory, and a cloned manifest's `jev_budget` points at the copy. The real settlement code runs on it: budget.mjs:24 and :108, and `assertAdaptiveCohortCapacity` (adaptive-dag-runner.mjs:650).
- **`benchmarks/e2e-swe/rehearsal/faults.v1.json` (new).** Each row is `{id, inject, expect: {reach:[stages]} | {code, attribution}}`:

  | Row | What it injects or checks |
  |---|---|
  | `baseline` | No fault. |
  | `partial_execution` | One worker exits non-zero. |
  | `public_defect` | A defect patch is applied. The run must reach `repair_owners` and a repair round. |
  | `unknown_model_build` | Jev returns `typesafe/jev-9.99-20991231`. |
  | `ledger_unlimited`, `ledger_finite` | The ledger copy has an unlimited cap or a finite cap. |
  | `missing_cli` | `claude` returns ENOENT. |
  | `missing_module` | The real image plus the `unavailable_runtime_import` control. |
  | `oversized_request` | A worker emits a 300 KB failure log. |
- **`scripts/rehearse.mjs` (new).**
  - It runs the existing free probe `preflightAdaptiveComparison({probe:true})` (adaptive-dag-runner.mjs:1282).
  - It then runs every fault row through `runAdaptiveArm` with the doubles, for **every arm the protocol requires**. docs/orchestration/EVALUATION_PROTOCOL.md:8 requires `claude_all` alongside the Jev arm.
  - It writes `benchmark-runs/rehearsal-<ts>/rehearsal.json`: `{schema:"rehearsal/v1", git_tree, clean, manifest_sha256, image_id, cli_version, ledger_shape, probe, rows:[{fault, arm, stages_reached, terminal_cause, attribution, matched}], unmapped_paths, shared_ledger_sha256_before, shared_ledger_sha256_after, passed}`.
- **Replay (`rehearse.mjs --replay <paid-run-dir>`).** This is how a failure is attributed to the harness or to the model.
  1. It feeds the paid run's recorded receipts from `calls/*.process.json` and the Jev receipts back through the doubles, and checks that the same stop code comes back.
  2. It swaps the failing leaf's artifacts for the public reference files and reruns.
  3. If the stop persists, the cause is `harness`. If it disappears, the cause is `product` (the model).
  4. Only `product` stops count as model failures in `report.json`.
- **Gate.** `scripts/adaptive-dag-comparison.mjs:23` makes `--spend` also require `--rehearsal <dir>`. A new `assertRehearsal()` runs at the top of `runAdaptiveArm` and `runAdaptiveComparison`. It requires all of the following:
  - `passed` is true and every row matched;
  - `git_tree` equals `HEAD^{tree}` and the tree is clean;
  - `origin/research` is an ancestor of `HEAD`;
  - the manifest hash and the image ID match;
  - the rehearsal is less than 24 hours old.

  Otherwise it throws `REHEARSAL_REQUIRED`, `REHEARSAL_STALE` or `REHEARSAL_MISMATCH`.
- **Probe additions** to `preflightDagRun` (src/benchmark/dag-runner.mjs:154):
  - Run the free `claude --version` and compare it with `manifest.profile_policy.cli_version`. adaptive-dag-runner.mjs:227 already makes this comparison for catalogs.
  - Compare `listModels` with `JEV_SETTLEMENT_MODELS` (budget.mjs:26).
- **Attribution field.** `adaptiveTerminalCause` (src/orchestration/adaptive-failure.mjs:17) gains `attribution ∈ {harness, host, provider, policy, product}`. A static table keyed by code and stage sets it, and a replay verdict overrides it.

## 3. Defects 1-7

1. **Partial execution.** The `partial_execution` row hits the missing-revision refusal at adaptive-inferred-repair.mjs:91. Caught **before** a paid call. adaptive-partial-repair.mjs must reach the trunk first.
2. **Unknown model build.** The `unknown_model_build` row shows the `BUDGET_MODEL_UNSUPPORTED` stop and the ledger block, on the ledger copy only. The probe flags a `listModels` ID that is not on the whitelist. This is known **before** a paid call. If the dated build appears only on the POST, the stop is attributed to `provider`, not `product`.
3. **tomllib missing in Python 3.10.** In the `baseline` row, the reference `pyproject.toml` fails the real readiness check in the real h2 image. Caught **before** a paid call. Replaying pilot-01 labels the n1 failure `harness`, because the reference control fails the same way.
4. **Unlimited ledger.** `ledger_unlimited` runs the real capacity check against a null remaining count. Caught **before** a paid call.
5. **Missing CLI.** `claude --version` in the probe returns PROCESS_START_FAILED. The `missing_cli` row checks that the run stops before any Jev POST. Caught **before** a paid call.
6. **Hard-coded openapi.** The rehearsal uses the target task's manifest, registry and image, so any openapi constant fails at load or check time. Caught **before** a paid call.
7. **No same-run baseline.** The rehearsal must run `claude_all`. The v8 loader check (adaptive-dag-runner.mjs:154) refuses it, so the rehearsal fails. Caught **before** a paid call.

## 4. Process changes

- **One trunk for harness code: `research`.** It needs a one-time consolidation:
  - Merge `research-d095-final-20261017` and `feat/heldout-eval-20261018` into `research`.
  - Commit the main checkout's roughly 100 uncommitted files to a preserved branch, `salvage/main-checkout-20261018`.
  - From there, cherry-pick only the harness fixes: adaptive-partial-repair.mjs and the D086 whitelist entry.
- **The gate enforces propagation.** It requires a clean tree that descends from `origin/research`. A fix that lives only in a dirty checkout or on a side branch therefore cannot back a paid run. The fault matrix lives on the trunk, so a branch that lacks a trunk fix fails rehearsal after it rebases.
- **Every new paid-run stop code adds a row to `faults.v1.json` in the same PR as its fix.** A fix without a row is not merged.
- **Worktrees are short-lived.** They branch from `research`, hold results only, and return harness edits as PRs; STATE.md lists `git branch --no-merged research`.
- **Re-freezing the source pins is one command:** `rehearse.mjs --freeze --reason "<text>"`. It writes the next `jev-transmission-preflight.vN.json`, refuses an empty reason, and is followed by a rehearsal.

## 5. Safety

- **No auto-resend of an uncertain POST.** Rehearsal never contacts a paid endpoint: the Jev client is the double, `jevConfig` is `{}`, and the real `createJevClient` throws under rehearsal.
- **The shared ledger is never reset or rewritten.** Rehearsal uses a copy at a different real path and fails if the shared ledger's sha256 changed.
- **Hidden tests stay out.** The doubles read only `public-checks/controls/` and public inputs. Per controls/NOTES.md, those controls were written from the instruction alone. A test checks that rehearsal.mjs never opens `grade.json` or the heldout `tests/`.
- **Historical evidence is preserved.** Output goes to new `wx`-created `benchmark-runs/rehearsal-*` directories; replay only reads paid-run originals.
- **Fail closed.**
  - The gate refuses a missing, stale or mismatched record, a dirty tree, an unmatched row, or a `WOULD_HTTP_400`.
  - A task without a public reference control cannot pass, so it cannot be spent on.

## 6. Cost

**Build: about 500 lines in total.**

| File | Change | Size |
|---|---|---|
| rehearsal.mjs | new | ~250 |
| rehearse.mjs | new | ~60, including replay and freeze |
| faults.v1.json | new | ~60 |
| test/rehearsal.test.mjs | new | ~80 |
| adaptive-dag-comparison.mjs | edit | +10 |
| adaptive-dag-runner.mjs | `assertRehearsal` | +20 |
| dag-runner.mjs | probe | +8 |
| adaptive-failure.mjs | attribution table | +25 |
| two mock-arm tests | use the shared doubles | about −80 |

**Run.**
- Model cost is zero.
- Rows that stop before any check run take seconds.
- The three rows that run checks (`baseline`, `partial_execution`, `public_defect`) need roughly 10-30 minutes of Docker time for h2. That is less than one paid run's wall time, against 30 of 41 arms lost to pipeline stops.

## 7. Verification without paid runs

- **Catching past defects.** On the pre-fix commits of h2 pilots 01-03, D086 and codex-mac Jev, rehearsal must fail with each original stop code; likewise with a dangling `claude` on `PATH` and the v8 manifest.
- **Current head.** Rehearsal passes, and the shared ledger hash is unchanged.
- **Replay.** Replaying pilot-01 labels n1 `harness`.
- **Gate unit tests.** Refuse a dirty tree, stale rehearsal, other manifest or image, and a non-`research` descendant.

## 8. Risks and what it does not solve

- **Provider behaviour.** Doubles miss real outputs, provider token counting, rate limits and POST-only provider changes.
- **Coverage.** Coverage is limited to the fault matrix and the reference control.
  - A new failure shape escapes once, then becomes a row.
  - `unmapped_paths` reports artifact kinds the reference misses but does not block.
- **New tasks.** A task without a public reference control needs one written from its instruction first.
- **Docker time** grows with the matrix.
- **Out of scope.** Model quality, and whether new dated builds should be whitelisted.
