# R20261019-REHEARSAL-E — 부분 수리 뒤의 공개 실패를 수리 경로로 넘기기

요청: [R20261019-REHEARSAL-D](R20261019_REHEARSAL_D.md)에서 찾은 결함을 사용자가 "좋아 그럼 일단 수리하고 필요하면 유료 수리도 가능하니 진행해"라고 지시했다. 결함은 로컬 readiness 수리 라운드 뒤에 공개 검사가 실패하면 `ADAPTIVE_CAUSAL_HISTORY_INVALID`로 멈추는 것이다. 이 수정으로 공개 실패는 실제 실행에서 유료가 되는 Jev 수리 경로로 넘어간다. 리허설에서는 Jev와 Claude를 가짜로 대신했으므로 유료 호출은 없었다. Claude 경로만 다룬다.

구현 커밋: `2b98f84`(브랜치 `feat/heldout-eval-20261018`).

## 바꾼 것

- **원인**:
  - 로컬 수리 라운드는 전체 결과물의 revision이 갖춰지지 않은 채 끝난다. 그래서 causal 기록 항목이 될 수 없고, 일부러 기록에서 빠진다.
  - 그런데 `checkedHistory`는 기록 항목 수가 실패의 `round_index`와 같아야 한다고 요구했다.
- **수정**: [adaptive-causal-repair.mjs](../../src/orchestration/adaptive-causal-repair.mjs), [adaptive-dag-execution.mjs](../../src/orchestration/adaptive-dag-execution.mjs)
  - 로컬 수리 라운드를 기록의 `local_repair_round_indices`에 라운드 번호로 남긴다. 이 필드는 로컬 수리 라운드가 있을 때만 생긴다. 따라서 로컬 수리가 없는 기록은 이전과 바이트 단위로 같다.
  - causal 항목은 실제 라운드 번호를 가진다.
  - 연속성 검사와 최종 revision 검사는 인접한 라운드 사이에서만 적용한다.
  - 길이 검사는 "항목 수 + 로컬 라운드 수 = round_index"로 바꿨다.
- **테스트**: [adaptive-partial-repair.test.mjs](../../test/adaptive-partial-repair.test.mjs)에 추가했다. 흐름은 로컬 수리 → 공개 실패 → owner 수리 → 완료다.
  - 수정 전 코드에서는 리허설과 같은 `ADAPTIVE_CAUSAL_HISTORY_INVALID`(repair 단계)로 실패했다. 수정 후에는 완료된다.
- **고정 파일 점검**:
  - v11 고정 파일과 두 카탈로그의 고정 파일 모두 바뀌지 않았다. 재고정 스크립트는 `REPIN_NO_CHANGE`를 냈다.
  - v11 계약과 d076 manifest는 바꾸지 않았다.
- **전체 테스트**: `npm test` 결과는 1418/1419이다. 남은 실패 1개는 이미 있던 D071 테스트다.

## 리허설 결과

조건:
- 커밋 `2b98f84`, 깨끗한 트리에서 실행했다.
- 공유 장부 해시는 실행 전후로 같았다.
- 기록과 참조 대조군은 REHEARSAL-D와 같다.

| 과제 | baseline | readiness_failure | missing_output | unknown_model_build | 통과 |
| --- | --- | --- | --- | --- | --- |
| h2 (`rehearsal-h2-20261019-03`) | 완료, 공개 통과 | 완료, 공개 통과 | 완료, 공개 통과 | `BUDGET_MODEL_UNSUPPORTED` | **예, 4/4** |
| openapi (`rehearsal-openapi-20261019-02`) | 완료, 공개 통과 | 완료, 공개 통과 | 완료, 공개 통과 | `BUDGET_MODEL_UNSUPPORTED` | **예, 4/4** |

**주의: 고장을 받는 작업자가 실행마다 다르다.** `readiness_failure` 고장은 "처음 실행된 작업자"에 걸린다. 처음 실행되는 작업자는 스케줄링 순서에 따라 바뀐다.

- **openapi 4행 실행(02)**: 고장이 `.jinja` 템플릿만 쓰는 `adaptive-leaf-n5`에 걸렸다.
  - readiness가 템플릿을 통과시켰고, 0라운드에 공개 검사가 실패했다.
  - D085 check-error 수리로 1라운드에 완료됐다.
  - 따라서 이 실행은 이번 수정 경로(로컬 수리 → 공개 수리)를 거치지 않았다.
- **openapi readiness_failure만 다시 2회 실행(03, 04)**: 두 번 모두 고장이 `adaptive-leaf-n3`에 걸렸다. 흐름도 두 번 같았다.
  - 0라운드: 로컬 검사가 실패했고, 부분 수리가 결과물 5개(`A06`, `A07`, `A10`, `A12`, `A14`)를 골랐다. provider 호출은 0회였다.
  - 1라운드: 공개 검사가 실패했다. 깨진 `.jinja` 템플릿 때문이다.
    - 기록은 `local_repair_round_indices: [0]`이었고, 항목은 0개였다.
    - D085 check-error 수리(`repair-check-error-generation`)가 선택됐다.
  - 2라운드: 완료됐고, 공개 검사를 통과했다.
  - 이 실행에서 가짜로 대신한 Jev 판단은 12회다. 실제 실행이었다면 유료다.
- **h2**: 고장이 `adaptive-leaf-n2`에 걸렸다. 부분 수리 1회(결과물 3개, provider 호출 0회)로 1라운드에 완료됐다.

**유료 실행 관문**
- 관문은 같은 git tree를 요구한다. 이 기록을 커밋하면 tree가 바뀐다.
- 그래서 유료 실행 전에는 기록 커밋에서 h2와 openapi 리허설을 다시 통과시켜야 한다.

검증은 `check_record.py --root /Users/lee/workspace/plugins/jev-router`로 한다.

```decision-record
{
  "id": "R20261019-REHEARSAL-E",
  "goal": "Let a public failure after a local readiness repair round reach the causal (Jev-decided) repair path instead of stopping with ADAPTIVE_CAUSAL_HISTORY_INVALID, then rerun the free rehearsals.",
  "owner": "side session of the held-out stage 1 prep session",
  "status": "complete",
  "next_trigger": "Rerun the h2 and openapi rehearsals on the commit that adds this record, then use those folders as --rehearsal for the paid runs.",
  "conditions": [
    "User approval: fix the defect; paid repair is acceptable when needed.",
    "No paid calls in this record: Claude inference and Jev POST doubled; Docker, task images, readiness/public checks, runner, repair paths and budget.mjs settlement on a ledger copy were real.",
    "Rehearsals ran from clean commit 2b98f84 with the same manifests, catalogs, records and references as R20261019-REHEARSAL-D.",
    "Claude-only scope."
  ],
  "sources": [
    {"id": "openapi_rehearsal", "path": "benchmark-runs/rehearsal-openapi-20261019-02/rehearsal.json", "sha256": "d1e64cf7ab525b340d89afe89cd49af9ebcc2beb3f154fd23e03a019baf97cfa"},
    {"id": "openapi_readiness_02", "path": "benchmark-runs/rehearsal-openapi-20261019-02/readiness_failure/events.jsonl", "sha256": "f2aab51ebb5168f38e87db51a31ce10e54e2de08ddb23e2760318a6ef777b00b"},
    {"id": "openapi_rerun_03", "path": "benchmark-runs/rehearsal-openapi-20261019-03/rehearsal.json", "sha256": "7e5fc4868b33fad3e57837e10d660092a522dbec3611bf74a6120ab89a4a6fdc"},
    {"id": "openapi_readiness_03", "path": "benchmark-runs/rehearsal-openapi-20261019-03/readiness_failure/events.jsonl", "sha256": "cb08341f47d6ce8b200c5decec622f069f8ff1d6be87caa151121847f3050485"},
    {"id": "openapi_rerun_04", "path": "benchmark-runs/rehearsal-openapi-20261019-04/rehearsal.json", "sha256": "38dd16c64c07c6b915a8acf634c28f9b69df2123175ffb60d4eacfae30ba1c2a"},
    {"id": "openapi_readiness_04", "path": "benchmark-runs/rehearsal-openapi-20261019-04/readiness_failure/events.jsonl", "sha256": "6675b55d61f434c2743e473628277e853fe0b6225efeb318614d35a0b5727a1e"},
    {"id": "h2_rehearsal", "path": "benchmark-runs/rehearsal-h2-20261019-03/rehearsal.json", "sha256": "98c152118c40139a026fe98f7eb4377668f009c17af3738f5e62c7db3882ffad"},
    {"id": "h2_readiness", "path": "benchmark-runs/rehearsal-h2-20261019-03/readiness_failure/events.jsonl", "sha256": "e59603dff60331734a0079bb8dc11c845235facd88a534fa92384aff293df1cb"}
  ],
  "claims": [
    {"id": "both_pass", "kind": "measured", "text": "h2 and openapi rehearsals each passed 4 of 4 rows at clean commit 2b98f84 (baseline, readiness_failure, missing_output completed with public checks passed; unknown_model_build stopped BUDGET_MODEL_UNSUPPORTED); shared ledger hash unchanged.", "source_ids": ["openapi_rehearsal", "h2_rehearsal"]},
    {"id": "openapi_02_path", "kind": "measured", "text": "In the 4-row openapi run the fault hit adaptive-leaf-n5 (templates only); readiness passed, round 0 failed the public check, D085 check-error repair completed it in round 1, so this run did not exercise the local-then-public path.", "source_ids": ["openapi_readiness_02"]},
    {"id": "openapi_fixed_path", "kind": "measured", "text": "In two readiness_failure-only openapi reruns (03, 04) the fault hit adaptive-leaf-n3: round 0 partial repair selected A06, A07, A10, A12, A14 with 0 provider calls; round 1 failed the public check with history local_repair_round_indices [0] and 0 entries, D085 check-error repair (repair-check-error-generation) was selected; round 2 completed with public checks passed. Both reruns matched.", "source_ids": ["openapi_rerun_03", "openapi_readiness_03", "openapi_rerun_04", "openapi_readiness_04"]},
    {"id": "h2_path", "kind": "measured", "text": "h2 readiness_failure: one partial repair of A02-config, A08-stream, A09-windows with 0 provider calls; completed in round 1.", "source_ids": ["h2_readiness"]},
    {"id": "fault_target_varies", "kind": "measured", "text": "The readiness_failure fault targets whichever worker starts first, which varied between runs (adaptive-leaf-n5 in 02, adaptive-leaf-n3 in 03 and 04); a single passing row does not show which repair path ran.", "source_ids": ["openapi_readiness_02", "openapi_readiness_03"]}
  ],
  "costs": [],
  "unresolved": [
    "Readiness does not validate .jinja templates; template breakage is caught only by public checks.",
    "readiness_failure targets a scheduling-dependent worker; pinning the faulted task would make the row exercise one path deterministically.",
    "Pre-existing D071 cohort dispatch test failure."
  ],
  "side_effects": [
    "Commit 2b98f84 on feat/heldout-eval-20261018.",
    "New rehearsal folders benchmark-runs/rehearsal-openapi-20261019-02..04 and rehearsal-h2-20261019-03 (benchmark-runs is the main checkout's folder via symlink)."
  ]
}
```
