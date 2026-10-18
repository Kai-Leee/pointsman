# Design brief: why Jev full-development runs keep stopping on pipeline defects

Repository: /Users/lee/workspace/plugins/jev-router. Current consolidated branch: worktree /Users/lee/workspace/plugins/jev-router-heldout-20261018, branch feat/heldout-eval-20261018. Read AGENTS.md "유지할 경계" and docs/orchestration/EVALUATION_PROTOCOL.md first.

## What the system is
Jev Router / Pointsman: an external Jev model makes typed runtime choices inside a multi-agent full-development pipeline. The choices cover decomposition, owners, model/effort profile per task, and repair owners. Claude CLI workers implement the code. Public checks gate the result, and hidden independent tests grade it. Paid runs take 12-40 min each.

Safety rules that must survive any redesign:
- Never auto-resend an uncertain paid POST.
- Never reset or rewrite the shared ledger.
- Hidden tests never enter planning or repair.
- Preserve historical evidence.
- Fail closed on integrity problems.

## Evidence: stop causes
Classification of 57 arms (local plus sibling worktrees; benchmark-runs/heldout-h2-pilot-03/report.json and benchmark-runs/eval-protocol-20261017-01/report-combined.json):
- 41 arms did not succeed.
- 29 of the 41 ended with pipeline, infrastructure or policy stop codes, not code-quality failures. Pilot-03's ARTIFACT_CHECK_NOT_PASSED was also a harness defect, so the total is 30/41.
- Counts: HTTP_ERROR 7 (own oversized requests), ARTIFACT_CHECK_NOT_PASSED 7, ADAPTIVE_INFERRED_ARTIFACT_BINDING 3, ADAPTIVE_ARM_TOKEN_LIMIT 3, NO_ARM_RESULT 3, ADAPTIVE_TOKEN_PREFLIGHT_BLOCKED 2, BUDGET_LOCKED 2, BUDGET_MODEL_UNSUPPORTED 2, PROVIDER_FAILED 2, graded_incomplete 4, and single cases of others.

## Defects found in the last two days, each discovered only by a paid run or a manual probe

| # | Defect | Where | Hidden assumption | Fix already existed elsewhere? |
|---|---|---|---|---|
| 1 | Partial execution → repair-owner binding refuses artifacts with no revision (ADAPTIVE_INFERRED_ARTIFACT_BINDING; D086 jev_all, codex-mac Jev, h2 pilot-01) | src/orchestration/adaptive-inferred-repair.mjs:102 | Every leaf ran before repair | Yes: adaptive-partial-repair.mjs (2026-10-15), uncommitted in main checkout; also in branch research-d095-final-20261017; not in origin/research |
| 2 | Jev returned dated build typesafe/jev-1.14-20261014 and the settlement whitelist rejected it (BUDGET_MODEL_UNSUPPORTED; D086, h2 pilot-02) | src/benchmark/budget.mjs:22 | Provider model IDs are fixed | Yes: D086 branch (2026-10-16), uncommitted |
| 3 | Readiness check imports tomllib; the h2 task image is Python 3.10 → every pyproject.toml owner fails whatever model writes it (h2 pilots 01-03, n1 failed 3/3 with identical artifact) | src/benchmark/adaptive-dag-runner.mjs READINESS, src/benchmark/dag-runner.mjs | Task images are Python ≥3.11 like openapi | Yes: src/orchestration/artifact-verifier.mjs has a tomli fallback since 2026-10-12; scripts/lifecycle-e2e-resume.mjs records "controller Python3.10 has no tomllib" |
| 4 | v1 catalog preparation compared null remaining tokens of the unlimited ledger (since D067) → always refused | adaptive-dag-runner.mjs assertAdaptiveCohortCapacity | Ledger has a finite cap | No |
| 5 | Pinned Claude CLI 2.1.293 binary removed; /opt/homebrew/bin/claude dangles → probe PROCESS_START_FAILED | host | Host CLI version is fixed | No |
| 6 | Whole pipeline hard-coded to openapi (93 public checks, registry.v4, D066 catalog) | adaptive-dag-runner.mjs loader | Only one task exists | Partly (generalized 2026-10-18) |
| 7 | v8+ manifests admit only the jev_profile arm → no same-run Claude-only baseline | loader `value.arms` check | Comparison was settled earlier | No |

Process facts:
- Research history is split across at least three lines: origin/research (D084/D085), research-d095-final-20261017 (D087-D095, built on the older D083 commit), and feat/heldout-eval-20261018.
- There are 12 worktrees and 19 local branches.
- The main checkout has about 100 uncommitted files from parallel sessions.
- Source pins (jev-transmission-preflight.v11.json) must be re-frozen after almost every runner edit. One re-freeze silently missed its reason field.
- A misattribution happened: the pilot record first said n1 failed after Jev chose claude_haiku55_low. The real cause was defect 3, so the model choice was irrelevant.

## The question
After fixing each defect directly, the same class of failure keeps coming back: a hidden assumption about environment, provider or task, found one at a time in paid runs, with fixes that already existed elsewhere and never reached the main line. Design a better system and process that removes this class of failure while keeping the safety rules above.
