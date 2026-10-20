<p align="center"><img src="docs/brand/pointsman-256.png" width="160" height="160" alt="Pointsman mascot: a frog pulling a rail switch lever with its tongue"></p>
<p align="center"><a href="https://m8ven.ai/mcp/kai-leee-jev-router-1k0heh?s=readme"><img src="https://m8ven.ai/badge/mcp/kai-leee-jev-router-1k0heh?v=048f027e982892c5acfd612cc732a9bb" alt="M8ven Score"></a></p>

<h1 align="center">Pointsman</h1>

<p align="center"><em>Dependency-DAG task routing for coding agents, measured end to end.</em><br><sub>formerly Jev Router</sub></p>

**English** | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

Pointsman splits a coding task into scoped units, orders them as a dependency DAG and dispatches
ready units to coding workers. Each routing step is kept only when a full development run shows it
saves time or tokens without lowering the checked result. Jev answers fixed, typed questions inside
that loop; the controller enforces scopes, and public plus independent hidden tests decide the outcome.

This release ships the Jev client, evaluation tools, run contracts and a usage dashboard
([what is released, public research or local only](docs/CAPABILITIES.en.md)).
The DAG runner and all experiments live on the [research branch](https://github.com/Kai-Leee/pointsman/tree/research).

[Measured gains](#measured-gains) · [Not yet established](#not-yet-established) ·
[How routing works](#how-routing-works) · [Quick start](#quick-start) · [Documentation](#documentation) · [Security](#security)

## Measured gains

Task: build an OpenAPI Python client generator from its specification. Workers are Opus 5.5 medium in every
condition; only the routing decisions change. All rows passed **85/85 public and 63/63 independent checks**.

| D067 cohort, one run per condition | Development time | Reported tokens | API-rate-equivalent cost |
|---|---:|---:|---:|
| Claude structured decisions (baseline) | 36m 20.704s | 6,772,666 | $21.135172 |
| Jev decomposition | 25m 54.036s (**−28.74%**) | 3,967,289 (**−41.42%**) | $9.864863 (**−53.32%**) |
| Jev decomposition + dependencies | 28m 24.540s (**−21.84%**) | 3,623,150 (**−46.50%**) | $8.766580 (**−58.52%**) |

Repair routing, same failed starting candidate (public 79/93), before and after giving repair workers
read access to related artifacts ([D076 / D081 §2](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/D081_REPAIR_PATH_AND_RESULTS.md)):

| Repair run | Result | Repair time |
|---|---|---:|
| Before: write scope only | 88/93 public, 60/63 independent (incomplete) | 527.7s, two rounds |
| After: read access to related artifacts | **93/93 public, 63/63 independent** | 270.4s (**−48.76%**), one round |

How these were measured:

- Time covers decisions, implementation, repairs and public checks; it excludes shared preparation and independent grading.
- Tokens are Claude input, output, cache creation and cache reads plus Jev input and output. Providers use different tokenizers.
- Cost uses historical API list rates; it is not a subscription bill. Reductions use the baseline row as denominator.
- Each row is a single observation.

[Methods and token breakdown](docs/MEASURED_ROUTING.en.md) ·
[aggregate JSON](docs/evidence/measured-results-20261015.json) ·
[full D067 record](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/D067_RESULTS.md) ·
[D068–D085 timeline](docs/POST_D067_RESULTS.en.md)

## Not yet established

The gains above are efficiency at equal checked quality in one cohort. They do not yet show that Pointsman
is more reliable or produces better results than a Claude-only run. The evaluation protocol from
2026-10-17 ([evaluation-protocol.v1](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/EVALUATION_PROTOCOL.md))
records where the evidence stands:

| Question | Current evidence | Status |
|---|---|---|
| Is quality at least equal? | Same-run pairs, Claude-only vs full Jev routing: Claude 2 wins, 1 tie, 0 losses (D066, D067, D071) | Not shown |
| How often does a run complete? | Later cloud runs, 93/93 + 63/63 required: D082 5/7 (Wilson 95% 35.9–91.8%), D083 2/3, D085 2/3 (20.8–93.9%) | Wide intervals |
| Do gains repeat? | 2 of 37 conditions have three or more counted runs | Not repeated |
| Do gains transfer to other tasks? | 15 held-out tasks are fixed in advance; none run yet | Pending |

Later runs changed the check set (85 → 93), policies and hosts, so they are not pooled into one savings figure.
Current work evaluates Claude-worker paths only.

## How routing works

```text
Goal + specification + artifact contracts
→ input validation and fixed typed questions
→ work decomposition and dependency choices
→ dependency DAG and ready-task queue
→ coding workers, each limited to its file scope
→ public checks tied to artifact revisions
→ evidence-scoped repair of the failing artifact only
```

- **Ready units run concurrently.** Downstream work starts from validated upstream artifacts.
- **Repair stays local.** A failing check routes back to the artifact that owns it, not to a full rebuild.
- **Every step leaves evidence.** Questions, answers, usage, artifact revisions and check results stay linked.

See the [technical specification](docs/TECHNICAL_SPEC.en.md) and the
[research state](https://github.com/Kai-Leee/pointsman/blob/research/docs/agents/STATE.md).

## Quick start

Requires Node.js 22 or later. There are no external packages.

```sh
git clone https://github.com/Kai-Leee/pointsman.git
cd pointsman
npm run mcp:fetch   # pinned jev-mcp binary for the MCP tests, checksum-verified
npm test            # fake key and mock HTTP only; no inference, no balance use
npm run check:links # relative links, heading anchors and research-branch links
npm run eval:demo   # offline evaluation of synthetic records
```

`mcp:fetch` supports macOS ARM64, Linux x64 and Linux arm64 ([SOURCE.json](vendor/jev-mcp/SOURCE.json)).
Without it, the three MCP tests fail. CI runs the tests on macOS (Node 22) and in Docker (Node 24 and 26).

Connecting to Jev needs a Jev AI account and key, and acceptance of the Jev AI Terms of Use
([sign-in](docs/USAGE.en.md#sign-in)):

```sh
npm run login            # accept terms, sign in on the key page, paste the key (hidden)
npm run config           # prints settings and whether a key exists; no network
npm run models           # one authenticated GET
npm run demo -- --spend  # one paid POST; uses your Jev balance
```

More: [all usage, failure handling and deployment](docs/USAGE.en.md) ·
[MCP launcher](MCP.md) · [dashboard](docs/DASHBOARD.en.md) (`npm run dashboard`) ·
[benchmarks](benchmarks/README.md).

## Documentation

`main` holds code, run contracts and usage documents. Experiments, decisions and logs live on the
[`research` branch](https://github.com/Kai-Leee/pointsman/tree/research).

- **Start here:** [technical spec](docs/TECHNICAL_SPEC.en.md) ·
  [run contracts](docs/orchestration/contracts/README.en.md)
- **Usage:** [usage guide](docs/USAGE.en.md) · [evaluation CLI](docs/EVALUATION_USAGE.en.md) and
  [input contract](docs/EVALUATION_CONTRACT.en.md) · [dashboard](docs/DASHBOARD.en.md) ·
  [paired run and separate Opus monitor](docs/PAIRED_RUN.md) · [benchmarks](benchmarks/README.md) ·
  [MCP](MCP.md)
- **Results:** [D067 measurements](docs/MEASURED_ROUTING.en.md) · [D068–D085 timeline](docs/POST_D067_RESULTS.en.md) ·
  [evaluation protocol (Korean)](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/EVALUATION_PROTOCOL.md)
- **Research branch (Korean):** [current state](https://github.com/Kai-Leee/pointsman/blob/research/docs/agents/STATE.md) ·
  [document index](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/README.md) · [decisions](https://github.com/Kai-Leee/pointsman/blob/research/docs/DECISIONS.md) ·
  [work log](https://github.com/Kai-Leee/pointsman/blob/research/docs/WORK_LOG.md) · [verification](https://github.com/Kai-Leee/pointsman/blob/research/VERIFICATION.md) ·
  [evaluation methods](https://github.com/Kai-Leee/pointsman/blob/research/docs/EVALUATION_RESEARCH.md) ·
  [live experiment feasibility](https://github.com/Kai-Leee/pointsman/blob/research/docs/LIVE_EXPERIMENT_FEASIBILITY.md) ·
  [real-time failure reporting](https://github.com/Kai-Leee/pointsman/blob/research/docs/REALTIME_FAILURE_RESEARCH.md)
- **Releases:** [changelog](CHANGELOG.md)
- **Contributors and agents:** [AGENTS.md](AGENTS.md) (Codex entry) ·
  [CLAUDE.md](CLAUDE.md) (Claude entry, imports AGENTS.md) ·
  [agent roles and handoff](https://github.com/Kai-Leee/pointsman/blob/research/docs/agents/README.md)

## Security

- Keep `JEV_AI_API_KEY` on the server: a process environment variable or `~/workspace/.env`.
  Set another file path with `JEV_AI_ENV_FILE`.
- Never put the key in chat, browser code, Git, command-line arguments or logs. Do not use public
  prefixes such as `NEXT_PUBLIC_`, `VITE_` or `PUBLIC_`.
- Destination URLs are fixed in [src/config.mjs](src/config.mjs). Redirects are refused.
  Diagnostic output never prints the key or the Authorization header.

## License

[Apache License 2.0](LICENSE).

The license covers the code in this repository only. It grants no rights to the Jev AI service.
Live Jev features need your own Jev AI account and key, and you must accept the Jev AI
[Terms of Use](https://jev-ai.pro/terms) and [Privacy Policy](https://jev-ai.pro/privacy).

The reused `jev-mcp` v0.3.1 binary is Apache-2.0 and is not committed. Its source and checksums
are in [vendor/jev-mcp/SOURCE.json](vendor/jev-mcp/SOURCE.json).
