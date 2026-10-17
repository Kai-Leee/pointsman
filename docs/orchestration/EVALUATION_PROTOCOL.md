# 평가 구조와 신뢰성 점검 — R20261017-EVAL-PROTOCOL

사용자 요청: Harness(revfactory/claude-code-harness) A/B 연구와 비교한다. 평가 방식을 구조화하고, 평가용 목록을 만들어 "우리 방식이 더 효과적"이라는 주장의 신빙성을 높인다. Harness 플러그인 기반 구조 확장은 사용자와 함께 이후 검토한다.

정본은 [evaluation-protocol.v1.json](contracts/evaluation-protocol.v1.json)이다. 실측 보고서는 [report.md](../../benchmark-runs/eval-protocol-20261017-01/report.md)이고, 보류 과제 목록은 [evaluation-tasks.v1.json](../../benchmarks/e2e-swe/manifests/evaluation-tasks.v1.json)이다. 유료 모델 호출, Docker 실행, 재채점은 하지 않았다. 기존 실행 원본도 수정하지 않았다.

**범위(2026-10-18 사용자 결정)**: "우리는 클로드에서만 먼저 진행을 할게."
- 다음 평가와 확장은 Claude 경로만 대상으로 한다. 비교 조건은 Claude 단독(`claude_all`)과 Claude 작업자를 쓰는 Jev arm이다.
- Codex 비교(D087·D088 등)는 기존 결과를 기록으로만 보존하고, 새 조건이나 확장은 하지 않는다.
- pstack의 여러 회사 모델 패널(opus·grok)도 Claude 모델 계열 안에서만 검토한다.

## 1. 결론 먼저

- **평가 방법의 신뢰성**(1차 집계, 2차는 7절): 점검표 14개 항목에서 Jev가 `yes`인 항목은 9개이고, Harness는 2개(C09, C11)다. 실행 기반 채점, 채점기 모델 호출0, 숨김 검사 격리, 조건 비공개 채점, 사전 고정 규칙, 시작 실행 전부 보고, 구간 추정, 시간·토큰 측정이 Jev 쪽 근거다.
- **제품 효과**: 이번 자료로는 "Jev가 Claude 단독보다 효과적"이라는 주장을 세울 수 없다. 같은 실행 안에서 비교한 결과 Claude 단독이 Jev(jev_all)를 상대로 2승 1무 0패다(d066·d067·d071). 반복3회 이상인 조건은 28개 중 2개뿐이다.
- **Jev가 못 채운 항목**: C06(반복), C08(후보1개 누락), C11(과제 1개뿐), C12(튜닝 과제로만 평가), C14(제3자 재현). 이 중 C11·C12를 해결하려고 보류 과제 15개를 실행 전에 고정했다.

## 2. Harness 연구에서 확인한 사실

원본 저장소를 scratchpad에 shallow clone해 직접 셌다. 아래 수치는 저자 자체 측정값의 재계산이다.

| 확인 항목 | 결과 | 확인 방법 |
| --- | --- | --- |
| 채점 방식 | LLM이 10개 차원을 0–10점으로 채점, 같은 파일에서 두 조건을 나란히 평가 | `.claude/skills/output-evaluator.md`, `results/case-*/evaluation.json` |
| 반복 | 과제당 조건별 1회 | `summary-15cases.json` |
| "분산 −32%" | 서로 다른 15개 과제 간 **표준편차**가 5.3→3.6으로 줄었다는 뜻이다. 표본SD로는 5.51→3.56(−35.5%), 분산으로는 −58.3% | `case_results[].baseline/harness` 재계산 |
| Expert 5개(011–015) 산출물 | baseline 파일 0개. harness 쪽은 `.claude/` 설정 7–8개뿐이고 코드·테스트는 없다 | `fd -t f` 케이스별 개수 |
| Expert 채점 근거 | case-011 baseline 근거에 "5개 시나리오 중 1-2개만 동작 예상"처럼 산출물 없이 동작을 추정한 문장이 있다. "가능·예상·추정" 단어 빈도로는 구분되지 않는다(001–010: 1–7줄, 011–015: 3–10줄; "확장 가능" 같은 일반 용법 포함) | case-011 `evaluation.json`, [harness-file-counts.txt](../../benchmark-runs/eval-protocol-20261017-01/harness-file-counts.txt) |
| 채점 기준 | 산출물을 본 뒤 기준을 다시 썼다("편향 2: Harness 사소한 결함에 과도한 감점") | `experiments/calibration-rubric.md` |

Harness 효과가 가장 크다는 근거(+36.2)는 Expert 구간이다. 그런데 공개 저장소에는 이 구간의 산출물이 없다. 저장소에 올리지 않았을 가능성도 있으므로 "실행하지 않았다"고 단정하지는 않는다.

## 3. 평가 구조

1. **단위**: arm 1개 = 조건 1개 × 과제 1개 × 시작 상태 1개.
2. **결과 지표**
   - 주 지표는 `resolved`(숨김 독립 검사 전부 통과, 0/1)이고 Wilson 95% 구간과 함께 보고한다.
   - 보조 지표는 네 가지다: 독립 통과율(0–100, 진단용), 같은 실행 안의 쌍 승률, 숨김 검사 클래스별 실패, arm별 시간·사용량.
   - 독립 통과율은 벤치마크 점수가 아니다(`partial_pass_fraction_is_benchmark_score=false`).
3. **포함 규칙(intention-to-treat)**
   - 채점된 arm은 종료 코드와 상관없이 채점 결과대로 센다.
   - 채점 없이 끝난 arm은 원인으로 나눈다. 제품 자체 원인(예: `ADAPTIVE_ARM_TOKEN_LIMIT`)이면 0점이다.
   - 환경(`BUDGET_LOCKED`), 사용자 중단(`ADAPTIVE_CANCELLED`), 결과 파일 없음(`NO_ARM_RESULT`)은 제외하되 사유와 함께 나열한다.
   - 분류에 없는 코드는 `unclassified`로 표시하고, 분류하기 전에는 보고서를 인용하지 않는다.
4. **통계**: 조건별로 k/n과 Wilson 구간, 평균, 표본SD, 최소·최대를 낸다. 쌍 비교는 같은 실행 디렉터리의 arm끼리만 한다.
5. **신뢰성 점검**: 14개 항목. 9개는 보고서가 실행 기록에서 자동 판정하고 5개는 근거 경로를 고정했다.

## 4. 신뢰성 점검표 실측 (로컬 arm 41개)

| ID | 기준 | Harness | Jev | 관측 |
| --- | --- | --- | --- | --- |
| C01 | 숨김 검사 실행으로 채점 | no | yes | 집계 35개 중 32개 채점, 나머지 3개는 산출물 없음 0점 |
| C02 | 채점기 모델 호출 0 | no | yes | 32/32 |
| C03 | 작업자가 채점 검사를 못 봄 | 해당없음 | yes | [grade-adaptive-arm.mjs:4](../../scripts/grade-adaptive-arm.mjs:4), [adaptive-dag-runner.mjs:883](../../src/benchmark/adaptive-dag-runner.mjs:883) |
| C04 | 채점기가 조건을 모름 | no | yes | 후보 디렉터리만 입력 |
| C05 | 결과 보기 전 규칙 고정 | no | yes | E2E-SWE b11ac067 + 이미지 digest |
| C06 | 조건당 3회 이상 | no | **no** | 2/28 조건 |
| C07 | 시작 실행 전부 보고 | unknown | yes | 41 = 집계35 + 제외6(사유 포함) |
| C08 | 점수마다 산출물 보존 | partial | **no** | 31/32, `d075-same-source-01` 후보 없음 |
| C09 | 같은 과제·시작·시간대 쌍 | yes | yes | 쌍 15개 |
| C10 | 구간 추정 | no | yes | Wilson 95% |
| C11 | 난이도 구간당 과제 3개 이상 | yes | **no** | 채점 과제 1개(openapi_python_client) |
| C12 | 튜닝에 쓰지 않은 과제로 평가 | unknown | **no** | 0/1 |
| C13 | arm별 시간·토큰·비용 | no | yes | `adaptive-arm-result/v1` |
| C14 | 제3자 재현 | no | **no** | 저장소 소유자 실행뿐 |

추가 관측:
- **실패 차원**: 숨김 검사 클래스별 실패 횟수가 많은 순으로 `TestConst` 8/32, `TestUnprocessableSchemasWarn` 6/32, `TestMultipartBody`·`TestPathParameterEncoding`·`TestUrlEncodedBody` 각 5/32다. Harness의 LLM 차원 점수 대신 실행된 검사 클래스를 차원으로 쓴다.
- **로컬에 원본이 없는 실행**: D082–D085 클라우드 실행은 원본이 이 Mac에 없어 보고서에 들어가지 않았다. 문서 기준 수치는 D082 5/7(08은 사용자 중단), D083 2/3, D085 2/3이고, Wilson 구간은 5/7이 35.9–91.8%, 2/3이 20.8–93.9%다. 원본을 가져와 같은 스크립트로 다시 집계하기 전까지는 문서 수준 근거다.
- **보고서가 처음에 놓친 실행**: 첫 판에서는 결과 파일이 없는 계획 arm 3개(`d079-no-deferral-01`, `d080-defaults-02`, `d081-defaults-04`)가 보이지 않았다. C07은 판정 대상에서 빠진 채로 `yes`였다. `protocol.json`의 `arms[]`와 대조하도록 고친 뒤 제외 목록에 나타난다.

## 5. 평가용 보류 과제 15개

- **선정 규칙**: E2E-SWE의 Python 과제 103개에서 튜닝 과제 `openapi_python_client`를 빼고 102개를 모집단으로 삼았다.
- **난이도 구간**: 명세(`instruction.md`) 크기의 삼분위수인 13,737B와 19,271B를 경계로 나눴다. 이 기준이면 튜닝 과제(19,656B)는 expert 구간에 해당한다.
- **과제 선택**: 구간마다 `sha256("jev-eval-v1:" + 과제명)` 오름차순으로 5개씩 골랐다.
- **고정 확인**: `node scripts/select-evaluation-tasks.mjs --check`가 재생성 결과와 파일이 같은지 확인한다.

| 구간 | 과제(명세 바이트 / 숨김 검사 수) |
| --- | --- |
| basic | h2 (11,977/25), git-code-debt (8,619/33), beaker (7,032/37), nose2 (13,276/37), monkeytype (10,203/23) |
| advanced | pycparser (17,390/38), playback (17,746/51), tremolo (13,799/33), deepdiff (14,747/29), sqlparse (18,388/38) |
| expert | django-modelcluster (21,509/91), kcwarden (29,213/46), yamlpath (19,746/111), water (27,076/77), mapillary_tools (45,030/54) |

**실행 전 필요한 것(미구현)**:
- 현재 전체 개발 경로는 openapi 과제 전용이다. 의무 목록(`d056-obligations.json`), D066 카탈로그, 공개 검사 93개가 모두 이 과제에 맞춰져 있다.
- 새 과제마다 공개 명세만으로 의무·카탈로그·공개 검사를 만들어야 한다. 숨김 검사 내용은 넣지 않는다.
- 과제별 Docker 이미지 잠금도 필요하다.

**비용 추정**: D079 성공 1회(25분16초, $9.84)를 단위로 잡으면, 1단계(구간당 과제1 × 조건2 × 반복3 = 18 arm)는 약 $180·7.6시간(순차)이다. 실측 전 추정치다.

## 6. Harness 플러그인 대응표 — 확장 검토 자료

설치본: `~/.claude/plugins/marketplaces/harness-marketplace` v2.1.0. 구현하지 않은 검토 자료다.

| Harness v2 요소 | Harness 방식 | Jev 현재 대응 | 확장 후보 |
| --- | --- | --- | --- |
| 설계도 `CLAUDE.md` | 파일 구조·규칙을 미리 작성 | 공유 카탈로그(산출물22 경로, 단위21 인터페이스, 약26KB)를 모든 초기 작업자에게 전달 | 중복이라 우선순위 낮음 |
| 에이전트 정의 | 설계 시 역할·품질 기준 고정 | Jev가 실행 중 작업 수·담당·쓰기 범위 결정(layered-v2, owner criteria) | 역할별 품질 기준 문구를 작업자 입력에 추가 |
| 스킬(도메인 참고자료) | 에이전트별 `SKILL.md`+references | **없음.** 작업자는 명세+카탈로그만 받고 `--setting-sources ''`로 실행되므로 스킬을 자동으로 읽지 않는다 | 공개 명세만으로 만든 참고자료를 opt-in으로 전달(`worker_preconfiguration`). 숨김 실패 지식으로 쓰면 누출이다 |
| 모델 티어 선택 | 설계 시 fable/opus/sonnet 규칙 | Jev profile 선택(20개 프로필, 작업별) | Harness 규칙을 고정 기준선 조건으로 만들어 비교 |
| 실행 모드 | workflow/지속형/서브에이전트 중 설계 시 선택 | DAG 실행기 고정(슬롯2, 임계 경로 스케줄) | 모드 선택을 Jev 판단으로 둘지 검토 |
| 검증 패턴 | 적대적 검증, 심사위원단, 누락 검토자 | 공개 검사93 + 공개 명세 검토(누락 검토자와 유사) | 적대적 검증을 수리 후보 선택에 적용할지 검토 |
| 단계 경계 동결 | 산출물 해시 기록 | artifact revision binding, source pin | 이미 있음 |
| 재시도 불가 실패 | 한도·인증·권한은 재시도 금지 | 불확실 POST 재전송 금지, 정산 확인 | 이미 있음 |
| `harness:evolve` | 실행 회고 → 에이전트·스킬 갱신 | D0xx 결정 기록, 수동 개선 | 실패 차원 표 → 개선 후보 자동 정리 |
| 스킬 테스트 | with-skill vs baseline, 테스트 요청2–3개 | 이 프로토콜 | 이 프로토콜을 Harness 산출물 평가에 그대로 적용 |

Jev와 Harness의 결정 시점은 다르다. Harness는 사전 구성(정적)이고 Jev는 실행 중 판단(동적)이다. 둘은 서로 대체하기보다 보완하는 관계일 수 있다. 다만 이것은 가설이며 측정한 적이 없다.

## 7. pstack 병렬 분석과 2차 집계

pstack은 Lauren Tan의 Cursor 스킬 스택이다. 최신 `cursor/plugins` 101b274(2026-10-16)를 받았다. 규모는 파일 168개, 스킬 54개(원칙 스킬 24개)이고 라이선스는 MIT다([재고](../../benchmark-runs/eval-protocol-20261017-01/pstack-inventory.txt)). 읽기 전용 에이전트 3개를 병렬로 돌려 오케스트레이션·검증·원칙을 나눠 분석했다. 아래 핵심 주장은 원문에서 다시 확인했다.

**성격**
- 실행 규칙 대부분이 모델에게 주는 문장 규칙이다.
- 코드(`scripts/orch/orch.ts`)는 기록만 한다. 원문 표현은 "The CLI never spawns, waits, or wakes anything".
- 스킬 53개가 `disable-model-invocation: true`라서 사용자가 직접 호출해야 한다.
- 성능 주장(예: "fearless parallelism")은 있지만 수치나 실행 기록은 없다.
- Jev 작업자는 `--setting-sources ''`, `--tools ''`로 실행되므로 pstack 스킬을 보지 못한다. 쓰려면 문구를 입력에 직접 넣어야 한다.

| 영역 | pstack | Jev |
| --- | --- | --- |
| 작업 분기 수 | 모델이 실행 중에 정함. 패널은 사용자 설정 목록 수만큼 | Jev가 고정 질문에 선택값으로 답함(layered-v2) |
| 역할별 모델 | 사용자 설정 표 + 모델의 한 단계 조정. 여러 회사 모델(opus·grok) | Jev가 작업마다 선택. Claude 모델만 20개 프로필 |
| 후보 여러 개 + 심사 | arena·architect·interrogate(다른 모델 계열 심사) | 없음. 공개 명세 검토 1회(고정 코드) |
| 재시도 | 실패 유형별 규칙 문장(용량→범위 축소, 도구 오류→다른 모델, 최대 2회) | 자동 재시도 0. 새 근거 없이는 재요청하지 않음. 모델만 바꾸는 것은 진전으로 보지 않음 |
| 확신 낮음 처리 | 없음 | confidence 0.5 미만이면 다른 세션에 재질문(현재 기본 꺼짐) |
| 근거 기록 | 추가만 하는 TSV, 해시 없음 | 결정 기록, SHA-256, 주장 유형 구분 |
| 교훈 → 강제 | `correct`: 같은 실수가 두 번 나오면 구조·타입·lint·테스트 순으로 강제하고, 규칙마다 무엇이 강제하는지 표로 관리 | 기록만 있고 강제 장치와 연결되지 않음 |

**pstack `benchmark-checklist`에서 가져올 점검 후보** (다음 검토에서 채택 여부를 정함. v1에는 반영하지 않음):

| 후보 | 기준 | 근거 |
| --- | --- | --- |
| C15 | 조건마다 결과를 제한한 요인(토큰 한도, 슬롯, 수리 예산, 시간)을 이름 붙이지 못하면 판정을 보류 | Q1 "Why not double?" |
| C16 | 각 arm의 설정 해시를 기록하고, 기본값과 튜닝값을 비교한 결과는 승부로 세지 않음 | Q2 |
| C17 | A·B·A·B 교차 순서와 캐시 상태를 기록 | Q2, Q5 |
| C18 | 조건 안 반복 간 편차보다 작은 차이는 "차이 없음"으로 판정 | Q5 |
| C19 | 절감 주장은 생략된 부분이 전체에서 차지하는 비율을 넘지 못함 | Q3, Q6 |
| C20 | 숨김 검사 수집 수 = 기대 수, 수집 오류 0 | Q7 |
| C21 | arm 시작 때 부하와 동시 실행 수를 기록 | 실행 전 점검 |
| C22 | 판정을 빨라짐/느려짐/차이 없음/판단 보류 넷 중 하나로만 내림 | Report |

C20에 쓸 필드(`expected_test_count_observed`)는 이미 채점 결과에 있다. 원칙 중에는 우리 규칙과 충돌하는 것도 있다. 기존 API를 지우라는 원칙(migrate-callers-then-delete-legacy-apis)은 재현용 v1 보존과 충돌하고, 사람을 기다리지 말라는 원칙(never-block-on-the-human)은 불확실한 유료 POST를 자동 재전송하지 않는 규칙과 충돌한다. 그대로 들여오지 않는다.

**2차 집계에서 바뀐 것**
- **스크립트 한계 수정**: 보고 스크립트는 탐색 깊이 3 제한 때문에 `실행/cohort/arm`(D086)과 `실행/pair/arm`(Codex) 결과를 놓쳤다. 깊이 4와 `codex-e2e-arm/v1` 형식을 지원하도록 고쳤다.
- **로컬 집계**: arm 41개 → 46개(집계38·제외8).
- **형제 작업 폴더 포함**(D086·D087·D088): arm 54개(집계44·제외10), 분류되지 않은 종료 코드 0([report-combined.md](../../benchmark-runs/eval-protocol-20261017-01/report-combined.md)).
- **같은 실행 쌍 비교**: Codex 판단과 Jev 판단은 2승 0무 1패로 Codex가 앞선다(mac-02 90.5 대 0, d087 93.7 대 0, d088 90.5 대 93.7). Claude 단독과 jev_all은 2승 1무 0패로 그대로다.
- **새 종료 코드 분류**: 제공자 실패는 양쪽 조건 모두 제외한다. `BUDGET_MODEL_UNSUPPORTED`는 우리 실행기 결함이므로 0점이다.
- **작업 기준**: 이 작업 브랜치(`feat/d083-skill-gateway`)는 `origin/research`(D084·D085 포함)보다 커밋 9개 뒤다. 미커밋 파일이 100개라 병합하지 않았다. 앞으로 어떻게 구성할지는 사용자 검토 뒤 정한다.

## 8. 재현

```bash
node scripts/harness-style-report.mjs benchmark-runs [다른 benchmark-runs ...] --json <out.json>
node scripts/select-evaluation-tasks.mjs --check
node --test test/harness-style-report.test.mjs
```

보고서의 `kind`(full/repair)는 디렉터리 이름 규칙으로 정한다(`ponytail:` 주석). 이름 규칙이 바뀌면 arm 결과에 명시 필드가 필요하다.
