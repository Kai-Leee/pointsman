# R20261020-INTERFACE-FIRST — 인터페이스 먼저 만들기: 설계와 h2 비교 실험

사용자 요청: "인터페이스 먼저 만들기 단계를 설계하고, 커밋 후 h2에서 켜고 끈 조건을 비교 실험해줘."

배경은 [R20261020-COUPLING](R20261020_COUPLING.md)과 대화에서 정리한 구조 공백이다. 지금 DAG는 작업 순서와 파일 문법만 막는다. 작업 사이의 합의(함수 이름, 시그니처, 오류 타입)는 글로 쓴 설명뿐이고, 동작 검사는 모든 작업이 끝난 뒤에 한 번만 돈다. 그래서 조각끼리 어긋나는 문제가 맨 끝의 수리 단계로 넘어간다.

## 설계 (커밋 `4fb47ad`, 검증 수정 `aa5ff5b`)

| 항목 | 내용 |
|---|---|
| 위치 | Jev가 분해와 프로필을 정한 직후, 첫 작업자가 시작하기 전 |
| 호출 | Opus 5.5 medium 1회. 도구 없음, 구조화 출력. 계약: `adaptive-interface-first.v1.json` |
| 입력 | 공개 명세, 요구사항 설명, 인터페이스 카탈로그, 작업별 쓰기 파일만. 숨김 검사와 과거 후보는 넣지 않음 |
| 출력 | 파일마다 공개 이름과 시그니처, 다른 파일에서 가져오는 이름, import 시점(모듈 맨 위인지 함수 안인지) |
| 사용 | 모든 작업자와 수리 작업자 입력에 `interface_contract`로 넣고, 시스템 지시에 한 문장을 덧붙임. 끈 조건에서는 프롬프트가 글자 단위로 같음 |
| 실패 처리 | 계약이 소유하지 않은 파일을 가리키면 쓰지 않고 기록만 함. 이 단계 때문에 실행이 멈추지는 않음 |
| 켜는 방법 | manifest `interface_first {policy, contract, sha256}`(v12 전용). h2 켬 조건 = `v12-interface-first.json` |

## 실험 결과 (h2 보류 과제, 숨김 검사 25개)

순서는 off-01, on-01, off-02(트리 `8202fd6`), 그다음 on-02, off-03, on-03, on-04(트리 `aa5ff5b`)다. 모두 순차로 돌렸고, 실행마다 무료 리허설 관문을 통과한 뒤 돌렸다.

| 조건 | 제품 성공 | Wilson 95% | 첫 회차 공개 통과 | 쓴 수리 회차 | 시간(초) | 총비용 | 성공 1회당 비용 | 성공 1회당 시간 |
|---|---|---|---|---|---|---|---|---|
| 끔 | 1/3 | 6–79% | 1/3 | 0, 2, 2 | 996, 1,792, 1,059 | $20.29 | $20.29 | 64.1분 |
| 켬(계약 사용) | **3/3** | 44–100% | **0/3** | 1, 1, 1 | 1,372, 1,004, 1,062 | $17.31 | **$5.77** | **19.1분** |
| 켬(배정 기준, on-01 포함) | 3/4 | 30–95% | 0/4 | 2, 1, 1, 1 | +1,668 | $24.70 | $8.23 | 28.4분 |

- 비용은 API 환산 금액이다(작업자 + 명세 검토 + 인터페이스 단계 + Jev 입력 토큰 × $0.6/M).
- 인터페이스 단계 자체는 실행당 96–146초, $0.27–$0.56이 들었다.
- 7회 전체 비용은 $44.99, Jev 입력 토큰은 1,030,145개다.
- 실행마다 회차별로 실패한 공개 검사:

| 실행 | 회차별 실패 검사 |
|---|---|
| off-02 | 회차 0·1: request-response, stream-control-frames / 회차 2: request-response |
| off-03 | 회차 0·1·2: stream-control-frames |
| on-02 | 회차 0: request-response → 회차 1에서 통과 |
| on-03 | 회차 0: 검사 6개 실패 → 회차 1에서 통과 |
| on-04 | 회차 0: request-response → 회차 1에서 통과 |

## 해석

1. **예상과 다른 결과다.** 이 단계의 목적은 첫 회차부터 조각이 맞게 하는 것이었다. 그런데 계약을 쓴 3회는 모두 첫 회차 공개 검사에서 실패했다(0/3). 끈 조건은 1/3이 첫 회차에 통과했다. 첫 회차 어긋남을 막는 효과는 관측되지 않았다.
2. **대신 수리가 1회 만에 끝났다.** 켬 조건 3회는 모두 수리 1회로 통과했다. 끈 조건의 실패 2회는 수리 2회를 다 써도 같은 검사(stream-control-frames, request-response)를 고치지 못했다. 수리 작업자도 같은 계약을 받기 때문에, 고칠 때 맞춰야 할 기준이 분명해진 것으로 보인다(가설, 원인은 측정하지 않음).
3. **통계적으로 확정되지 않는다.** 3/3 대 1/3의 Fisher 정확 검정 양측 p는 0.40이고 Wilson 구간도 겹친다. 효과가 있다고 말하려면 반복과 다른 과제(openapi 등)가 필요하다.
4. 성공 1회당 비용과 시간이 줄어든 것은 성공률 차이에서 나온다. 성공한 실행만 보면 켬 조건(평균 1,146초)이 끔 조건(996초, 1회)보다 길다. 인터페이스 단계와 수리 1회가 더해지기 때문이다.

## 이번 작업에서 생긴 결함과 처리

- **켬 조건 검증 결함(on-01 무효)**: 실제 계약은 import 출처를 모듈 이름(`h2.exceptions`)으로 썼고 외부 라이브러리(`hpack`, `hyperframe`)도 넣었다. 출처 소유 검사가 이를 거부해(`ADAPTIVE_INTERFACE_FIRST_IMPORT_UNOWNED`) on-01은 계약 없이 돌았다. `aa5ff5b`에서 출처 검사를 빼고 테스트를 추가했다. on-01 계약을 다시 넣으면 이제 받아들여진다.
- **리허설 대역의 공백**: 대역이 import 없는 계약만 돌려줘서 위 결함을 무료 단계에서 잡지 못했다. 대역이 실제와 같은 모양의 import를 내도록 고쳤다. 다시 돌린 켬 조건 리허설에서는 계약이 실제로 쓰였고, 유료 실행 전에 이를 확인하는 단계를 실험 스크립트에 넣었다.
- **h2 대조군 기록이 낡아 있었음(제 변경과 무관)**: `b444a5f` 병합이 가져온 감사 스크립트 변경 때문에, 그 뒤로 h2 실행은 모두 `PUBLIC_CONTROL_FROZEN_SOURCE_DRIFT`로 막혀 있었다. 대조군을 다시 돌려(정상 6/6, 결함 52/52, 같은 이미지) 기록을 갱신했다(`8202fd6`). 예전 기록은 `8651d0b`에 있다.
- **전송 검사 고정 해시**: 실행기를 바꾸자 v11 전송 정책 테스트 9개가 실패했다. v11의 실행기 해시를 제자리에서 다시 고정하고 이유를 덧붙였으며, `d076-preserved-repair.json`을 다시 묶었다. 그 뒤 해당 16개 파일의 실패 집합은 변경 전과 같다(24개, 모두 이전부터 있던 실패).
- **검증 장치가 아무것도 실행하지 않음**: zsh에서 파일 목록 변수가 나뉘지 않아, 변경 전후 비교가 테스트 0개를 돌리고 "양쪽 실패 0"을 냈다. 요약 줄을 확인해서 발견했고, 배열로 다시 비교했다.
- **트리 차이**: off-01·off-02는 `8202fd6`, 나머지는 `aa5ff5b`에서 돌았다. 두 트리의 차이는 인터페이스 검증과 리허설 대역뿐이라 끈 조건의 동작은 같다.

```decision-record
{
  "id": "R20261020-INTERFACE-FIRST",
  "goal": "Design an interface-first contract stage and compare it on and off on the h2 held-out task.",
  "owner": "root",
  "status": "complete",
  "next_trigger": "Repeat on and off on h2 and on openapi before claiming an effect; investigate whether the gain comes from repair convergence rather than first-round agreement.",
  "conditions": [
    "h2 held-out task, jev_profile arm, 25 hidden tests; runs strictly sequential, each after a passing free rehearsal of the same clean tree.",
    "off-01, on-01, off-02 at 8202fd6; on-02, off-03, on-03, on-04 at aa5ff5b; the difference only touches the on condition.",
    "Costs are API-equivalent USD; Jev at USD 0.6 per million input tokens; no actual billing."
  ],
  "sources": [
    {"id": "runs", "path": "docs/decisions/evidence/R20261020_interface_first_runs.json", "sha256": "47e362eadf27bb0dc157008dc9b21fc749e3dae785be1f0952799114fdcdcb33"},
    {"id": "contract", "path": "docs/orchestration/contracts/adaptive-interface-first.v1.json", "sha256": "aa9343b4b1ee49623bab404f492e532fedd63c7c68bc8b21e843903abff3d586"},
    {"id": "module", "path": "src/benchmark/adaptive-interface-first.mjs", "sha256": "ebbbab62736742eb6efa13253c7609e154361e2ee793f60788d7d18323d2a3b6"},
    {"id": "controls", "path": "benchmarks/e2e-swe/heldout/h2/public-checks/results/controls.json", "sha256": "632c2232101d3ed260c66b5a772cfaf9f282c460fe8b356aef8a40d1956562cb"}
  ],
  "claims": [
    {"id": "off", "kind": "measured", "text": "Off: product success 1/3 (Wilson 6-79%), first-round public pass 1/3, repair rounds 0/2/2, total USD 20.29, 64.1 min per success.", "source_ids": ["runs"]},
    {"id": "on", "kind": "measured", "text": "On with the contract used: product success 3/3 (Wilson 44-100%), first-round public pass 0/3, one repair round each, total USD 17.31, USD 5.77 and 19.1 min per success; the stage cost 96-146 s and USD 0.27-0.56 per run.", "source_ids": ["runs"]},
    {"id": "itt", "kind": "measured", "text": "On as assigned including on-01 (contract rejected): 3/4 (Wilson 30-95%), USD 8.23 and 28.4 min per success.", "source_ids": ["runs"]},
    {"id": "not_first_round", "kind": "measured", "text": "The stage did not raise first-round public pass (on 0/3 vs off 1/3); every on run recovered in one repair round while both off failures kept failing stream-control-frames or request-response after two rounds.", "source_ids": ["runs"]},
    {"id": "mechanism", "kind": "hypothesis", "text": "The shared contract helps repair workers converge rather than preventing first-round mismatches.", "source_ids": ["runs"]},
    {"id": "not_significant", "kind": "decision", "text": "No effect is claimed: 3/3 vs 1/3 gives two-sided Fisher exact p = 0.40 and overlapping Wilson intervals.", "source_ids": ["runs"]},
    {"id": "validator_defect", "kind": "correction", "text": "on-01 never used its contract because the import-source ownership check rejected module-name and external-package imports; fixed in aa5ff5b and on-01 is excluded from the contract-used comparison.", "source_ids": ["runs", "module"]},
    {"id": "controls_drift", "kind": "measured", "text": "The h2 public control receipt had drifted since b444a5f and blocked every h2 run; controls rerun with normal 6/6 and defective 52/52 on the same image.", "source_ids": ["controls"]}
  ],
  "costs": [
    {"role": "seven paid h2 runs: workers, spec review, interface stage and Jev input tokens (1,030,145)", "basis": "api_equivalent", "usd": 44.99, "source_ids": ["runs"]}
  ],
  "unresolved": [
    "More repetitions and a second task (openapi) before any effect claim.",
    "Mechanism: repair convergence vs first-round agreement is not measured.",
    "The interface stage is research-only; the plugin path does not have it."
  ],
  "side_effects": [
    "Run folders benchmark-runs/h2-iface-{off-01,on-01,off-02,on-02,off-03,on-03,on-04} and rehearsal folders rehearsal-h2-iface-*-20261020-0{1,2,3}; shared ledger settled after each run.",
    "Merged origin/research into the branch (e42e885) for the spend gate; nothing pushed."
  ]
}
```
