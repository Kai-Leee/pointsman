# Verdict: X vs Y vs Z

Checked at `1aa547e`. Defects 2-4 are already fixed at HEAD (`budget.mjs:26-27`, `adaptive-dag-runner.mjs:712-713`, `:664-665`), so any defect replay must revert each fix first.

## 1. Claim checks

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| X1 | d080 test hard-codes the ledger snapshot (:13) | confirmed | lines 13-14 |
| X2 | `cohortPreflight` is a fixture (:25) | confirmed | line 26, `environment: {fixture: true}` |
| X3 | `listModels` returns only `jev-latest` | confirmed | line 29 |
| X4 | protocol v1 :18-27 charges BINDING, MODEL_UNSUPPORTED and ARTIFACT_CHECK as zero | confirmed | `evaluation-protocol.v1.json:18-27` |
| X5 | `--spend` already runs `preflightAdaptiveComparison` (comparison.mjs:26) | **wrong, load-bearing** | `:25` calls it only when `!spend`; spend goes `runAdaptiveArm` → `adaptivePreflight` → `preflightDagRun`, so X's line check and lint never run |
| X6 | `research` is an ancestor of HEAD and the D095 line is not | confirmed | `git merge-base --is-ancestor` |
| X7 | `ddbf44d` is the tomli fix | confirmed | commit subject |
| Y1 | READINESS is duplicated (dag-runner:48, adaptive:701) | confirmed | two sources |
| Y2 | ledger-capacity logic is duplicated (dag-runner:165-169, adaptive:650-667) | confirmed | |
| Y3 | h2 `environment.json:7` says Python 3.10.20 | confirmed | line 7 |
| Y4 | `listModels` is a free GET (dag-runner:194, client:519) | confirmed | |
| Y5 | hard-coded 93 at :121; arms equality check at :154 | confirmed | |
| Y6 | spend refuses on preflight blockers (:1054, :1200) | confirmed | `:1203 ADAPTIVE_PREFLIGHT_BLOCKED` |
| Y7 | `runNamedContainer` at :143 | minor error | defined at :112 |
| Y8 | dated model IDs are accepted in requests | unverifiable | Y flags this risk itself |
| Z1 | adapters at :1031 / :336 / :477 / :490 | confirmed | |
| Z2 | the d080 test fakes docker and every check passes (:44-90) | confirmed | returns `status: 'passed'` unconditionally |
| Z3 | `jev-1.13.0` hard-coded (:41) | confirmed | at :42 |
| Z4 | reference controls and `defects.json` exist, written from the instruction only | confirmed | 3 tasks; h2 `NOTES.md` |
| Z5 | `unavailable_runtime_import` control exists | confirmed | h2 `controls/catalog.json`, `defects.json` |
| Z6 | inferred-repair refusal at :91 | confirmed | :91-95 |
| Z7 | `preflightAdaptiveComparison` at :1282; CLI compared at :227 | confirmed | :1283, :227 |

## 2. Scores (0-5)

| Criterion (weight) | X | Y | Z |
|---|---|---|---|
| C1 hidden-assumption class (3) | 3 | 3 | 4 |
| C2 defects 1-7 before paid (2) | 4 | 4 | 4 |
| C3 one main line (2) | 4 | 5 | 4 |
| C4 attribution (2) | 3 | 5 | 4 |
| C5 safety (2) | 2 | 3 | 5 |
| C6 cost / leanness (1) | 4 | 4 | 3 |
| C7 verifiable unpaid (1) | 5 | 5 | 5 |
| C8 residual-risk honesty (1) | 4 | 4 | 4 |
| **Weighted total (max 70)** | **48** | **56** | **58** |

Reasons:
- **C1.** Z rehearses the full pipeline with only the paid boundaries faked, so it catches unlisted assumptions, and its `oversized_request` row targets HTTP_ERROR (7, the largest class). X's register and Y's contract are lists.
- **C2.** All catch 1 and 3-7; none catches 2 when the dated build first appears in a POST response.
- **C3.** Y's stray-fix sweep goes straight at "fix existed elsewhere"; X's gate is unreachable on `--spend` (X5).
- **C4.** Y requires a class for every `fail()` code and replays on the reference fixture; Z lacks the completeness test; X's signatures work only after registration.
- **C5.** X and Y settle an unknown model at a guessed multiplier (section 5).
- **C6.** Z costs 10-30 min Docker per task, valid 24 h.

## 3. Winner: Z

Z is the only design that removes the root cause both other proposals also name: the tests fake the very boundaries where the defects live. It is also the only design with no safety violation. It wins by 2 points over Y, and Y supplies Z's missing parts.

## 4. Merge list (into Z)

1. **Y's `SOURCE_NOT_ON_MAINLINE` and stray-fix sweep** in `preflightDagRun` (spend path): `git branch --no-merged research` and each worktree's porcelain status; blocking for pinned source paths. Gap: Z refuses a dirty tree but cannot see a fix on another line.
2. **Y's completeness test**: every `fail()` and `BUDGET_ERROR_CODES` code has a class in protocol v2. Gap: Z's static table can silently miss new codes.
3. **Y's single helpers**: one `ledgerCapacity()` and one READINESS source for both runners. Gap: the verified duplicates let a fix land in one copy only.
4. **Y's host check**: `realpath` plus `--version`, named `HOST_CLI_MISSING`. Gap: Z gives an anonymous `PROCESS_START_FAILED`.
5. **X's harness-yield line** per condition, listing excluded stops with fix commit. Gap: Z's exclusions have no visible denominator.
6. **Y's fast probe tier** before the long rehearsal rows. Gap: Z's run cost.

Not merged: X's signature register and Y's assumption contract; the rehearsal plus fault rows subsume them.

## 5. Safety flags

- **X, provider degrade.** "Settle at the highest whitelisted multiplier … and continue" violates fail-closed on a billing anomaly. It writes a guessed settlement to the shared ledger and bypasses the existing block-and-reconcile path (`budget.mjs:168`, `:432-446`). **Reject.**
- **Y, `PROVIDER_MODEL_DRIFT` "settled under the requested ID".** This is the same guessed-multiplier problem. **Reject.** Keep the `BUDGET_MODEL_UNSUPPORTED` block and offline `reconcile`, and stop the arm.
- **X, cleanup.** "Delete worktrees and branches already contained in `research`" can delete untracked `benchmark-runs/` evidence that lives only inside a worktree. This breaks the rule to preserve historical evidence unless every worktree is first checked for untracked files.
- **Z, salvage commit.** Committing the main checkout's ~100 files from parallel sessions could capture in-flight work from other sessions. It is not a listed rule, but it needs coordination, and only an archive branch with no edits is acceptable.
- **X, gate placement (X5).** As written, the integrity gate is skipped on `--spend`, so the system would fail open. It must move into `adaptivePreflight` or `preflightDagRun`.

## 6. Build order for the merged design

1. **One line**: archive-tag every branch and worktree (no deletion); merge the D095 line and `feat/heldout-eval-20261018` into `research`; add `SOURCE_NOT_ON_MAINLINE` and the sweep.
2. **Dedupe**: shared `ledgerCapacity()` and READINESS; host CLI `realpath` check; `listModels` vs whitelist probe; ledger-version × manifest-family unit table.
3. **`rehearsal.mjs`**: doubles moved out of the d079/d080 tests; ledger copy with sha256 before/after; `faults.v1.json` rows; every protocol-required arm.
4. **Attribution**: `attribution` in `adaptiveTerminalCause`; `evaluation-protocol.v2.json` (v1 kept); completeness test; `--replay` with reference swap; harness-yield line; backtest on the 57 arms with zero unclassified.
5. **Gate**: `assertRehearsal()` in `runAdaptiveArm` and `runAdaptiveComparison`; one pin-freeze command that refuses an empty reason; replay the 7 defects with fixes reverted and assert each blocker.
