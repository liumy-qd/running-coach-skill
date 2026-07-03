# Running Coach Skill

[![CI](https://github.com/liumy-qd/running-coach-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/liumy-qd/running-coach-skill/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/liumy-qd/running-coach-skill?include_prereleases&label=release)](https://github.com/liumy-qd/running-coach-skill/releases)
[![GitHub stars](https://img.shields.io/github/stars/liumy-qd/running-coach-skill?style=social)](https://github.com/liumy-qd/running-coach-skill/stargazers)

An OpenAI Codex skill for COROS runners: daily readiness, HRV/sleep recovery, training load, lap analysis, fueling, weather risk, injury risk, and race plans from 5K to marathon.

中文快速入口：这是一个面向高驰 COROS 跑者的 Codex skill，用于分析恢复、训练负荷、圈速分段、补给、天气热应激、伤病风险，并生成 5K/10K/半马/全马训练建议。

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

## Quick Start

Install the skill into Codex:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/liumy-qd/running-coach-skill ~/.codex/skills/running-coach
```

Run the synthetic examples:

```bash
cd ~/.codex/skills/running-coach
python3 scripts/analyze_laps.py --input examples/laps.json --json
python3 scripts/build_coros_summary.py --input examples/coros-summary.txt
python3 scripts/evaluate_context.py --input examples/context-summary.json --markdown
```

Use it in Codex:

```text
Use $running-coach to review my last 14 days of COROS running data and tell me whether I should run today.
```

中文：

```text
使用 $running-coach 分析我最近 14 天的高驰跑步数据，判断今天是否适合跑步，并给出训练安排。
```

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
| Race planning | Supports 5K, 10K, half marathon, marathon, maintenance, recovery, and fat-loss phases. |
| Environment | Adjusts recommendations for heat, humidity, dew point, wind, rain, and time of day. |
| Fueling | Adds carb, hydration, electrolyte, and GI feedback checks for long runs and races. |
| Safety | Includes stop rules, downshift options, and injury-risk prompts. |

## How It Works

1. Classify the request: daily check, weekly review, activity review, race plan, or data inventory.
2. Pull the minimum required COROS data.
3. Score data coverage and confidence.
4. Build personal baselines.
5. Gate training intensity with readiness.
6. Deep-dive key activities when needed.
7. Adjust for environment, fueling, fatigue, and injury risk.
8. Return a concrete action plan plus stop rules and feedback questions.

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

## Optional COROS MCP

The skill expects a COROS MCP server when available. If direct MCP access is unavailable, it can use the local `coros-mcp` CLI fallback described in [references/coros-tools.md](references/coros-tools.md).

Do not commit access tokens, OAuth callback parameters, passwords, or exported private health files.

## Validation

```bash
python3 -m py_compile scripts/*.py
python3 scripts/analyze_laps.py --input examples/laps.json --json
python3 scripts/build_coros_summary.py --input examples/coros-summary.txt
python3 scripts/evaluate_context.py --input examples/context-summary.json --markdown
```

If you have Codex's `skill-creator` validation script available:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## Roadmap

- Add more synthetic examples for 5K, 10K, half marathon, marathon, recovery week, and heat-stress scenarios.
- Add optional structured output schemas for readiness and activity review.
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

安装：

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/liumy-qd/running-coach-skill ~/.codex/skills/running-coach
```

使用：

```text
使用 $running-coach 分析我近期的高驰数据，判断今天适合休息、轻松跑还是质量课。
```

## License

MIT

