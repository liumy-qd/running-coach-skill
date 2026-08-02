---
name: running-coach
description: 面向高驰 COROS 用户的个人跑步数据管理、跨平台授权、每日恢复门控、活动分析、训练处方、周复盘和目标赛事计划工作流。Use when the user asks about COROS/高驰 data or login, daily readiness, sleep HRV, resting heart rate, stress, recovery, training load, running fitness, race predictions, FIT/lap/segment analysis, weekly review, injury or fatigue risk, weather or fueling impact, or 5K/10K/half-marathon/marathon planning.
---

# Running Coach

## 核心流程

优先使用 `coros` MCP；当前 agent 没有原生 bridge 时，使用 `coros-mcp call-tool`。不要输出或保存 token、OAuth state、poll token、授权链接、回调参数、FIT 文件或真实健康导出。

1. 将请求分类为 `daily-check`、`weekly-review`、`activity-review`、`race-plan`、`data-inventory` 或 `coros-auth`。
2. 获取完成任务所需的最小数据。先读取 `references/coros-tools.md`，严格按实时工具 Schema 传参。
3. 遇到未登录、授权过期或 `401` 时，读取 `references/coros-auth.md` 并运行 `scripts/coros_auth_bootstrap.py --mode auto`；验证通过后继续原任务。
4. 将工具结果整理成紧凑上下文。结构化 bundle 使用 `scripts/build_athlete_context.py`；旧版 MCP 文本可继续使用 `scripts/build_coros_summary.py`。
5. 先执行确定性恢复与风险门控，再进行语义综合。数值聚合、趋势、负荷比、漂移和处方约束交给脚本，不让模型凭长文本估算。
6. 对关键跑步按需读取详情、圈速、自定义时间窗或 FIT。普通日常建议不要下载 FIT。
7. 生成 `TrainingPrescription`，再用 `scripts/validate_prescription.py` 校验。模型不得把 `yellow/red` 的安全上限升级为高强度。
8. 输出观察、推断、行动和不确定性；提供停止规则、降级选项、反馈问题与下一检查点。

## 最小取数

- `daily-check`：近 7 天睡眠、睡眠 HRV、静息心率、压力、恢复、训练负荷和运动记录；有主观疲劳、疼痛或环境信息时一并纳入。
- `weekly-review`：追加体能评估；对最长跑、质量课、比赛和最近高负荷跑读取详情与圈速。
- `activity-review`：先定位活动，再读取详情和圈速；指定最后 N 分钟或精确时间段时使用自定义分段。
- `race-plan`：体能评估、恢复、30 天负荷、训练日程、60-90 天活动和关键活动圈速；按需读取天气、补给和全马参考。
- `data-inventory`：列出覆盖范围、日期、时区、数据源和缺失项；不要为“全面”而默认下载 FIT。

月经周期数据只在用户明确提出周期相关问题时临时查询；不要纳入默认检查、长期上下文或报告归档。

## 判断与安全边界

- 先用个人 7/28/56 天基线，再参考通用阈值。关键数据不足时降低置信度，不伪造基线。
- 至少使用两个相互支持的信号下强结论；信号冲突时明确冲突并采用保守选项。
- `red`：只允许休息、步行或恢复活动；`yellow`：最高为轻松强度；`green`：仍需满足计划、训练史和环境约束才允许质量课。
- 胸痛、晕厥、异常呼吸/心律、影响步态的疼痛或热病表现优先停止训练并建议专业评估。不要进行医疗诊断。
- COROS 预测成绩仅作体能信号。配速建议必须绑定阈值、近期同类训练、目标或心率/RPE。

## 输出契约

简洁输出必须包含：数据置信度、结论、证据窗口、观察、推断、训练处方、停止规则、降级选项、缺失数据、反馈问题和下一检查点。

结构化输出遵循 `references/v2-schemas.md`。处方校验失败时，使用校验器返回的保守方案，并说明失败原因。

## 按需参考

- COROS 工具与参数：`references/coros-tools.md`
- 授权和远程环境：`references/coros-auth.md`
- V2 上下文与处方 Schema：`references/v2-schemas.md`
- 覆盖度和来源置信度：`references/data-quality.md`
- 7/28/56 天个人基线：`references/personal-baselines.md`
- readiness、负荷和安全门控：`references/metrics.md`
- 圈速、漂移、间歇和关键活动：`references/coros-analytics.md`
- 目标周期与全马：`references/training-goals.md`、`references/marathon-framework.md`
- 伤病风险、环境与补给：`references/injury-risk.md`、`references/environment.md`、`references/environment-sources.md`、`references/fueling.md`
- 计划执行复盘与输出模板：`references/plan-feedback-loop.md`、`references/output-templates.md`

## 可复用脚本

- `build_athlete_context.py`：将结构化数据 bundle 归一为 AthleteContext V2。
- `build_coros_summary.py`：兼容旧版 COROS MCP 文本输入，并输出 V1 字段加 V2 版本标记。
- `analyze_laps.py`：确定性分析分段、漂移、间歇稳定性和后段衰减。
- `evaluate_context.py`：评估 readiness 并生成保守的基础训练处方。
- `validate_prescription.py`：校验 LLM 或脚本生成的训练处方是否符合安全上限。
- `coros_auth_bootstrap.py`：跨平台引导 COROS 授权并验证只读接口。
- `save_report.py`：仅在用户要求保存时写入 Markdown 报告。
