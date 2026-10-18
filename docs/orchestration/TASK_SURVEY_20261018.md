# E2E-SWE Python 과제 조사 (2026-10-18)

읽기 전용 조사다. 유료 호출·이미지 pull·`tests/` 내용 열람·`solution/` 열람은 하지 않았다. `tests/`는 파일 수만 셌다(모든 Python 과제가 2개).

- 원본: `/Users/lee/workspace/plugins/jev-router/.benchmarks/E2E-SWE/tasks` (186개 중 Python 103개)
- held-out 목록: `benchmarks/e2e-swe/manifests/evaluation-tasks.v1.json` (15개)
- 기준 과제 openapi_python_client: 명세 19,656 B, 숨김 검사 63, `devtools-and-analysis`

## 1. 요약

- **openapi보다 작은 과제**(명세 < 19,656 B 이고 숨김 검사 < 63): **64개**. 이 중 10개가 held-out 목록에 있다(h2, git-code-debt, beaker, nose2, monkeytype, pycparser, playback, tremolo, deepdiff, sqlparse).
- **h2**(11,977 B / 25)와 **pycparser**(17,390 B / 38)는 둘 다 조건을 만족한다. 단, 둘 다 held-out 목록에 있다. 개발(튜닝) 과제로 쓰면 그 두 과제는 더 이상 held-out이 아니다.
- **Dockerfile은 Python 버전을 선언하지 않는다.** 103개 Dockerfile이 모두 `FROM ghcr.io/facebookresearch/e2e-swe:<task>` 한 줄이다. 버전 고정도 없다.
- **이미지 env는 믿을 수 없다.** openapi 이미지는 `PYTHON_VERSION=3.10.20` env를 갖지만 실제 `/usr/local/bin/python`은 **3.11.2**다. 로컬에 있는 5개 이미지만 `--pull never`로 실행해 확인했다: openapi 3.11.2, h2·pycparser·django-modelcluster·pytest-check 3.10.20.
- 따라서 "Python ≥3.11 이미지 선호"는 후보 판정에 **적용하지 못했다.** 후보 이미지는 로컬에 없고, pull 없이는 실제 버전을 알 수 없다. 명세 문구로 보면 3.10(all-repos), 3.12(inline-snapshot), 3.13(masoniteorm, django-migration-linter)이 섞여 있다. 후보 6개의 명세에는 버전 언급이 없다. 이미지 잠금 단계에서 실제 버전을 확인하고, 3.10이면 tomli 대체 경로(수정됨)를 탄다.

## 2. 후보 6개 순위

조건: openapi보다 작음, held-out 밖, `devtools-and-analysis` 아님. 점수가 낮을수록 준비·실행이 싸다고 본다. 이 점수는 이번 조사에서 정한 **휴리스틱**이며 실측 준비 시간이 아니다.

`점수 = 명세 KB + 숨김 검사/4 + 3×필수 외부 의존 수 + 3×실행 위험(소켓·스레드·하위 프로세스·인터프리터 내부 의존) + 참조 구현 난도(낮음 0, 중간 3, 높음 6)`

| 순위 | 과제 | 명세 B | 숨김 검사 | 범주 | 필수 의존 | 실행 위험 | 참조 난도 | 점수 |
|---|---|---:|---:|---|---|---|---|---:|
| 1 | lark | 9,533 | 16 | parsers-and-languages | 없음 | 없음 | 높음(LALR+Earley, Reconstructor) | 19.5 |
| 2 | fparser | 6,916 | 30 | parsers-and-languages | 없음 | 없음 | 높음(Fortran 고정/자유 형식) | 20.4 |
| 3 | dateutil | 8,057 | 14 | other | six (+zoneinfo 데이터) | 없음 | 높음(rrule RFC 5545, parser, tz) | 20.6 |
| 4 | dill | 7,751 | 30 | serialization-and-formats | 없음 | 있음(CodeType 등 CPython 버전 의존) | 중간 | 21.25 |
| 5 | qrcode | 8,619 | 17 | data-structures-and-algorithms | pillow, deprecation | 없음 | 중간(Reed-Solomon, 마스크) | 21.9 |
| 6 | pyyaml | 8,205 | 31 | serialization-and-formats | 없음 | 없음 | 높음(YAML 1.1 로더·이미터) | 21.95 |

예비 후보: waitress 22.0 (web, 소켓·스레드), gym3/`vectorenv` 23.8 (numeric, numpy, SubprocEnv), xlsxwriter 23.9 (serialization), websockets 25.3 (web), apscheduler 31.0 (concurrency, 외부 의존 4개).

참고:
- 1·2위는 pycparser(held-out)와 같은 `parsers-and-languages` 범주다. 범주 분산을 우선하면 2위 fparser 대신 waitress(web)나 gym3(numeric)을 넣을 수 있다.
- dill은 인터프리터 버전에 따라 code 객체 생성 방식이 다르다. 이미지 버전을 확인하기 전에는 환경 위험이 가장 크다.
- dateutil은 숨김 검사가 14개로 가장 적다. 하지만 검사 1개가 넓은 동작을 묶을 가능성이 있다.

## 3. 준비 노력 추정 (h2 기준)

h2 실측 산출물: obligations 52(tests 58), atoms 52(+integration 6), 공개 검사 `cases.py` 1,289줄, 대조군 결함 52종, 참조 구현 525줄(`controls/reference/h2`), `grade.json`(tests/ SHA-256 고정, verified_files 7), `image-lock.json`(234,853,188 B). atoms는 과제당 작성 에이전트 1개가 약 9–15분 걸렸다(`docs/orchestration/HELDOUT_STAGE1_PREP.md`:39). pycparser: obligations 57, 결함 53종, `cases.py` 1,133줄, 참조 1,116줄.

명세 KB당 obligations 3.28(pycparser)–4.34(h2)를 적용했다. 대조군 결함 수 ≈ obligations, `cases.py` ≈ obligation당 20–25줄, 참조 구현 ≈ obligation당 10–20줄로 잡았다. 추정치이며 실측이 아니다.

| 과제 | obligations/atoms | 대조군 결함 | cases.py 줄 | 참조 구현 줄 | grade.json | 이미지 잠금 |
|---|---|---|---|---|---|---|
| lark | 31–41 | 31–41 | 620–1,025 | 310–820 | tests/ 2파일 고정 | pull 필요, 버전 미확인 |
| fparser | 23–30 | 23–30 | 460–750 | 230–600 | 〃 | 〃 |
| dateutil | 26–35 | 26–35 | 520–875 | 260–700 | 〃 | 〃, zoneinfo 존재 확인 |
| dill | 25–34 | 25–34 | 500–850 | 250–680 | 〃 | 〃, 버전 확인이 우선 |
| qrcode | 28–37 | 28–37 | 560–925 | 280–740 | 〃 | 〃, pillow 버전 기록 |
| pyyaml | 27–36 | 27–36 | 540–900 | 270–720 | 〃 | 〃 |
| (h2 실측) | 52 | 52 | 1,289 | 525 | verified 7 | 잠금 완료 |
| (pycparser 실측) | 57 | 53 | 1,133 | 1,116 | verified 7 | 잠금 완료 |

과제마다 같은 단계가 필요하다: obligations·atoms 작성 → 공개 검사·`environment.json`(이미지 안 의존 버전 관측) → 참조 구현 + 결함 대조군 → `grade.json`(adapter `preflight`) → `image-lock.json`(digest·id·크기).

## 4. 실행 명령

```sh
# 과제 목록, 언어 분포, Dockerfile 형태
cd /Users/lee/workspace/plugins/jev-router/.benchmarks/E2E-SWE/tasks
fd -d1 -t d . | wc -l
rg -o --no-filename 'programming_language = ".*"' -g task.toml | sort | uniq -c
cat openapi_python_client/environment/Dockerfile h2/environment/Dockerfile

# 로컬 이미지만 확인 (pull 없음)
docker image ls --format '{{.Repository}}:{{.Tag}} {{.Size}}' | rg e2e-swe
for i in openapi_python_client h2 pycparser django-modelcluster pytest-check; do
  docker image inspect ghcr.io/facebookresearch/e2e-swe:$i --format '{{json .Config.Env}}'
  docker run --rm --pull never --platform linux/amd64 --network none --entrypoint sh \
    ghcr.io/facebookresearch/e2e-swe:$i -c 'command -v python; python -c "import sys;print(sys.version.split()[0])"'
done

# 수집 (scratchpad의 survey.py; tomllib 때문에 Python 3.14 사용)
/opt/homebrew/bin/python3.14 -I survey.py /Users/lee/workspace/plugins/jev-router/.benchmarks/E2E-SWE/tasks survey.json
# 의존 절, 명세 형태(제목·목록 수), Python 버전 문구
/opt/homebrew/bin/python3.14 -I deps.py   <tasks> survey.json
/opt/homebrew/bin/python3.14 -I shape.py  <tasks> survey.json h2 pycparser openapi_python_client dateutil lark fparser dill pyyaml waitress qrcode apscheduler websockets xlsxwriter pyrsistent trio jurigged
/opt/homebrew/bin/python3.14 -I pyhint.py <tasks> survey.json
for t in rapidy jurigged pytest-bdd beaker pyrate-limiter pgqueuer claripy; do rg -n -i 'installed|depend' $t/instruction.md | head -6; done
rg '^#{1,3} ' <task>/instruction.md   # 후보 범위 판단

# 기존 held-out 준비물 크기
cd /Users/lee/workspace/plugins/jev-router-heldout-20261018/benchmarks/e2e-swe/heldout
wc -l {h2,pycparser}/public-checks/cases.py {h2,pycparser}/public-checks/controls/reference/*/*.py
```

`survey.py` 핵심:

```python
m = tomllib.load(open(tf, 'rb'))                       # task.toml
if m['metadata']['programming_language'] != 'Python': continue
spec_bytes = len(open('instruction.md','rb').read())
hidden_tests = m['verifier']['test_case_count']
category = m['metadata']['category']; image = m['environment']['docker_image']
froms = re.findall(r'^FROM\s+(\S+)', dockerfile, re.M)
tests_files = sum(len(fs) for _, _, fs in os.walk('tests'))  # 파일 수만
```

"작은 과제" 필터: `spec_bytes < 19656 and hidden_tests < 63`.

## 5. 전체 Python 과제 (103개, 명세 바이트 오름차순)

- Python 열: `(실행)`은 로컬 이미지에서 `--pull never`로 실행해 확인한 값이다. `명세 …`는 instruction.md 문구다. `미확인`은 이미지가 없고 명세에도 언급이 없다는 뜻이다.
- 의존 열: 작은 과제 64개는 명세 Dependencies 절을 사람이 정리했다. 나머지 39개는 `(자동)` 표시이며, 절 안의 강조·코드 토큰을 정제 없이 뽑은 것이다(API 이름이 섞여 있다).
- 이미지 열은 `ghcr.io/facebookresearch/e2e-swe:` 뒤의 태그다. 모든 Dockerfile의 FROM과 같다.

| 과제 | 명세 B | 숨김 검사 | 범주 | 이미지 태그 | Python | 런타임 의존 | 작음 | 구분 |
|---|---:|---:|---|---|---|---|---|---|
| fparser | 6,916 | 30 | parsers-and-languages | `fparser` | 미확인 | 없음(stdlib) | 예 |  |
| beaker | 7,032 | 37 | query-and-database | `beaker` | 미확인 | 필수 없음; 선택 redis·python-memcached·sqlalchemy·pycryptodome/cryptography + redis/memcached 서비스 | 예 | held-out |
| jurigged | 7,364 | 24 | devtools-and-analysis | `jurigged` | 미확인 | codefind, ovld, blessed, watchdog | 예 |  |
| dill | 7,751 | 30 | serialization-and-formats | `dill` | 미확인 | 없음(stdlib) | 예 |  |
| apscheduler | 7,774 | 21 | concurrency-and-systems | `apscheduler` | 미확인 | anyio, attrs, tenacity, tzlocal | 예 |  |
| waitress | 8,035 | 32 | web-and-network | `waitress` | 미확인 | 없음(stdlib) | 예 |  |
| dateutil | 8,057 | 14 | other | `dateutil` | 미확인 | six (+/usr/share/zoneinfo) | 예 |  |
| pyyaml | 8,205 | 31 | serialization-and-formats | `pyyaml` | 미확인 | 없음(stdlib) | 예 |  |
| git-code-debt | 8,619 | 33 | devtools-and-analysis | `git-code-debt` | 미확인 | cfgv, flask, identify, mako, markdown-code-blocks, pyyaml, pytest | 예 | held-out |
| qrcode | 8,619 | 17 | data-structures-and-algorithms | `qrcode` | 미확인 | pillow, deprecation | 예 |  |
| pytest-check | 8,648 | 30 | devtools-and-analysis | `pytest-check` | 3.10.20 (실행) | pytest, typing-extensions | 예 |  |
| django_cqrs | 8,764 | 9 | query-and-database | `django_cqrs` | 명세 3.10+ | Django 5.2 (선택: pika, kombu, ujson, django-model-utils, python-dateutil, watchfiles) | 예 |  |
| lark | 9,533 | 16 | parsers-and-languages | `lark` | 미확인 | 없음(stdlib) | 예 |  |
| trio | 9,564 | 58 | concurrency-and-systems | `trio` | 명세: ExceptionGroup 내장(→≥3.11 추정) | attrs, sortedcontainers, outcome, sniffio, idna, exceptiongroup | 예 |  |
| monkeytype | 10,203 | 23 | devtools-and-analysis | `monkeytype` | 미확인 | mypy_extensions, libcst | 예 | held-out |
| websockets | 10,543 | 35 | web-and-network | `websockets` | 미확인 | 없음(stdlib) | 예 |  |
| pytest-bdd | 10,695 | 25 | devtools-and-analysis | `pytest-bdd` | 미확인 | pytest>=7, gherkin-official, parse, parse-type, Mako | 예 |  |
| griffe | 10,920 | 29 | devtools-and-analysis | `griffe` | 미확인 | 없음(stdlib) | 예 |  |
| organize | 11,440 | 83 | concurrency-and-systems | `organize` | 미확인 | (자동) 절 없음 |  |  |
| isobar | 11,802 | 27 | other | `isobar` | 미확인 | numpy (선택: mido, python-osc, python-rtmidi, LinkPython-extern) | 예 |  |
| xlsxwriter | 11,867 | 36 | serialization-and-formats | `xlsxwriter` | 미확인 | 없음(stdlib) | 예 |  |
| h2 | 11,977 | 25 | web-and-network | `h2` | 3.10.20 (실행) | hyperframe, hpack | 예 | held-out |
| pdfminer | 12,106 | 33 | serialization-and-formats | `pdfminer` | 미확인 | charset-normalizer, cryptography, Pillow | 예 |  |
| icontract | 12,201 | 32 | devtools-and-analysis | `icontract` | 미확인 | asttokens<3, typing_extensions | 예 |  |
| gym3 | 12,284 | 10 | numeric-and-scientific | `gym3` | 미확인 | numpy (선택 cloudpickle) | 예 |  |
| papers-cli | 12,671 | 31 | cli-and-terminal | `papers-cli` | 명세 ≥3.9 | PyMuPDF, bibtexparser, unidecode, python-slugify, rapidfuzz, requests + git | 예 |  |
| pyrsistent | 12,823 | 49 | data-structures-and-algorithms | `pyrsistent` | 미확인 | 없음(stdlib) | 예 |  |
| py-trie | 12,825 | 53 | data-structures-and-algorithms | `py-trie` | 미확인 | eth-hash(pycryptodome), eth-utils, hexbytes, rlp, sortedcontainers | 예 |  |
| pyupgrade | 12,878 | 48 | devtools-and-analysis | `pyupgrade` | 미확인 | tokenize-rt | 예 |  |
| schematics | 13,273 | 52 | serialization-and-formats | `schematics` | 미확인 | 없음(ObjectIdType만 bson) | 예 |  |
| nose2 | 13,276 | 37 | devtools-and-analysis | `nose2` | 미확인 | 없음(선택 coverage) | 예 | held-out |
| pydantic-ai | 13,627 | 37 | other | `pydantic-ai` | 미확인 | pydantic>=2.12, pydantic-core, httpx, anyio, opentelemetry-api, typing-inspection, griffelib, genai-prices, logfire-api | 예 |  |
| rapidy | 13,717 | 25 | web-and-network | `rapidy` | 미확인 | aiohttp, pydantic v2, dishka | 예 |  |
| cattrs | 13,737 | 16 | serialization-and-formats | `cattrs` | 미확인 | attrs, typing-extensions, exceptiongroup | 예 |  |
| tremolo | 13,799 | 33 | web-and-network | `tremolo` | 명세 3.10+ | 없음(stdlib) | 예 | held-out |
| import-tracker | 14,060 | 14 | devtools-and-analysis | `import-tracker` | 미확인 | 없음(검사용 alchemy-logging, PyYAML) | 예 |  |
| autopep8 | 14,333 | 59 | devtools-and-analysis | `autopep8` | 미확인 | pycodestyle>=2.12 | 예 |  |
| deepdiff | 14,747 | 29 | data-structures-and-algorithms | `deepdiff` | 미확인 | orderly-set>=5.4.1,<6 | 예 | held-out |
| remi | 14,835 | 22 | web-and-network | `remi` | 미확인 | 없음(stdlib) | 예 |  |
| tsrc | 15,080 | 95 | devtools-and-analysis | `tsrc` | 미확인 | (자동) cli-ui, colored_traceback, git, mypy_extensions, ruamel-yaml, schema, tsrc |  |  |
| pyaf | 15,429 | 30 | numeric-and-scientific | `pyaf` | 미확인 | numpy, scipy, pandas, scikit-learn, statsmodels, xgboost, matplotlib, pydot, dill | 예 |  |
| sqlalchemy-continuum | 15,431 | 51 | query-and-database | `sqlalchemy-continuum` | 미확인 | SQLAlchemy 2.0 | 예 |  |
| rpyc | 16,033 | 33 | web-and-network | `rpyc` | 미확인 | plumbum (선택 gevent, openssl CLI) | 예 |  |
| all-repos | 16,305 | 26 | devtools-and-analysis | `all-repos` | 명세 3.10 | identify, packaging, contextlib-chdir + git, GNU sed | 예 |  |
| tortoise-orm | 16,322 | 42 | query-and-database | `tortoise-orm` | 미확인 | pypika-tortoise, aiosqlite, iso8601/ciso8601, anyio, tomlkit, typing-extensions | 예 |  |
| xmldiff | 16,404 | 36 | serialization-and-formats | `xmldiff` | 미확인 | lxml | 예 |  |
| confection | 16,436 | 11 | serialization-and-formats | `confection` | 미확인 | 없음(pydantic v2 지연 import) | 예 |  |
| mongita | 16,459 | 24 | query-and-database | `mongita` | 미확인 | pymongo(bson), sortedcontainers | 예 |  |
| reader | 16,785 | 94 | query-and-database | `reader` | 미확인 | (자동) beautifulsoup4, cli, click, feedparser, import, requests, sqlite3, structlog, typing-extensions, werkzeug, xml |  |  |
| python-pytest-cases | 16,975 | 26 | devtools-and-analysis | `python-pytest-cases` | 미확인 | pytest 8.4, makefun, decopatch, packaging | 예 |  |
| faststream | 17,013 | 36 | web-and-network | `faststream` | 미확인 | fast-depends[pydantic], pydantic v2, anyio, typing-extensions, redis + Redis 서버 | 예 |  |
| supervisor | 17,023 | 22 | concurrency-and-systems | `supervisor` | 미확인 | 없음(stdlib) | 예 |  |
| formulaic | 17,130 | 60 | numeric-and-scientific | `formulaic` | 미확인 | numpy, pandas, scipy, wrapt, interface-meta, narwhals, typing-extensions | 예 |  |
| django-computedfields | 17,256 | 18 | query-and-database | `django-computedfields` | 명세 3.10+ | Django 5.2, django-fast-update, typing_extensions | 예 |  |
| diskcache | 17,340 | 60 | query-and-database | `diskcache` | 미확인 | 없음(DjangoCache만 Django) | 예 |  |
| pgqueuer | 17,360 | 21 | concurrency-and-systems | `pgqueuer` | 명세 3.10+ | asyncpg, psycopg3, anyio, croniter 등 + PostgreSQL 서버 | 예 |  |
| pycparser | 17,390 | 38 | parsers-and-languages | `pycparser` | 3.10.20 (실행) | 없음(stdlib) | 예 | held-out |
| dnspython | 17,489 | 37 | web-and-network | `dnspython` | 미확인 | 없음(stdlib) | 예 |  |
| playback | 17,746 | 51 | devtools-and-analysis | `playback` | 미확인 | jsonpickle, six, parse, contextlib2, decorator | 예 | held-out |
| masoniteorm | 17,751 | 80 | query-and-database | `masoniteorm` | 명세 3.13 | (자동) cleo, faker, inflection, pendulum |  |  |
| invoke | 17,763 | 79 | cli-and-terminal | `invoke` | 미확인 | (자동) invoke |  |  |
| pyrate-limiter | 17,875 | 40 | concurrency-and-systems | `pyrate-limiter` | 명세 ≥3.10 | 핵심 없음; 선택 filelock, redis, psycopg, aiohttp, httpx + Redis/PostgreSQL 서비스 | 예 |  |
| claripy | 18,033 | 60 | concurrency-and-systems | `claripy` | 미확인 | z3-solver, cachetools | 예 |  |
| sqlparse | 18,388 | 38 | query-and-database | `sqlparse` | 미확인 | 없음(stdlib) | 예 | held-out |
| fireant | 18,428 | 28 | query-and-database | `fireant` | 미확인 | pandas>=2, pypika, toposort | 예 |  |
| mpmath | 18,570 | 28 | numeric-and-scientific | `mpmath` | 미확인 | 없음(stdlib) | 예 |  |
| fiddle | 19,200 | 58 | other | `fiddle` | 미확인 | libcst, absl-py, graphviz, typing-extensions | 예 |  |
| grappa | 19,271 | 24 | devtools-and-analysis | `grappa` | 미확인 | colorama, six | 예 |  |
| pypulseq | 19,491 | 56 | geometry-and-simulation | `pypulseq` | 미확인 | numpy, scipy, matplotlib, coverage | 예 |  |
| openapi_python_client | 19,656 | 63 | devtools-and-analysis | `openapi_python_client` | 3.11.2 (실행) | httpx, attrs, ruamel.yaml (선택 pydantic, jinja2, typer+shellingham, ruff) |  | 튜닝 |
| inline-snapshot | 19,660 | 26 | devtools-and-analysis | `inline-snapshot` | 명세 CPython 3.12 | (자동) asttokens, attrs, black, dirty-equals, executing, inline_snapshot, pydantic, pydantic.BaseModel, pytest, pytest11, rich, |  |  |
| yamlpath | 19,746 | 111 | query-and-database | `yamlpath` | 미확인 | (자동) python-dateutil, ruamel.yaml |  | held-out |
| django-migration-linter | 19,769 | 23 | devtools-and-analysis | `django-migration-linter` | 명세 3.13 | (자동) appdirs, asgiref, sqlparse, toml, tomllib, your |  |  |
| barf | 19,875 | 23 | concurrency-and-systems | `barf` | 미확인 | (자동) BARF, System, capstone, future, networkx, pefile, pydot, pyelftools, pygments, pyparsing, z3 |  |  |
| transitions | 20,102 | 47 | concurrency-and-systems | `transitions` | 미확인 | (자동) GraphMachine, graphviz, six |  |  |
| pingtop | 20,200 | 47 | cli-and-terminal | `pingtop` | 명세 3.10+ | (자동) click, rich, textual |  |  |
| dnachisel | 20,870 | 35 | numeric-and-scientific | `dnachisel` | 미확인 | (자동) biopython, docopt, flametree, numpy, primer3-py, proglog, python_codon_tables |  |  |
| wrapt | 21,440 | 43 | other | `wrapt` | 미확인 | (자동) MyProxy.__doc__, NotImplementedError, ObjectProxy, TypeError, copy.copy, copy.deepcopy, pickle.dumps, proxy.__class__ |  |  |
| django-modelcluster | 21,509 | 91 | query-and-database | `django-modelcluster` | 3.10.20 (실행) | (자동) datetime.timezone.utc, django-taggit, django.utils.timezone.utc, modelcluster.contrib.taggit |  | held-out |
| tuf | 21,537 | 6 | security-and-crypto | `tuf` | 명세 3.10+ | (자동) securesystemslib, urllib3 |  |  |
| klongpy | 21,838 | 72 | parsers-and-languages | `klongpy` | 미확인 | (자동) colorama, import, numpy |  |  |
| sapp | 21,905 | 26 | devtools-and-analysis | `sapp` | 명세 3.8+ | (자동) SQLAlchemy, graphene, graphene-sqlalchemy, munch, ordered-set, pyre-extensions, typing-extensions |  |  |
| sec-parser | 21,948 | 28 | text-and-templating | `sec-parser` | 미확인 | (자동) beautifulsoup4, cssutils, hashlib, lxml, pandas |  |  |
| huey | 22,990 | 53 | concurrency-and-systems | `huey` | 미확인 | (자동) django, gevent, huey, peewee, redis, redis-server |  |  |
| returns | 23,059 | 23 | other | `returns` | 명세 3.10+ | (자동) typing-extensions |  |  |
| xknx | 23,144 | 37 | web-and-network | `xknx` | 명세: <3.11용 의존 언급 | (자동) async_timeout, cryptography, dataclasses, enum, ifaddr, struct, typing_extensions |  |  |
| pytermgui | 24,044 | 32 | cli-and-terminal | `pytermgui` | 미확인 | (자동) PyTermGUI, ptg.Container, ptg.Label, ptg.Layout, ptg.Splitter, ptg.Window, pytermgui, pytermgui.__init__, pytermgui.colo |  |  |
| j1939 | 24,353 | 81 | web-and-network | `j1939` | 미확인 | (자동) 절 없음 |  |  |
| graphql-core | 24,404 | 22 | parsers-and-languages | `graphql-core` | 미확인 | (자동) graphql, graphql-core, graphql.version, graphql.version_info |  |  |
| hojichar | 25,732 | 81 | text-and-templating | `hojichar` | 미확인 | (자동) 절 없음 |  |  |
| regipy | 26,184 | 27 | security-and-crypto | `regipy` | 미확인 | (자동) click, construct, inflection, pytz, tabulate |  |  |
| cement | 26,753 | 96 | cli-and-terminal | `cement` | 미확인 | (자동) 절 없음 |  |  |
| invariant | 26,861 | 45 | parsers-and-languages | `invariant` | 미확인 | (자동) Contents, Event, Function, Image, Message, None, TextChunk, Tool, ToolCall, ToolOutput, ToolParameter, True, additionalP |  |  |
| water | 27,076 | 77 | concurrency-and-systems | `water` | 미확인 | (자동) COMPLETED, FAILED, FlowPausedError, FlowStoppedError, InMemoryStorage, PAUSED, RUNNING, RuntimeError, SQLiteStorage, STO |  | held-out |
| probnum | 27,852 | 80 | numeric-and-scientific | `probnum` | 미확인 | (자동) NumPy, SciPy, numpy.random.Generator, probnum |  |  |
| authlib | 28,470 | 76 | security-and-crypto | `authlib` | 미확인 | (자동) authlib.jose, cachelib, cryptography, django, flask, flask-sqlalchemy, httpx, joserfc, requests, sqlalchemy, starlette |  |  |
| kcwarden | 29,213 | 46 | security-and-crypto | `kcwarden` | 명세 3.10+ | (자동) kcwarden, pyyaml, requests, rich, yaml |  | held-out |
| ldaptor | 29,918 | 114 | web-and-network | `ldaptor` | 미확인 | (자동) LineReceiver, Twisted, passlib, pyparsing, six, twisted.protocols.basic.LineReceiver, zope.interface |  |  |
| pipelinedp | 33,589 | 69 | security-and-crypto | `pipelinedp` | 미확인 | (자동) PLDBudgetAccountant, apache-beam, dill, dp-accounting, numpy, pandas, pydp.algorithms.laplace.BoundedMean, pydp.algorith |  |  |
| pysmt | 35,127 | 27 | concurrency-and-systems | `pysmt` | 미확인 | (자동) ENVIRONMENTS_STACK, Environment, allow_empty_var_names, ao, dwf, enable_div_by_0, enable_infix_notation, formula_manager |  |  |
| mapillary_tools | 45,030 | 54 | serialization-and-formats | `mapillary_tools` | 미확인 | (자동) AccelerationData, BlackVueInfo, Box32ConstructBuilder, Box64ConstructBuilder, CAMMGPSPoint, CAMMInfo, CMAP, ErrorMetadat |  | held-out |
| kafka-python | 60,268 | 61 | web-and-network | `kafka-python` | 미확인 | (자동) False, abc, atexit, collections, copy, crc32c, functools, gzip, hashlib, hmac, inspect, io, itertools, logging, lz4, pyt |  |  |
| protobuf-to-pydantic | 110,443 | 42 | devtools-and-analysis | `protobuf-to-pydantic` | 명세 3.13 언급 | (자동) email, email-validator, grpcio-tools, lark, mypy-protobuf, poetry-core, poetry-dynamic-versioning, toml |  |  |
