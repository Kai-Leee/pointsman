# R20261020-PLUGIN-PLAN — main으로 올릴 Pointsman 플러그인 수정 계획

사용자 요청: "이거는 메인으로 올라갈 작업으로 해서 진행할 것. 단, 작업자 에이전트는 진행하는 에이전트를 따르게 하는 게 첫 번째. 그리고 계획을 다시 더 보는 게 좋을 것 같다." 이어서 추가 기능 3개, 수정·확인 3개, 흑백 애니메이션 HTML 1개를 요청했다.

- 이 문서는 계획이다. 구현과 유료 호출은 아직 없다.
- 근거는 실제 실행 2건이다: openapi-partial-repair-02(독립 63/63)와 heldout-h2-pilot-04(독립 25/25).
- 두 실행에서 뽑은 타임라인은 [R20261020_run_timelines.json](evidence/R20261020_run_timelines.json)에 커밋했다.
- 설계 바탕은 [R20261020-WORKFLOW-DESIGN](R20261020_WORKFLOW_DESIGN.md)의 혼합안이다: 플러그인 1개, 기존 `jev-ai` MCP 서버 확장, research 실행기는 측정 전용으로 유지.

## 0. 첫 번째 원칙: 작업자는 진행 중인 에이전트를 따른다

해석(사용자 확인 필요): 제품 모드의 작업자는 메인 세션 에이전트의 설정을 그대로 물려받는다. 물려받는 것은 기본 모델, 권한, 사용자 저장소의 CLAUDE.md다. Jev는 그 범위 안에서 작업별 모델과 추론 수준만 고른다.

- 어제 검토한 작업자 격리(도구 제한, CLAUDE.md 차단)는 **research 측정 전용**으로 내린다. 사용자 저장소 작업에는 숨김 검사가 없으므로, 격리보다 사용자 규칙을 따르는 것이 맞다.
- 확인 방법: 플러그인 스킬이 띄운 작업자가 세션의 CLAUDE.md 규칙을 따르는지, 같은 질문 세 줄로 확인한다(R20261020 작업자 확인 실험과 같은 방식).

## 실측 기준선

| 구간 | openapi-02 | h2 pilot-04 |
|---|---|---|
| 전체 | 1,895.0초 | 1,177.5초 |
| 준비(환경·장부·모델 확인) | 0–97초 | 0–53초 |
| Jev 판단 | 7회, 호출 합계 10.2초, 196,662 입력 토큰, $0.118 | 5회, 8.0초, 86,365 입력 토큰, $0.052 |
| 작업(2슬롯) | 110–1,262초, 6개, $8.50 | 63–747초, 5개, $3.89 |
| 공개 검사 | 1,262–1,359초 | 747–793초 |
| 명세 검토와 재검사 | 1,359–1,895초(전체의 28%), 검토 $2.35 | 794–1,177초(전체의 33%), 검토 $1.30 |
| Claude 합계 | **$10.85** | **$5.19** |

- **정정**: R20261019-RESULTS-ANALYSIS는 두 실행의 Claude 비용을 $8.50, $3.89로 적었다. 그 값은 작업자만 합한 것이고, 명세 검토 비용이 빠져 있다. 다른 arm의 비용 집계에도 같은 누락이 있을 수 있어 다시 계산해야 한다.
- Jev 판단은 시간의 0.5%, 비용의 1.1%(openapi)다. 시간을 줄일 여지는 작업 구간과 명세 검토 구간에 있다.
- openapi의 임계 경로는 n3(Opus, 912.7초) 다음 n2(214.5초)였다. 2슬롯 때문에 늦어진 시간은 n2의 시작 지연 약 7초뿐이다. n1은 선행 작업이 없는데도 923초를 기다렸지만, 임계 경로에는 영향이 없었다.
- h2는 작업 5개 사이의 의존 관계가 **하나도 없었다**(predecessors 모두 빈 목록). 이것이 실제로 맞는지는 1.2에서 확인한다.

## 1. 추가할 기능

### 1.1 예상 감소 토큰과 시간

- **현재**: 실행 전 예측이 없다. 비교는 실행 후 기록으로만 한다.
- **설계**: Jev가 분해와 프로필을 정한 직후, 작업마다 예상 시간·비용 범위를 붙인다.
  - 계수는 기록된 실행의 프로필별 실측값(초/$, write_scope 파일 수 기준)이다.
  - 같은 과제를 메인 에이전트 하나가 처리할 때의 예상치(openapi Claude 단독 3회 평균 38.3분, $19.83)와 비교해 차이를 보여 준다.
  - 표시는 항상 "추정"이다. 실행이 끝나면 예측과 실측을 나란히 기록해 계수를 보정한다.
- **확인**: 기록된 실행 2건에 예측기를 거꾸로 적용해 오차를 보고한다. 표본 2건이라 보정 전 수치로 표시한다.

### 1.2 업무 크기와 연결 관계 누락 확인

- **현재**: 의존 관계는 알려진 파일 의존 정보로 코드가 만든다. h2에서는 그 정보가 비어 있어 의존 관계가 0개였다. 작업 크기도 n3 912.7초와 n1 38초로 24배 차이가 났다.
- **설계**: 실행 전에 무료 정적 점검을 한다.
  - 요구사항마다 담당 작업이 있는지 확인한다.
  - 각 작업의 쓰기 파일이 다른 작업 파일을 import·참조하는지 훑어서, 계획에 없는 의존을 찾는다.
  - 예상 크기가 중앙값의 5배를 넘는 작업이 있으면 경고한다.
  - 빠진 것이 있을 때만 Jev에 좁은 질문 하나를 보낸다.
- **확인**: h2와 openapi 후보 코드에 점검을 돌려 h2의 "의존 0개"가 실제와 맞는지 판정한다.

### 1.3 Jev 판단 직후 배치·순서 그림

- **설계**: 판단이 끝나면 HTML 아티팩트로 작업 배치를 그린다. 슬롯별 순서, 의존선, 임계 경로를 보여 준다. 실행 중에는 상태가 갱신된다.
  - **1.3.1** 작업마다 예상 시간·비용을 표시하고, 끝나면 실측으로 바꾼다.
  - **1.3.2** 마무리 피드백 루프: 끝에 "남은 일" 목록을 만든다. 실패한 검사, 명세 검토가 바꾼 파일, 수리 회차가 들어간다. 이 목록이 다음 수리 회차의 입력이 되거나 사용자 결정으로 넘어간다. 진전 없이 2회가 지나면 멈추고 목록을 보여 준다.
- **확인**: 기록된 실행 2건의 이벤트로 그림을 다시 그려서 실제 순서와 일치하는지 대조한다. 3번 HTML이 첫 시제품이다.

## 2. 수정과 확인

### 2.1 의존 관계 때문에 생기는 배치 오류 없애기

- **현재 실패 기록**(로컬 runs-table): `ADAPTIVE_INFERRED_ARTIFACT_BINDING` 3건, `ADAPTIVE_CAUSAL_HISTORY_INVALID` 1건, `ARTIFACT_CHECK_NOT_PASSED` 4건. 결과물 누락(`DAG_RUNTIME_ARTIFACT_MISSING`)은 R20261018에서 부분 수리로 고쳤다.
- **설계**: 실행 전 계획 검증기를 둔다.
  - 순환이 없어야 한다.
  - 쓰기 범위가 서로 겹치지 않아야 한다.
  - 모든 선행 산출물에 만드는 작업이 있어야 한다.
  - 수리 대상이 실제 실행 기록과 묶여 있어야 한다.
- **확인**: 위 실패 유형마다 고정 테스트 데이터를 만들고, 무료 리허설의 고장 목록에 추가한다.

### 2.2 어떤 상황에서도 수리 방법이 정해져 있게 하기

- **현재**: 수리 경로가 셋이다.
  - 로컬 검사 실패와 결과물 누락: 부분 수리(판단 호출 0회)
  - 공개 검사 실패: Jev가 수리 담당을 정함
  - 그 외: 중단 코드로 멈춤(`ADAPTIVE_REPAIR_BUDGET_EXCEEDED`, `ADAPTIVE_TOKEN_PREFLIGHT_BLOCKED`, `HTTP_ERROR` 등)
- **설계**: 수리 사다리를 둔다.
  1. 결정적 부분 수리
  2. Jev 수리 담당 선택
  3. Jev를 쓸 수 없을 때(HTTP 오류, 사전 검사 차단, 모르는 모델)는 메인 에이전트가 담당을 고른다. 결과가 불확실한 POST는 다시 보내지 않는다.
  4. 진전 없이 2회가 지나면 멈추고 1.3.2 목록을 사용자에게 보여 준다.
- 모든 중단 코드는 사다리의 한 칸에 매핑돼야 한다. 매핑이 빠진 코드가 있으면 테스트가 실패하게 한다. 이것은 R20261018 병합 항목 2(중단 코드 완전성 테스트)를 구현하는 것이다.
- **확인**: 중단 코드 목록 전체를 대상으로 하는 완전성 테스트와, 리허설 고장으로 3단계 경로를 검증한다.

### 2.3 Jev를 거치지 않고 에이전트가 더 빨리 할 일

- **실측**:
  - Jev 판단은 1회 1.1–2.3초이고, 질문 53개 묶음도 2.2초였다.
  - Mac 비교에서 초기 210개 질문 구간은 Codex 판단 243.81초, Jev 9.26초였다. 모델과 조건이 달라 직접 비교에는 한계가 있다.
  - 따라서 여러 후보 중 고르는 묶음 판단은 Jev가 빠르다.
- **에이전트(또는 코드)가 맡을 일**:
  - 후보가 1개인 판단(이미 무호출)
  - 의존 순서 계산과 로컬 수리(이미 코드)
  - 저장소를 읽어야 답이 나오는 판단(예: 1.2의 import 확인)
  - 작업이 하나뿐인 작은 변경. 이 경우 준비 53–97초와 명세 검토 383–536초가 고정으로 붙으므로 분해 자체를 건너뛴다.
- 건너뛰는 기준값은 미측정이다. 1.1 예측기로 정하고, 같은 과제 비교 실행으로 보정한다.

## 3. 흑백 애니메이션 HTML

현재 시스템을 회색조 애니메이션 HTML로 보여 준다.
- 두 실행을 나란히 놓고, Jev 요청이 업무를 어떻게 나누고 순서를 잡고 연결하는지, 그리고 검사와 검증 결과까지 보여 준다.
- 각 구간의 시간과 비용을 함께 표시한다.
- 데이터는 위 증거 파일에서만 가져온다.

## 진행 순서와 규칙

| 순서 | 항목 |
|---|---|
| 1 | 0번 원칙 |
| 2 | 2.1 계획 검증기 |
| 3 | 2.2 수리 사다리 |
| 4 | 1.2 누락 점검 |
| 5 | 1.1 예측기 |
| 6 | 1.3 배치 그림과 피드백 루프 |
| 7 | 2.3 건너뛰기 기준 |

- 단계마다 커밋한 뒤 무료 리허설이나 실험을 한다.
- 구현은 `origin/main`에서 새 브랜치로 진행한다.
- main에 올리는 목표마다 버전을 올리고, CHANGELOG에 Goal 줄과 태그를 남긴다.

```decision-record
{
  "id": "R20261020-PLUGIN-PLAN",
  "goal": "Plan the main-bound Pointsman Claude Code plugin: workers follow the session agent, plus estimation, gap checks, placement visuals, a repair ladder and Jev-skip rules.",
  "owner": "root",
  "status": "planned",
  "next_trigger": "User confirms the interpretation of principle 0; then branch from origin/main and implement 0 and 2.1 first, committing before each rehearsal.",
  "conditions": [
    "Plan only: no implementation, no paid call.",
    "Baselines from two completed runs only (openapi-partial-repair-02, heldout-h2-pilot-04); costs are API-equivalent USD.",
    "The Codex-vs-Jev 210-question latency comparison used different models and hosts."
  ],
  "sources": [
    {"id": "timelines", "path": "docs/decisions/evidence/R20261020_run_timelines.json", "sha256": "1537f1e04aa0e813dca7f99c3a36b412c4fe7394b5b38c2c109c4e595181242e"},
    {"id": "workflow_design", "path": "docs/decisions/R20261020_WORKFLOW_DESIGN.md", "sha256": "53043e8edb171a3b7490472585e6f2dbc8442bc1e1e8a5e907de733ea8cafee7"}
  ],
  "claims": [
    {"id": "baseline_openapi", "kind": "measured", "text": "openapi-partial-repair-02: 1,895.0 s; 7 Jev calls 10.2 s, 196,662 input tokens, USD 0.118; 6 workers USD 8.50 from 110 to 1,262 s; spec review 1,359-1,895 s with USD 2.35; Claude total USD 10.85.", "source_ids": ["timelines"]},
    {"id": "baseline_h2", "kind": "measured", "text": "heldout-h2-pilot-04: 1,177.5 s; 5 Jev calls 8.0 s, 86,365 input tokens, USD 0.052; 5 workers USD 3.89 from 63 to 747 s; spec review 794-1,177 s with USD 1.30; Claude total USD 5.19; the plan had no edges among its 5 tasks.", "source_ids": ["timelines"]},
    {"id": "cost_correction", "kind": "correction", "text": "R20261019-RESULTS-ANALYSIS Claude costs for these two runs (USD 8.50 and 3.89) counted workers only and omitted spec review (USD 2.35 and 1.30); other arms' cost totals may share the omission.", "source_ids": ["timelines"]},
    {"id": "principle_0", "kind": "decision", "text": "In product mode workers inherit the session agent's model, permissions and CLAUDE.md; Jev picks model and effort within that; worker isolation stays a research measurement requirement. Interpretation awaits user confirmation.", "source_ids": ["workflow_design"]},
    {"id": "jev_skip", "kind": "hypothesis", "text": "Single-task changes should skip decomposition because fixed preparation (53-97 s) and spec review (383-536 s) dominate; the threshold is unmeasured.", "source_ids": ["timelines"]}
  ],
  "costs": [],
  "unresolved": [
    "Confirmation of principle 0 interpretation.",
    "Recompute Claude cost for all arms including spec review.",
    "Whether h2 truly had no inter-task dependencies."
  ],
  "side_effects": [
    "New plan record and committed timeline evidence; no code change."
  ]
}
```
