<p align="center"><img src="docs/brand/pointsman-256.png" width="160" height="160" alt="Pointsman 마스코트: 혀로 선로 전환 레버를 당기는 개구리"></p>
<p align="center"><a href="https://m8ven.ai/mcp/kai-leee-jev-router-1k0heh?s=readme"><img src="https://m8ven.ai/badge/mcp/kai-leee-jev-router-1k0heh?v=048f027e982892c5acfd612cc732a9bb" alt="M8ven Score"></a></p>

<h1 align="center">Pointsman</h1>

<p align="center"><em>코딩 에이전트를 위한 의존성 DAG 작업 라우팅, 처음부터 끝까지 실측합니다.</em><br><sub>이전 이름 Jev Router</sub></p>

[English](README.md) | **한국어** | [简体中文](README.zh-CN.md)

Pointsman은 코딩 작업을 담당 범위가 정해진 단위로 나누고, 의존성 DAG로 순서를 잡아 준비된 단위를
코딩 작업자에게 보냅니다. 각 라우팅 단계는 전체 개발 실행에서 검사 결과를 낮추지 않고 시간이나 토큰을
줄였을 때만 남깁니다. Jev는 이 과정 안에서 고정된 형식의 질문에 답하고, 컨트롤러가 작업 범위를 강제하며,
공개 검사와 독립 숨김 검사가 결과를 판정합니다.

이번 배포는 Jev 클라이언트·평가 도구·실행 계약·사용량 대시보드를 제공합니다
([main·research·로컬 기능 구분](docs/CAPABILITIES.md)).
DAG 실행기와 모든 실험은 [research 브랜치](https://github.com/Kai-Leee/pointsman/tree/research)에 있습니다.

[실측 개선](#실측-개선) · [아직 입증되지 않은 것](#아직-입증되지-않은-것) ·
[라우팅 과정](#라우팅-과정) · [빠른 시작](#빠른-시작) · [문서](#문서) · [보안](#보안)

## 실측 개선

과제: 명세로부터 OpenAPI Python client generator를 만든다. 모든 조건의 작업자는 Opus 5.5 medium이고
라우팅 판단만 바뀝니다. 모든 행이 **공개 85/85·독립 63/63 검사**를 통과했습니다.

| D067 비교, 조건당 1회 | 개발 시간 | 보고 토큰 | API 단가 환산 비용 |
|---|---:|---:|---:|
| Claude 구조화 판단 (기준선) | 36분 20.704초 | 6,772,666 | $21.135172 |
| Jev 작업 분해 | 25분 54.036초 (**−28.74%**) | 3,967,289 (**−41.42%**) | $9.864863 (**−53.32%**) |
| Jev 작업 분해 + 의존 관계 | 28분 24.540초 (**−21.84%**) | 3,623,150 (**−46.50%**) | $8.766580 (**−58.52%**) |

수리 라우팅: 같은 실패 후보(공개 79/93)에서 수리 작업자에게 관련 산출물 읽기 권한을 주기 전과 후
([D076 / D081 §2](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/D081_REPAIR_PATH_AND_RESULTS.md)):

| 수리 실행 | 결과 | 수리 시간 |
|---|---|---:|
| 전: 쓰기 범위만 | 공개 88/93, 독립 60/63 (미완료) | 527.7초, 2라운드 |
| 후: 관련 산출물 읽기 허용 | **공개 93/93, 독립 63/63** | 270.4초 (**−48.76%**), 1라운드 |

측정 방법:

- 시간은 판단·구현·수리·공개 검사를 포함하고, 공통 준비와 독립 채점은 제외합니다.
- 토큰은 Claude 입력·출력·캐시 생성·캐시 읽기와 Jev 입력·출력의 합입니다. 공급자마다 토크나이저가 다릅니다.
- 비용은 당시 API 정가 환산이며 구독 청구액이 아닙니다. 감소율의 분모는 기준선 행입니다.
- 각 행은 1회 관측입니다.

[측정 방법과 토큰 내역](docs/MEASURED_ROUTING.md) ·
[집계 JSON](docs/evidence/measured-results-20261015.json) ·
[D067 전체 기록](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/D067_RESULTS.md) ·
[D068–D085 이후 결과](docs/POST_D067_RESULTS.md)

## 아직 입증되지 않은 것

위 개선은 한 비교 묶음에서 같은 검사 품질을 유지한 효율입니다. Pointsman이 Claude 단독 실행보다
더 안정적이거나 더 좋은 결과를 낸다는 것은 아직 보여주지 못했습니다. 2026-10-17 평가 프로토콜
([evaluation-protocol.v1](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/EVALUATION_PROTOCOL.md))이 현재 근거를 정리합니다.

| 질문 | 현재 근거 | 상태 |
|---|---|---|
| 품질이 최소한 같은가? | 같은 실행 안의 쌍, Claude 단독 대 Jev 전체 라우팅: Claude 2승 1무 0패 (D066, D067, D071) | 미입증 |
| 실행이 얼마나 자주 완료되는가? | 이후 클라우드 실행, 93/93 + 63/63 필요: D082 5/7 (Wilson 95% 35.9–91.8%), D083 2/3, D085 2/3 (20.8–93.9%) | 구간이 넓음 |
| 개선이 반복되는가? | 37개 조건 중 2개만 집계 실행이 3회 이상 | 반복 안 됨 |
| 다른 과제로 옮겨지는가? | 사전 고정한 보류 과제 15개, 아직 실행 없음 | 대기 |

이후 실행은 검사 수(85 → 93)·정책·호스트가 바뀌어 하나의 절감 수치로 합치지 않습니다.
현재 작업은 Claude 작업자 경로만 평가합니다.

## 라우팅 과정

```text
목표 + 명세 + 산출물 계약
→ 입력 검증과 고정 형식 질문
→ 작업 분해와 의존 관계 선택
→ 의존성 DAG와 준비된 작업 대기열
→ 파일 범위가 제한된 코딩 작업자
→ 산출물 버전에 묶인 공개 검사
→ 실패 근거에 맞춘 해당 산출물만의 수리
```

- **준비된 단위는 동시에 실행합니다.** 하위 작업은 검증된 상위 산출물에서 시작합니다.
- **수리는 국소적으로 합니다.** 실패한 검사는 전체 재작성이 아니라 그 검사를 담당하는 산출물로 돌아갑니다.
- **모든 단계가 근거를 남깁니다.** 질문·답·사용량·산출물 버전·검사 결과가 연결됩니다.

[기술 명세](docs/TECHNICAL_SPEC.md)와 [연구 상태](https://github.com/Kai-Leee/pointsman/blob/research/docs/agents/STATE.md)를 참고하세요.

## 빠른 시작

Node.js 22 이상이 필요합니다. 외부 패키지는 없습니다.

```sh
git clone https://github.com/Kai-Leee/pointsman.git
cd pointsman
npm run mcp:fetch   # MCP 테스트용 고정 jev-mcp 바이너리. 체크섬 확인
npm test            # 가짜 키와 모의 HTTP만 사용. 추론·잔액 사용 없음
npm run check:links # 상대 링크, 제목 앵커, research 브랜치 링크 검사
npm run eval:demo   # 합성 기록의 오프라인 평가
```

`mcp:fetch`는 macOS ARM64, Linux x64, Linux arm64를 지원합니다([SOURCE.json](vendor/jev-mcp/SOURCE.json)).
바이너리가 없으면 MCP 테스트 3개가 실패합니다. CI는 macOS(Node 22)와 Docker(Node 24, 26)에서 테스트합니다.

Jev 연결에는 Jev AI 계정과 키, Jev AI 이용약관 동의가 필요합니다 ([로그인](docs/USAGE.md#로그인)).

```sh
npm run login            # 약관 동의, 키 페이지에서 로그인, 키 숨김 입력
npm run config           # 설정과 키 존재 여부만 출력. 네트워크 없음
npm run models           # 인증 GET 1회
npm run demo -- --spend  # 유료 POST 1회. Jev 잔액 사용
```

더 보기: [전체 사용·실패 처리·배포 안내](docs/USAGE.md) ·
[MCP 실행 연결](MCP.md) · [대시보드](docs/DASHBOARD.md) (`npm run dashboard`) ·
[벤치마크](benchmarks/README.md).

## 문서

`main`에는 코드, 실행 계약, 사용 문서를 둡니다. 실험·결정·작업 기록은
[`research` 브랜치](https://github.com/Kai-Leee/pointsman/tree/research)에 있습니다.

- **시작:** [기술 명세](docs/TECHNICAL_SPEC.md) · [실행 계약](docs/orchestration/contracts/README.md)
- **사용:** [사용 안내](docs/USAGE.md) · [평가 CLI](docs/EVALUATION_USAGE.md)와
  [입력 계약](docs/EVALUATION_CONTRACT.md) · [대시보드](docs/DASHBOARD.md) ·
  [개발 연결과 별도 Opus 모니터](docs/PAIRED_RUN.md) · [벤치마크](benchmarks/README.md) ·
  [MCP](MCP.md)
- **결과:** [D067 실측](docs/MEASURED_ROUTING.md) · [D068–D085 이후 결과](docs/POST_D067_RESULTS.md) ·
  [평가 프로토콜](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/EVALUATION_PROTOCOL.md)
- **research 브랜치:** [현재 상태](https://github.com/Kai-Leee/pointsman/blob/research/docs/agents/STATE.md) ·
  [문서 찾아보기](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/README.md) · [결정 기록](https://github.com/Kai-Leee/pointsman/blob/research/docs/DECISIONS.md) ·
  [작업 기록](https://github.com/Kai-Leee/pointsman/blob/research/docs/WORK_LOG.md) · [검증 기록](https://github.com/Kai-Leee/pointsman/blob/research/VERIFICATION.md) ·
  [평가 방법](https://github.com/Kai-Leee/pointsman/blob/research/docs/EVALUATION_RESEARCH.md) ·
  [실제 구현 평가 가능성](https://github.com/Kai-Leee/pointsman/blob/research/docs/LIVE_EXPERIMENT_FEASIBILITY.md) ·
  [실시간 실패 표시](https://github.com/Kai-Leee/pointsman/blob/research/docs/REALTIME_FAILURE_RESEARCH.md)
- **릴리스:** [변경 기록](CHANGELOG.md)
- **기여자·에이전트:** [AGENTS.md](AGENTS.md) (Codex 진입점) ·
  [CLAUDE.md](CLAUDE.md) (Claude 진입점, AGENTS.md import) ·
  [개발 에이전트 역할·인계](https://github.com/Kai-Leee/pointsman/blob/research/docs/agents/README.md)

## 보안

- `JEV_AI_API_KEY`는 서버에만 둡니다. 프로세스 환경변수 또는 `~/workspace/.env`를 사용합니다.
  다른 파일 경로는 `JEV_AI_ENV_FILE`로 지정합니다.
- 키를 채팅, 브라우저 코드, Git, 명령행 인수, 로그에 넣지 않습니다. `NEXT_PUBLIC_`, `VITE_`,
  `PUBLIC_` 같은 공개 접두사를 쓰지 않습니다.
- 목적지 URL은 [src/config.mjs](src/config.mjs)에 고정돼 있습니다. 리다이렉트를 거부합니다.
  진단 출력에는 키나 Authorization 헤더가 없습니다.

## 라이선스

[Apache License 2.0](LICENSE).

이 라이선스는 이 저장소의 코드에만 적용되며 Jev AI 서비스 이용 권한을 주지 않습니다.
실제 Jev 기능에는 본인의 Jev AI 계정과 키가 필요하고, Jev AI
[이용약관](https://jev-ai.pro/terms)과 [개인정보 처리방침](https://jev-ai.pro/privacy)에 동의해야 합니다.

재사용하는 `jev-mcp` v0.3.1 바이너리는 Apache-2.0이며 저장소에 커밋하지 않았습니다. 출처와
체크섬은 [vendor/jev-mcp/SOURCE.json](vendor/jev-mcp/SOURCE.json)에 있습니다.
