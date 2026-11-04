# 本地运动员档案

目标链、锁定配速、场地与停表习惯这类长期上下文，靠对话记忆跨会话重建既慢又容易丢。运动员档案把它们放进仓库外的本地 JSON，由脚本按需读取。

## 位置与隐私

- 默认 `~/.running-coach/profile.json`，可用 `--profile` 或环境变量 `RUNNING_COACH_PROFILE` 覆盖。
- 档案是个人训练上下文，**绝不提交到本仓库**（公开仓库），也不放 token、导出原件或 GPS 数据。
- 仓库内的 `examples/athlete-profile.json` 是合成示例，仅用于展示结构。

## Schema

```json
{
  "schema_version": "1.0",
  "updated_at": "2026-08-01",
  "athlete": {"nickname": "", "location": "", "devices": ["COROS"]},
  "goal": {
    "season_goal": "…",
    "race_chain": [
      {"race": "…", "date": "YYYY-MM-DD", "target": "…", "pace_lock_sec_km": [266, 268]}
    ]
  },
  "standing_constraints": ["…"],
  "coach_style": "balanced",
  "preferences": {"goal_bias": "balanced", "process_style": "standard", "volume_bias": "standard"},
  "notes": "…"
}
```

- `goal.race_chain`：按日期升序的目标链；配速锁死的比赛必须写 `pace_lock_sec_km`（秒/km 区间）。
- `standing_constraints`：长期成立的事实与习惯（如"课间停表是常态""常在田径场训练"，场地配速修正规则见 `coros-analytics.md`）。分析配速与恢复前先读，避免重复犯已纠正过的错误。
- `coach_style`：教练性格，控制建议文案的表达风格，数值与安全规则不受影响。可选 `balanced`（稳健专业，默认）、`drill_sergeant`（严格鞭策）、`encourager`（鼓励陪伴）、`data_geek`（数据极客）；缺失或为空按 `balanced` 处理。措辞规则见 `coach-personas.md`；当次对话明确指定时优先于档案。
- `preferences`：训练偏好三轴，控制教练内容层行为（怎么定目标、怎么盯过程、给多少量），只在既有安全包络内取档。`goal_bias` 目标取向（`conservative` 保守 / `balanced` 均衡 / `aggressive` 进取，锚定 `training-goals.md` 三层目标）；`process_style` 过程风格（`flexible` 随缘 / `standard` 标准 / `strict` 严格）；`volume_bias` 训练量级（`low` 量小 / `standard` 标准 / `high` 量大）。缺省键按 balanced/standard，即现状行为。行为规则见 `coach-personas.md`；当次对话明确指定时优先于档案。
- `notes`：其他长期背景（出差航班规律、酒精对 RHR 的干扰幅度等）。

## 使用方式

- `build_athlete_context.py --profile <path>`：档案填充 AthleteContext 的 `goal`（bundle 带了当次目标时以 bundle 为准）、`athlete`、`standing_constraints`、`coach_style` 和 `preferences`。
- `race-plan`、周期规划、配速横向对比之前先读档案；档案与当次数据冲突时说明冲突，以当次数据为准。
- 新目标、新习惯确认后更新档案并刷新 `updated_at`；过期的比赛从 `race_chain` 移除。
- 档案只做上下文，不做数据源：所有生理判断仍以当次取数和本地数据档案为准。
