# R20261019-REHEARSAL-D — readiness가 한 라운드에 깨진 결과물을 모두 보고하게 바꾸기

요청: 사용자가 "1번을 먼저 진행"이라고 지시했다(상위 세션 경유). 1번은 "readiness 검사가 한 번에 깨진 결과물을 모두 보고하게 바꾸기"다. `max_repair_rounds`를 늘리는 2번은 고르지 않았다. 유료 호출은 없고, 공유 장부는 리허설 복사본으로만 만진다. Claude 경로만 다룬다.

배경: [R20261018-REHEARSAL-C](R20261018_REHEARSAL_C.md)에서 작업별 readiness 검사가 첫 실패에서 멈추는 것을 확인했다. 그래서 결과물이 3개 이상 깨진 작업은 고정된 2번의 수리 라운드 안에 복구되지 않았다.

구현 커밋: `647638d`(브랜치 `feat/heldout-eval-20261018`).

## 바꾼 것

- **멈추는 위치**: [artifact-verification-gate.mjs](../../src/orchestration/artifact-verification-gate.mjs)의 `if (failure) throw failure;`가 첫 실패에서 멈춘다.
  - 이 파일은 h2·openapi 두 카탈로그의 `source-pins.json`에 고정되어 있다.
  - 카탈로그 재사용 허용 목록(`reuseMutableSources`)에는 없다. 그래서 고치면 두 과제의 카탈로그 재사용이 깨진다. 이 파일은 바꾸지 않았다.
- **수정 위치**: [adaptive-dag-execution.mjs](../../src/orchestration/adaptive-dag-execution.mjs)의 `runCheck` 감싸개.
  - 이 파일은 재사용 허용 목록에 있고, v11 고정 대상이 아니다.
  - 동작은 `partial_repair: local-readiness-v1`인 manifest에서만 켜진다. 다른 manifest의 동작은 그대로다.
  - 로컬 검사가 확실히 실패하면(불확실 아님), 같은 시도에서 그 작업의 남은 로컬 검사를 이어서 실행한다.
  - 이어서 실행한 검사의 증거도 `local_evidence`에 넣고, `adaptive_local_checks_continued` 이벤트를 남긴다.
  - 반환하는 결과는 원래의 첫 실패다. 따라서 작업은 그대로 실패한다(실패 시 닫힘 유지). 이어서 실행한 검사가 예외를 던지거나 불확실하면 치명적 실패로 남긴다.
- **테스트**: [adaptive-partial-repair.test.mjs](../../test/adaptive-partial-repair.test.mjs)에 추가했다. 한 작업에서 결과물 3개가 깨진 경우다.
  - 수정 전 코드에서는 실패했다. 라운드마다 깨진 검사가 하나씩만 드러났다(`check-core`, 그다음 `check-ir`).
  - 수정 후에는 0라운드에 3개가 모두 보고되고, 수리 1회로 완료된다.
- **고정 파일 점검**: v11 `source_pins`는 그대로다. 재고정 스크립트가 `REPIN_NO_CHANGE`(종료 코드 4)를 냈으므로 v11 계약과 d076 manifest는 바꾸지 않았다.
- **전체 테스트**: `npm test` 결과는 1417/1418이다. 이전 기준 1416/1417에 새 테스트 1개가 더해졌다. 남은 실패 1개는 이미 있던 D071 cohort dispatch 테스트다.

## 재리허설 결과

조건:
- 커밋 `647638d`, 깨끗한 트리에서 실행했다.
- 두 과제 모두 공유 장부 해시는 실행 전후로 같았다.
- 기록과 참조 대조군은 REHEARSAL-C와 같다.

| 과제 | baseline | readiness_failure | missing_output | unknown_model_build | 리허설 통과 |
| --- | --- | --- | --- | --- | --- |
| h2 | 완료, 공개 통과 | **완료, 공개 통과** | 완료, 공개 통과 | `BUDGET_MODEL_UNSUPPORTED` | **예** (4/4행 일치) |
| openapi | 완료, 공개 통과 | `ADAPTIVE_CAUSAL_HISTORY_INVALID`(수리 단계) | 완료, 공개 통과 | `BUDGET_MODEL_UNSUPPORTED` | 아니오 (3/4행 일치) |

**h2 readiness_failure**
- 0라운드에서 `readiness.10`이 실패한 뒤 `.12`와 `.13`을 이어서 실행했다.
- 부분 수리 후보는 결과물 3개(`A10-utilities`, `A12-connection`, `A13-roundtrip-tests`)를 모두 골랐다. provider 호출은 0회였다.
- 1라운드에 완료됐다.
- REHEARSAL-C에서는 같은 경우가 3라운드째에 `ARTIFACT_CHECK_NOT_PASSED`로 멈췄다.

**openapi readiness_failure**
- 0라운드에서 `readiness.6`이 실패한 뒤 `.7`, `.10`, `.12`, `.14`, `.18`을 이어서 실행했다.
- 부분 수리 후보는 결과물 5개(`A06`, `A07`, `A10`, `A12`, `A14`)를 골랐다. provider 호출은 0회였다.
- 1라운드에서는 로컬 검사가 모두 통과했지만 공개 검사가 실패했다(`verify-public`).
- 남은 원인 두 가지:
  1. **readiness가 템플릿을 검사하지 못한다.**
     - `A18`은 `.jinja` 템플릿 4개다.
     - 고장(fault)은 이 파일에도 `(((`를 썼지만, readiness는 ast·toml·bash 구문만 검사한다. 그래서 `readiness.18`은 통과했다.
     - 깨진 템플릿은 공개 검사에서야 드러난다.
  2. **새 결함: 부분 수리 뒤의 공개 실패는 수리할 수 없다.**
     - 공개 실패는 causal/inferred 수리로 넘어간다.
     - 이 수리는 `adaptive-causal-repair.mjs`의 `checkedHistory`에서 `history.entries.length === failure.round_index`를 요구한다.
     - 그런데 부분 수리 라운드는 causal 기록에서 일부러 빠진다(`adaptive-dag-execution.mjs`의 `selectedAction.policy !== PARTIAL_REPAIR_POLICY` 조건).
     - 그래서 1라운드 실패에서 entries 0개와 round_index 1이 어긋나 `ADAPTIVE_CAUSAL_HISTORY_INVALID`로 멈췄다. 이 실행에서 `adaptive_causal_repair_history_updated` 이벤트는 0건이다.
  - 2번을 고치는 방법은 둘이다. 부분 수리 라운드를 causal 기록에 넣거나, 기록 길이 검사에서 부분 수리 라운드를 빼는 것이다. 어느 쪽이든 Jev가 보는 수리 기록의 내용이 바뀌므로, 이번 범위(1번)에서는 고치지 않았다.

**유료 실행 관문**
- h2 리허설은 `passed: true`, `clean: true`이고, 커밋 `647638d`는 `origin/research`에서 이어진다.
- 그러나 관문은 같은 git tree를 요구한다. 이 기록을 커밋하면 tree가 바뀌므로, h2 유료 실행 전에 최종 커밋에서 리허설을 다시 통과시켜야 한다.
- openapi는 계속 막혀 있다.

검증: `check_record.py --root /Users/lee/workspace/plugins/jev-router`로 확인한다. 이 worktree를 root로 쓰면 `benchmark-runs` 심볼릭 링크 때문에 거부된다(REHEARSAL-C와 같음).

```decision-record
{
  "id": "R20261019-REHEARSAL-D",
  "goal": "Make per-task readiness report every failing local check in one round so local-readiness-v1 partial repair fixes all broken artifacts at once, then rerun the free rehearsals.",
  "owner": "side session of the held-out stage 1 prep session",
  "status": "complete",
  "next_trigger": "Choose how a public failure after a local-readiness repair round is repaired (add partial rounds to causal repair history, or exclude them from the history length check), fix it, then rehearse openapi again; rerun the h2 rehearsal on the final commit before any h2 paid run.",
  "conditions": [
    "User choice: option 1 (report all broken artifacts in one round); option 2 (more repair rounds) not chosen; max_repair_rounds stays 2.",
    "No paid calls: Claude inference and Jev POST doubled; Docker, task images, readiness/public checks, runner, partial repair and budget.mjs settlement on a ledger copy were real.",
    "Rehearsals ran from clean commit 647638d with the same manifests, catalogs, records and references as R20261018-REHEARSAL-C.",
    "Claude-only scope."
  ],
  "sources": [
    {"id": "h2_rehearsal", "path": "benchmark-runs/rehearsal-h2-20261019-01/rehearsal.json", "sha256": "7e7c97c2403aae23f21483ba50cce22103c1ea6ccbcc5dbec2f50bc704a15153"},
    {"id": "h2_readiness_events", "path": "benchmark-runs/rehearsal-h2-20261019-01/readiness_failure/events.jsonl", "sha256": "759688002c8ee8050ac59c7416d337ae5fb618a6924d6452db2e9ff9ca23a8bf"},
    {"id": "h2_missing_events", "path": "benchmark-runs/rehearsal-h2-20261019-01/missing_output/events.jsonl", "sha256": "1a48a6853a3824414097e7cb78123ab34f3bf4645b163260c749801a5761eda9"},
    {"id": "openapi_rehearsal", "path": "benchmark-runs/rehearsal-openapi-20261019-01/rehearsal.json", "sha256": "4801e0e6ab50dfb550ab10f03b387481f4b12301537eb30a8957bb1aa9e4328c"},
    {"id": "openapi_readiness_events", "path": "benchmark-runs/rehearsal-openapi-20261019-01/readiness_failure/events.jsonl", "sha256": "8f195c96c69bc8156d08a6cd3c131d77cf01aae61ae0b8912cb13c4c756c57c3"},
    {"id": "openapi_missing_events", "path": "benchmark-runs/rehearsal-openapi-20261019-01/missing_output/events.jsonl", "sha256": "8a4deb626e142e4faa7aed82a57d61dcf0a0eed904d36a169786ca586bb6e68a"}
  ],
  "claims": [
    {"id": "h2_all_rows", "kind": "measured", "text": "h2 rehearsal passed with 4 of 4 rows matched (baseline, readiness_failure and missing_output completed with public checks passed; unknown_model_build stopped BUDGET_MODEL_UNSUPPORTED); head 647638d, clean true, shared ledger hash unchanged.", "source_ids": ["h2_rehearsal"]},
    {"id": "h2_one_round", "kind": "measured", "text": "h2 readiness_failure: round 0 continued readiness.12 and .13 after readiness.10 failed; one partial repair with provider_calls 0 selected A10-utilities, A12-connection and A13-roundtrip-tests; round 1 completed.", "source_ids": ["h2_readiness_events"]},
    {"id": "openapi_one_round", "kind": "measured", "text": "openapi readiness_failure: round 0 continued readiness.7, .10, .12, .14, .18 after readiness.6 failed; one partial repair with provider_calls 0 selected A06, A07, A10, A12, A14; round 1 passed every local check but failed the public aggregate check on verify-public.", "source_ids": ["openapi_readiness_events"]},
    {"id": "template_readiness_gap", "kind": "measured", "text": "A18 (four .jinja templates) received the fault's unparsable content yet readiness.18 passed, because readiness parses only ast/toml/bash; the broken templates surfaced only in public checks.", "source_ids": ["openapi_readiness_events"]},
    {"id": "causal_history_gap", "kind": "measured", "text": "After that public failure the run stopped at stage repair with ADAPTIVE_CAUSAL_HISTORY_INVALID: checkedHistory requires history entries equal to failure.round_index (1), but partial-repair rounds are excluded from causal history, and the run recorded 0 adaptive_causal_repair_history_updated events.", "source_ids": ["openapi_rehearsal", "openapi_readiness_events"]},
    {"id": "openapi_other_rows", "kind": "measured", "text": "openapi baseline and missing_output completed with public checks passed and unknown_model_build stopped BUDGET_MODEL_UNSUPPORTED; rehearsal passed false (3 of 4 rows matched); shared ledger hash unchanged.", "source_ids": ["openapi_rehearsal", "openapi_missing_events"]},
    {"id": "gate_state", "kind": "decision", "text": "openapi stays gated. h2 passed at 647638d, but the spend gate binds the git tree, so the h2 rehearsal must pass again on the commit that adds this record before an h2 paid run.", "source_ids": ["h2_rehearsal", "openapi_rehearsal"]}
  ],
  "costs": [],
  "unresolved": [
    "Public failure after a local-readiness repair round cannot be repaired (causal history length invariant vs excluded partial rounds).",
    "Readiness does not validate .jinja templates, so template breakage reaches public checks.",
    "The verification gate itself still stops at the first failed check; only the local-readiness-v1 path continues, because the gate file is catalog-pinned and not reuse-mutable.",
    "Pre-existing D071 cohort dispatch test failure."
  ],
  "side_effects": [
    "Commit 647638d on feat/heldout-eval-20261018.",
    "New rehearsal folders benchmark-runs/rehearsal-h2-20261019-01 and rehearsal-openapi-20261019-01 (benchmark-runs is the main checkout's folder via symlink)."
  ]
}
```
