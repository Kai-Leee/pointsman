# R20261019-ADMISSION-V5 — jev-1.14를 검증하는 토큰 admission v5와 현재 빌드를 돌려주는 리허설

요청: 사용자가 "jev-1.14를 검증하는 새 admission 정책 버전을 만들고(문맥 크기 근거 확인), 리허설 가짜 Jev가 현재 서빙 중인 dated 빌드를 돌려주게 고친 뒤 무료 리허설을 다시 돌려"라고 지시했다. 유료 호출은 없었다. 무료 GET(공식 문서, 모델 목록, 잔액)만 썼다. Claude 경로만 다룬다.

배경: [R20261019-PAID-H2-OPENAPI](R20261019_PAID_H2_OPENAPI.md)의 openapi 실행은 Jev가 `typesafe/jev-1.14-20261014`로 응답한 뒤 멈췄다. 토큰 admission v4가 1.13만 검증하기 때문에 다음 요청을 보내기 전에 막혔다.

구현 커밋: `328c105`(브랜치 `feat/heldout-eval-20261018`).

## 문맥 크기 근거

공식 페이지를 2026-10-19에 무료 GET으로 받았다. 원본과 SHA-256은 `benchmark-runs/jev-114-admission-evidence-20261019/`에 저장했다.

- [Jev 1.14.0 model guide](https://jev-ai.pro/model/jev-1.14)
  - 기본 한도는 1.13과 같다. 요청당 64k 토큰, state와 가장 긴 질문의 합 32k 토큰이다.
  - 262k는 long-context를 명시적으로 켰을 때만 적용된다. 이 프로젝트는 켜지 않는다.
  - 2026-10-14에 jev-preview로 나왔고, jev-latest는 약 1주 뒤 1.14.0으로 옮겨 간다.
- [Jev API](https://jev-ai.pro/jev-api): Jev 모델 목록에 jev-1.14.0이 있다. 한도는 같은 64k/32k다.
- [docs](https://jev-ai.pro/docs): 2026-10-14부터 jev-preview가 jev-1.14.0을 가리킨다.
- dated ID `typesafe/jev-1.14-20261014`는 문서에 나오지 않는다.
  - 근거는 jev-latest 요청에 대한 provider 응답으로 관측한 것이다(D086, `openapi-partial-repair-01`의 `jev-0014`).
  - 정산 계약에도 1.14의 dated 빌드로는 이것 하나만 있다.

## 바꾼 것

- **admission v5**: [계약](../orchestration/contracts/jev-token-admission.v5.json), [모듈](../../src/orchestration/jev-token-admission-v5.mjs)
  - v4 계약과 모듈을 해시로 고정해 상속한다.
  - 허용하는 관측 모델에 `jev-1.14.0`과 `typesafe/jev-1.14-20261014` 두 개만 더한다.
  - 나머지 검사는 그대로다: 공식 256,000바이트 본문 검사, 신뢰된 stage, 요청 모델, 정책·요청 해시, 로컬 상한 null.
  - 미래 빌드와 움직이는 1.14 별칭은 받지 않는다.
- **실행기 연결**: inferred-repair manifest만 `repair_policy.token_admission_contract`로 v5를 고를 수 있다. v5를 쓰면 v5 모듈도 source pin에 들어간다.
  - h2 `v12.json`과 `openapi-partial-repair-v12.json`은 v5로 바꿨다.
  - d085를 포함한 다른 manifest는 v4 그대로다.
- **리허설 가짜 Jev**: 매 응답에서 현재 서빙 중인 dated 빌드를 돌려준다.
  - 서빙 빌드는 무료 `GET /v1/models` 목록의 가장 높은 Jev 버전을 정산 계약의 dated 빌드에 대응해 정한다. 지금은 `typesafe/jev-1.14-20261014`다.
  - 목록에 있는 버전에 대응하는 dated 빌드가 없으면 `REHEARSAL_SERVED_MODEL_UNKNOWN`으로 크게 실패한다.
  - 리허설 보고서에 `listed_models`와 `served_model`을 남긴다.
- **테스트**:
  - v5: 1.14 허용, 미지 빌드·stage·요청 모델·정책 해시는 차단(2건).
  - loader: v4와 v5는 받고 v3는 거부(기존 테스트에 추가).
  - 리허설 서빙 빌드(1건).
- **고정**: 실행기가 v11 고정 대상이므로 v11을 다시 고정하고 `supersedes.reason`에 사유를 덧붙였다. d076은 새 해시 `b1e7b612…`로 다시 연결했다.
- **전체 테스트**: `npm test` 결과는 1421/1422이다. 남은 실패 1개는 이미 있던 D071 테스트다.

## 리허설 결과 (커밋 `328c105`, 깨끗한 트리, 공유 장부 불변)

| 과제 | served_model | baseline | readiness_failure | missing_output | unknown_model_build | 통과 |
| --- | --- | --- | --- | --- | --- | --- |
| h2 (`rehearsal-h2-20261019-05`) | `typesafe/jev-1.14-20261014` | 완료 | 완료 | 완료 | `BUDGET_MODEL_UNSUPPORTED` | **예, 4/4** |
| openapi (`rehearsal-openapi-20261019-06`) | `typesafe/jev-1.14-20261014` | 완료 | 완료 | 완료 | `BUDGET_MODEL_UNSUPPORTED` | **예, 4/4** |

- 모든 가짜 Jev 응답의 모델은 1.14 dated 빌드였다. 모든 admission 검사는 v5 정책에서 `admit_observed`였다.
- openapi readiness_failure에서는 고장이 `adaptive-leaf-n3`에 걸렸다. 그래서 로컬 수리 → 공개 실패 → profiles 단계 수리 경로를 1.14 응답으로 거쳤다.
- **대조 실행**(`rehearsal-control-v4-20261019`, 저장소 밖 임시 manifest):
  - 같은 openapi manifest에서 admission만 v4로 바꾸면, 새 리허설의 baseline이 `ADAPTIVE_TOKEN_PREFLIGHT_BLOCKED`(split 단계)로 실패한다.
  - 즉 유료 실행에서 드러났던 결함을 이제 무료 리허설이 첫 Jev 응답 직후에 잡는다.

**유료 실행 관문**: 이 기록을 커밋하면 tree가 바뀐다. 유료 실행 전에는 기록 커밋에서 리허설을 다시 통과시켜야 한다.

```decision-record
{
  "id": "R20261019-ADMISSION-V5",
  "goal": "Add a token admission policy version that verifies the jev-1.14 build from documented context limits, make the rehearsal's Jev double answer with the currently served dated build, and rerun the free rehearsals.",
  "owner": "side session of the held-out stage 1 prep session",
  "status": "complete",
  "next_trigger": "Rerun the h2 and openapi rehearsals on the commit that adds this record before the next paid run; openapi's paid rerun is a new run, the terminal openapi-partial-repair-01 is not resumed.",
  "conditions": [
    "No paid calls: only free GETs (official docs, model list, credits); Claude inference and Jev POST doubled in rehearsals.",
    "Rehearsals ran from clean commit 328c105 with the same records, references and catalogs as before; shared ledger hash unchanged.",
    "Claude-only scope."
  ],
  "sources": [
    {"id": "guide_114", "path": "benchmark-runs/jev-114-admission-evidence-20261019/jev-ai.pro_model_jev-1.14.html", "sha256": "e3da7984abbf03aba9a05059be778b1d2ce1f1efa52f663a6559c0e1ee5d056d"},
    {"id": "api_page", "path": "benchmark-runs/jev-114-admission-evidence-20261019/jev-ai.pro_jev-api.html", "sha256": "8e6346e7ba55f6d01a2733d795a327f7a7f1628f1e9d7599e31fbaa5af83eb4f"},
    {"id": "h2_rehearsal", "path": "benchmark-runs/rehearsal-h2-20261019-05/rehearsal.json", "sha256": "b7294ec85900bb943521c46349045471acfecfb6d6f1f585da3a83134b61e341"},
    {"id": "openapi_rehearsal", "path": "benchmark-runs/rehearsal-openapi-20261019-06/rehearsal.json", "sha256": "e49b351f739edb248a71392dd34091659f29bca4152e48ebc831d5f99ca4be7e"},
    {"id": "openapi_readiness", "path": "benchmark-runs/rehearsal-openapi-20261019-06/readiness_failure/events.jsonl", "sha256": "ecb1383385b22f7394e6cdc3f8e85511c4495e81e6cca7fe062d13bdf8f1c8df"},
    {"id": "control_v4", "path": "benchmark-runs/rehearsal-control-v4-20261019/run/rehearsal.json", "sha256": "b15498f2cdd8f1b01e9c06bf26d06488389bc6e55ecff7ef92c8ecb00f645d05"}
  ],
  "claims": [
    {"id": "context_evidence", "kind": "measured", "text": "The official Jev 1.14.0 model guide and the Jev API page state the same default limits as 1.13 (64k tokens per request, 32k for state plus the longest question), with 262k only under an explicit long-context opt-in; the dated ID typesafe/jev-1.14-20261014 is not in the docs and rests on provider observations.", "source_ids": ["guide_114", "api_page"]},
    {"id": "both_pass", "kind": "measured", "text": "h2 and openapi rehearsals each passed 4 of 4 rows at clean commit 328c105 with served_model typesafe/jev-1.14-20261014; every Jev double answer reported that build and every token admission check was admit_observed under policy r20261019-jev114-observed-build-v5.", "source_ids": ["h2_rehearsal", "openapi_rehearsal", "openapi_readiness"]},
    {"id": "control_catches_v4", "kind": "measured", "text": "With only the admission contract switched back to v4, the new rehearsal's openapi baseline fails ADAPTIVE_TOKEN_PREFLIGHT_BLOCKED at stage split, so the defect behind openapi-partial-repair-01 is now caught for free.", "source_ids": ["control_v4"]},
    {"id": "v5_scope", "kind": "decision", "text": "Admission v5 adds only jev-1.14.0 and typesafe/jev-1.14-20261014 on top of v4 and is opt-in per inferred-repair manifest; h2 v12 and openapi-partial-repair-v12 opt in, d085 and other manifests keep v4.", "source_ids": ["guide_114"]}
  ],
  "costs": [],
  "unresolved": [
    "The dated 1.14 ID is a provider observation, not a documented ID; a later 1.14 build or a 1.15 release needs a new admission version and settlement entry.",
    "Readiness does not validate .jinja templates.",
    "Pre-existing D071 cohort dispatch test failure."
  ],
  "side_effects": [
    "Commit 328c105 on feat/heldout-eval-20261018 (v11 re-frozen, d076 rebound).",
    "Evidence folder benchmark-runs/jev-114-admission-evidence-20261019; rehearsal folders rehearsal-h2-20261019-05, rehearsal-openapi-20261019-06 and rehearsal-control-v4-20261019 (temporary v4 manifest copy inside it)."
  ]
}
```
