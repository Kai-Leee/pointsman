# R20261018-HELDOUT-PILOT — 보류 과제 h2 시범 1회

사용자 요청: "1단계 반복 3회 말고 과제 1에 1회 반복 먼저 진행하고 확인할 것. 브랜치는 너가 잘 다시 정리해줘." 범위는 Claude만이다(2026-10-18 결정).

브랜치 `feat/heldout-eval-20261018`은 `origin/research`(5f9b668)를 기준으로 한다. 여기에 평가 프로토콜, 보류 과제 준비, 실행기 일반화를 3-way 병합으로 옮겼다. 다른 세션의 미커밋 pointsman/Codex 변경은 옮기지 않았다.

**실행 장소와 조건**
- 실행 장소는 Mac이다. 사용자가 이 세션에서 실행을 지시했고, 유료 실행은 사전 승인 상태다. 원본 장부는 메인 체크아웃의 `benchmark-runs/jev-usd1-budget.json`을 심볼릭 링크로 공유했다.
- 현재 기본 경로(v8 이상) manifest는 `jev_profile` 조건 하나만 허용한다. 그래서 같은 실행 안의 Claude 단독(`claude_all`) 비교는 하지 않았다.
- 고정 CLI 2.1.293이 설치돼 있지 않아 2.1.299를 PATH 앞에 두고 실행했다. 실행기는 CLI 버전을 기록만 하고 일치 여부는 검사하지 않는다.

**결과**
- 실행은 855.6초 뒤 `repair_owners` 단계에서 `ADAPTIVE_INFERRED_ARTIFACT_BINDING`으로 멈췄다. 공개 검사는 0회 실행됐고 수리도 0회다.
- 원인 순서:
  1. Jev가 n1에 `claude_haiku55_low`를 골랐다. n1의 결과물이 준비 검사를 통과하지 못했다(`ARTIFACT_CHECK_NOT_PASSED`).
  2. n1에 의존하는 n3과 공개 검사가 실행되지 않았다.
  3. 수리 담당 선택은 모든 산출물에 버전이 있어야 진행되는데(`adaptive-inferred-repair.mjs:102`), 일부만 실행된 상태라 binding 오류로 멈췄다.
- 같은 종료 코드는 D086 `jev_all`과 Codex Mac 비교의 Jev 실행에도 있었다. 이번까지 3번째다.

```decision-record
{
  "id": "R20261018-HELDOUT-PILOT",
  "goal": "Run one held-out pilot (h2, one jev_profile arm, Claude workers) to check the Jev full-development path on a task it was not tuned on. Rerun 02 enables partial_repair local-readiness-v1. Rerun 03 adds Jev 1.14 settlement.",
  "owner": "root",
  "status": "complete",
  "next_trigger": "Run h2 once more on ddbf44d (partial repair, Jev 1.14 settlement and the Python 3.10 TOML readiness fix all in); only then does a run measure Jev rather than harness defects.",
  "conditions": [
    "One sample, one task (h2), one arm (jev_profile); not a comparison and not a success-rate estimate.",
    "Catalog prepared fresh for h2 (heldout-h2-catalog-01); D083-derived v12 policies; Claude-only profiles.",
    "Shared ledger reused by absolute path through a symlink; no reset, no automatic retry.",
    "Claude CLI 2.1.299 used; manifests still record the historical 2.1.293 pin."
  ],
  "sources": [
    {
      "id": "catalog",
      "path": "benchmark-runs/heldout-h2-catalog-01/result.json",
      "sha256": "bf49bbdfdca9020afadc0564471d26e6ecfb8ea4d9e7c04071c2492bacd9b433"
    },
    {
      "id": "arm",
      "path": "benchmark-runs/heldout-h2-pilot-01/jev_profile/result.json",
      "sha256": "2854bd2082c5af80d9affbb7600bf0e010f4c87ae83f75bea9af6d67d3b6c203"
    },
    {
      "id": "execution",
      "path": "benchmark-runs/heldout-h2-pilot-01/jev_profile/adaptive-execution/result.json",
      "sha256": "161fadc88fc2287736fdca7ae397b1fb340fd52e860a8d087f5bef93a65a6a70"
    },
    {
      "id": "events",
      "path": "benchmark-runs/heldout-h2-pilot-01/jev_profile/events.jsonl",
      "sha256": "1635f5a86156b2bbf2380f26f85a7a38d042e3d8d06596febb6f0f1d7f005415"
    },
    {
      "id": "report",
      "path": "benchmark-runs/heldout-h2-pilot-01/report.md",
      "sha256": "29170e535fcb8a962b29723407c6ccfc0d5e4294eb74dd1ed221cc40e4ad3678"
    },
    {
      "id": "run02_arm",
      "path": "benchmark-runs/heldout-h2-pilot-02/jev_profile/result.json",
      "sha256": "6e2fbf678942109465480f5c15727a980f7b7181d408a2ec7bca904ce8fd272a"
    },
    {
      "id": "run02_events",
      "path": "benchmark-runs/heldout-h2-pilot-02/jev_profile/events.jsonl",
      "sha256": "738d9bc875239ca28ee612eb08f6c2c0824bb2f7445d9aff760986b555f0a621"
    },
    {
      "id": "run02_reconcile",
      "path": "benchmark-runs/heldout-h2-pilot-02/reconciliation-applied/audit.json",
      "sha256": "58ce4021994d4a2ef9de67004c4ea7da8d1444e0823a2e447cf4908fd6115ab2"
    },
    {
      "id": "run02_report",
      "path": "benchmark-runs/heldout-h2-pilot-02/report.md",
      "sha256": "fbac67e937e3384c02a74a7a67c77fe3708cdf1d909923c9819d243a3af9cafc"
    },
    {
      "id": "v11_history",
      "path": "benchmark-runs/heldout-h2-pilot-02/v11-reason-evidence.txt",
      "sha256": "f6bee4c0653dc702110050aa43e48d21dede9174dbbc1f1dfb0e4d1dcc1ec01a"
    },
    {
      "id": "run03_arm",
      "path": "benchmark-runs/heldout-h2-pilot-03/jev_profile/result.json",
      "sha256": "0055644a5123d58287436a0e761400cf0bbc1c09fb255aa88b2d35194a31aebd"
    },
    {
      "id": "run03_events",
      "path": "benchmark-runs/heldout-h2-pilot-03/jev_profile/events.jsonl",
      "sha256": "1c1f6c88b97205a1d8db3a90dcfcd87a7e9cab11243a82d6214f9d057bb3eb64"
    },
    {
      "id": "run03_report",
      "path": "benchmark-runs/heldout-h2-pilot-03/report.md",
      "sha256": "2fd56aee08c79782738744f5b6d5c7eee8e4332ef5978a762be218f1edae9ddc"
    },
    {
      "id": "readiness_replay",
      "path": "benchmark-runs/heldout-h2-pilot-03/readiness-replay.txt",
      "sha256": "2f1ac7120e747e846210a1e3ac5e87445bbd07946cce11d42e2d0e0df356943f"
    }
  ],
  "claims": [
    {
      "id": "catalog",
      "kind": "measured",
      "text": "h2 catalog: 1 Claude Opus medium call, 114.6 s, 13 artifacts, 12 units; Jev ledger unchanged.",
      "source_ids": [
        "catalog"
      ]
    },
    {
      "id": "outcome",
      "kind": "measured",
      "text": "Pilot arm failed after 855.6 s at stage repair_owners with ADAPTIVE_INFERRED_ARTIFACT_BINDING; public checks executed 0 times, repair rounds 0, not graded. Under evaluation-protocol.v1 it counts as 0 (ungraded system stop).",
      "source_ids": [
        "arm",
        "execution",
        "report"
      ]
    },
    {
      "id": "cause",
      "kind": "measured",
      "text": "Leaf n1 ran on Jev-selected claude_haiku55_low and failed its readiness check (ARTIFACT_CHECK_NOT_PASSED at 461 s); n3 and verify-public were blocked; n2/n5 ran on opus55_medium and n4 on sonnet55_medium.",
      "source_ids": [
        "events"
      ]
    },
    {
      "id": "usage",
      "kind": "measured",
      "text": "Claude 4 calls, API-equivalent USD 4.56 (known subtotal); Jev 5 calls, 86,374 input tokens settled (ledger 1544 -> 1549 settled, pending 0).",
      "source_ids": [
        "arm"
      ]
    },
    {
      "id": "recurrence",
      "kind": "measured",
      "text": "Third occurrence of ADAPTIVE_INFERRED_ARTIFACT_BINDING after partial execution (D086 jev_all, codex-e2e-mac Jev, this pilot).",
      "source_ids": [
        "report"
      ]
    },
    {
      "id": "fix_direction",
      "kind": "hypothesis",
      "text": "Accepting never-run artifacts in repair-owner binding, and/or not selecting low-effort Haiku for implementation leaves, would let this run reach public checks; unmeasured.",
      "source_ids": []
    },
    {
      "id": "run02_partial_repair",
      "kind": "measured",
      "text": "Rerun 02 (partial_repair on): Jev again chose claude_haiku55_low for n1, which again failed ARTIFACT_CHECK_NOT_PASSED; the partial readiness repair committed a scripted repair of n1 with 0 provider calls instead of the earlier binding stop.",
      "source_ids": [
        "run02_events"
      ]
    },
    {
      "id": "run02_outcome",
      "kind": "measured",
      "text": "Rerun 02 then stopped after 719.6 s at stage profiles with BUDGET_MODEL_UNSUPPORTED (uncertain): the repair-profile Jev call completed (HTTP 200, 8,444 input / 312 output tokens) but returned typesafe/jev-1.14-20261014, which the settlement whitelist did not include; public checks 0, not graded; counts 0 under evaluation-protocol.v1.",
      "source_ids": [
        "run02_arm",
        "run02_events",
        "run02_report"
      ]
    },
    {
      "id": "run02_reconcile",
      "kind": "measured",
      "text": "Offline reconciliation (scripts/reconcile-d086-response.mjs, ported from D086) applied once: 8,444 observed input tokens charged, ledger 27,928,205 -> 27,936,649, settled 1554 -> 1555, pending 1 -> 0; 0 model and 0 network calls.",
      "source_ids": [
        "run02_reconcile"
      ]
    },
    {
      "id": "run02_correction",
      "kind": "correction",
      "text": "Earlier v11 re-freeze commits 8651d0b and 9b59081 updated only the runner pin; their supersedes.reason text was not changed because the edit targeted a top-level field. bdeb058 records the reason.",
      "source_ids": [
        "v11_history"
      ]
    },
    {
      "id": "run03_outcome",
      "kind": "measured",
      "text": "Rerun 03 (partial repair and Jev 1.14 settlement in): partial readiness repair committed twice; n1 ran on claude_haiku55_low, then repair profiles haiku55_medium and sonnet55_medium, and failed readiness every time with the same A01-packaging revision; stopped after 1187.9 s with ARTIFACT_CHECK_NOT_PASSED, repairs 2, public checks 0, not graded; counts 0. Claude USD 5.06 API-equivalent, Jev 7 calls, 104,008 input tokens; ledger 1562 settled, 0 pending.",
      "source_ids": [
        "run03_arm",
        "run03_events",
        "run03_report"
      ]
    },
    {
      "id": "readiness_root_cause",
      "kind": "measured",
      "text": "Root cause of n1 failures in all three runs: the generic readiness check imported tomllib, absent from the h2 public image (Python 3.10.20). Replaying pilot-03 round-0 n1 files in that image: old check ModuleNotFoundError; fixed check (ddbf44d, tomli fallback) passed with 6 assertions.",
      "source_ids": [
        "readiness_replay"
      ]
    },
    {
      "id": "cause_correction",
      "kind": "correction",
      "text": "The earlier claim that n1 failed after Jev chose claude_haiku55_low stated a sequence, not a cause: n1 would have failed on any profile because the readiness check could not parse TOML on Python 3.10. All three h2 runs stopped on harness defects (repair binding, Jev 1.14 settlement whitelist, TOML readiness) and are not evidence about Jev decision quality.",
      "source_ids": [
        "readiness_replay",
        "run03_events"
      ]
    }
  ],
  "costs": [
    {
      "role": "pilot Claude decisions and workers",
      "basis": "api_equivalent",
      "usd": 4.56265705,
      "source_ids": [
        "arm"
      ]
    },
    {
      "role": "catalog preparation",
      "basis": "unknown",
      "usd": null,
      "source_ids": [
        "catalog"
      ]
    },
    {
      "role": "rerun 02 Claude decisions and workers",
      "basis": "api_equivalent",
      "usd": 4.59092426,
      "source_ids": [
        "run02_arm"
      ]
    },
    {
      "role": "rerun 03 Claude decisions and workers",
      "basis": "api_equivalent",
      "usd": 5.06296865,
      "source_ids": [
        "run03_arm"
      ]
    }
  ],
  "unresolved": [
    "No h2 run has reached public checks; no grade exists yet.",
    "Whether low-effort Haiku should be offered for implementation leaves is undecided and now unmeasured, since the observed n1 failures were not caused by it.",
    "No Claude-only baseline on h2; the v8+ path admits only jev_profile.",
    "pycparser and django-modelcluster catalogs are not prepared; django-modelcluster and pycparser images also need a Python-version check against the readiness fix."
  ],
  "side_effects": [
    "New run folders benchmark-runs/heldout-h2-catalog-01 and heldout-h2-pilot-01 in the main checkout's benchmark-runs.",
    "Worktree /Users/lee/workspace/plugins/jev-router-heldout-20261018 with symlinks to the main checkout's benchmark-runs and .benchmarks.",
    "Scratchpad PATH shim for Claude CLI 2.1.299; /opt/homebrew/bin/claude still points to the removed 2.1.293.",
    "Shared ledger reconciled once for r1555 with before/after bytes in heldout-h2-pilot-02/reconciliation-applied."
  ]
}
```
