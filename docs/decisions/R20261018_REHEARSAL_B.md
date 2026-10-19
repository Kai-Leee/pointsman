# R20261018-REHEARSAL-B — 기록 기반 무료 리허설, Jev 모델 사전 점검, 앱 CLI 구현

사용자 요청: "앞으로 기록을 기반으로 한 무료 리허설 B로 진행하게 하고, jev 모델은 실험 전에 미리 체크해서 업데이트를 진행하게 하자. 클로드 cli도 앱에 맞춰서 진행하게 하자. 과제는 다른 과제도 병렬로 조사해서 가져오고 일단 openapi와 이것보다 작은 것도 가져오게 할 것. 설계와 수정을 모두 진행 해봐"

설계 선정은 [R20261018-DESIGN-SELECTION](R20261018_DESIGN_SELECTION.md)에 있고, 구현 커밋은 `f9d32e4`다. 유료 호출은 하지 않았다.

## 만든 것

- **기록 기반 무료 리허설**: `scripts/rehearse.mjs`, `src/benchmark/rehearsal.mjs`
  - 가짜로 바꾸는 것은 유료 경계 두 곳(Claude 추론, Jev POST)뿐이다.
  - 가짜 Jev는 과거 실행에 기록된 답과 모델 ID를 재사용한다. 가짜 작업자는 과거 성공 후보나 과제의 공개 참조 대조군 파일을 쓴다.
  - Docker, 과제 이미지, readiness·공개 검사, 실행기, 정산 코드(장부 복사본 사용), 잔액 조회(무료 GET)는 실제로 실행한다.
- **유료 실행 관문**: `scripts/adaptive-dag-comparison.mjs`
  - `--spend`로 arm을 실행하려면 `--rehearsal <dir>`가 필요하다.
  - 리허설이 같은 커밋 트리, 깨끗한 작업 폴더, 같은 manifest·이미지에서 24시간 안에 통과했어야 한다.
  - 커밋이 `origin/research`에서 이어져야 한다. 아니면 `SOURCE_NOT_ON_MAINLINE`으로 막는다.
- **Jev 모델 사전 점검**: `scripts/jev-model-check.mjs`
  - 무료 GET만 쓴다. 모델 목록에 새 Jev 버전이 보이는데 정산 허용 목록에 항목이 없으면 종료 코드 3으로 유료 실행을 막는다.
  - `--update`는 문서 증거를 저장한 정확한 dated ID만 추가한다. 허용 목록은 이제 `contracts/jev-settlement-models.v1.json`에 있다.
  - 한계: dated ID는 공개 문서에 나오지 않는다. 첫 유료 응답에서 처음 보이면 그 실행은 여전히 막히고 오프라인 정산으로 처리한다.
- **앱 CLI 연결**: `src/benchmark/claude-cli.mjs`
  - 앱에 내장된 최신 CLI(현재 2.1.299)를 찾아 PATH 맨 앞에 넣는다.
  - 고정 대상인 실행기 파일은 바꾸지 않았다. 바꾸면 이미 준비한 카탈로그 재사용이 깨지기 때문이다.
- **카탈로그 경로 비교 수정**: 카탈로그 경로를 실제 파일 경로(realpath)로 비교한다. 이것으로 research 기준 실패 11개 중 10개가 해결됐다.
- **과제 조사**: [TASK_SURVEY_20261018](../orchestration/TASK_SURVEY_20261018.md)
  - openapi보다 작은 Python 과제가 64개다. h2와 pycparser도 작지만 보류 과제 목록에 들어 있다.
  - 보류 목록 밖의 후보 6개를 순위로 정리했다: lark, fparser, dateutil, dill, qrcode, pyyaml.

## 리허설 결과 (무료, 공유 장부 해시 변화 없음)

| 과제 | 경우 | 결과 | 판정 |
| --- | --- | --- | --- |
| h2 | baseline | 완료, 공개 검사 통과 | 기대대로 |
| h2 | unknown_model_build | `BUDGET_MODEL_UNSUPPORTED`, 장부 복사본에서만 막힘 | 기대대로 |
| h2 | missing_output(파일 미작성) | `ADAPTIVE_INFERRED_ARTIFACT_BINDING` | **새 결함**: 부분 수리는 `ARTIFACT_CHECK_NOT_PASSED`만 처리하고 `DAG_RUNTIME_ARTIFACT_MISSING`은 처리하지 못한다 |
| h2 | readiness_failure | `ARTIFACT_CHECK_NOT_PASSED` | 판단 보류: 가짜 작업자가 수리 요청의 쓰기 범위를 다 반영하지 못했다(가짜 쪽 한계) |
| openapi(d085) | baseline | 완료, 공개 검사 통과 | 기대대로, 이 작업 폴더에서 D066 카탈로그 재사용 확인 |
| openapi(d085) | readiness_failure | `ADAPTIVE_INFERRED_ARTIFACT_BINDING` | 현재 기본 manifest에는 부분 수리가 켜져 있지 않다 |
| openapi(d085) | unknown_model_build | `BUDGET_MODEL_UNSUPPORTED` | 기대대로 |

결과적으로 관문이 h2와 openapi 유료 실행을 모두 막는다. 막는 이유는 위 표의 실패 행(새 결함 1건, 기본 설정 한계 1건, 가짜 쪽 한계 1건)이고, 유료 실행 전에 무료로 드러났다.

```decision-record
{
  "id": "R20261018-REHEARSAL-B",
  "goal": "Implement the selected record-based zero-cost rehearsal with a spend gate, a Jev model pre-check, app-bundled Claude CLI resolution, and survey smaller tasks.",
  "owner": "root (rehearsal, gate, realpath fix); subagents for model check, CLI resolver, task survey",
  "status": "complete",
  "next_trigger": "Fix DAG_RUNTIME_ARTIFACT_MISSING recovery and the repair-prompt fidelity of the worker double, enable partial_repair in an openapi manifest, then rerun rehearsals; only a passing rehearsal unlocks the next paid run.",
  "conditions": [
    "No paid calls: Claude inference and Jev POST doubled; free GETs (models, credits, docs) and Docker were real.",
    "Rehearsals ran on an uncommitted tree before f9d32e4; their records show clean=false and cannot unlock --spend.",
    "Claude CLI 2.1.299 from the app bundle."
  ],
  "sources": [
    {"id": "h2_rehearsal", "path": "benchmark-runs/rehearsal-h2-20261018-03/rehearsal.json", "sha256": "c8d0453c09e011ef24ed859a7cea4a5a5493a0bf5b1df73adf7b70af79d28c1a"},
    {"id": "h2_readiness", "path": "benchmark-runs/rehearsal-h2-20261018-04/rehearsal.json", "sha256": "e566129ca17a4e63e88145f5f20ef6be0705b01af47703ec0627411fa0759f38"},
    {"id": "openapi_rehearsal", "path": "benchmark-runs/rehearsal-openapi-20261018-01/rehearsal.json", "sha256": "7fa3346e8e64ebcc233f6705323983087bdaba998b3b66f01d5327c3bc82349e"},
    {"id": "missing_output_events", "path": "benchmark-runs/rehearsal-h2-20261018-03/partial_execution/events.jsonl", "sha256": "a9328890662c2c7af794a704e1a7b1581de905ff49551d19f614743434491b27"}
  ],
  "claims": [
    {"id": "baseline", "kind": "measured", "text": "Baseline rehearsals completed with public checks passed on h2 (heldout-h2-catalog-01) and openapi (d085-direct-repair, D066 catalog reused from this worktree).", "source_ids": ["h2_rehearsal", "openapi_rehearsal"]},
    {"id": "unknown_model", "kind": "measured", "text": "An unlisted Jev build stopped with BUDGET_MODEL_UNSUPPORTED on the ledger copy for both tasks; shared ledger hash identical before and after every rehearsal.", "source_ids": ["h2_rehearsal", "openapi_rehearsal"]},
    {"id": "missing_output_gap", "kind": "measured", "text": "A worker that writes nothing fails DAG_RUNTIME_ARTIFACT_MISSING and the run stops at repair_owners with ADAPTIVE_INFERRED_ARTIFACT_BINDING, because partial readiness repair accepts only ARTIFACT_CHECK_NOT_PASSED; found before any paid run.", "source_ids": ["missing_output_events", "h2_rehearsal"]},
    {"id": "openapi_no_partial", "kind": "measured", "text": "openapi d085 default manifest has no partial_repair, so an injected readiness failure stops at ADAPTIVE_INFERRED_ARTIFACT_BINDING.", "source_ids": ["openapi_rehearsal"]},
    {"id": "double_limit", "kind": "unknown", "text": "h2 readiness_failure ended ARTIFACT_CHECK_NOT_PASSED because the worker double did not rewrite all files for repair prompts; the real partial-repair outcome for this shape is untested here.", "source_ids": ["h2_readiness"]}
  ],
  "costs": [],
  "unresolved": [
    "DAG_RUNTIME_ARTIFACT_MISSING recovery; worker-double repair-prompt fidelity; partial_repair for openapi.",
    "Merge items 2 and 3 from the selection (stop-code attribution completeness test, single shared readiness/ledger helpers) and the replay attribution mode are not implemented.",
    "Preparing the surveyed smaller non-held-out tasks (lark, fparser, ...) is not started.",
    "Consolidating origin/research, research-d095-final-20261017 and this branch is pending."
  ],
  "side_effects": [
    "New rehearsal folders benchmark-runs/rehearsal-h2-20261018-01..04 and rehearsal-openapi-20261018-01 (01-02 are failed starts of my own script).",
    "Commit f9d32e4 on feat/heldout-eval-20261018."
  ]
}
```
