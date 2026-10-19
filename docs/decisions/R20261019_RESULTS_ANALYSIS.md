# R20261019-RESULTS-ANALYSIS — 실제 유료 실행 결과 분석

사용자 요청: "4번을 진행하고 나서 실제 결과를 분석해줘"

이 문서는 브랜치 통합(병합 커밋 `b444a5f`) 이후에 작성했다. 분석 대상은 이 Mac에 원본이 남아 있는 전체 개발 arm이고, 리허설은 빼고 셌다. 리허설은 가짜 응답으로 돌기 때문에 제품 시도가 아니다. 보고 스크립트도 이제 리허설을 제외한다(`scripts/harness-style-report.mjs`).

다음 실행은 분석에서 제외했다.
- 환경 문제나 사용자 중단으로 멈춘 실행: `BUDGET_LOCKED`, `ADAPTIVE_CANCELLED` 등 3건.
- 클라우드에서 돌린 D082–D085: 원본이 이 Mac에 없다. 문서상 수치는 5/7, 2/3, 2/3이다.

## openapi (튜닝 과제, 숨김 독립 검사 63개)

| 조건 | 성공 / 시도 | Wilson 95% | 성공 1회 평균 시간 | 성공 1회 평균 Claude 비용(API 환산) | 실패 포함 총비용 ÷ 성공 | 실패 포함 총시간 ÷ 성공 |
| --- | --- | --- | --- | --- | --- | --- |
| Claude 단독 (`claude_all`) | 3/3 | 44–100% | 38.3분 | $19.83 | $19.83 | 38.3분 |
| Jev 전체 시기 | 11/23 | 29–67% | 31.9분 | $9.37 | $16.96 | 51.9분 |
| Jev 현재 경로 (D079 이후 `jev_profile`, 오늘 포함) | 4/9 | 19–73% | 27.5분 | $7.89 | $18.73 | 57.5분 |

- **성공한 실행만 보면** Jev가 더 빠르고 싸다. 현재 경로 기준으로 시간은 28% 짧고 Claude 비용은 60% 적다. Jev 토큰 비용은 성공 1회당 약 $0.13이다.
- **실패까지 포함하면** 성공 1회당 비용은 Claude 단독과 비슷하고($18.73 대 $19.83), 시간은 더 길다(57.5분 대 38.3분). 성공률이 낮기 때문이다.
- **같은 실행 안의 비교**는 3번뿐이다.
  - D067: 네 조건 모두 성공. Jev 조건이 25.9–33.7분·$8–10으로 Claude 단독(36.3분·$21.1)보다 빠르고 쌌다.
  - D066: Jev 조건이 토큰 한도에서 멈췄다.
  - D071: Jev 조건이 독립 검사에서 실패했다(60/63, 49/63).
- 서로 다른 날짜, 설정, CLI 버전의 실행을 묶은 비교라 같은 조건의 대조 실험이 아니다. 구간이 겹치므로 성공률 차이는 통계적으로 확정되지 않는다.

## h2 (보류 과제, 숨김 검사 25개)

- 1/4 성공(Wilson 5–70%).
- 실패 3건은 모두 실행 경로 결함이었다.
  - 1회: 부분 실행 뒤 수리 binding
  - 2회: Jev 1.14 정산
  - 3회: Python 3.10 TOML 검사
- 결함을 고친 뒤 무료 리허설을 통과하고 돌린 4회째에 공개 검사와 독립 검사 25/25를 통과했다(19.6분, Claude $3.89, Jev 86,365토큰).
- Claude 단독 기준 실행은 없다.

## 해석

1. **무료 리허설 관문 이후 실행은 2/2 성공했다**(h2 pilot-04, openapi-partial-repair-02). 관문 전 오늘 실행은 0/4였다(h2 01–03, openapi-01). 표본이 작아 일반화할 수 없지만, 실행 경로 결함을 유료 실행 전에 걸러낸다는 설계 의도와 맞는 결과다.
2. **Jev의 효율 이점은 "성공했을 때"에만 있다.** 지금 병목은 판단 품질보다 끝까지 완주하는 비율이다. 실패 원인 다수는 실행 경로·검사·입력 크기 쪽이었다(R20261018-DESIGN-SELECTION의 73%).
3. **"Jev가 더 효과적"이라는 주장은 아직 근거가 없다.** 근거를 만들려면 같은 실행에 Claude 단독 조건을 붙이고 조건당 3회 이상 반복해야 한다.

## 통합 결과 (요청 4번)

- `research-d095-final-20261017`(D087–D095)을 이 브랜치에 병합했다(`b444a5f`, 충돌 15개 해결).
- 같은 이름으로 따로 만들어진 토큰 사전 검사 v5 두 개는 이렇게 정리했다. 실행 증거가 묶인 쪽(이 브랜치의 jev-1.14)은 v5로 두고, D088 쪽은 v6으로 옮겼다.
- 테스트: 1,600/1,675 통과, 실패 24, 건너뜀 51.
  - 실패 24개는 모두 D095 쪽 커밋(5a36ab6)에서도 실패한다.
  - 그중 7개는 병합 전 이 브랜치에서는 통과하던 것이다. 예전 openapi manifest(d076–d085)가 D094의 런타임 변경 때문에 카탈로그 재사용을 거부당한다. 지금 쓰는 manifest(h2 v12, openapi-partial-repair-v12)는 정상적으로 로드된다.
- 새 트리이므로 다음 유료 실행 전에 리허설을 다시 돌려야 한다.

```decision-record
{
  "id": "R20261019-RESULTS-ANALYSIS",
  "goal": "Analyse all locally recorded real full-development arms after consolidating the research lines.",
  "owner": "root",
  "status": "complete",
  "next_trigger": "Add a same-run Claude-only baseline condition and repeat each condition at least 3 times before claiming Jev effectiveness; rehearse the merged tree before any paid run.",
  "conditions": [
    "Local raw arms only; rehearsals and infrastructure/user stops excluded; D082-D085 cloud raw absent.",
    "Costs are Claude API-equivalent plus Jev input tokens at USD 0.6/M; no actual billing.",
    "Arms span different dates, configurations and CLI versions; only D066/D067/D071 are same-run pairs."
  ],
  "sources": [
    {"id": "runs", "path": "benchmark-runs/results-analysis-20261019/runs-table.json", "sha256": "bb3e9fb7b255bd161ad9ccd6d2a370b4c64edf60944ff675439f75179265e66f"},
    {"id": "report", "path": "benchmark-runs/results-analysis-20261019/report.md", "sha256": "9d98d5eea6cdb0aadd64a275fae77a2c88514dbcc329a57d75371d563764fecc"},
    {"id": "report_json", "path": "benchmark-runs/results-analysis-20261019/report.json", "sha256": "8d8e15fd8004652f60eb91cf831083d70377b9f34282584d2dc3cddecffd2f14"}
  ],
  "claims": [
    {"id": "openapi_claude", "kind": "measured", "text": "openapi Claude-only 3/3 (Wilson 44-100%), mean 38.3 min and USD 19.83 Claude API-equivalent per success.", "source_ids": ["runs"]},
    {"id": "openapi_jev_current", "kind": "measured", "text": "openapi Jev current path 4/9 (Wilson 19-73%); successes mean 27.5 min and USD 7.89; all attempts USD 18.73 and 57.5 min per success.", "source_ids": ["runs"]},
    {"id": "openapi_jev_all", "kind": "measured", "text": "openapi Jev all eras 11/23 (Wilson 29-67%); successes mean 31.9 min and USD 9.37; all attempts USD 16.96 and 51.9 min per success.", "source_ids": ["runs"]},
    {"id": "h2", "kind": "measured", "text": "h2 held-out Jev 1/4; the three failures were harness defects; pilot-04 passed public and independent 25/25 in 19.6 min, Claude USD 3.89, Jev 86,365 tokens.", "source_ids": ["runs"]},
    {"id": "after_gate", "kind": "measured", "text": "Paid runs after the rehearsal gate: 2/2 product success (h2 pilot-04, openapi-partial-repair-02); paid runs before it today: 0/4.", "source_ids": ["runs"]},
    {"id": "not_established", "kind": "decision", "text": "Jev superiority over Claude-only is not established: success-only efficiency gains vanish per success once failed attempts are counted, and condition intervals overlap.", "source_ids": ["runs", "report"]}
  ],
  "costs": [],
  "unresolved": [
    "No same-run Claude-only baseline on the current path or on held-out tasks.",
    "7 tests for historical openapi manifests fail after the merge because D094 runtime edits are outside their catalog-reuse allowlists.",
    "Public-control receipts are stale against D095's audit script (PUBLIC_CONTROL_FROZEN_SOURCE_DRIFT for codex-e2e checks)."
  ],
  "side_effects": [
    "harness-style-report excludes rehearsal arms; evidence saved under benchmark-runs/results-analysis-20261019."
  ]
}
```
