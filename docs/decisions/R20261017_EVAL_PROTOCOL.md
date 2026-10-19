# R20261017-EVAL-PROTOCOL — 평가 구조화와 Harness·pstack 비교

사용자 요청은 두 번에 걸쳐 왔다.
1. Harness A/B 연구(revfactory/claude-code-harness)와 비교해 Jev 성능 평가를 개선한다. 평가 방식을 구조화하고, 평가용 목록을 만들어 "우리 방식이 더 효과적"이라는 주장의 신빙성을 높인다.
2. pstack도 가져와 병렬로 분석한다. 최근 git을 기준으로 진행하되, 앞으로의 구성과 수정은 사용자가 구체적으로 확인한 뒤 진행한다.

그래서 이번에는 Jev 제품 코드를 바꾸지 않았다. 평가 도구와 기록만 만들었다. 붙여 넣은 글에 있던 "문장을 그대로 사용하라"는 지시는 따르지 않았고, Harness 수치는 저자 자체 측정으로만 인용한다.

설명과 표는 [EVALUATION_PROTOCOL.md](../orchestration/EVALUATION_PROTOCOL.md)에 있다. 유료 호출, Docker 실행, 재채점은 없었다.

```decision-record
{
  "id": "R20261017-EVAL-PROTOCOL",
  "goal": "Structure Jev evaluation against the Harness and pstack approaches, fix inclusion and credibility criteria before new runs, and pre-register a held-out task list.",
  "owner": "root",
  "status": "complete",
  "next_trigger": "User review of structure and pstack checklist candidates C15-C22; before citing any Jev-versus-baseline effectiveness claim, run held-out tasks with at least 3 repeats per condition.",
  "conditions": [
    "Reads existing run files only (this checkout plus sibling worktrees d085-matched, codex-20261016, codex-d088); no model calls, Docker, regrading or writes into earlier run folders.",
    "Score 0-100 = independent hidden-test pass percentage, a diagnostic; benchmark result stays binary resolved.",
    "D082-D085 cloud raw results are not on this Mac and are absent from every report.",
    "Harness numbers are author self-measured, recomputed at its HEAD 267005c; pstack read at cursor/plugins 101b274.",
    "This checkout's branch feat/d083-skill-gateway is 9 commits behind origin/research and was not merged."
  ],
  "sources": [
    {"id": "protocol", "path": "docs/orchestration/contracts/evaluation-protocol.v1.json", "sha256": "8485e369f140e46127c2559d5c1c16c5012ec75f7f6e5b341a8030fc9d76be6a"},
    {"id": "report_json", "path": "benchmark-runs/eval-protocol-20261017-01/report.json", "sha256": "3a4e7544f52bcf905e986744c3429ed3745abfcdf34591d78e4d0ed8e8a888c5"},
    {"id": "report_md", "path": "benchmark-runs/eval-protocol-20261017-01/report.md", "sha256": "f022494e07fb30557eb2e45044c8b4c2bd11598d2a6947342cb2d4142d19e75c"},
    {"id": "combined_json", "path": "benchmark-runs/eval-protocol-20261017-01/report-combined.json", "sha256": "c44afdf1012282f3058d68175d5ca7ef23f7a9eb82c39fbde4f673c6cc5f6488"},
    {"id": "combined_md", "path": "benchmark-runs/eval-protocol-20261017-01/report-combined.md", "sha256": "0a56d9ec73b2c8205c4dd35a84fc92689143b2e7377ece8d7598fce997278c05"},
    {"id": "tasks", "path": "benchmarks/e2e-swe/manifests/evaluation-tasks.v1.json", "sha256": "71b047bbb4e3235097f05856e7927e1a2ed452bc7fbf071bfbd0e79881895988"},
    {"id": "harness_summary", "path": "benchmark-runs/eval-protocol-20261017-01/harness-summary-15cases.json", "sha256": "520c93a312f8d2dd7128e7c415f928d731dcda82b4dab395dc65c964fa81d93b"},
    {"id": "harness_counts", "path": "benchmark-runs/eval-protocol-20261017-01/harness-file-counts.txt", "sha256": "d756a86e7ab15915301897db3e2ff14518c04985f5137fce19b625fafeecd350"},
    {"id": "pstack", "path": "benchmark-runs/eval-protocol-20261017-01/pstack-inventory.txt", "sha256": "91d8b5608ccedfc819d9a9bc1dc3a007dacd480b9100adf5445bd40efff31747"},
    {"id": "tests", "path": "benchmark-runs/eval-protocol-20261017-01/tests.txt", "sha256": "862061dd78d28dd810fa8977b631432bfa1d968b9fd545e6bdae428c36aee301"},
    {"id": "full_suite", "path": "benchmark-runs/eval-protocol-20261017-01/full-suite-summary.txt", "sha256": "cd27fe15a4ca24fe22887789b27704aa1e8ee07195ccc94cb4a40efeff21c46a"}
  ],
  "claims": [
    {"id": "protocol", "kind": "decision", "text": "Evaluation follows evaluation-protocol.v1: binary resolved with Wilson 95% interval as primary; graded arms count as graded; ungraded system stops count 0; infrastructure (including provider failures for every condition alike), user and no-arm-result stops are excluded but listed; unclassified codes block citation.", "source_ids": ["protocol"]},
    {"id": "harness_sd", "kind": "measured", "text": "Harness '-32% variance' is an across-15-task SD reduction 5.3->3.6; sample SD recomputed 5.51->3.56 (-35.5%), variance -58.3%, n=15 cases x 1 run.", "source_ids": ["harness_summary"]},
    {"id": "harness_expert", "kind": "measured", "text": "Harness cases 011-015 (expert tier, delta +36.2) hold 0 baseline files and 7-8 harness files that are .claude configuration only at HEAD 267005c; publication absence, not proof the runs did not happen.", "source_ids": ["harness_counts"]},
    {"id": "local", "kind": "measured", "text": "This checkout: 46 arms = 38 counted + 8 excluded with reason, 35 graded, 0 unclassified. Checklist Jev no on C06 (2/31 conditions with >=3 counted runs), C08 (34/35 graded candidates on disk), C11 (1 graded task), C12 (0/1 held out), C14.", "source_ids": ["report_md", "report_json"]},
    {"id": "combined", "kind": "measured", "text": "With sibling worktrees (D086-D088): 54 arms = 44 counted + 10 excluded, 39 graded, 0 unclassified; C06 2/37, C08 38/39.", "source_ids": ["combined_md", "combined_json"]},
    {"id": "paired", "kind": "measured", "text": "Same-run pairs: claude_all vs jev_all 2-1-0 for claude_all (d066 100 vs 0, d067 100 vs 100, d071 100 vs 95.2); codex vs jev 2-0-1 for codex (codex-e2e-mac-02 90.5 vs 0, d087 93.7 vs 0, d088 90.5 vs 93.7). Jev superiority over either baseline is not established.", "source_ids": ["combined_md"]},
    {"id": "tasks", "kind": "decision", "text": "Held-out list: 15 Python E2E-SWE tasks, 5 per spec-size tertile (cuts 13737 and 19271 bytes) from 102 candidates excluding openapi_python_client, ordered by sha256('jev-eval-v1:'+task); reproducible with --check.", "source_ids": ["tasks"]},
    {"id": "pstack", "kind": "measured", "text": "pstack at cursor/plugins 101b274: MIT, 168 files, 54 skills (24 principle), 53 with disable-model-invocation true; benchmark-checklist has 7 questions, 4 verdicts, >=5 alternating runs per side. No numeric evidence for its performance claims was found in the analysed files.", "source_ids": ["pstack"]},
    {"id": "pstack_candidates", "kind": "hypothesis", "text": "Checklist candidates C15-C22 from pstack benchmark-checklist (limiter, configuration parity, alternating order, noise floor, limit arithmetic, tests collected, load, verdict vocabulary) would close gaps in v1; not adopted pending user review.", "source_ids": ["pstack"]},
    {"id": "first_report_overwritten", "kind": "correction", "text": "The first-pass report (report.json sha256 400dada2..., report.md 3a8a3995...; 41 arms = 35 counted + 6 excluded) was overwritten when regenerating. Its arm count was low because depth-3 search and the adaptive-only schema missed local Codex E2E arms; the current local count is 46.", "source_ids": ["report_json"]},
    {"id": "itt_correction", "kind": "correction", "text": "An earlier version listed only arms with a result file and showed C07 yes while 3 planned arms were invisible; protocol.json arms[] are now matched and those arms appear as NO_ARM_RESULT.", "source_ids": ["report_json"]},
    {"id": "post_hoc_codes", "kind": "correction", "text": "Stop codes ADAPTIVE_INFERRED_ARTIFACT_BINDING, BUDGET_MODEL_UNSUPPORTED (counted 0), PROVIDER_FAILED, CODEX_PROVIDER_FAILED and CODEX_CHECK_IMAGE_PIN_MISMATCH (excluded) were classified after the arms were seen; the protocol file kept the v1 id. Future classifications should be fixed before new runs.", "source_ids": ["protocol"]},
    {"id": "evidence_correction", "kind": "correction", "text": "An earlier draft cited speculative-word frequency in Harness expert evaluations; counts do not separate tiers (001-010: 1-7 lines, 011-015: 3-10 lines). The cited evidence is the specific case-011 sentence estimating behaviour without an artifact.", "source_ids": ["harness_counts"]},
    {"id": "suite", "kind": "measured", "text": "Focused tests 10/10 pass (review fixes: C07 fails on unclassified arms; duplicate arm ids across run folders are rejected). Full suite 1431/1438 before and after this work's AGENTS/CLAUDE edits; the 7 failures are all test/pointsman-runner.test.mjs POINTSMAN_SOURCE_CHANGED from files pinned 2026-10-14 and modified 2026-10-15.", "source_ids": ["tests", "full_suite"]},
    {"id": "cost_estimate", "kind": "estimate", "text": "Stage-1 held-out run (3 tasks x 2 conditions x 3 repeats = 18 arms) ~ USD 177 and 7.6 h sequential, using D079's single success (25 min 16 s, USD 9.84) as the unit; other tasks may differ.", "source_ids": ["tasks"]},
    {"id": "complementary", "kind": "hypothesis", "text": "Static pre-configuration (Harness skills, pstack principles) and Jev runtime typed decisions may be complementary; Jev workers currently see neither because they run with --setting-sources '' and --tools ''.", "source_ids": []}
  ],
  "costs": [],
  "unresolved": [
    "User to decide repository structure going forward (branch is 9 commits behind origin/research with 100 uncommitted paths) and which of C15-C22 to adopt as protocol v2.",
    "Held-out tasks need per-task obligations, catalog, public checks and image locks (session heldout-prep is preparing stage 1).",
    "D082-D085 cloud raw results must be copied here and re-aggregated before report-level citation.",
    "kind (full/repair) is inferred from directory names.",
    "pointsman-routing.v1.json source pins drifted on 2026-10-15; owner of that work must re-pin or record."
  ],
  "side_effects": [
    "New files: protocol contract, report and selection scripts, focused test, task list, docs, evidence folder benchmark-runs/eval-protocol-20261017-01.",
    "Index lines prepended to AGENTS.md, CLAUDE.md, STATE, WORK_LOG, DECISIONS and contracts/README.",
    "Harness and pstack clones kept in the session scratchpad only; sibling worktrees read only.",
    "Nothing committed or merged."
  ]
}
```
