# R20261019-PAID-OPENAPI-02 — Jev 실행 설정 정리와 openapi 유료 재실행

요청(상위 세션 경유): 사용자가 "jev 실행 설정을 모두 진행하고 나서 유료 재실행까지 왈료하도록해"라고 지시했다. 실행 조건은 다음과 같다.

- 시도는 1회만 하고, 자동 재시도나 불확실한 POST 재전송은 하지 않는다.
- h2는 이미 성공했으므로 다시 실행하지 않는다.
- Claude 경로만 다루고, push하지 않는다.
- 유료 실행은 사전 승인 상태이며, 이전 기록과 같은 이 Mac에서 실행한다.

## Jev 실행 설정 정리

배경: Jev 모델 관문은 정산 허용 목록, 토큰 admission, 무료 사전 점검 세 곳에 있다. 이 셋이 서로 어긋날 수 있었다. [R20261019-PAID-H2-OPENAPI](R20261019_PAID_H2_OPENAPI.md)의 openapi 실행은 사전 점검을 통과했지만, 정산에는 있고 admission v4에는 없는 1.14 빌드 때문에 멈췄다.

- **사전 점검** [jev-model-check.mjs](../../scripts/jev-model-check.mjs)에 확인을 하나 더했다.
  - 무엇을 보나: 나열된 Jev 버전의 정산 항목 전부와, 버전이 없는 provider 별칭 전부를 본다. 이 모델들은 활성 토큰 admission 정책의 허용 관측 모델과 정확히 같아야 한다.
  - 어긋나면 종료 코드 3을 내고, `settlement_models_not_admitted`에 해당 모델을 남긴다.
  - 활성 정책은 기본이 v5다. `--admission-contract`로 manifest와 같은 v4나 v5를 고를 수 있다.
  - 정확 일치 규칙과 근거 규칙은 그대로다.
- **테스트**: [jev-model-check.test.mjs](../../test/jev-model-check.test.mjs)에 추가했다.
  - v4에서 1.14가 나열되면 종료 코드 3. 1.14가 나열되지 않으면 0. v5는 0. 알 수 없는 계약은 거부.
  - 이전 스크립트에서는 이 테스트가 실패했다.
- **고정과 테스트 결과**: 고정 대상은 바뀌지 않았다(`REPIN_NO_CHANGE`). 전체 테스트는 1422/1423이며, 남은 실패 1개는 이미 있던 D071 테스트다.
- 커밋: `895b49e`.

## 실행 전 확인 (커밋 `895b49e`, tree `8cc31ad…`)

- **사전 점검**: `node scripts/jev-model-check.mjs`의 종료 코드는 0이었다.
  - `settlement_models_not_admitted: []`
  - 정책은 `r20261019-jev114-observed-build-v5`
  - 나열된 Jev 버전은 1.14.0과 1.13.0
- **무료 리허설**: 둘 다 같은 tree에서 4/4로 통과했다. `served_model`은 `typesafe/jev-1.14-20261014`이고, 공유 장부는 바뀌지 않았다.
  - h2: `rehearsal-h2-20261019-06`
  - openapi: `rehearsal-openapi-20261019-07`

## 유료 재실행 결과 (`openapi-partial-repair-02`)

| 항목 | 값 |
| --- | --- |
| manifest | `openapi-partial-repair-v12.json`(admission v5, partial_repair local-readiness-v1) |
| 상태 | **완료**, 종료 원인 없음, 결과 확정(불확실 아님) |
| 공개 검사 | **8/8 묶음 통과**, assertion 2,236개 |
| 독립 채점 | **63/63 통과**, 후보 불변, `product_success: true`(채점 21.4초, 모델 호출 0) |
| 실행 시간(wall) | 1,895.0초 |
| 작업 | 구현 6, 수리 0, 수리 라운드 0 |
| Claude | 6회, API 환산 $8.50(명세 검토 포함 $10.85) |
| Jev | 7회, 입력 196,662·출력 19,721 토큰. 장부 추정 $0.118(196,662×$0.6/M) |
| 장부 | 청구 입력 토큰 28,360,261 → 28,556,923, settled, 예약 0 |

비용은 API 환산 추정치이며, 실제 청구액은 확인하지 않았다.

**해석**
- openapi의 첫 제품 성공이고, 이 manifest로는 첫 완료다.
- 이번에는 0라운드에 공개 검사가 실패하지 않았다. 그래서 수리 경로(부분 수리·check-error·owner 수리)는 쓰이지 않았다.
- Jev 응답 모델은 `jev-1.13.0` 4회와 `typesafe-ai/jev` 3회였다. 1.14 dated 빌드는 응답에 나오지 않았다.
  - 그래서 유료 실행에서 v5의 1.14 허용 경로는 실행되지 않았다. 그 경로는 무료 리허설에서만 확인했다.
- 이전 실행 `openapi-partial-repair-01`은 0라운드에 공개 검사가 실패했다. 같은 조건에서도 실행마다 결과가 다르므로, 이 1회 성공을 성공률로 해석하지 않는다.

```decision-record
{
  "id": "R20261019-PAID-OPENAPI-02",
  "goal": "Make the three Jev model gates (settlement, token admission, free pre-check) agree, then complete one paid openapi jev_profile rerun behind a passing rehearsal and grade it independently.",
  "owner": "side session of the held-out stage 1 prep session",
  "status": "complete",
  "next_trigger": "Decide the held-out stage-1 comparison runs (conditions, repeats) now that h2 and openapi each have one graded product success under this harness.",
  "conditions": [
    "User instruction relayed by the parent session: finish the Jev run settings, then complete the paid rerun; one attempt, no automatic retry or resend, h2 not rerun, Claude-only, no push.",
    "Commit 895b49e, clean tree 8cc31ad; jev-model-check exit 0; rehearsals rehearsal-h2-20261019-06 and rehearsal-openapi-20261019-07 passed 4/4 on that tree.",
    "Paid runs pre-approved; executed on this Mac as in R20261018-HELDOUT-PILOT. Costs are API-equivalent estimates; actual billing unknown."
  ],
  "sources": [
    {"id": "openapi_result", "path": "benchmark-runs/openapi-partial-repair-02/result.json", "sha256": "588d8fc407b8e792976f990b8d7e498173b36623f670683c97bd1c8a1a0ec233"},
    {"id": "openapi_grade", "path": "benchmark-runs/openapi-partial-repair-02/independent-evaluation.json", "sha256": "b26777359712d17d6d3db479fb4755f998954bf4a62475f7f8f50f85dcbdd881"},
    {"id": "openapi_events", "path": "benchmark-runs/openapi-partial-repair-02/events.jsonl", "sha256": "adee5f40645f8b1e3dd813f5d50e70b817a3bdcb23b8c3b13686b1d1923fd639"}
  ],
  "claims": [
    {"id": "openapi_success", "kind": "measured", "text": "openapi jev_profile completed in 1,895.0 s wall with all 8 public check suites passed (2,236 assertions), 6 implementation tasks and 0 repair rounds; the independent grade passed 63 of 63 hidden tests with the candidate unchanged, product_success true.", "source_ids": ["openapi_result", "openapi_grade", "openapi_events"]},
    {"id": "openapi_usage", "kind": "measured", "text": "Usage: Claude 6 calls, API-equivalent USD 8.50 (10.85 including spec review); Jev 7 calls, 196,662 input and 19,721 output tokens; ledger settled with 0 reservations, charged input tokens 28,360,261 -> 28,556,923.", "source_ids": ["openapi_result"]},
    {"id": "no_114_observed", "kind": "measured", "text": "Jev responses reported jev-1.13.0 (4) and typesafe-ai/jev (3); no 1.14 dated build was observed, so the v5 1.14 admission path was not exercised in this paid run.", "source_ids": ["openapi_events"]},
    {"id": "precheck_gate", "kind": "decision", "text": "The free pre-check now exits 3 when any settlement model a listed Jev version could report is not accepted by the active token-admission policy; with v4 and a listed jev-1.14.0 it would have blocked the openapi-partial-repair-01 configuration before spending.", "source_ids": []}
  ],
  "costs": [
    {"role": "openapi Claude workers and spec review", "basis": "api_equivalent", "usd": 10.8548047, "source_ids": ["openapi_result"]},
    {"role": "openapi Jev", "basis": "conservative_budget", "usd": 0.1179972, "source_ids": ["openapi_result"]}
  ],
  "unresolved": [
    "One success per task is not a success rate; the earlier openapi run with the same manifest failed public checks in round 0.",
    "The v5 jev-1.14 admission path has been exercised only in free rehearsals.",
    "Readiness does not validate .jinja templates.",
    "Pre-existing D071 cohort dispatch test failure."
  ],
  "side_effects": [
    "Commit 895b49e on feat/heldout-eval-20261018.",
    "Paid run folder benchmark-runs/openapi-partial-repair-02 (graded); rehearsal folders rehearsal-h2-20261019-06 and rehearsal-openapi-20261019-07.",
    "Shared ledger benchmark-runs/jev-usd1-budget.json advanced to 28,556,923 charged input tokens, 0 reserved."
  ]
}
```
