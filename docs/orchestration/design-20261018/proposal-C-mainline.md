# Design C: one line, one defect register, classified stops

Paths are relative to `jev-router-heldout-20261018` at `1aa547e`.

## 1. Diagnosis

Each defect sits on a boundary that the tests replace with a fixture holding the same assumption as the code. `test/d080-defaults-mock-arm.test.mjs:13` hard-codes the ledger snapshot. Line 25 stubs `cohortPreflight` with `environment: {fixture: true}`. `listModels` returns only `jev-latest`, and the decision stub always answers with the openapi D066 catalog. So defects 1, 2, 3, 4 and 6 can only fail against the real boundary, which means in a paid run. Each fix then lands on whichever of the three research lines the session was using. `research-d095-final-20261017` is not an ancestor of HEAD, and the main checkout holds about 100 uncommitted files. A paid run cannot know that a fix exists, and the report has no field for "this stop is harness defect X". `evaluation-protocol.v1.json:18-27` puts `ADAPTIVE_INFERRED_ARTIFACT_BINDING`, `BUDGET_MODEL_UNSUPPORTED` and `ARTIFACT_CHECK_NOT_PASSED` under `system_failure_counted_as_zero`, which charges harness defects to the Jev arm. That is how n1's tomllib failure was first read as a Haiku choice.

## 2. Design

There are three pieces. All reuse existing modules, and none adds a new runtime layer.

**A. Register `docs/orchestration/contracts/known-defects.v1.json`**, the only authority, with two tables:

```json
{"schema_version":"known-defects/v1",
 "code_classes":{"ADAPTIVE_INFERRED_ARTIFACT_BINDING":"harness","BUDGET_LOCKED":"environment",
   "PROVIDER_FAILED":"provider","ADAPTIVE_ARM_TOKEN_LIMIT":"policy","ARTIFACT_CHECK_NOT_PASSED":"model_output",
   "ADAPTIVE_CANCELLED":"user", "...":"..."},
 "defects":[{"id":"KD-003","class":"harness","hidden_assumption":"task image Python>=3.11",
   "signature":{"stop_code":"ARTIFACT_CHECK_NOT_PASSED","error_code":"ModuleNotFoundError","message_contains":"tomllib"},
   "fix":{"commit":"ddbf44d","status":"on_line"},"check":"probe.readiness_fixture",
   "seen_in":["benchmark-runs/heldout-h2-pilot-03"]}]}
```

`fix.status` takes one of four values: `on_line`, `committed_off_line` (the commit is given), `uncommitted` (the worktree path is given) or `none`. `check` names the probe or rehearsal check that now detects the defect. A defect without a check cannot be entered.

**B. A stop class on every terminal stop.** `adaptiveTerminalCause` (`src/orchestration/adaptive-failure.mjs:17-28`) gains two fields: `class`, looked up from `code_classes`, and `defect_id`. `defect_id` is filled when the terminal cause plus the arm's last check error match a register `signature`, and a match overrides `class` to `harness`. Codes that are not in the table get `unclassified`, which already blocks citing a report (EVALUATION_PROTOCOL §3). The value flows into `stop_code`/`terminal_cause` in `adaptive-dag-execution.mjs:1267` and the arm results. `scoreRun` (`scripts/harness-style-report.mjs:83-89`) then reads the class rather than the three code lists, and the protocol code lists move into `code_classes`:

- `model_output` and `policy` count as 0 under ITT.
- `harness`, `environment`, `provider` and `user` are excluded. They are listed with `defect_id` and the fix commit ("harness defect KD-003, fixed in ddbf44d").
- A per-condition harness-yield line keeps a breaking pipeline visible.

**C. A launch gate.** It is added to `preflightAdaptiveComparison` (`src/benchmark/adaptive-dag-runner.mjs:1283-1290`), which `--spend` already runs (`scripts/adaptive-dag-comparison.mjs:26`). Every check is free.

1. **Line check.** `git merge-base --is-ancestor <fix.commit> HEAD` for every defect not in status `none`. A miss gives `KNOWN_DEFECT_FIX_ABSENT:<id>`. A fix in status `uncommitted` gives `KNOWN_DEFECT_FIX_UNCOMMITTED:<id>`. `git status --porcelain -- src scripts docs/orchestration/contracts benchmarks/e2e-swe/manifests` must be empty, and the attestation records the HEAD sha.
2. **Boundary probe.** This extends `preflightDagRun` (`src/benchmark/dag-runner.mjs:154-200`), and each check is taken from a register `check`:
   - `probe.readiness_fixture` runs the real `READINESS_CODE` (`adaptive-dag-runner.mjs:701-716`) and `artifact-verifier.mjs:6` imports in the real task image on known-good fixtures, via `runNamedContainer`.
   - `probe.host_cli` resolves `claude` with `realpath`, runs `--version` (moved from `runner.mjs:127`) and compares the result to the manifest's attested version.
   - `probe.model_ids` blocks any `listModels()` ID (`dag-runner.mjs:194`) missing from `JEV_SETTLEMENT_MODELS` (`budget.mjs:22-28`).
   - `probe.ledger_shape` runs `assertAdaptiveCohortCapacity` and the catalog-preparation path against the real snapshot. The snapshot is read only.
3. **Manifest lint against the protocol.** A comparison manifest must contain `claude_all` plus the same-run Jev arms (rule `paired_baseline` in `evaluation-protocol.v1.json`). This catches the `v8 ? ['jev_profile']` restriction at `adaptive-dag-runner.mjs:154`.
4. **Rehearsal (`--rehearse`).** This new flag in `scripts/adaptive-dag-comparison.mjs:12` runs the real manifest and the real task through `runAdaptiveArm` with the existing mock adapters (`jevClientFactory`, `runCommand`, `openBudget`). Three adapters stay real: `cohortPreflight` is the real probe result from step 2, `openBudget` opens a temporary copy of the real ledger, and readiness and public checks run in the real image. The fake Jev plays scenarios (leaf stopped then repair, unseen dated model ID, every arm); the fake worker writes minimal valid files. It must pass per manifest and task before `--spend`.

**Fail-closed or degrade, by class.**

| Class | Before a paid call | During a run |
|---|---|---|
| integrity (ledger, hidden-test isolation, source pins, uncertain POST) | fail closed | fail closed. No resend and no ledger rewrite. Unchanged. |
| harness | fail closed (gate) | stop the arm with `defect_id`. No retry. Artifacts are kept for `preserved-artifact-repair-runner`. |
| environment | fail closed (probe) | stop and exclude |
| provider | fail closed (probe) | certain failure: stop and exclude. Uncertain: stop, mark uncertain, no resend. Response model ID outside the settlement set: degrade (see note). |
| policy | fail closed where it can be predicted (D072 size validator in rehearsal) | stop, counted 0 |
| model_output | not applicable | degrade into the existing repair loop |

Provider degrade: the call is billed and its token usage known, so settle at the highest whitelisted multiplier, record entry code `BUDGET_MODEL_UNSUPPORTED` (already in `ENTRY_CODES`, `budget.mjs:47`), queue offline reconciliation and continue. Today this aborts an arm whose spend is already sunk.

## 3. How each defect would have been caught

1. **Partial repair binding.** The rehearsal repair scenario hits `ADAPTIVE_INFERRED_ARTIFACT_BINDING` locally, and the `uncommitted` register entry blocks launch. Before.
2. **Dated Jev build.** `probe.model_ids` flags a listed build; one first seen in a response is settled by the provider degrade. Before, or degraded.
3. **tomllib on Python 3.10.** `probe.readiness_fixture` fails in the h2 image; the signature charges n1 to KD-003, not Haiku. Before.
4. **Null ledger cap.** `probe.ledger_shape` on the real v4 snapshot raises `ADAPTIVE_COHORT_BUDGET_INSUFFICIENT`. Before.
5. **Removed CLI binary.** `probe.host_cli` finds the dangling realpath (`environment`). Before.
6. **openapi hard-coding.** Rehearsal on each held-out task fails in the loader. Before.
7. **No same-run baseline.** The `paired_baseline` lint refuses the manifest (`policy`). Before.

## 4. Process changes

- **One line.** `research` becomes the only research line. It is already an ancestor of `feat/heldout-eval-20261018`, and `research-d095-final-20261017` is not. `feat/heldout-eval-20261018` and the D095 line are merged into it once, and conflicts are resolved by the register owner. After that, feature branches live less than a day and merge before any paid launch.
- **Paid runs launch only from a clean worktree** whose HEAD is reachable from `research`. The gate enforces both.
- **Fix-first.** A defect fix is a commit on `research` that, in the same commit, adds or updates its register entry and its `check`. Sibling worktrees take it with `git merge research`. The register, not memory, records that a fix exists. Writing a fix and leaving it uncommitted is allowed only with status `uncommitted`, and that status blocks launch.
- **Pins.** The D064 single owner keeps the register. Pin re-freezes go through one script that refuses an empty `reason`; `JEV_TRANSMISSION_SOURCE_DRIFT` (`jev-transmission-preflight.mjs:69-81`) still verifies them.
- **Cleanup.** After the merge, delete only worktrees and branches already contained in `research`. Tag any unmerged branch `archive/<name>` first so its history is kept.

## 5. Safety

- **No auto-resend.** No class has a retry path; rehearsal makes no network calls.
- **Ledger.** The gate only reads; rehearsal uses a temporary copy; degraded settlement uses the existing append-only `settle`.
- **Hidden tests.** Probe, rehearsal and signatures use only public checks, fixtures and terminal causes. Grading stays in `scripts/grade-adaptive-arm.mjs`.
- **History.** Run results are never edited; classes are computed at report time.
- **Fail closed.** Any gate check that cannot run counts as a blocker, never as a pass.

## 6. Cost to build and run

Build, about 450 lines: register JSON ~150; `adaptive-failure.mjs` ~30; `dag-runner.mjs` probe ~60; `adaptive-dag-runner.mjs` gate and lint ~60; `--rehearse` ~80 (adapters lifted from the d080 mock test); `harness-style-report.mjs` ~20; `evaluation-protocol` v2 (v1 kept); one pin re-freeze; tests ~150.

Run: probe about 30–60 s; rehearsal about 2–5 min per manifest and task pair, with no tokens. The merge is a one-time job of about half a day.

## 7. Verification (no paid calls)

- **Replay the seven defects.** Check out the parent of each fix commit, or a register fixture that reverts the fix, run gate plus rehearsal, and assert the expected blocker code. For defect 3, use the h2 image in Docker. For defect 4, use a copy of the real ledger. For defect 5, point PATH at a dangling symlink.
- **Reclassify the 57 arms.** Run the classifier over `heldout-h2-pilot-03/report.json` and `eval-protocol-20261017-01/report-combined.json`, and assert zero `unclassified` and that the 30 harness, environment, provider or policy stops are not charged as model_output.
- Full suite on `research` after the merge.
- **Negative control.** A clean HEAD gives `ready`.

## 8. Risks and what this does not solve

- The register only knows defects already seen. A new boundary assumption still slips through unless rehearsal exercises it. Rehearsal covers the boundaries the mocks used to stub, not every boundary.
- A misfiring signature could exclude a real model error, so every `defect_id` exclusion is listed with its evidence.
- Excluding harness stops shrinks n. Reporting harness yield keeps that exclusion from flattering the results.
- The one-time merge of three lines carries conflict risk in `adaptive-dag-runner.mjs`.
- It does not fix the defects themselves, the oversized-request HTTP_ERROR cause, or single-run statistics.
