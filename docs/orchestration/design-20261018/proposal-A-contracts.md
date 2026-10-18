# Design A — Explicit run contracts, checked for free at probe time

## 1. Diagnosis

The pipeline already records facts about its world: h2's `environment.json` says Python 3.10.20 (`benchmarks/e2e-swe/heldout/h2/public-checks/environment.json:7`), the ledger snapshot says `remaining_input_tokens: null`, the manifest pins `profile_policy.cli_version`. What is never written down is what the **harness itself** needs: `tomllib`, a fixed model ID, a `claude` binary at that version, a finite ledger cap, 93 checks, every leaf run before repair. These needs live inline, in duplicated copies (READINESS in `src/benchmark/dag-runner.mjs:48` and `src/benchmark/adaptive-dag-runner.mjs:701`; capacity logic in `dag-runner.mjs:165-169` and `adaptive-dag-runner.mjs:650-667`). The `--probe` preflight (`dag-runner.mjs:154-199`) checks a fixed list of facts, not the harness's needs against them, so a mismatch shows up only as a paid-run stop code. Fixes then land on whichever branch found them, because nothing ties a paid run to one main line.

## 2. Design

**A. Assumption contract** — `docs/orchestration/contracts/run-assumptions.v1.json`. Each entry has `id`, `kind` (`task_env | provider | host | ledger | task_shape | code_path`), `probe` (the name of a check function), `blocker` (stop code), and `source` (file:line of the code that relies on it). Example entries:

```json
{"id":"harness.readiness.toml","kind":"task_env","probe":"readinessControl","blocker":"HARNESS_READINESS_CONTROL_FAILED","source":"src/benchmark/adaptive-dag-runner.mjs:701"}
{"id":"provider.settlement_model","kind":"provider","probe":"requestedModelSettles","blocker":"PROVIDER_MODEL_UNSETTLEABLE","source":"src/benchmark/budget.mjs:22"}
```


**B. Probe checks** — extend `preflightDagRun` (`dag-runner.mjs:154`). It loops over the contract, runs each check, and returns `assumptions: [{id, status: held|violated|unverified, observed}]`. Any `violated` or `unverified` result becomes a blocker (fail closed). `--spend` already refuses when blockers exist (`adaptive-dag-runner.mjs:1054`, `:1200`). The checks are:

- **Task environment, by execution rather than by declaration.** The probe runs the real harness program in the pinned image with `network none`. It runs `READINESS_CODE` (exported at `adaptive-dag-runner.mjs:721`) on a two-artifact fixture: a valid `pyproject.toml`, which must pass, and a broken one, which must fail. The probe does the same for `READINESS_BATCH` and for `artifact-verifier.mjs`. Same normal/defect pattern as `auditPublicChecks` controls (`dag-runner.mjs:192`), reusing `runNamedContainer` (`:143`). Any import or syntax assumption is caught without listing it.
- **Provider identity.** Manifests request a **dated** model ID, never `jev-latest`. The probe already calls the free GET `listModels()` (`dag-runner.mjs:194`, `src/client.mjs:519`). It now requires the requested ID to appear in that listing **and** in `JEV_SETTLEMENT_MODELS` (`budget.mjs:22`). A response with `model !== requested` is recorded as `PROVIDER_MODEL_DRIFT`, settled under the requested ID, never resent.
- **Host tools.** The probe runs `claude --version` and `realpath $(command -v claude)` through `checkedProcess`, which is already used for `claude auth status` at `dag-runner.mjs:184`. Both must equal `profile_policy.cli_version`. (today compared only to a stored file, `adaptive-dag-runner.mjs:227`); same for `docker`, `python3`. A dangling link becomes `HOST_CLI_MISSING` instead of an unnamed `PROCESS_START_FAILED`.
- **Ledger shape.** One exported helper, `ledgerCapacity(snapshot) → {unlimited:true} | {remaining:n}`, goes in `src/benchmark/budget.mjs`. It replaces both copies of the inline logic (`dag-runner.mjs:165-169` and `adaptive-dag-runner.mjs:663-666`). A table test covers ledger v1–v4 × every manifest family.
- **Task shape.** Delete the openapi special case at `adaptive-dag-runner.mjs:121` (`? 93 :`). Every task then goes through `validateTaskPublicRegistry` (`:124`), which counts tests from the task's own input. Arms change from a version-keyed equality check (`:154`) to a check against the allowed set, plus one rule from `evaluation-protocol.v1.json`: a manifest marked `"purpose":"evaluation"` must contain `claude_all` so that each run has a same-run pair (protocol C09).
- **Code-path assumptions** (defect 1 is not environmental). Each such entry names a **mock scenario**: an injected-adapter run (`adapters.preflight`, `adapters.runCommand`, `adapters.jevClientFactory` already exist) that reaches the stage with the scenario state, here partial execution followed by repair. `npm test` runs these scenarios. `--spend` refuses unless `test/run-assumptions.test.mjs` passed at the current source digest. (receipt `benchmark-runs/.assumption-receipt.json`, `{source_digest, passed_at}`).

**C. Attribution record.** Each arm result (`adaptive-arm-result/v1`) gains two fields: `assumptions` (the probe report) and `attribution: harness | infra | model | user | unknown`. Attribution is set in one of two ways:

1. **Stop-code class.** `evaluation-protocol.v2.json` extends `ungraded_stop_codes` with a class for every code in `BUDGET_ERROR_CODES` and in the runner's `fail()` codes. A unit test enumerates the codes with `rg "fail\('([A-Z_]+)'"` and requires that each one has a class. `harness-style-report.mjs:89` already blocks on unclassified.
2. **Reference replay.** This applies to a graded or check-failed arm. Before any record names a model choice as the cause, `scripts/attribute-arm.mjs` (new, about 60 lines) replays the failing public check or readiness check, locally and for free, on the task's reference fixture in the same image. If the reference also fails, the attribution is `harness`. The n1 case would have shown this: the same check failed on a correct `pyproject.toml`. Public check IDs only.

## 3. Defects 1–7

1. **Partial-execution repair binding.** A code-path entry with a partial-execution mock scenario fails in `npm test`, and the receipt check blocks `--spend`. **Caught before paid.** The §4 ancestor rule also prevents it.
2. **Dated Jev 1.14 build rejected at settlement.** The manifest pins the dated ID, and the probe requires it in both `listModels` and the settlement whitelist. **Before paid.** Unrequested drift is recorded at response time with no resend.
3. **`tomllib` on Python 3.10.** The readiness control runs in the h2 image and the valid fixture fails. **Before paid** (a `--probe` of about 10 s).
4. **`null` ledger capacity.** One `ledgerCapacity` helper plus the version × family table test. **Before paid** (unit test).
5. **Dangling Claude CLI.** `claude --version` and `realpath` checks give `HOST_CLI_MISSING`. **Before paid**; it is already free today, and now it has a named cause.
6. **Openapi hard-coding.** The `93` constant is removed, and the registry, count and environment are derived per task in the loader. **Before paid** (load time).
7. **No same-run baseline.** The loader rejects an evaluation manifest without `claude_all`. **Before paid** (load time).

## 4. Process

- **One integration line.** Merge `origin/research` and `research-d095-final-20261017` into `feat/heldout-eval-20261018` once, then rename it `research`. Every fix after that is a short branch off `research` and merges the same day. The main checkout holds no uncommitted fixes.
- **Paid runs from `research` only.** A new probe blocker, `SOURCE_NOT_ON_MAINLINE`, fires unless `git merge-base --is-ancestor research HEAD` succeeds and `git status --porcelain` is empty for the pinned source paths.
- **Stray-fix sweep** (free, run before each paid batch). `git branch --no-merged research` plus `git -C <wt> status --porcelain` for each entry in `git worktree list`. A warning; it would have listed `adaptive-partial-repair.mjs` and the D086 whitelist edit.
- **Pin refreeze becomes a command.** `scripts/freeze-transmission-policy.mjs --reason "<text>"` writes `jev-transmission-preflight.v(N+1).json`. It refuses an empty reason and never rewrites vN. CI checks that the newest policy hashes match the sources.
- **Every new defect adds one contract entry** and its probe or scenario in the same commit.

## 5. Safety

- **No uncertain resend.** Probes make no POST (`listModels` is a GET; the rest is local). Drift is recorded, never retried.
- **Ledger untouched.** Read via `readTokenBudgetSnapshot` only; `ledgerCapacity` is pure.
- **Hidden tests isolated.** Controls and the attribution replay use public fixtures and public check IDs only. `attribute-arm.mjs` rejects any path under the hidden test root, reusing D080's hidden-path rejection.
- **Historical evidence preserved.** Contract, protocol and policy changes are new vN files. Old manifests still load; run directories are read only.
- **Fail closed.** `unverified`, missing receipt, unclassified code or off-mainline source all block spend.

## 6. Cost

**To build:** `dag-runner.mjs` +90 (contract loop), `adaptive-dag-runner.mjs` −25/+20, `budget.mjs` +12, response-model assertion +5, contract JSON ~80, readiness fixtures (4 files), `evaluation-protocol.v2.json` ~40, `attribute-arm.mjs` ~60, `freeze-transmission-policy.mjs` ~50, `test/run-assumptions.test.mjs` ~250.

Total: about 600 lines across about 10 files, plus the one-time merge.

**To run:** about 15–30 s more per `--probe`; zero paid tokens.

## 7. Verification without paid runs

- **Defect replay suite.** One test per defect, using injected adapters:
  - a `runCommand` that runs the real h2 image, or a stub returning `ModuleNotFoundError: tomllib` (1/3);
  - a `listModels` that returns only the dated 1.14 build (2);
  - a v4 unlimited snapshot with a v1 catalog manifest (4);
  - a `claude` path that does not exist (5);
  - a heldout manifest (6);
  - a v8 evaluation manifest without `claude_all` (7);
  - the partial-execution repair scenario (1).

  Each asserts the named blocker; reverting each fix in a scratch branch must turn its test red.
- **Real free probe.** Run `node scripts/adaptive-dag-comparison.mjs --probe` against the h2, pycparser and django-modelcluster manifests with local Docker. All assumptions should be held. Removing the tomli fallback should flip h2 to `HARNESS_READINESS_CONTROL_FAILED`.
- **Attribution backtest.** Run `harness-style-report.mjs` over the 57 recorded arms with protocol v2. All 30 harness or policy stops should be classed, none unclassified. `attribute-arm.mjs` on pilot-03 n1 should return `harness`.

## 8. Risks and limits

- **Dated model IDs may not be accepted.** If Jev or Vercel will not accept a dated model ID in the request, provider identity drops to response-time detection only, which still has no resend but is after the call. This needs one manual GET check of the docs or models list.
- **The contract only covers assumptions someone has listed.** Execution controls catch broad classes, but code-path scenarios must be written. A new class can still surface in a paid run once; it is then classified, attributed and added.
- **Out of scope:** model-quality failures, oversized requests (HTTP_ERROR ×7, token admission's job), provider outages.
- **The one-time three-way merge may conflict** in `adaptive-dag-runner.mjs` and the pin files. It needs a careful pass and a full `npm test`.
