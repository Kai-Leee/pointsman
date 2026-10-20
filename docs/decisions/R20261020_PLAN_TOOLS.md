# R20261020-PLAN-TOOLS — 계획 점검 도구 구현과 기록된 실행 적용

사용자 요청: "2.1인 수리라는 것만 제외하고는 다 맞아. 실제로 수리 단계가 어떻게 되는지를 몰라서 나는 일단 빼는 거야. 나머지는 먼저 진행을 바로 해줘."

- 이번 구현에서 수리(R20261020-PLUGIN-PLAN의 2.2 수리 사다리와 2.1의 수리 binding 검사)는 뺐다.
- 나머지 항목은 main으로 올릴 브랜치 `feat/plan-tools-20261020`의 커밋 `92e231d`(v0.4.0)로 구현했다: 0, 1.1, 1.2, 1.3, 2.1의 배치 검사, 2.3.
- 사용자 규칙("항상 커밋 → 실험")에 따라 커밋한 뒤에 실험했다.
- 유료 호출은 없었다.

## 구현한 것

| 항목 | 위치 | 내용 |
|---|---|---|
| 0 작업자는 세션 에이전트를 따름 | `skills/pointsman/SKILL.md` | 작업자 유형 제한 없음. 사용자 CLAUDE.md를 따르고, 프로필에서 모델과 추론 수준만 정함 |
| 2.1 배치 검사(수리 제외) | `src/plan/plan.mjs` `validatePlan` | 쓰기 겹침, 생산자 없는 입력, 생산자 중복, 순환, 담당 없는 요구사항 |
| 1.2 연결 누락 | `findMissingLinks` | Python과 JS의 import를 다른 작업의 파일로 해석해, 계획에 선후가 없으면 보고 |
| 1.1 예상 시간·비용 | `estimatePlan`, `rates.v1.json` | 프로필별 기록 중앙값과 범위, 2슬롯 일정, 순차 대비 시간과 전부 Opus 대비 비용 |
| 2.3 건너뛰기 | `shouldSkipJev` | 작업 1개이거나 예상 시간이 기록된 고정 비용보다 짧으면 분해하지 않음. 기준값은 미보정 |
| 1.3 그림·마무리 목록 | `src/plan/view.mjs`, `closingFeedback` | 회색조 배치·순서 그림(예상과 실제), 작업 표, 연결 누락, 마무리 목록(사용자에게 넘김) |
| 플러그인 | `.claude-plugin/plugin.json` | 기존 jev-ai MCP를 `${CLAUDE_PLUGIN_ROOT}` 경로로 등록 |

테스트 결과:
- 새 테스트 8/8 통과. 버전 검사는 Claude 플러그인 버전까지 확인하도록 늘렸다.
- 링크 검사: Markdown 52개, 링크 320개, 깨진 링크 0개.
- 전체 401개 중 398개 통과. 실패 3개는 MCP 테스트로, 새 worktree에 고정 버전 jev-mcp 바이너리가 없어서 생긴 것이다(`vendor/jev-mcp`에 SOURCE.json만 있음). 받으려면 `npm run mcp:fetch`가 필요한데, 파일 다운로드라서 실행하지 않았다.

## 기록된 실행에 적용한 결과

기록된 계획(profiled-planning.json)을 새 형식으로 바꾸고, 완성된 후보 코드(spec-review/candidate)와 실제 작업 시각을 함께 넣었다. 원시 결과는 `evidence/R20261020_plan_tools/`에 있다.

| 항목 | openapi-02 | h2 pilot-04 |
|---|---|---|
| 배치 오류 | 0 | 0 |
| 계획에 없던 import 연결 | 20개(작업 쌍 13개) | 18개(작업 쌍 7개) |
| 서로를 import하는 쌍 | n2↔n4, n4↔n5 | n2↔n5 |
| 예상 작업 구간 / 실제 | 1,542초 / 1,152초(+34%) | 623초 / 684초(−9%) |
| 예상 작업자 비용 / 실제 | $7.69 / $8.50(−10%) | $4.05 / $3.89(+4%) |
| 크기 경고 | 없음 | n2, n5(514초, 중앙값 80초의 5배 초과) |
| 분해 건너뛰기 | 아니오 | 아니오 |

해석:
1. **h2의 "의존 0개"는 실제와 달랐다.** 예를 들어 n5의 `h2/connection.py`는 n2, n3, n4가 쓴 파일을 import한다. 그런데도 성공한 것은, 각 작업자가 같은 명세의 인터페이스를 보고 만들었기 때문으로 보인다(가설). 따라서 연결 누락은 실패 예고가 아니라 위험 신호로 다뤄야 한다.
2. **서로를 import하는 쌍이 있어서, 모든 연결을 선후 관계로 바꿀 수는 없다.** 그렇게 하면 계획 검사에서 순환이 된다. 이런 쌍은 같은 작업으로 묶거나, 인터페이스를 먼저 만드는 작업을 따로 두는 것이 후보다.
3. **예상 오차는 −10%에서 +34%였다.** 다만 계수를 같은 두 실행에서 만들었기 때문에 이것은 검증이 아니라 일관성 확인이다. 다른 실행으로 따로 검증해야 한다.
4. **연결 점검은 실행 뒤의 완성 코드를 훑은 것이다.** 새로 만드는 과제에서는 실행 전에 파일이 없어서 같은 점검을 할 수 없다. 이 점검이 실행 전에 의미가 있는 것은 기존 코드를 고치는 작업이다.

## 이번 작업에서 생긴 결함

- **import 파서 버그(커밋 전에 수정)**: 한 줄짜리 `from … import` 뒤에 오는 줄까지 이름으로 읽어, 다음 import 문을 놓쳤다. 테스트에서 발견해 고쳤다.
- **테스트 기댓값 계산 오류**: Opus 표본 중앙값을 516으로 적었는데 실제는 514였다.
- **실험 변환 버그**: 요구사항 ID 대신 배열 번호를 넣어서, 첫 실행에서 담당 없는 요구사항이 모두 오류로 나왔다. 변환을 고쳐 다시 실행했다.
- **잘못된 호출로 생긴 파일**: `check-document-link.mjs`에 `--help`를 넘겼더니 `--help`라는 이름의 파일이 생겼다. 커밋 전에 지웠다.

```decision-record
{
  "id": "R20261020-PLAN-TOOLS",
  "goal": "Implement the non-repair items of R20261020-PLUGIN-PLAN on a main-bound branch and apply them to two recorded runs.",
  "owner": "root",
  "status": "complete",
  "next_trigger": "Open the main PR for feat/plan-tools-20261020 (v0.4.0) when the user asks; validate the estimator on runs outside its calibration set; decide how to handle mutually importing task pairs; explain the repair stages before the user decides on repair.",
  "conditions": [
    "Code at 92e231d on feat/plan-tools-20261020 (from origin/main baab3d1); committed before the experiment.",
    "Offline only: no network and no model calls.",
    "Rates are calibrated on the same two runs they were applied to; link scan read completed candidates after the run."
  ],
  "sources": [
    {"id": "openapi_report", "path": "docs/decisions/evidence/R20261020_plan_tools/openapi-partial-repair-02.report.json", "sha256": "e7b0ac639aa55aa7ae4da0befb9945d117b075eb2133841e2f032ee28fba40e4"},
    {"id": "h2_report", "path": "docs/decisions/evidence/R20261020_plan_tools/heldout-h2-pilot-04.report.json", "sha256": "b50f6f421f295ad9e27f8f25ae3cecf3470eb85bef4d4c9836369e5f084d4146"},
    {"id": "openapi_plan", "path": "docs/decisions/evidence/R20261020_plan_tools/openapi-partial-repair-02.plan.json", "sha256": "145517bbcdf862002121edb11b8469a13206dd2aa7d6b28e4cbcdbd068ba7c49"},
    {"id": "h2_plan", "path": "docs/decisions/evidence/R20261020_plan_tools/heldout-h2-pilot-04.plan.json", "sha256": "5a141a5db29532a05a60fda7a11904c2324d71a095a26c62a84fbf8d15cc64d3"}
  ],
  "claims": [
    {"id": "valid", "kind": "measured", "text": "Both recorded plans pass the placement checks with zero errors.", "source_ids": ["openapi_report", "h2_report"]},
    {"id": "links", "kind": "measured", "text": "Completed candidates import other tasks' files without a plan link: openapi 20 links over 13 task pairs (mutual n2-n4, n4-n5), h2 18 links over 7 pairs (mutual n2-n5), although h2's plan had no edges.", "source_ids": ["openapi_report", "h2_report", "h2_plan"]},
    {"id": "estimate", "kind": "measured", "text": "In-sample estimates versus actual worker span and cost: openapi 1,542 s vs 1,152 s and USD 7.69 vs 8.50; h2 623 s vs 684 s and USD 4.05 vs 3.89.", "source_ids": ["openapi_report", "h2_report"]},
    {"id": "links_not_failure", "kind": "hypothesis", "text": "Both runs succeeded despite unexpressed links, likely because workers built against the same specified interfaces; a missing link is a risk signal, not a predicted failure.", "source_ids": ["openapi_report", "h2_report"]},
    {"id": "repair_excluded", "kind": "decision", "text": "Repair automation (ladder and repair binding) is excluded at the user's request until the repair stages are explained; the closing list goes to the user.", "source_ids": []}
  ],
  "costs": [],
  "unresolved": [
    "Estimator validation on runs outside the calibration set.",
    "Handling of mutually importing task pairs (merge or interface-first task).",
    "Pre-execution link scan only applies to edits of existing code.",
    "Three MCP tests need the pinned jev-mcp binary in the new worktree (npm run mcp:fetch, a download).",
    "pointsman_decide with ledger and token admission is still absent on the plugin path.",
    "Main PR, CI and tag v0.4.0 not done."
  ],
  "side_effects": [
    "New worktree /Users/lee/workspace/plugins/pointsman-plan-tools-20261020 on feat/plan-tools-20261020 with commit 92e231d; not pushed.",
    "Experiment evidence committed under docs/decisions/evidence/R20261020_plan_tools on this research branch."
  ]
}
```
