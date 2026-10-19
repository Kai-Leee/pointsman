# R20261018-DESIGN-SELECTION — 반복되는 실행 경로 결함의 원인과 재설계안 선정

사용자 요청: "1. 원인 분석 2. 해당 원인을 직접적으로 수정을 해야하는건가? 3. 수정 후에도 동일한 원인이 반복된다면 이건 설계 문제 아닌가? 4. 더 좋은 설계안을 에이전트 3개에게 새로 만들게 진행. 5. 그 중 더 좋은 설계안을 추리기"

자료는 [design-20261018](../orchestration/design-20261018/)에 있다. 문제 정리(brief), 설계안 3개, 블라인드 판정, 익명 표지 대응표다. 이번 작업에서 제품 코드는 고치지 않았다.

## 1. 원인

결함 하나하나의 원인은 숨은 가정 7개다.
- 수리 전에 모든 작업이 실행됐다.
- 제공자 모델 ID가 고정돼 있다.
- 과제 이미지는 Python 3.11 이상이다.
- 장부에는 상한이 있다.
- CLI 버전이 고정돼 있다.
- 과제는 openapi 하나뿐이다.
- 비교 조건은 하나로 고정된다.

이 결함들이 반복된 구조적 원인은 세 가지다.
- **한 과제·한 환경만으로 개발하고 검증했다.** 모의 테스트가 바로 그 경계를 꾸며서 가린다. 예를 들어 `test/d080-defaults-mock-arm.test.mjs:42,73`은 모델 ID를 `jev-1.13.0`으로 고정하고 모든 검사를 `passed`로 돌려준다.
- **수정이 한 줄기로 모이지 않았다.** 결함 7개 가운데 3개는 이미 다른 곳에 수정이 있었다.
  - 부분 실행 수리: 10-15 작성, 미커밋.
  - Jev 1.14 정산: D086 브랜치, 미커밋.
  - tomli 대체: 다른 모듈에 10-12부터 있었음.
  - 연구 기록은 `origin/research`, `research-d095-final-20261017`, `feat/heldout-eval-20261018` 세 갈래로 나뉘어 있다.
- **결함이 유료 실행에서야, 그것도 하나씩 드러난다.** `--spend` 경로는 `preflightAdaptiveComparison`을 거치지 않는다([adaptive-dag-comparison.mjs:26](../../scripts/adaptive-dag-comparison.mjs)). 종료 원인을 분류하지 않기 때문에 잘못된 원인 판단도 생겼다(n1을 Haiku 탓으로 기록).

## 2–3. 직접 수정만으로 충분한가, 설계 문제인가

직접 수정은 필요하지만 충분하지 않다. 성공하지 못한 arm 41개 중 30개(73%)가 결과물 품질이 아니라 실행 경로·환경·인프라 원인으로 멈췄다. 그러니 이것은 설계 문제로 다룬다.

## 4–5. 설계안과 선정

세 에이전트가 각자 다른 출발점에서 완전한 설계안을 썼다.
- A: 명시적 환경 계약
- B: 무과금 전체 리허설
- C: 단일 줄기와 실패 원인 분류

판정 에이전트에게는 작성자 표지를 지우고 순서를 섞어(X=C, Y=A, Z=B) 넘겼다. 판정 기준과 가중치는 판정 전에 고정했다. 판정 에이전트는 각 안의 인용 근거를 직접 확인한 뒤 채점했다.

| 안 | 가중 합계(70점 만점) | 주요 감점 |
| --- | --- | --- |
| Z = B 리허설 | **58** | 비용(과제당 Docker 10–30분), 분류 완전성 검사 없음 |
| Y = A 계약 | 56 | 모르는 모델을 요청 모델 배율로 정산(안전 규칙 위반) |
| X = C 단일 줄기 | 48 | 핵심 장치가 유료 경로에서 실행되지 않음(인용 오류), 모르는 모델을 추정 배율로 정산하고 계속 진행 |

**선정: B(무과금 리허설).** 유료 경계 두 곳(Claude 추론, Jev POST)만 가짜로 대체한다. 나머지인 실제 과제 이미지, readiness 검사, 공개 검사, 정산 코드(장부 복사본 사용)는 끝까지 실제로 돌린다. 그래서 목록에 없는 가정도 잡을 수 있다. 안전 규칙 위반이 없는 유일한 안이다.

**A에서 B로 합칠 것:**
1. 유료 경로에 단일 줄기 검사를 추가한다(`SOURCE_NOT_ON_MAINLINE`). 병합되지 않은 브랜치와 작업 폴더의 미커밋 변경을 훑어서, 다른 곳에 있는 수정을 찾아낸다.
2. 모든 `fail()` 코드와 장부 오류 코드에 원인 분류가 있어야 한다는 완전성 테스트를 둔다(프로토콜 v2).
3. 공통 함수를 하나로 합친다. readiness 검사 코드를 하나로, 장부 용량 검사를 `budget.mjs`의 한 함수로.

**받아들이지 않는 것:** 모르는 모델 ID를 추정 배율로 정산하는 것(X, Y), 작업 폴더를 삭제하는 정리(X), 다른 세션의 미커밋 파일을 일괄 커밋하는 것(Z의 salvage는 조율이 필요하다).

```decision-record
{
  "id": "R20261018-DESIGN-SELECTION",
  "goal": "Find why paid runs keep stopping on pipeline defects and select a redesign by independent proposals and blind judging.",
  "owner": "root",
  "status": "complete",
  "next_trigger": "User approval to build the merged design (rehearsal + mainline sweep + attribution completeness + shared helpers) before any further paid run.",
  "conditions": [
    "Three general-purpose agents wrote proposals from the same brief with different starting emphases; none modified the repository.",
    "One separate judge scored anonymized, shuffled proposals on weights fixed beforehand and spot-checked citations; root re-verified the four load-bearing checks.",
    "No paid call, Docker run or product code change in this record."
  ],
  "sources": [
    {"id": "brief", "path": "docs/orchestration/design-20261018/brief.md", "sha256": "f4ab24bb398fbac8ba1d902a321d64cfa09ca3636dd04f21d0e6a868c5aa34bb"},
    {"id": "proposal_a", "path": "docs/orchestration/design-20261018/proposal-A-contracts.md", "sha256": "85c2653420ef0c2e40d68a211d5b60c236fe7ce92004bf98397cfeba51c97de9"},
    {"id": "proposal_b", "path": "docs/orchestration/design-20261018/proposal-B-rehearsal.md", "sha256": "a48fd04ff0503481f4b61c2053b65dc1eb3fe8666dba95f38a50c99750e9c124"},
    {"id": "proposal_c", "path": "docs/orchestration/design-20261018/proposal-C-mainline.md", "sha256": "d7fb248315c8cc85d1a9e5ef7633e322026aa30d56aed3d26792e7fd04d6e069"},
    {"id": "verdict", "path": "docs/orchestration/design-20261018/verdict-blind.md", "sha256": "1c84dc92b32a6fea0187cce4fa7ccd43e3de6f45134fef6eb3ebcc1636b9cfa1"},
    {"id": "mapping", "path": "docs/orchestration/design-20261018/blind-mapping.md", "sha256": "9016e82e157fef4c393dab70bbb03edaf2ed29e60e8ee4ded5e5e2de2fb11ace"},
    {"id": "spend_path", "path": "scripts/adaptive-dag-comparison.mjs", "sha256": "ffd4a490945771a44002923af1430a6b205ba6d87b1db0f2d71e5f0ef1212b23"},
    {"id": "mock_test", "path": "test/d080-defaults-mock-arm.test.mjs", "sha256": "944d8e557909d33efeff944ae7c4eebb26391e85eab609d63780fe7df6815907"},
    {"id": "dag_runner", "path": "src/benchmark/dag-runner.mjs", "sha256": "87ae7e61718d64659eb6d919dca4e619bfb241ebb6c542f0b3980e7437ef9301"},
    {"id": "adaptive_runner", "path": "src/benchmark/adaptive-dag-runner.mjs", "sha256": "1aa22d5f5f481687c6d010835a96dc54b5a9e677d65b8122514582ce3d2ee76a"}
  ],
  "claims": [
    {"id": "stop_share", "kind": "measured", "text": "Of 57 arms (local plus sibling worktrees), 41 did not succeed; 29 ended with pipeline/infra/policy stop codes, 30 including pilot-03's harness-caused ARTIFACT_CHECK_NOT_PASSED (73%).", "source_ids": ["brief"]},
    {"id": "fix_elsewhere", "kind": "measured", "text": "3 of the 7 recent defects already had fixes outside the line being run (partial repair, Jev 1.14 settlement, tomli fallback).", "source_ids": ["brief"]},
    {"id": "spend_skips_preflight", "kind": "measured", "text": "scripts/adaptive-dag-comparison.mjs calls preflightAdaptiveComparison only when not spending; a gate placed there would not run on --spend.", "source_ids": ["spend_path"]},
    {"id": "mock_hides_boundaries", "kind": "measured", "text": "The d080 mock-arm test fixes the Jev model to jev-1.13.0 and returns passed for every check, hiding the boundaries where defects 2 and 3 lived.", "source_ids": ["mock_test"]},
    {"id": "duplication", "kind": "measured", "text": "The readiness program and the ledger-capacity rule each exist in two copies (dag-runner.mjs:48/:169 and adaptive-dag-runner.mjs:701/:666).", "source_ids": ["dag_runner", "adaptive_runner"]},
    {"id": "scores", "kind": "measured", "text": "Blind weighted totals out of 70: rehearsal (Z=B) 58, contracts (Y=A) 56, mainline/register (X=C) 48.", "source_ids": ["verdict", "mapping"]},
    {"id": "selection", "kind": "decision", "text": "Select the rehearsal design B, merged with A's mainline sweep blocker, stop-code attribution completeness test and single shared readiness/ledger helpers; reject guessed-multiplier settlement and worktree deletion.", "source_ids": ["verdict", "proposal_a", "proposal_b"]},
    {"id": "residual", "kind": "hypothesis", "text": "A rehearsal with faked paid boundaries still cannot catch provider behaviour that appears only on a real POST (e.g. a new dated build first seen in a response); those stops stay fail-closed with offline reconciliation.", "source_ids": ["proposal_b", "verdict"]}
  ],
  "costs": [],
  "unresolved": [
    "Building the merged design is not started; estimated ~500 lines plus tests per proposal B, unmeasured.",
    "Consolidating the three research lines and the main checkout's ~100 uncommitted files needs coordination with the sessions that own them.",
    "Rehearsal Docker time per task (10-30 min) is the proposal's estimate, not measured."
  ],
  "side_effects": [
    "New docs under docs/orchestration/design-20261018/ and this record; scratchpad copies remain."
  ]
}
```
