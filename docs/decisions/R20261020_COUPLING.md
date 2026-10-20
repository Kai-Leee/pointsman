# R20261020-COUPLING — 서로 import하는 작업 쌍의 처리 방침

사용자 요청: "PR 전에 서로 import하는 작업 쌍을 어떻게 다룰지 먼저 정리해줘."

- 코드: `feat/plan-tools-20261020`의 `7053d41`(결합 분석)과 `92088e4`(지연 import 구분).
- 순서: 커밋한 뒤 기록된 두 실행에 다시 적용했다. 유료 호출은 없다.
- 원시 결과: `evidence/R20261020_plan_tools/*.coupling.json`

## 무엇을 봤나

R20261020-PLAN-TOOLS에서 계획에 없던 import 연결은 openapi에서 20개, h2에서 18개 나왔다. 연결을 그대로 선후 관계로 바꾸면 순환이 되는 쌍이 있었다: openapi의 n2↔n4, n4↔n5, h2의 n2↔n5.

import 줄을 하나씩 확인한 결과, 대부분은 여러 작업이 함께 쓰는 **기반 파일**(diagnostics, ir, naming, config, utilities, errors 등)이 사용하는 쪽 파일과 **같은 작업에 묶여서** 생긴 순환이었다.

## 처리 방침

| 경우 | 판정 | 처리 |
|---|---|---|
| **모듈 수준** import끼리 순환하는 파일들이 서로 다른 작업에 나뉨 | 실행하면 import 시점에 실패할 수 있음 | 실행 전에 같은 작업으로 묶는다 |
| 작업 단위 순환이고, 공용 파일을 첫 작업으로 옮기면 순환이 풀리며, 옮길 파일이 묶음 파일의 절반 이하 | 묶음 방식 때문에 생긴 순환 | 공용 파일을 **먼저 만드는 작업**으로 분리한다 |
| 그 밖의 작업 단위 순환 | 결합이 촘촘함 | 계획은 유지한다. 묶음 안 작업자들에게 공용 파일의 이름과 시그니처를 명세에서 뽑아 **고정 인터페이스**로 준다 |

- 함수 안에서 하는 지연 import(들여쓴 Python import, JS `import()`·`require()`)는 첫 번째 줄의 파일 순환 판정에서 뺀다. 실행 시점에만 불리므로 import 시점 실패를 만들지 않기 때문이다.
- 지연 import도 서로의 인터페이스에 의존한다는 뜻은 같다. 그래서 작업 간 연결과 작업 단위 순환 판정에는 계속 넣는다.
- "절반 이하" 기준은 판단으로 정한 값이며, 측정한 값이 아니다(코드에 shortcut 주석으로 표시함).

## 기록된 실행에 적용한 결과

| | openapi-02 | h2 pilot-04 |
|---|---|---|
| import 연결 중 지연 import | 37개 중 20개 | 26개 중 3개 |
| 작업에 걸친 모듈 수준 파일 순환 | 없음 | 없음 |
| 작업 단위 순환 묶음 | n2, n3, n4, n5, n6 (6개 중 5개) | n2, n5 |
| 공용 파일 / 비율 | 9개 / 27% | `h2/config.py`, `h2/utilities.py` / 33% |
| 첫 작업으로 옮기면 풀림 | 아니오 | 예 |
| 권고 | 계획 유지 + 고정 인터페이스 | 공용 파일 2개를 먼저 만드는 작업 |

## 정정과 중간 결과

- **사용자에게 한 설명의 정정**: 대화에서 "openapi의 파일 단위 순환은 모두 같은 작업 안에 있다"고 말했다. 그때는 두 파일이 서로 import하는 쌍만 확인했다. 실제로는 enums → ir → operations → properties → enums로 이어지는 5개 파일 순환이 n4, n5, n6에 걸쳐 있었다.
- **중간 결과**: 지연 import를 구분하기 전(`7053d41`)에는 도구가 이 5개 파일을 "같은 작업으로 묶어야 함"으로 판정했다.
- **지연 import 구분 후**: 순환의 되돌아가는 쪽 import는 모두 함수 안의 지연 import였다(ir→operations, operations→properties, properties→enums, unions→properties). `92088e4`부터는 모듈 수준 순환으로 보지 않는다.
- **해석(가설)**: 작업자들이 import 순환을 피하려고 일부러 지연 import를 쓴 것으로 보인다. 이 실행은 독립 검사 63/63을 통과했다.

## 한계

- 표본은 성공한 실행 2건뿐이다. 이 방침이 실패를 줄이는지는 측정하지 않았다.
- 새로 만드는 과제에서는 실행 전에 파일이 없어서 import를 훑을 수 없다. 실행 전에 이 판정이 의미가 있는 것은 기존 코드를 고치는 작업이다.
- "먼저 만드는 작업" 분리는 권고만 한다. 계획을 자동으로 고치지는 않는다.

```decision-record
{
  "id": "R20261020-COUPLING",
  "goal": "Decide how the plan tools handle tasks that import each other before the main PR.",
  "owner": "root",
  "status": "complete",
  "next_trigger": "Open the main PR for feat/plan-tools-20261020 when the user asks; later, measure whether interface-first splits or fixed-interface prompts change outcomes on runs outside these two.",
  "conditions": [
    "Code 7053d41 and 92088e4 on feat/plan-tools-20261020, committed before each experiment.",
    "Applied after the fact to completed candidates of two successful runs; offline, no model calls."
  ],
  "sources": [
    {"id": "openapi_coupling", "path": "docs/decisions/evidence/R20261020_plan_tools/openapi-partial-repair-02.coupling.json", "sha256": "d41110c8deb6f389801180163f51a86295c278ef30a5f3f7bf9095f647c21d23"},
    {"id": "h2_coupling", "path": "docs/decisions/evidence/R20261020_plan_tools/heldout-h2-pilot-04.coupling.json", "sha256": "34ee378ebbc112e46ae1e962e1bc0288f1d83b283ca8fc7d71c7384671d65a9c"}
  ],
  "claims": [
    {"id": "policy", "kind": "decision", "text": "Load-time file cycles split across tasks are regrouped; task cycles that a first task with at most half the group's files would break get an interface-first task; other task cycles keep the plan with fixed interfaces. Lazy imports are excluded from file-cycle detection but kept for task links.", "source_ids": ["openapi_coupling", "h2_coupling"]},
    {"id": "openapi", "kind": "measured", "text": "openapi-partial-repair-02: 20 of 37 import edges lazy; no load-time file cycle across tasks; task cycle n2-n6 with 9 shared files (27%) that a first task would not break; advice is fixed interfaces.", "source_ids": ["openapi_coupling"]},
    {"id": "h2", "kind": "measured", "text": "heldout-h2-pilot-04: 3 of 26 import edges lazy; no load-time file cycle; task cycle n2-n5 broken by a first task with h2/config.py and h2/utilities.py (33%).", "source_ids": ["h2_coupling"]},
    {"id": "verbal_correction", "kind": "correction", "text": "The earlier statement that openapi file cycles all sit inside one task checked only mutual pairs; a five-file cycle spanned n4, n5 and n6, and all its back edges were lazy imports.", "source_ids": ["openapi_coupling"]},
    {"id": "lazy_cause", "kind": "hypothesis", "text": "Workers used function-level imports to avoid load-time cycles across tasks.", "source_ids": ["openapi_coupling"]}
  ],
  "costs": [],
  "unresolved": [
    "Whether either advice improves outcomes is unmeasured.",
    "The half-of-files threshold is a judgment line.",
    "Pre-execution scan only applies to edits of existing code."
  ],
  "side_effects": [
    "New evidence files *.coupling.json; commits 7053d41, 1e0741d and 92088e4 on feat/plan-tools-20261020, not pushed."
  ]
}
```
