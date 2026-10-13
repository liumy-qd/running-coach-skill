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
  "notes": "…"
}
```

- `goal.race_chain`：按日期升序的目标链；配速锁死的比赛必须写 `pace_lock_sec_km`（秒/km 区间）。
- `standing_constraints`：长期成立的事实与习惯（如"课间停表是常态""常在田径场训练，与公路配速差 3-5 秒/km"）。分析配速与恢复前先读，避免重复犯已纠正过的错误。
- `notes`：其他长期背景（出差航班规律、酒精对 RHR 的干扰幅度等）。

## 使用方式

- `build_athlete_context.py --profile <path>`：档案填充 AthleteContext 的 `goal`（bundle 带了当次目标时以 bundle 为准）、`athlete` 和 `standing_constraints`。
- `race-plan`、周期规划、配速横向对比之前先读档案；档案与当次数据冲突时说明冲突，以当次数据为准。
- 新目标、新习惯确认后更新档案并刷新 `updated_at`；过期的比赛从 `race_chain` 移除。
- 档案只做上下文，不做数据源：所有生理判断仍以当次取数和本地数据档案为准。
