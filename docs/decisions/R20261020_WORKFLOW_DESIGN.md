# R20261020-WORKFLOW-DESIGN — Pointsman을 Claude Code Workflow 스크립트로 옮기는 설계 검토

사용자 요청: "영상보다 먼저 Pointsman을 Claude Code Workflow 스크립트로 옮기는 설계를 검토해줘." 이어서 "이 검토를 결정 기록 문서로 저장해줘."

계기: 한 Instagram 릴스가 "Opus가 계획하고, Haiku가 훑고, Sonnet이 고치고, 검증 에이전트가 거르고, JEV가 경로를 정한다"는 Workflow 구성을 소개했다. 이 문서는 그 구성을 Pointsman에 적용할 수 있는지 검토한 설계 판단이다.

- 코드는 바꾸지 않았고, Workflow 실행이나 유료 호출도 없었다.
- Workflow 제약은 Workflow 작성 문서를 읽고 정리한 것이며 실측하지 않았다.
- 코드 근거는 이 브랜치의 `a4f820f` 기준이다.

## 결론

**실험 실행기(Node)는 유지한다. Workflow는 제품용 실행 모드로 따로 만든다(혼합안).** 실행기를 Workflow로 통째로 옮기면 지금의 평가 신뢰성이 깨진다. 깨지는 것은 작업자 격리, 무료 리허설, 작업자별 비용 측정이다.

## Workflow 제약과 영향

| Workflow 제약 | Pointsman에 주는 영향 |
|---|---|
| 스크립트 안에서는 파일·Node·HTTP를 쓸 수 없고 `agent()`만 일을 함 | Jev POST, Docker 검사, 장부를 스크립트에서 직접 할 수 없다. 에이전트나 MCP 도구가 대신 실행해야 한다 |
| `agent()`는 세션 CLAUDE.md를 주입받고, 기본으로 모든 도구를 가짐 | 가장 큰 위험이다. 지금 작업자는 `--tools ''`, `--setting-sources ''`로 실행하고 MCP 허용 경로에만 쓴다(`adaptive-dag-runner.mjs` 392행). Workflow 작업자는 Bash로 `benchmark-runs/`의 과거 성공 후보나 과제 이미지 안의 숨김 검사에 닿을 수 있다 |
| `agent()` 실패는 예외가 아니라 `null` | 실패하면 멈추는 동작을 스크립트가 매번 직접 검사해야 한다 |
| `Date.now()` 사용 불가, `budget.spent()`는 출력 토큰만 셈 | 시간과 비용은 CLI 쪽에서 측정해야 한다. 작업자별 Claude 비용을 받을 수 있는지는 미확인이다 |
| 재개할 때 끝난 `agent()`는 캐시를 쓰고, 중단된 것은 다시 실행 | 결과가 불확실한 Jev POST가 다시 나갈 수 있다. 장부의 pending 예약 검사를 CLI 안에 유지해야 한다 |
| 동시 실행 상한은 min(16, CPU−2) | 임계 경로 우선과 2슬롯 실행은 스크립트에서 대기열로 직접 구현해야 한다 |
| 작업자를 가짜로 바꿀 수 없음 | 무료 리허설 B(`rehearsal.mjs`의 `runCommand` 교체)를 그대로 쓸 수 없다 |

## 잘 맞는 부분

- **Jev 프로필이 `agent()` 옵션에 1:1로 대응한다.** 20개 프로필은 모델 × 추론 수준이고, `agent()`도 `{model, effort}`를 받는다.
- **수리 최대 2회**는 스크립트 반복문으로 바로 표현된다.
- **`isolation: 'worktree'`** 는 병렬 편집 충돌을 막는다. 쓰기 범위 제한까지 대신해 주지는 않는다.
- **재개 저널**은 지금 없는 "중단 후 이어서 실행"을 제공한다.
- **검증**은 LLM 검증자 대신 기존 공개 검사 CLI를 쓰면 결정적 검증이라는 장점이 유지된다.

## 권하는 구조

| 단계 | 담당 | 비고 |
|---|---|---|
| Jev 판단(분해·담당·프로필·수리 담당) | 새 MCP 도구 `pointsman_decide`. 내부는 기존 `budget.mjs`, 토큰 사전 검사, 장부를 사용 | 지금 있는 MCP 서버는 작업자용 `artifact-transport.mjs`뿐이다 |
| 작업 실행 | `pipeline()` + `agent({model, effort, isolation:'worktree'})` | 모델과 추론 수준에 Jev 답을 그대로 넣는다 |
| 로컬·공개 검사 | 에이전트가 기존 검사 CLI를 실행하고 결과 파일의 해시를 반환 | 에이전트가 결과를 옮겨 적지 않는다 |
| 수리 루프(최대 2회) | 스크립트 | 부분 수리는 판단 호출 0회로 유지한다 |
| 최종 확인 | 메인 세션 | 검사를 통과한 결과만 본다 |
| 숨김 채점 | Workflow 밖, 지금과 동일 | 계획·수리에 숨김 검사를 넣지 않는다 |

- 이 모드는 사용자 저장소 작업용이다. 벤치마크 수치는 계속 Node 실행기로만 낸다.
- Workflow 모드를 평가할 때는 별도 조건(arm)으로 추가하고, 기존 조건을 대체하지 않는다.

## 후속 실험: 작업자 격리 확인 (2026-10-20, 커밋 `5e6f4aa` 이후)

사용자 지시 "항상 커밋 -> 실험을 유지 할 것"에 따라 기록과 실험 정의를 먼저 커밋(`5e6f4aa`)한 뒤 실행했다.

- **방법**: Agent 도구, 모델 haiku, 세 유형에 같은 질문 세 줄. 답은 작업자의 자기 보고이고 파일은 읽게 하지 않았다.
- **원시 결과**: `docs/decisions/evidence/R20261020_worker_probe.json`

| 작업자 유형 | 실행 여부 | 셸(Bash) | CLAUDE.md 주입 | 비고 |
|---|---|---|---|---|
| `pointsman-probe`(직접 정의, `tools: Glob`) | **찾지 못함** | — | — | 정의 파일이 이 worktree에만 있고, 세션은 main checkout에서 시작함. 세션 도중에 다른 폴더의 `.claude/agents`는 읽지 않음 |
| `Explore`(내장) | 실행됨 | **있음** | 없음 | "읽기 전용"이지만 Bash와 Read가 있어 `benchmark-runs/`에 닿을 수 있음 |
| `general-purpose`(내장) | 실행됨 | 있음 | 있음 | Edit·Write·Agent까지 모두 가짐 |

해석:

1. CLAUDE.md 주입을 끄는 것(Explore)과 도구를 막는 것은 별개다. 내장 유형 중에는 둘을 동시에 만족하는 것이 없다.
2. 도구 제한이 실제로 지켜지는지는 여전히 미확인이다. 정의 파일을 세션이 찾지 못해 실행 자체가 되지 않았다.

다음 확인은 `feat/heldout-eval-20261018` worktree에서 새로 시작한 세션에서 `pointsman-probe`를 다시 실행하는 것이다.

```decision-record
{
  "id": "R20261020-WORKFLOW-DESIGN",
  "goal": "Decide whether and how to move Pointsman onto Claude Code Workflow scripts without losing evaluation integrity.",
  "owner": "root",
  "status": "complete",
  "next_trigger": "Rerun the pointsman-probe agent from a session started in the feat/heldout-eval-20261018 worktree to test whether a custom agentType restricts tools and whether CLAUDE.md is injected; only then prototype pointsman_decide as an MCP tool on one small task as a separate condition.",
  "conditions": [
    "Design review only: no code change, no Workflow run, no paid call.",
    "Workflow constraints taken from the workflow-authoring reference, not measured.",
    "Code evidence at commit a4f820f on feat/heldout-eval-20261018."
  ],
  "sources": [
    {"id": "runner", "path": "src/benchmark/adaptive-dag-runner.mjs", "sha256": "b7393483225dd3fbc55ef45f417ca54bc17eb979e7b0547bd8a7cc64af73c387"},
    {"id": "transport", "path": "src/orchestration/artifact-transport.mjs", "sha256": "5bdaead0cfec2b4c2b8c008a221f8d3591086cb7b550147060cf1c041ce100c2"},
    {"id": "grader", "path": "scripts/grade-adaptive-arm.mjs", "sha256": "89ef8f0f50114e8a3ba32b2b6f83b3eee78ddea87d5362b01c1487ccacdae6ce"},
    {"id": "rehearsal", "path": "src/benchmark/rehearsal.mjs", "sha256": "3dfe23d11813705f2e9c71c3a663529214a3819bc3ec05b1557454a07f0d3767"},
    {"id": "probe_def", "path": ".claude/agents/pointsman-probe.md", "sha256": "008de0047e43e444e5f1ec1b230c16a519a0677d06001f726469643166e2be32"},
    {"id": "probe_result", "path": "docs/decisions/evidence/R20261020_worker_probe.json", "sha256": "9e9602bfb46776034102ae8843b38049064b19b17740a431e0e953a2ec015cd4"}
  ],
  "claims": [
    {"id": "hybrid", "kind": "decision", "text": "Keep the Node experiment runner as the only measured path; add a Workflow mode for product use, wrapping Jev decisions in an MCP tool; evaluate it only as a separate condition.", "source_ids": ["runner", "transport"]},
    {"id": "isolation_risk", "kind": "hypothesis", "text": "Default workflow agents with Bash and injected CLAUDE.md could read prior candidates under benchmark-runs or hidden tests in the task image, unlike current workers launched with --tools '' and --setting-sources ''.", "source_ids": ["runner", "grader"]},
    {"id": "rehearsal_loss", "kind": "hypothesis", "text": "Rehearsal B cannot double workflow agents because it replaces runCommand, so a Workflow mode loses the zero-cost rehearsal gate unless a new double is designed.", "source_ids": ["rehearsal"]},
    {"id": "profile_map", "kind": "decision", "text": "Jev model/effort profiles map directly onto agent() model and effort options.", "source_ids": ["runner"]},
    {"id": "agent_type_unknown", "kind": "unknown", "text": "Whether a custom agentType can restrict tools to the artifact MCP write tool and omit CLAUDE.md injection is untested.", "source_ids": []},
    {"id": "probe_not_found", "kind": "measured", "text": "The pointsman-probe definition committed in this worktree was not found by the Agent tool of a session started in the main checkout, so tool restriction could not be exercised.", "source_ids": ["probe_def", "probe_result"]},
    {"id": "probe_builtin", "kind": "measured", "text": "Self-reports under haiku: Explore had Bash and Read without project instructions; general-purpose had Bash, Edit, Write and Agent with project instructions. No built-in type both lacks a shell and omits CLAUDE.md.", "source_ids": ["probe_result"]},
    {"id": "cost_unknown", "kind": "unknown", "text": "Whether per-worker Claude cost or token usage is recoverable from workflow agents is untested.", "source_ids": []}
  ],
  "costs": [],
  "unresolved": [
    "Custom agentType tool restriction and CLAUDE.md suppression test: definition not found from a main-checkout session; rerun from a worktree-started session.",
    "Per-worker cost capture in workflow agents.",
    "A rehearsal double for workflow agents.",
    "pointsman_decide MCP tool does not exist yet."
  ],
  "side_effects": [
    "Record and probe definition committed as 5e6f4aa before the probe; probe evidence committed at docs/decisions/evidence/R20261020_worker_probe.json; three haiku subagent runs."
  ]
}
```
