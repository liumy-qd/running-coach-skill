# Running Coach Skill

[![CI](https://github.com/liumy-qd/running-coach-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/liumy-qd/running-coach-skill/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/liumy-qd/running-coach-skill?include_prereleases&label=release)](https://github.com/liumy-qd/running-coach-skill/releases)
[![GitHub stars](https://img.shields.io/github/stars/liumy-qd/running-coach-skill?style=social)](https://github.com/liumy-qd/running-coach-skill/stargazers)

An Agent Skill for COROS runners, following the open [agentskills.io](https://agentskills.io) format. Works with OpenAI Codex, ZCode, Qwen Code, Kimi Code, Deep Code and other skill-compatible agents (office/consumer apps such as WorkBuddy and Coze: see [非编程用户应用](#非编程用户应用workbuddy--扣子--消费级智能体)); daily readiness, sleep HRV recovery, training load, lap/FIT analysis, structured athlete context, validated training prescriptions, fueling, weather risk, injury risk, and race plans from 5K to marathon.

中文快速入口：这是一个面向高驰 COROS 跑者的 Agent Skill（遵循 agentskills.io 开放格式，兼容 Codex、ZCode、Qwen Code、Kimi Code 等），用于分析恢复、训练负荷、圈速分段、补给、天气热应激、伤病风险，并生成 5K/10K/半马/全马训练建议。

```text
Use $running-coach to analyze my recent COROS running data and give today's training recommendation.
```

## Why This Skill

Most running dashboards show data. This skill turns COROS data into an agent-friendly coaching workflow:

- Check data quality before making a recommendation.
- Build personal 7/28/56 day baselines for sleep, HRV, resting heart rate, running volume, long runs, and quality sessions.
- Gate intensity with readiness before suggesting workouts.
- Analyze laps, segments, intervals, marathon-pace blocks, long-run drift, and late-run fade.
- Adjust for heat, humidity, wind, rain, fueling, fatigue, pain, and injury risk.
- Produce a plan-execute-review loop with stop rules and feedback questions.
- Build an `AthleteContext` and validate `TrainingPrescription` outputs before presenting training advice.

## Quick Start

本 skill 是标准 `SKILL.md` + `references/` + `scripts/` 结构，可安装到任何支持 Agent Skills 的工具：

| Harness | 安装目录 | 备注 |
| --- | --- | --- |
| OpenAI Codex | `~/.codex/skills/` |  |
| 智谱 ZCode | `~/.agents/skills/`（或 `~/.zcode/skills/`） |  |
| Qwen Code | `.qwen/skills/` | v0.6.0+ 实验特性，需 `--experimental-skills` 启动或在 settings.json 开启 |
| Kimi Code | 对应 skills 目录 | 遵循同一 Agent Skills 格式 |
| Deep Code（DeepSeek） | 对应 skills 目录 | 遵循 agentskills.io 标准 |

```bash
# 以 Codex 为例
mkdir -p ~/.codex/skills
git clone https://github.com/liumy-qd/running-coach-skill ~/.codex/skills/running-coach

# 以 ZCode 为例
mkdir -p ~/.agents/skills
git clone https://github.com/liumy-qd/running-coach-skill ~/.agents/skills/running-coach
```

唯一的外部依赖是数据接入（二选一）：harness 支持 MCP 时配置 COROS MCP；否则安装本机 `coros-mcp` CLI（授权引导见 [references/coros-auth.md](references/coros-auth.md)）。运行脚本只需 Python ≥3.8 标准库；仅解析 FIT 二进制时需要 `pip install fitdecode`（JSON 输入路径不需要）。

Run the synthetic examples:

```bash
cd ~/.codex/skills/running-coach
python3 scripts/analyze_laps.py --input examples/laps.json --json
python3 scripts/build_coros_summary.py --input examples/coros-summary.txt
python3 scripts/evaluate_context.py --input examples/context-summary.json --markdown
python3 scripts/build_athlete_context.py --input examples/athlete-bundle.json > /tmp/athlete-context.json
python3 scripts/validate_prescription.py --input examples/prescription-safe.json --context /tmp/athlete-context.json
python3 scripts/archive_snapshot.py --input examples/athlete-bundle.json --context /tmp/athlete-context.json --archive-dir /tmp/rc-archive
python3 scripts/archive_snapshot.py --stats --days 36500 --archive-dir /tmp/rc-archive
```

Every check can be archived as a slim, redacted snapshot into a local history outside this repository (default `~/.running-coach/archive/`); see `references/data-archive.md`.

Use it in Codex:

```text
Use $running-coach to review my last 14 days of COROS running data and tell me whether I should run today.
```

中文：

```text
使用 $running-coach 分析我最近 14 天的高驰跑步数据，判断今天是否适合跑步，并给出训练安排。
```

## 非编程用户应用（WorkBuddy / 扣子 / 消费级智能体）

上面的安装矩阵面向编码 Agent（有终端和本地 Python）。面向普通用户的国内应用按能力分三层适配：

| 层 | 代表应用 | 适配方式 | 降级说明 |
| --- | --- | --- | --- |
| 带技能市场的办公 Agent | 腾讯 WorkBuddy（CodeBuddy 团队） | 从其技能市场一键安装（内置 30+ 技能、社区上万个，`/` 调用，支持自建技能）；COROS 数据经「连接器」接入远程 MCP（`agents/openai.yaml` 声明的 server） | 技能格式是否完全兼容 SKILL.md 以官方文档为准（待实测）；本地数据档案与运动员档案（`~/.running-coach/`）不可用；脚本能否执行取决于其沙箱能力 |
| MCP 智能体平台 | 扣子（Coze）、文心智能体、Dify 等 | 把 `SKILL.md` + `references/` 导入为知识库/系统提示词，COROS MCP 挂载为工具 | 确定性门控退化为"模型按规则执行"，没有代码级处方校验；只依赖保守阈值兜底 |
| 纯对话助手 | 豆包、Kimi、通义等 App | 仅导入 `references/` 作为知识库 | 无实时数据、无脚本校验，只能给规则性建议，输出需明确标注降级模式 |

隐私注意：经远程 MCP 取数意味着健康数据离开本机（敏感个人信息传输），必须用户明确知情后使用；本仓库的本地档案、脱敏扫描等能力仅适用于本机运行场景。智能体平台侧的留存与合规由该平台策略决定。

## Sample Output

```text
Readiness: yellow
Action: downshift
Recommendation: Keep the habit, but reduce intensity and volume. Avoid intervals, threshold work, and long runs today.

Reasons:
- Short-term / long-term load ratio is above 1.3.
- Recovery percentage is low.
- The longest run takes too much of recent total mileage.

Next action:
- 20-40 min easy run, brisk walk, or full rest.
- Stop if pain changes your gait, heart rate spikes abnormally, or heat stress symptoms appear.
```

More examples:

- [Daily readiness output](examples/outputs/readiness.md)
- [Lap analysis output](examples/outputs/lap-analysis.md)
- [Training context evaluation](examples/outputs/training-context-evaluation.md)

## Example Prompts

- [Daily check](examples/prompts/daily-check.md)
- [Weekly review](examples/prompts/weekly-review.md)
- [Lap analysis](examples/prompts/lap-analysis.md)
- [Marathon plan](examples/prompts/marathon-plan.md)
- [Injury risk](examples/prompts/injury-risk.md)

## Features

| Area | What it does |
| --- | --- |
| COROS workflow | Uses COROS MCP first, with `coros-mcp` CLI as fallback. |
| Readiness | Combines sleep, HRV, resting heart rate, stress, recovery, load, pain, and recent workouts. |
| Personal baselines | Uses 7/28/56 day trends instead of generic thresholds only. |
| Lap analysis | Detects cardiac drift, pace fade, interval candidates, segment stability, and long-run risk. |
| FIT deep review | Per-km GAP, grade-pace-HR coupling, same-pace HR drift, blow-up detection (stop-aware), and heart-rate recovery (HRR). |
| Local data archive | Upserts slim, redacted snapshots into `~/.running-coach/archive/` (monthly JSONL) for real personal baselines. |
| Athlete profile | Standing race chain, locked paces, and training constraints from a local profile outside the repo. |
| Plan adherence | Treats prescribed distance as a hard cap, with escalation rules for repeated over-distance. |
| Race planning | Supports 5K, 10K, half marathon, marathon, maintenance, recovery, and fat-loss phases. |
| Environment | Adjusts recommendations for heat, humidity, dew point, wind, rain, and time of day. |
| Fueling | Adds carb, hydration, electrolyte, and GI feedback checks for long runs and races. |
| Safety | Includes stop rules, downshift options, and injury-risk prompts. |
| V2 schemas | Produces compact AthleteContext and validates TrainingPrescription safety gates. |

## How It Works

1. Classify the request: daily check, weekly review, activity review, race review, form review, race plan, data inventory, or COROS auth.
2. Pull the minimum required COROS data.
3. Build a compact AthleteContext with coverage, baselines, risk flags, and evidence (merged with the local athlete profile when present).
4. Gate training intensity deterministically before the model explains the plan.
5. Deep-dive key activities when needed.
6. Adjust for environment, fueling, fatigue, and injury risk.
7. Validate the TrainingPrescription safety contract.
8. Return a concrete action plan plus stop rules and feedback questions.
9. Archive the session's slim, redacted metrics into a local history under `~/.running-coach/archive/`.

## Repository Layout

```text
.
├── SKILL.md
├── agents/openai.yaml
├── references/
├── scripts/
├── examples/
│   ├── prompts/
│   └── outputs/
└── .github/
```

## COROS Data Access

两条等价的数据通路，可按 harness 能力任选：

- **远程 COROS MCP**：`agents/openai.yaml` 声明了 streamable_http 的 MCP server，供支持依赖清单的 harness（如 Codex）自动配置。
- **本地 `coros-mcp` CLI**：通用兜底，任何能执行 shell 命令的 harness 都可用；授权引导见 [references/coros-auth.md](references/coros-auth.md)，工具清单见 [references/coros-tools.md](references/coros-tools.md)。

优先使用 harness 原生 MCP bridge；没有 bridge 时用 CLI。真实凭证只留在本机，不要提交 token、OAuth 回调参数、密码或私有健康导出文件。

## Validation

```bash
python3 -m py_compile scripts/*.py
python3 scripts/analyze_laps.py --input examples/laps.json --json
python3 scripts/build_coros_summary.py --input examples/coros-summary.txt
python3 scripts/evaluate_context.py --input examples/context-summary.json --markdown
python3 scripts/build_athlete_context.py --input examples/athlete-bundle.json > /tmp/athlete-context.json
python3 scripts/validate_prescription.py --input examples/prescription-safe.json --context /tmp/athlete-context.json
python3 -m unittest discover -s tests -p 'test_*.py'
```

If you have Codex's `skill-creator` validation script available:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## Roadmap

- Package the deterministic gating scripts (`build_athlete_context` / `evaluate_context` / `validate_prescription`) as a remote MCP server, so MCP-capable consumer apps (WorkBuddy connectors, Coze) get code-level safety gates without local Python.
- Verify WorkBuddy skill-marketplace format compatibility and publish there if SKILL.md-compatible.
- Add more synthetic examples for 5K, 10K, half marathon, marathon, recovery week, and heat-stress scenarios.
- Add more optional parser adapters for direct MCP JSON bundles from different clients.
- Add more route/weather/fueling examples without storing private user data.
- Add community-contributed coaching templates for different experience levels.

## FAQ

### Does this require real COROS credentials?

No. The repository examples are synthetic. Real COROS access is optional and should happen through your local MCP or CLI environment, not through committed files.

### Is this medical advice?

No. It is a coaching workflow for training decisions. Chest pain, fainting, abnormal heart rhythm, acute injury, or persistent pain should be handled by a qualified professional.

### Can it work without COROS MCP?

Yes, partially. The scripts can analyze synthetic or exported summaries. For live coaching, COROS MCP or `coros-mcp` gives the agent a better data source.

## 中文说明

这个项目的核心不是“看数据”，而是帮助 Codex 按教练流程使用数据：

- 先判断数据是否足够可靠。
- 再用个人基线判断今天能不能上强度。
- 对关键跑步做圈速、分段、心率漂移和间歇稳定性分析。
- 把天气、热湿、补给、疲劳和疼痛纳入训练建议。
- 最后给出可执行训练、停止规则、降级选项和复盘问题。

安装：按 [Quick Start](#quick-start) 的安装矩阵选择对应 harness 的目录，例如 ZCode：

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/liumy-qd/running-coach-skill ~/.agents/skills/running-coach
```

使用：

```text
使用 $running-coach 分析我近期的高驰数据，判断今天适合休息、轻松跑还是质量课。
```

非编程用户（WorkBuddy、扣子等）请看上面的「非编程用户应用」小节。

## License

MIT
