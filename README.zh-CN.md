<p align="center"><img src="docs/brand/pointsman-256.png" width="160" height="160" alt="Pointsman 吉祥物：用舌头拉动道岔扳手的青蛙"></p>
<p align="center"><a href="https://m8ven.ai/mcp/kai-leee-jev-router-1k0heh?s=readme"><img src="https://m8ven.ai/badge/mcp/kai-leee-jev-router-1k0heh?v=048f027e982892c5acfd612cc732a9bb" alt="M8ven Score"></a></p>

<h1 align="center">Pointsman</h1>

<p align="center"><em>面向编码智能体的依赖 DAG 任务路由，全流程实测。</em><br><sub>原名 Jev Router</sub></p>

[English](README.md) | [한국어](README.ko.md) | **简体中文**

Pointsman 将编码任务拆分为有明确范围的单元，按依赖 DAG 排序，并把就绪单元分派给编码工作智能体。
每个路由步骤只有在完整开发运行中证明能在不降低检查结果的前提下节省时间或 token 时才会保留。
Jev 在该流程中回答固定格式的问题；控制器强制执行范围，公开检查与独立隐藏测试判定结果。

本次发布提供 Jev 客户端、评估工具、运行契约和用量仪表盘
（[已发布、公开研究与仅本地的功能（英文）](docs/CAPABILITIES.en.md)）。
DAG 运行器与全部实验位于 [research 分支](https://github.com/Kai-Leee/pointsman/tree/research)。

[实测改进](#实测改进) · [尚未证实](#尚未证实) ·
[路由流程](#路由流程) · [快速开始](#快速开始) · [文档](#文档) · [安全](#安全)

## 实测改进

任务：根据规格构建 OpenAPI Python client generator。所有条件的工作智能体均为 Opus 5.5 medium，
只有路由判断不同。所有行均通过 **85/85 公开检查与 63/63 独立检查**。

| D067 对比，每个条件 1 次 | 开发时间 | 报告 token | API 价格折算成本 |
|---|---:|---:|---:|
| Claude 结构化判断（基线） | 36分 20.704秒 | 6,772,666 | $21.135172 |
| Jev 任务拆分 | 25分 54.036秒（**−28.74%**） | 3,967,289（**−41.42%**） | $9.864863（**−53.32%**） |
| Jev 任务拆分 + 依赖关系 | 28分 24.540秒（**−21.84%**） | 3,623,150（**−46.50%**） | $8.766580（**−58.52%**） |

修复路由：同一失败候选（公开 79/93），在给修复工作智能体相关产物读取权限之前与之后
（[D076 / D081 §2](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/D081_REPAIR_PATH_AND_RESULTS.md)）：

| 修复运行 | 结果 | 修复时间 |
|---|---|---:|
| 之前：仅写入范围 | 公开 88/93，独立 60/63（未完成） | 527.7秒，2 轮 |
| 之后：允许读取相关产物 | **公开 93/93，独立 63/63** | 270.4秒（**−48.76%**），1 轮 |

测量方法：

- 时间包含判断、实现、修复与公开检查，不含共享准备与独立评分。
- token 为 Claude 输入、输出、缓存创建、缓存读取与 Jev 输入、输出之和。各提供方分词器不同。
- 成本按当时 API 标价折算，并非订阅账单。降幅以基线行为分母。
- 每行均为单次观测。

[测量方法与 token 明细（英文）](docs/MEASURED_ROUTING.en.md) ·
[汇总 JSON](docs/evidence/measured-results-20261015.json) ·
[D067 完整记录](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/D067_RESULTS.md) ·
[D068–D085 后续结果（英文）](docs/POST_D067_RESULTS.en.md)

## 尚未证实

以上改进是在一个对比批次中、检查质量相同前提下的效率。尚未证明 Pointsman 比仅用 Claude 的运行更可靠或结果更好。
2026-10-17 的评估协议（[evaluation-protocol.v1](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/EVALUATION_PROTOCOL.md)，韩文）记录了当前证据：

| 问题 | 当前证据 | 状态 |
|---|---|---|
| 质量至少相同吗？ | 同一运行内配对，仅 Claude 对完整 Jev 路由：Claude 2 胜 1 平 0 负（D066、D067、D071） | 未证实 |
| 运行完成的频率？ | 之后的云端运行，需 93/93 + 63/63：D082 5/7（Wilson 95% 35.9–91.8%），D083 2/3，D085 2/3（20.8–93.9%） | 区间较宽 |
| 改进能否重复？ | 37 个条件中仅 2 个有 3 次以上计入运行 | 未重复 |
| 能否迁移到其他任务？ | 预先固定 15 个保留任务，尚未运行 | 待定 |

之后的运行更换了检查集（85 → 93）、策略与主机，因此不合并为单一节省数字。当前工作只评估 Claude 工作智能体路径。

## 路由流程

```text
目标 + 规格 + 产物契约
→ 输入验证与固定格式问题
→ 任务拆分与依赖选择
→ 依赖 DAG 与就绪任务队列
→ 限定文件范围的编码工作智能体
→ 与产物版本绑定的公开检查
→ 仅针对失败产物、依据证据的修复
```

- **就绪单元并行运行。** 下游工作从经验证的上游产物开始。
- **修复保持局部。** 失败的检查回到负责它的产物，而不是整体重建。
- **每一步都留下证据。** 问题、答案、用量、产物版本与检查结果保持关联。

参见[技术规格](docs/TECHNICAL_SPEC.en.md)与[研究状态](https://github.com/Kai-Leee/pointsman/blob/research/docs/agents/STATE.md)。

## 快速开始

需要 Node.js 22 或更高版本。没有外部依赖包。

```sh
git clone https://github.com/Kai-Leee/pointsman.git
cd pointsman
npm run mcp:fetch   # 为 MCP 测试安装固定版本的 jev-mcp 二进制文件，校验 SHA-256
npm test            # 仅使用假密钥和模拟 HTTP；不推理，不消耗余额
npm run check:links # 检查相对链接、标题锚点和 research 分支链接
npm run eval:demo   # 对合成记录进行离线评估
```

`mcp:fetch` 支持 macOS ARM64、Linux x64 和 Linux arm64（[SOURCE.json](vendor/jev-mcp/SOURCE.json)）。
缺少该二进制文件时，3 个 MCP 测试会失败。CI 在 macOS（Node 22）和 Docker（Node 24、26）中运行测试。

连接 Jev 需要 Jev AI 账户和密钥，并须同意 Jev AI 使用条款（[登录](docs/USAGE.en.md#sign-in)）：

```sh
npm run login            # 同意条款，在密钥页面登录，隐藏输入密钥
npm run config           # 仅输出配置和密钥是否存在；不访问网络
npm run models           # 1 次已认证的 GET
npm run demo -- --spend  # 1 次付费 POST；消耗 Jev 余额
```

更多：[完整使用、失败处理和部署说明](docs/USAGE.en.md) ·
[MCP 启动器](MCP.md) · [仪表盘](docs/DASHBOARD.en.md)（`npm run dashboard`）·
[基准测试](benchmarks/README.md)。

## 文档

`main` 保存代码、运行契约和使用文档。实验、决策和工作记录位于
[`research` 分支](https://github.com/Kai-Leee/pointsman/tree/research)。

- **入门：** [技术规格](docs/TECHNICAL_SPEC.en.md) · [运行契约](docs/orchestration/contracts/README.en.md)
- **使用：** [使用说明](docs/USAGE.en.md) · [评估 CLI](docs/EVALUATION_USAGE.en.md) 和
  [输入契约](docs/EVALUATION_CONTRACT.en.md) · [仪表盘](docs/DASHBOARD.en.md) ·
  [开发联动与独立 Opus 监控](docs/PAIRED_RUN.md) · [基准测试](benchmarks/README.md) ·
  [MCP](MCP.md)
- **结果：** [D067 实测（英文）](docs/MEASURED_ROUTING.en.md) · [D068–D085 后续结果（英文）](docs/POST_D067_RESULTS.en.md) ·
  [评估协议（韩文）](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/EVALUATION_PROTOCOL.md)
- **research 分支（韩语）：** [当前状态](https://github.com/Kai-Leee/pointsman/blob/research/docs/agents/STATE.md) ·
  [文档索引](https://github.com/Kai-Leee/pointsman/blob/research/docs/orchestration/README.md) · [决策记录](https://github.com/Kai-Leee/pointsman/blob/research/docs/DECISIONS.md) ·
  [工作记录](https://github.com/Kai-Leee/pointsman/blob/research/docs/WORK_LOG.md) · [验证记录](https://github.com/Kai-Leee/pointsman/blob/research/VERIFICATION.md) ·
  [评估方法](https://github.com/Kai-Leee/pointsman/blob/research/docs/EVALUATION_RESEARCH.md) ·
  [实际实验可行性](https://github.com/Kai-Leee/pointsman/blob/research/docs/LIVE_EXPERIMENT_FEASIBILITY.md) ·
  [实时失败报告](https://github.com/Kai-Leee/pointsman/blob/research/docs/REALTIME_FAILURE_RESEARCH.md)
- **发布：** [变更日志](CHANGELOG.md)
- **贡献者与智能体：** [AGENTS.md](AGENTS.md)（Codex 入口）·
  [CLAUDE.md](CLAUDE.md)（Claude 入口，导入 AGENTS.md）·
  [开发智能体角色与交接](https://github.com/Kai-Leee/pointsman/blob/research/docs/agents/README.md)

## 安全

- `JEV_AI_API_KEY` 只保存在服务端：进程环境变量或 `~/workspace/.env`。
  可用 `JEV_AI_ENV_FILE` 指定其他文件路径。
- 不要把密钥放入聊天、浏览器代码、Git、命令行参数或日志。不要使用 `NEXT_PUBLIC_`、`VITE_`、
  `PUBLIC_` 等公开前缀。
- 目标 URL 固定在 [src/config.mjs](src/config.mjs) 中。拒绝重定向。
  诊断输出从不打印密钥或 Authorization 头。

## 许可证

[Apache License 2.0](LICENSE)。

该许可证仅适用于本仓库的代码，不授予任何 Jev AI 服务的使用权。使用实际 Jev 功能需要您自己的
Jev AI 账户和密钥，并须同意 Jev AI 的[使用条款](https://jev-ai.pro/terms)和[隐私政策](https://jev-ai.pro/privacy)。

复用的 `jev-mcp` v0.3.1 二进制文件采用 Apache-2.0 许可，且未提交到仓库。其来源和校验和见
[vendor/jev-mcp/SOURCE.json](vendor/jev-mcp/SOURCE.json)。
