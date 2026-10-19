# R20261018-REHEARSAL-C — 무료 리허설이 찾은 세 공백 보완과 재리허설

요청(상위 세션 경유): [R20261018-REHEARSAL-B](R20261018_REHEARSAL_B.md)의 무료 리허설이 찾은 세 공백을 닫고, 깨끗한 커밋에서 h2·openapi 리허설을 다시 돌려 결과를 기록한다. 유료 호출은 없고, 공유 장부는 리허설 복사본으로만 만진다. Claude 경로만 다룬다.

구현 커밋은 `2d75833`다(브랜치 `feat/heldout-eval-20261018`).

## 바꾼 것

1. **결과물 미작성 복구**: [adaptive-partial-repair.mjs](../../src/orchestration/adaptive-partial-repair.mjs)
   - 대상: 구현 작업 하나가 `DAG_RUNTIME_ARTIFACT_MISSING`이나 `DAG_RUNTIME_ARTIFACT_EMPTY`로 실패한 경우다.
   - 그 작업이 정확한 소유자다. 이 경우 Jev와 Claude 판단 호출 없이(provider_calls 0) 그 작업만 다시 실행한다.
   - 안전 조건:
     - 판단 불확실 아님.
     - binding·환경 해시가 있음.
     - 실패 작업은 정확히 1개.
     - 그 작업의 스냅샷과 로컬 검사 행이 없음.
     - 결과물이 게시된 적 없음.
     - 기존 소비자 검사와 미실행 작업 검사는 그대로 적용한다.
   - 그 작업의 상태는 `missing_output`이다. 작업자에게는 허용된 모든 경로를 완전히 쓰라고 지시한다.
   - 한계: 같은 라운드에서 여러 작업이 동시에 결과물을 쓰지 않으면 지금처럼 멈춘다. `failure.code`가 스케줄러의 첫 실패만 담기 때문이며, 코드에 주석으로 남겼다.
   - 테스트: [adaptive-partial-repair.test.mjs](../../test/adaptive-partial-repair.test.mjs)
     - 수정 전 코드에서는 리허설과 같은 `ADAPTIVE_INFERRED_ARTIFACT_BINDING`(repair_owners)로 실패했다.
     - 수정 후에는 완료된다.
2. **가짜 작업자 충실도**: [rehearsal.mjs](../../src/benchmark/rehearsal.mjs)
   - 수리 요청에 `artifact_repair` 묶음이 있으면 그 `allowed_write_paths`만 쓴다.
   - 전송 설정(transport)이 허용하지 않는 경로는 쓰지 않고 `denied_by_transport`로 기록한다.
   - 테스트: [rehearsal.test.mjs](../../test/rehearsal.test.mjs)
3. **openapi manifest**: [openapi-partial-repair-v12.json](../../benchmarks/e2e-swe/manifests/openapi-partial-repair-v12.json)
   - `d085-direct-repair.json`에 `partial_repair: "local-readiness-v1"`만 더했다. d085 원본은 바꾸지 않았다.

**고정 파일**: v11 `source_pins` 17개는 모두 그대로 일치한다. 바꾼 파일 가운데 고정 대상은 없다. 재고정 스크립트는 `REPIN_NO_CHANGE`(종료 코드 4)로 크게 실패했고, v11 계약과 d076 manifest는 바꾸지 않았다. d076의 v11 해시 `ce518e32…`는 현재 파일과 같다.

**전체 테스트**: `npm test` 결과는 1416/1417이다.
- 이전 기준은 1414/1415였고, 새 테스트 2개가 더해졌다.
- 남은 실패 1개는 이미 있던 D071 cohort dispatch 테스트(`ADAPTIVE_FRESH_DIRECTORY_REQUIRED`)다.

## 재리허설 결과

조건:
- 커밋 `2d75833`, 깨끗한 트리에서 실행했다.
- 두 과제 모두 공유 장부 해시는 실행 전후로 같았다.
- 기록과 참조 대조군은 REHEARSAL-B와 같다.

| 과제 | 경우 | 이전(REHEARSAL-B) | 이번 | 판정 |
| --- | --- | --- | --- | --- |
| h2 | baseline | 완료 | 완료, 공개 검사 통과 | 기대대로 |
| h2 | missing_output | `ADAPTIVE_INFERRED_ARTIFACT_BINDING` | 완료, 공개 검사 통과. 결과물 미작성 수리 1회(`adaptive-leaf-n2`, provider_calls 0) | **해결** |
| h2 | readiness_failure | `ARTIFACT_CHECK_NOT_PASSED` | `ARTIFACT_CHECK_NOT_PASSED` | 원인 정정(아래) |
| h2 | unknown_model_build | `BUDGET_MODEL_UNSUPPORTED` | `BUDGET_MODEL_UNSUPPORTED` | 기대대로 |
| openapi | baseline | 완료(d085) | 완료, 공개 검사 통과 | 기대대로 |
| openapi | missing_output | 미실행 | 완료, 공개 검사 통과. 결과물 미작성 수리 1회(`adaptive-leaf-n3`, 결과물 6개, provider_calls 0) | **해결** |
| openapi | readiness_failure | `ADAPTIVE_INFERRED_ARTIFACT_BINDING`(부분 수리 꺼짐) | `ARTIFACT_CHECK_NOT_PASSED` | 부분 수리는 켜짐, 같은 한계에 걸림 |
| openapi | unknown_model_build | `BUDGET_MODEL_UNSUPPORTED` | `BUDGET_MODEL_UNSUPPORTED` | 기대대로 |

두 리허설 모두 `passed: false`이므로 유료 실행 관문은 계속 닫혀 있다. 또한 이 기록을 커밋하면 트리가 바뀐다. 따라서 다음 유료 실행 전에 리허설을 다시 돌려야 한다.

## 정정: readiness_failure는 가짜 작업자의 한계가 아니었다

REHEARSAL-B의 `double_limit` 주장("가짜 작업자가 수리 범위의 파일을 다 다시 쓰지 않았다")은 틀렸다.

- `rehearsal-h2-20261018-04`의 기록을 보면, 수리 때 가짜 작업자는 허용된 경로를 정확히 썼다.
  - 1라운드: `h2/utilities.py`
  - 2라운드: `h2/connection.py`
- 실제 원인은 두 가지가 겹친 것이다.
  - 첫 작업자 고장(fault)이 그 작업의 결과물 3개를 모두 깨뜨린다.
  - 작업별 readiness 검사는 첫 실패에서 멈춘다.
- 그래서 한 라운드에 깨진 결과물이 하나씩만 드러난다.
  - h2: 0/1/2라운드에 `readiness.10` → `.12` → `.13` 순서.
  - openapi: 0/1/2라운드에 `readiness.6` → `.7` → `.10` 순서. 깨진 파일은 9개다.
- 부분 수리는 증거가 있는 결과물만 고친다. `max_repair_rounds`는 실행기에서 2로 고정되어 있다(adaptive-dag-runner.mjs:185).
- 그러므로 결과물이 3개 이상 깨진 작업은 지금 경로로 복구할 수 없다. 이것은 가짜 쪽이 아니라 실제 경로의 한계이며, 이번 수정 범위 밖이라 열어 두었다.

검증: `check_record.py --root /Users/lee/workspace/plugins/jev-router`는 통과한다(sources 7, claims 5). 이 worktree를 root로 쓰면 `benchmark-runs` 심볼릭 링크 때문에 "not a file inside root"로 거부된다. REHEARSAL-B도 같은 이유로 거부된다.

```decision-record
{
  "id": "R20261018-REHEARSAL-C",
  "goal": "Close the three gaps found by the free rehearsal (never-produced output recovery, worker-double repair-packet fidelity, openapi partial_repair manifest) and rerun the free rehearsals from a clean commit.",
  "owner": "side session of the held-out stage 1 prep session",
  "status": "complete",
  "next_trigger": "Decide how a task with three or more readiness-broken artifacts recovers (run every readiness check of a failed task before stopping, or allow more partial-repair rounds, or narrow the readiness_failure fault to one file), then rehearse again; a paid run stays gated until both rehearsals pass.",
  "conditions": [
    "No paid calls: Claude inference and Jev POST doubled; Docker, task images, readiness/public checks, runner, partial repair and budget.mjs settlement on a ledger copy were real.",
    "Rehearsals ran from clean commit 2d75833 with the same records and references as R20261018-REHEARSAL-B.",
    "h2 manifest benchmarks/e2e-swe/heldout/h2/v12.json with catalog benchmark-runs/heldout-h2-catalog-01; openapi manifest benchmarks/e2e-swe/manifests/openapi-partial-repair-v12.json with catalog benchmark-runs/d066-catalog-01.",
    "Claude-only scope."
  ],
  "sources": [
    {"id": "h2_rehearsal", "path": "benchmark-runs/rehearsal-h2-20261018-05/rehearsal.json", "sha256": "44d1bf05933c4602a410cdb33083601fac785b1a03f1c348eed3e860c37ae100"},
    {"id": "h2_missing_events", "path": "benchmark-runs/rehearsal-h2-20261018-05/missing_output/events.jsonl", "sha256": "e75b28e695443be5276fa4980846afe86763f28b6e5ae87239339b803823d678"},
    {"id": "h2_readiness_events", "path": "benchmark-runs/rehearsal-h2-20261018-05/readiness_failure/events.jsonl", "sha256": "f63cb741211627d5068a8929d41620ceeccfb0e7cea935ea68c3a229faedca13"},
    {"id": "openapi_rehearsal", "path": "benchmark-runs/rehearsal-openapi-20261018-02/rehearsal.json", "sha256": "1f19a1007a4585aa25bf38307294d981d70319209eb6ca037d0f584dc38f24ce"},
    {"id": "openapi_missing_events", "path": "benchmark-runs/rehearsal-openapi-20261018-02/missing_output/events.jsonl", "sha256": "3604d299b90cb01525de8ab83a2fcd3165ff10543366956122deaf00709f04bf"},
    {"id": "openapi_readiness_events", "path": "benchmark-runs/rehearsal-openapi-20261018-02/readiness_failure/events.jsonl", "sha256": "d65e4bb42a50cdb3466a22cafc7fcb4ac5fbc6583eb33ef55f9a2739e2cc70cb"},
    {"id": "h2_readiness_prior_events", "path": "benchmark-runs/rehearsal-h2-20261018-04/readiness_failure/events.jsonl", "sha256": "bf72d335c0af8ab4f12dff23dcdf224ed9f2ad98075d666fd8bc554a1789d70d"}
  ],
  "claims": [
    {"id": "missing_output_fixed", "kind": "measured", "text": "missing_output now completes with public checks passed on both tasks; each run committed one local repair with provider_calls 0 for the single never-produced owner (h2 adaptive-leaf-n2, 3 artifacts; openapi adaptive-leaf-n3, 6 artifacts).", "source_ids": ["h2_rehearsal", "h2_missing_events", "openapi_rehearsal", "openapi_missing_events"]},
    {"id": "baseline_unknown_model", "kind": "measured", "text": "baseline completed with public checks passed and unknown_model_build stopped with BUDGET_MODEL_UNSUPPORTED on both tasks; shared ledger hash identical before and after; head 2d75833, clean true.", "source_ids": ["h2_rehearsal", "openapi_rehearsal"]},
    {"id": "readiness_fail_fast", "kind": "measured", "text": "readiness_failure ends ARTIFACT_CHECK_NOT_PASSED on both tasks: the first worker's fault breaks all its outputs (h2 3 files, openapi 9 files) and per-task readiness checks stop at the first failure, so rounds 0/1/2 each surface one new failed check (h2 readiness.10/.12/.13; openapi readiness.6/.7/.10); max_repair_rounds is fixed at 2.", "source_ids": ["h2_readiness_events", "openapi_readiness_events"]},
    {"id": "double_limit_correction", "kind": "correction", "text": "R20261018-REHEARSAL-B claim double_limit (the worker double did not rewrite all files for repair prompts) is wrong: in rehearsal-h2-20261018-04 each repair wrote exactly its one allowed path (h2/utilities.py, then h2/connection.py); the stop is the fail-fast readiness order plus the 2-round cap described in readiness_fail_fast.", "source_ids": ["h2_readiness_prior_events", "h2_readiness_events"]},
    {"id": "gate_closed", "kind": "decision", "text": "Both rehearsals report passed false, so the --spend gate keeps both paid runs closed; committing this record changes the tree, so a new rehearsal is needed anyway.", "source_ids": ["h2_rehearsal", "openapi_rehearsal"]}
  ],
  "costs": [],
  "unresolved": [
    "Recovery of a task with three or more readiness-broken artifacts (fail-fast local checks + max_repair_rounds 2).",
    "Concurrent never-produced outputs in one round still stop (single-owner shortcut).",
    "Pre-existing D071 cohort dispatch test failure (ADAPTIVE_FRESH_DIRECTORY_REQUIRED)."
  ],
  "side_effects": [
    "Commit 2d75833 on feat/heldout-eval-20261018.",
    "New rehearsal folders benchmark-runs/rehearsal-h2-20261018-05 and rehearsal-openapi-20261018-02 (benchmark-runs is the main checkout's folder via symlink)."
  ]
}
```
