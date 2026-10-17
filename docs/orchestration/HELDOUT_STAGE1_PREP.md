# 보류 과제 1단계 준비 (R20261017-EVAL-PROTOCOL)

상태: **준비만 했다. 실행하지 않았다.** 유료 모델 호출 0, 유료 실행 0, Jev 호출 0. 공유 원장과 이전 `benchmark-runs/` 폴더는 건드리지 않았다. 커밋 없음.

기준: [evaluation-protocol.v1.json](contracts/evaluation-protocol.v1.json)(base 작업 트리에만 있음, 미추적)과 `benchmarks/e2e-swe/manifests/evaluation-tasks.v1.json`의 구간별 첫 과제.

**작성 위치.** 요청은 `/Users/lee/workspace/plugins/jev-router`였으나 하네스가 base checkout(`feat/d083-skill-gateway`, 다른 세션의 미커밋 변경 다수) 쓰기를 막았다. 그래서 작업 트리 `.claude/worktrees/busy-lamport-d61cf0`에 새 로컬 브랜치 `research-heldout-stage1-prep`(= `2b3c9ac`, base의 HEAD와 같은 커밋)을 만들고 같은 상대 경로에 썼다. `.benchmarks`는 base 사본을 가리키는 심볼릭 링크다. base로 옮기려면 아래 한 줄을 쓴다(새 파일만 복사하고 기존 파일은 덮지 않는다).

```bash
cd /Users/lee/workspace/plugins/jev-router/.claude/worktrees/busy-lamport-d61cf0 && rsync -aO --ignore-existing --relative benchmarks/e2e-swe/heldout scripts/build-heldout-obligations.mjs test/heldout-obligations.test.mjs docs/orchestration/HELDOUT_STAGE1_PREP.md /Users/lee/workspace/plugins/jev-router/
```

## 1. 대상과 준비물

| 구간 | 과제 | 명세 바이트 | 숨김 검사 | 이미지 digest (amd64) |
| --- | --- | ---: | ---: | --- |
| basic | h2 | 11,977 | 25 | `sha256:2910551f…c958` |
| advanced | pycparser | 17,390 | 38 | `sha256:65788667…5dd97` |
| expert | django-modelcluster | 21,509 | 91 | `sha256:129764af…473e` |

과제마다 `benchmarks/e2e-swe/heldout/<task>/`에 다음을 두었다.

| 파일 | openapi 대응물 | 상태 |
| --- | --- | --- |
| `atoms.json` | `build-d056-obligations.mjs`의 ATOM/INTEGRATION 정의 | 공개 명세에서 작성 |
| `obligations.json` | `manifests/d056-obligations.json` | `scripts/build-heldout-obligations.mjs`가 생성, 같은 스키마 |
| `grade.json` | `manifests/openapi_python_client.json` | adapter `preflight` 통과 |
| `image-lock.json` | `benchmark-runs/d040-openapi-image-lock.json` | adapter `lock-image`로 작성 |
| `public-checks.plan.json` | `public-checks/registry.v4.json` + `controls/catalog.v4.json` | **계획만**, 실행 코드 없음 |
| `v12.draft.json` | `manifests/d083-repair-fixes.json` | 초안, 로더가 거부(2절) |

| 과제 | 절 | 의무(atom) | 통합 시나리오 | 검사 명세 | 공개 검사 suite | 결함 대조군(계획) | 결함이 실패시킬 ID(계획) | 기록한 모호점 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| h2 | 10 | 52 | 6 | 58 | 6 | 52 | 58/58 | 18 |
| pycparser | 9 | 57 | 5 | 62 | 8 | 53 | 62/62 | 40 |
| django-modelcluster | 9 | 82 | 6 | 88 | 9 | 88 | 88/88 | 52 |
| 참고: openapi (d056 + v4) | 20 | 80 | 5 | 85 + 공개 8 = 93 | 8 | 83 | — | — |

결함 대조군 열은 계획서의 `expected_failed_ids`다. 대조군 코드가 없으므로 실제로 그 ID를 실패시키는지는 **측정하지 않았다**. atoms는 과제당 작성 에이전트 1개가 썼다(Claude 서브에이전트, 각 약 9/10/15분). 이 문서 작성 세션이 빌더 `--check`, 표본 atom, 숨김 파일명 누출(`rg "test_h2|tests_app|conftest|solve\.sh|/tests/"` → 계획 파일 0건)을 다시 확인했다.

**숨김 자료 경계.** 계획 입력(atoms, obligations, 공개 검사 계획)은 각 과제의 `instruction.md`만 읽고 작성했다. 작성 에이전트에게 다른 경로 열람을 금지했다. 채점 쪽 `grade.json`은 adapter가 검사 폴더 목록을 대조하므로 `tests/` 파일을 경로와 SHA-256으로만 고정했다. 내용은 열지 않았다. `solution/`은 읽지 않아 `oracle_repository`/`oracle_commit`은 `null`이다. 이 값은 oracle 대조군에만 쓰이고 채점에는 쓰이지 않는다. 자원·시간·검사 수는 공개 메타데이터 `task.toml`에서 읽었다. `select-evaluation-tasks.mjs`도 같은 파일을 읽는다.

**write_scope.** openapi는 과거 설계(d052)에서 경로를 가져왔다. 보류 과제에는 설계가 없으므로 공개 import 경로(`h2.connection` → `h2/connection.py`)와 `setup.sh`/`pyproject.toml`만 넣었다. `interfaces`·`artifact_interfaces`는 비웠다. 적응 경로는 이 필드를 읽지 않는다(`adaptivePublicInput`, runner:209-216).

## 2. 검증 (실행한 명령과 결과)

| 명령 | 결과 |
| --- | --- |
| `python3 benchmarks/e2e-swe/adapter.py --manifest benchmarks/e2e-swe/heldout/<task>/grade.json preflight` ×3 | upstream `b11ac067…` 일치, verified_files 7 / 7 / 12, model_calls 0 |
| `… lock-image --output …/image-lock.json` ×3 | digest가 grade.json과 일치. image_id `cf708359…`, `abc67def…`, `a6b66b76…` |
| `node scripts/build-heldout-obligations.mjs <task> --check` ×3 | exit 0 ×3. 재생성 결과가 바이트 단위로 같고, 계획이 valid(모든 검사 ID가 suite 하나에만 들어감) |
| `node scripts/build-heldout-obligations.mjs --mock <task>` ×3 | 요구사항 52 / 57 / 82개 수락, 카탈로그 프롬프트 35,952 / 51,711 / 55,466 B(openapi는 80개, 52,126 B), source SHA 일치, 로더 `ADAPTIVE_MANIFEST_INVALID`, model_calls 0, docker_calls 0 |
| `node scripts/adaptive-dag-comparison.mjs --manifest …/v12.draft.json --probe` ×3 | `ADAPTIVE_MANIFEST_INVALID`, exit 1 (작업 트리·base 모두). 로더에서 멈춰 auth·Docker·Jev 호출 없음 |
| `node --test test/heldout-obligations.test.mjs` | 4/4 통과. `.benchmarks` 없이 `obligations.json`에 들어 있는 `source.text`로 재생성. 미커버 절과 미매핑 ID 거부 확인 |

`--probe`는 통과하지 못한다. 실행기가 보류 과제 manifest를 지원하지 않기 때문이다. 대신 `--mock`이 첫 유료 단계(카탈로그 준비)가 부를 실제 함수 `adaptivePublicInput` → `prepareAdaptiveCatalog`를 그대로 실행해 입력이 받아들여짐을 보였다.

**차단 원인 분리**(읽기 전용, 임시 사본은 scratchpad). base 실행기 `loadAdaptiveRunManifest`에 초안을 한 항목씩 고쳐 넣었다. 세 과제 모두 같은 결과다.

| 변형 | 결과 |
| --- | --- |
| A 초안 그대로 | `ADAPTIVE_MANIFEST_INVALID` |
| B = A + registry/runner를 openapi 경로로 | `ADAPTIVE_MANIFEST_INVALID` |
| D = A + 카탈로그 해시만 채움 | `ADAPTIVE_MANIFEST_INVALID` |
| C = B + 카탈로그 해시 | **accepted** |

로더 수준의 차단은 두 가지뿐이다. 나머지 계약 해시, 프로필 계정 증거, 예산, 질문 형식 바인딩은 그대로 통과한다. **경고:** C가 받아들여진다는 것은, 로더를 통과시키려고 registry만 openapi로 되돌리면 h2 후보에 openapi 공개 검사 93개가 오류 없이 돈다는 뜻이다. 검사 ID도 `T.R01.01` 형태로 두 과제에서 겹친다.

## 3. openapi 전용 가정 (file:line)

줄 번호는 base 작업 트리 기준이다(`2b3c9ac` + 미커밋 D083 v13 게이트웨이 변경. v12 경로는 커밋본과 같고 줄만 몇 칸 밀린다).

| 위치 | 가정 | 보류 과제에 미치는 영향 |
| --- | --- | --- |
| `scripts/adaptive-dag-comparison.mjs:8` | 기본 manifest `d066-adaptive.json` | 항상 `--manifest` 필요(무해) |
| `scripts/adaptive-dag-comparison.mjs:22` | `catalog_reuse`가 있으면 `--prepare-catalog` 금지 | v12는 `catalog_reuse` 필수 → 새 카탈로그는 별도 v1 manifest로만 준비 가능 |
| `src/benchmark/adaptive-dag-runner.mjs:115` | 기본 manifest `d066-adaptive.json` | 무해 |
| `adaptive-dag-runner.mjs:124` | v8+ arms = `['jev_profile']` 고정 | 대조 조건(`claude_all`)을 v12로 표현 불가 |
| `adaptive-dag-runner.mjs:128-133` | v2+는 고정된 카탈로그 재사용(해시 6개) 필수 | 과제마다 새 카탈로그 먼저 필요 |
| `adaptive-dag-runner.mjs:141` | assertion 계약 = `public-checks/assertions.v2.json` | openapi 검사 assertion 계약에 묶임 |
| `adaptive-dag-runner.mjs:145-146` | registry/runner 경로 = openapi `registry.v4.json`/`run_public_checks_v4.py` | **로더 거부(차단)** |
| `adaptive-dag-runner.mjs:336` | 세션 임시 폴더 접두사 `jev-d066/d067-session-` | 이름뿐 |
| `adaptive-dag-runner.mjs:503` | Jev group_id `d075/d073/d071-decisions` | 원장 라벨뿐 |
| `adaptive-dag-runner.mjs:628` | `publicSourceHashes()`가 openapi 공개 검사·d056·openapi 명세를 고정 | 보류 실행에 openapi 파일이 고정되고, 그 파일이 바뀌면 drift로 잡힘 |
| `adaptive-dag-runner.mjs:832` | 재사용 카탈로그의 원 manifest와 input/checker/env/image가 같아야 함 | 과제별 v1 준비 manifest 필요 |
| `adaptive-dag-runner.mjs:847-849` | `original_test_count: 85`, `current_test_count: 93` 고정 | 결과 기록에 틀린 값 |
| `adaptive-dag-runner.mjs:858`, `:1038` | registry를 `loadPublicAuditInputs`(openapi 감사)로 읽음 | 아래 감사 스크립트 결합 |
| `adaptive-dag-runner.mjs:860` | 매핑된 검사 ID가 정확히 93개 | **실행 중 거부**(`ADAPTIVE_PUBLIC_REQUIREMENT_MAPPING`) |
| `adaptive-dag-runner.mjs:1150` | `preparation_cost_basis: 'Historical D066 preparation only…'` | 결과 문구 오류 |

두 파일 밖의 결합(실행 경로에서 호출됨):

| 위치 | 가정 |
| --- | --- |
| `scripts/audit-dag-public-checks.mjs:12-14` | `BASE=public-checks`, `MANIFEST=d056-obligations.json`과 그 해시 |
| `scripts/audit-dag-public-checks.mjs:23-34` | registry는 `registry.json`/`registry.v4.json`만 허용 |
| `scripts/audit-dag-public-checks.mjs:43`, `:113` | 검사 수 85/93, inventory가 d056 해시에 고정 |
| `src/benchmark/dag-runner.mjs:152`, `:184` | preflight가 openapi 감사·정상 대조군을 실행 |
| `src/benchmark/dag-runner.mjs:165-168` | `public_checker_root/environment.json`의 image_id = image lock(일반적, 과제별 파일 필요) |
| `scripts/grade-adaptive-arm.mjs:11`, `:32`, `:42` | 기본 grade manifest openapi, image lock 경로 `d040-openapi-image-lock.json` 고정, `summary.tests === 63` |

플래너·질문 형식·실행(`adaptive-dag-planner.mjs`, `adaptive-question-forms.mjs`, `adaptive-dag-execution.mjs`, `adaptive-spec-review.mjs`)에서는 openapi 고정값을 찾지 못했다(`rg "openapi|pyclientgen|d056|d066|registry\.v4|\b93\b|\b63\b|\b85\b"`).

## 4. 남은 것 (차단 목록)

**2026-10-18 갱신.** 2(실행기 일반화)와 5(채점 스크립트)는 [HELDOUT-20261018](../decisions/HELDOUT-20261018.md)에서 처리했다. 1(공개 검사 실행 코드)도 같은 기록에서 처리했다. 세 초안의 `--probe`는 `ready`(blocker 0)다. 3(새 카탈로그)이 끝나기 전에는 arm이 `ADAPTIVE_CATALOG_REUSE_UNPINNED`로 거부된다. 4(대조 조건)는 여전히 사용자 결정이 필요하다.

1. **공개 검사 실행 코드.** 과제별 `public-checks/`(runner, fixture, 이미지별 `environment.json`, 공개 명세만으로 쓴 정상 대조 구현, 결함 대조군, 고정 대조 증거)가 없다. 계획만 있다. openapi는 D064–D065에서 이 작업에 여러 세션이 들었다.
2. **실행기 일반화.** runner:145-146·860·847-849·628, audit 스크립트, dag-runner preflight. `adaptive-dag-runner.mjs`, `adaptive-dag-comparison.mjs`, `audit-dag-public-checks.mjs`, `dag-runner.mjs`는 v12 `catalog_reuse.allowed_changed_source_paths`에 있고, runner는 `pointsman-routing.v1/v2`에도 고정돼 있다. 고칠 때 drift를 기록해야 한다. 이번에는 이 파일들을 고치지 않았다.
3. **과제별 새 카탈로그.** v1 준비 manifest를 과제마다 하나 만들고 `--prepare-catalog --spend`로 Claude 호출 1회씩(유료). v1 준비 preflight도 openapi 감사를 돈다(dag-runner:152). 완료 후 v12 초안의 `catalog_reuse` 해시 6개를 채운다.
4. **대조 조건.** 프로토콜은 "조건 2"라고만 하고 조건 이름은 정하지 않았다. 같은 실행 쌍 근거(claude_all 2승 1무 0패) 때문에 `claude_all` 대 `jev_profile`로 추정했다. v12는 `jev_profile`만 받는다(runner:124). `claude_all`에는 v7 manifest나 로더 변경이 필요하다. 사용자 결정이 필요하다.
5. **채점 스크립트.** `grade-adaptive-arm.mjs`에 `--image-lock` 인자가 없고 검사 수 63이 고정이다. 보류 과제는 `grade.json`의 `test_case_count`(25/38/91)로 판정해야 한다. `adapter.py grade`는 이미 과제 일반적이다.
6. **공개 명세 모호점.** 작성 에이전트가 atom별 `gaps`에 110건을 기록했다(h2 18, pycparser 40, modelcluster 52). 공개 검사를 구현할 때 이 항목은 단정하지 말고 `unspecified`로 둬야 한다. 공통 항목: 후보가 `setup.sh`/패키징 파일을 직접 써야 하는지(세 과제 모두). 과제별 대표 항목:
   - h2: 예외 상속 관계와 `StreamClosedError`가 쓰이는 때, `send_headers` 한도가 상대 `MAX_CONCURRENT_STREAMS`인지 로컬 기본값 100인지, `reset_stream`이 `ErrorCodes`의 위치를 §6이라 하지만 실제로는 §4다.
   - pycparser: `Coord` column 기준, `UL`/`LL` 접미사의 `Constant.type`. 선언자 중첩(예: `int (*fp)(int, double)`) 기대값 일부는 명세 문장이 아니라 C 의미에서 왔다(R04.03 gap).
   - modelcluster: `INSTALLED_APPS`/AppConfig 필요 여부, import 표면 밖의 `clusterform_factory` 위치, `prefetch_related`의 정확한 쿼리 수.
7. **클라우드 실행.** D082에 따라 유료 실행과 원장 기록은 클라우드 한 곳에서만 한다. 이미지 잠금은 Mac에서 digest로 기록했고, 클라우드에서는 같은 digest를 `--platform linux/amd64`로 받아야 한다. 이 디렉터리에는 클라우드용 잠금을 만들지 않았다.

## 5. 비용 추정 (**추정, 실측 아님**)

단위는 D079 E2(`d079-no-deferral-03`) 성공 1회다. 실행기 1,516 s(25분16초), API 환산 $9.84([D079_EVALUATION.md](D079_EVALUATION.md):15, :50). 같은 표의 다른 두 arm은 $9.03/1,581 s, $15.47/2,383 s다.

| 항목 | 계산 | 추정 |
| --- | --- | --- |
| 1단계 arm | 3 과제 × 2 조건 × 3 반복 = 18 | — |
| arm 비용 (D079 E2 단위) | 18 × $9.84 | **$177.12** |
| arm 시간 (순차) | 18 × 1,516 s = 27,288 s | **7시간 35분** |
| 새 카탈로그 3개 (D066 실측 1회: 187 s, $0.482) | 3 × $0.482, 3 × 187 s | $1.45, 9분 |
| 합계 | | **약 $178.6, 약 7.7시간(순차)** |
| D079 세 arm 범위로 본 폭 | 18 × $9.03–$15.47, 18 × 1,516–2,383 s | $162.5–$278.5, 7.6–11.9시간 |

포함하지 않은 것: Jev 토큰(원장의 토큰 환산 장부, 달러 청구 아님), 독립 채점 시간(D079에서 성공 1회당 19 s), 공개 검사 구현·대조군 준비 노동. 과제 차이도 반영하지 않았다. 명세 바이트는 openapi 19,656 대비 0.61×/0.88×/1.09×이고, 숨김 검사는 63 대비 25/38/91이다. 실패한 arm도 수리 라운드를 다 쓰면 성공 arm 이상 비용이 들 수 있다.

## 6. 부수 효과

- Docker 이미지 3개를 받았다(amd64, 234.9 + 228.3 + 257.1 MB = 720.2 MB). 컨테이너는 띄우지 않았다.
- 작업 트리: 새 브랜치 `research-heldout-stage1-prep`, 심볼릭 링크 `.benchmarks`(미추적), 위 새 파일들. 미커밋.
- 이전 `benchmark-runs/`, 공유 원장, 고정된 실행기 파일은 수정하지 않았다.
