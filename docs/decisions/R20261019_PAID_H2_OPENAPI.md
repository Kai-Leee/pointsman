# R20261019-PAID-H2-OPENAPI — 리허설 통과 뒤 h2·openapi jev_profile 유료 1회씩

요청: 사용자가 "통과한 리허설 폴더로 h2와 openapi를 jev_profile 1회씩 유료 실행해"라고 지시했다. 실행 조건은 다음과 같다.

- 유료 실행은 사전 승인 상태이고, 실행 장소는 [R20261018-HELDOUT-PILOT](R20261018_HELDOUT_PILOT.md)과 같은 이 Mac이다.
- 커밋 `441eb32`, 깨끗한 트리에서 실행했다.
- 관문은 리허설을 요구한다. h2는 `rehearsal-h2-20261019-04`, openapi는 `rehearsal-openapi-20261019-05`로 통과했다. 둘 다 같은 tree이며 4/4행이 일치했다.
- 실행 전 Jev 모델 사전 점검(`scripts/jev-model-check.mjs`)은 종료 코드 0이었다.
- 두 실행은 순서대로 했다. 자동 재시도와 재전송은 없었다.

## 결과

| | h2 (`heldout-h2-pilot-04`) | openapi (`openapi-partial-repair-01`) |
| --- | --- | --- |
| manifest | `heldout/h2/v12.json` | `openapi-partial-repair-v12.json` |
| 상태 | **완료**, 공개 검사 통과 | **실패** `ADAPTIVE_TOKEN_PREFLIGHT_BLOCKED`(profiles 단계, 확정) |
| 독립 채점 | **25/25 통과**, 후보 불변, `product_success: true` | 채점 안 함(완료 arm만 채점) |
| 실행 시간(wall) | 1,177.5초 | 1,312.9초 |
| 작업 | 구현 5, 수리 0 | 구현 6, 수리 0(수리 라운드 시작 전에 멈춤) |
| Claude | 5회, API 환산 $3.89(명세 검토 포함 $5.19) | 6회, API 환산 $8.03 |
| Jev | 5회, 입력 86,365·출력 7,467 토큰 | 응답 8회, 입력 233,239·출력 22,356 토큰. 9번째 요청은 보내기 전에 차단 |
| Jev 장부 추정 | $0.0518(86,365×$0.6/M) | $0.1399(233,239×$0.6/M) |
| 장부 정산 | settled, 예약 0 | settled, 예약 0 |

공유 장부의 청구 입력 토큰은 28,040,657 → 28,127,022(h2) → 28,360,261(openapi)로 늘었다. 마지막 값은 현재 장부 값과 같다. 비용은 API 환산 추정치이며, 실제 청구액은 확인하지 않았다(`actual_billed_usd: null`).

**h2**
- 보류 과제 h2가 공개 검사와 독립 채점을 모두 통과한 첫 실행이다.
- 이전 파일럿 3회(01–03)는 모두 공개 검사 전에 멈췄다.
- 고장 없이 실행했으므로 수리 경로는 쓰이지 않았다.

**openapi 실패 원인**
- 0라운드:
  - 구현 6개의 로컬 검사는 모두 통과했지만, 공개 집계 검사(`verify-public`)가 실패했다. 이것은 고장 주입이 아닌 실제 제품 결함이다.
  - Jev가 repair_owners 질문에 답했다(`jev-0014`). 응답 모델은 별칭 `typesafe-ai/jev`가 아니라 dated ID `typesafe/jev-1.14-20261014`였다.
- 1라운드 수리 프로필 요청(`jev-0015`):
  - 토큰 admission v4가 마지막으로 관측한 모델로 1.14를 사용했다. 그런데 v4는 1.13 문맥만 검증했다(`model_context_assumption: jev-1.13.0`). 그래서 `JEV_TOKEN_ADMISSION_MODEL_UNVERIFIED`로 보내기 전에 막았다.
  - 요청 크기는 추정 23,658 토큰, 57,864 wire bytes로 작았다. 로컬 상한도 없다. 즉 크기 때문이 아니라 모델 검증 때문에 막혔다.
- 같은 dated ID는 R20261018-HELDOUT-PILOT의 재실행 02에서 정산 단계를 막았다(`BUDGET_MODEL_UNSUPPORTED`). 그때 정산 허용 목록에는 추가됐지만, admission 정책에는 추가되지 않았다.
- 무료 모델 점검은 정산 허용 목록만 보므로 통과했다.

**리허설이 놓친 이유**
- 가짜 Jev는 기록에 남은 모델 ID를 그대로 돌려준다. openapi 기록(`d081-defaults-01`)에는 1.14가 없다.
- `unknown_model_build` 고장은 정산에서 막히는 미등록 빌드만 시험한다. "정산에는 등록됐지만 admission에는 미검증"인 빌드는 시험하지 않는다.
- 이것은 리허설의 새 공백이다.

종료된 openapi 원본은 다시 실행하거나 재개하지 않는다.

```decision-record
{
  "id": "R20261019-PAID-H2-OPENAPI",
  "goal": "Run one paid jev_profile arm each for h2 and openapi behind the passing rehearsals, then grade completed arms independently.",
  "owner": "side session of the held-out stage 1 prep session",
  "status": "complete",
  "next_trigger": "Decide how jev-1.14 (typesafe/jev-1.14-20261014) is admitted by token admission (new admission policy version with its context evidence, or another rule) and make the rehearsal's Jev double return the currently served dated build; then rehearse and rerun openapi as a new run.",
  "conditions": [
    "User instruction: one paid jev_profile run each for h2 and openapi with the passing rehearsal folders; paid runs pre-approved; on this Mac as in R20261018-HELDOUT-PILOT.",
    "Commit 441eb32, clean tree; gate passed with rehearsal-h2-20261019-04 and rehearsal-openapi-20261019-05; jev-model-check exit 0.",
    "Sequential runs, no automatic retry or resend; terminal runs are not resumed.",
    "Claude-only scope; costs are API-equivalent estimates, actual billing unknown."
  ],
  "sources": [
    {"id": "h2_result", "path": "benchmark-runs/heldout-h2-pilot-04/result.json", "sha256": "236ecbc68c8ae27fcffbf9b631f31bb3f9b820f884e5cb665c0e21fea0ccd7e4"},
    {"id": "h2_grade", "path": "benchmark-runs/heldout-h2-pilot-04/independent-evaluation.json", "sha256": "3bbbecd25673d7d9a5a9868f10c641f4e7547ddd5caedecc3bc501d3fefed641"},
    {"id": "h2_events", "path": "benchmark-runs/heldout-h2-pilot-04/events.jsonl", "sha256": "5ae03e8e64de8b6f3833197dbe82a32ac9349ec073a3bec440a74d0891ca6ae8"},
    {"id": "openapi_result", "path": "benchmark-runs/openapi-partial-repair-01/result.json", "sha256": "7e9ea15ee32aaa2d8f6ae63aea8c10bf35a2b14655d8bf4c659bcc7cb41997a7"},
    {"id": "openapi_events", "path": "benchmark-runs/openapi-partial-repair-01/events.jsonl", "sha256": "6e39e4f4965a9df10ce0ef9b86d6bcb855fb33c1f14b4fd33696b05edb6f714f"},
    {"id": "openapi_owner_response", "path": "benchmark-runs/openapi-partial-repair-01/calls/jev-0014.response.json", "sha256": "dd7d65644d97e5a9275a57885446afe619c872b1b73eb0091c4874404aac64d1"}
  ],
  "claims": [
    {"id": "h2_success", "kind": "measured", "text": "h2 jev_profile completed in 1,177.5 s wall with public checks passed, 5 implementation tasks and 0 repairs; the independent grade passed 25 of 25 hidden tests with the candidate unchanged, product_success true.", "source_ids": ["h2_result", "h2_grade"]},
    {"id": "h2_usage", "kind": "measured", "text": "h2 usage: Claude 5 calls, API-equivalent USD 3.89 (5.19 including spec review); Jev 5 calls, 86,365 input and 7,467 output tokens; ledger settled with 0 reservations, charged input tokens 28,040,657 -> 28,127,022.", "source_ids": ["h2_result"]},
    {"id": "openapi_stop", "kind": "measured", "text": "openapi jev_profile failed after 1,312.9 s with ADAPTIVE_TOKEN_PREFLIGHT_BLOCKED at stage profiles (outcome certain): round 0 passed every local check but failed the public aggregate check; the repair-owner Jev response jev-0014 reported model typesafe/jev-1.14-20261014, and the next repair-profile request was blocked before sending with JEV_TOKEN_ADMISSION_MODEL_UNVERIFIED (admission v4 assumes jev-1.13.0) at an estimated 23,658 tokens and 57,864 wire bytes.", "source_ids": ["openapi_result", "openapi_events", "openapi_owner_response"]},
    {"id": "openapi_usage", "kind": "measured", "text": "openapi usage: Claude 6 calls, API-equivalent USD 8.03; Jev 8 responses, 233,239 input and 22,356 output tokens; ledger settled with 0 reservations, charged input tokens 28,127,022 -> 28,360,261.", "source_ids": ["openapi_result"]},
    {"id": "rehearsal_gap", "kind": "hypothesis", "text": "The rehearsal missed this stop because its Jev double replays recorded model IDs and the openapi records contain no 1.14 response; unknown_model_build tests only a build unlisted for settlement.", "source_ids": []}
  ],
  "costs": [
    {"role": "h2 Claude workers and spec review", "basis": "api_equivalent", "usd": 5.18640032, "source_ids": ["h2_result"]},
    {"role": "h2 Jev", "basis": "conservative_budget", "usd": 0.051819, "source_ids": ["h2_result"]},
    {"role": "openapi Claude workers", "basis": "api_equivalent", "usd": 8.0298749, "source_ids": ["openapi_result"]},
    {"role": "openapi Jev", "basis": "conservative_budget", "usd": 0.1399434, "source_ids": ["openapi_result"]}
  ],
  "unresolved": [
    "Token admission v4 does not verify typesafe/jev-1.14-20261014; any run whose Jev response reports it stops before the next Jev request.",
    "The rehearsal's Jev double never returns the currently served dated build.",
    "openapi round-0 public failure remains unrepaired in this run; no openapi product result.",
    "Readiness does not validate .jinja templates."
  ],
  "side_effects": [
    "Paid run folders benchmark-runs/heldout-h2-pilot-04 (graded) and benchmark-runs/openapi-partial-repair-01.",
    "Shared ledger benchmark-runs/jev-usd1-budget.json advanced to 28,360,261 charged input tokens, 0 reserved."
  ]
}
```
