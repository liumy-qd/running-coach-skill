---
name: running-coach
description: 面向高驰 COROS 用户的个人跑步数据管理、恢复门控、训练建议和目标赛事计划工作流。Use when the user asks about COROS/高驰 data, daily readiness, HRV, sleep, resting heart rate, stress, recovery, training load, running fitness, race predictions, lap/segment analysis, single-run or weekly review, injury/fatigue risk, weather/heat impact, fueling, or creating/adjusting 5K/10K/half-marathon/marathon plans.
---

# Running Coach

## 核心工作流

将 `coros` MCP server 作为首选数据源。MCP 可用时，不要要求用户手动导出文件。不要输出 access token、OAuth state 或任何凭证材料。若当前 agent 不能直接调用 MCP tools，但本机有 `coros-mcp` CLI，则使用 `coros-mcp call-tool` 作为等价兜底路径。

1. 判断请求类型：
   - `daily-check`：今天是否适合跑、该怎么跑。
   - `weekly-review`：最近 7-14 天跑步与恢复复盘。
   - `activity-review`：单次或多次跑步详情分析。
   - `race-plan`：制定或调整 5K、10K、半马、全马或恢复/维持/减脂周期。
   - `data-inventory`：系统列出所有近期数据。
2. 先获取完成任务所需的最小数据；当用户要求“全面”“详细”“所有数据”时，再扩展到完整查询。
3. 先评估数据覆盖度、时效性和来源置信度，再下结论。数据不足时给保守建议并说明不能判断什么。
4. 建立个人基线：优先使用用户近期 7/28/56 天趋势，而不是通用阈值。
5. 先做今日恢复门控，再做周期目标判断。不要因为长期体能强或 COROS Recovery 高就忽略当天睡眠、HRV、RHR、疼痛和近期负荷。
6. 对关键活动做深挖：圈速/分段、后半程漂移、间歇稳定性、马配段、地形、环境和补给。
7. 融合环境、补给和伤病风险，输出具体行动：跑或休息、时长/距离、强度、配速/心率、停止规则、降级选项和复盘检查点。

## 数据获取顺序

`daily-check` 调用：
`queryDailyHealthData(days=7)`、`querySleepData(days=7)`、`queryHrvAssessment(days=7)`、`queryRestingHeartRate(days=7)`、`queryStressLevel(days=7)`、`queryRecoveryStatus()`、`queryTrainingLoadAssessment(days=7)`、`querySportRecords(startDate/endDate last 7 days)`。

`weekly-review` 额外调用：
`queryFitnessAssessmentOverview()`，并对关键跑步调用 `getActivityDetail()` 和 `queryActivityLapData()`。关键跑步包括最长跑、最快跑、间歇/节奏/马配课、最近一次高负荷跑和用户指定活动。

`activity-review`：如果用户没有提供 `labelId`，先调用 `querySportRecords` 找候选活动，再调用 `getActivityDetail(labelId, sportType)` 和 `queryActivityLapData(labelId, sportType)`。用户要求最后 N 分钟、马配段、指定时间窗或后半程时，使用 `queryCustomActivityLapData()`。

环境分析：使用每条活动的日期、地点、起点坐标和可推断的开始时间。今日训练建议要获取当前天气或预报。历史活动天气需要可靠来源；拿不到时明确说明天气缺失，并给条件式解释。

`race-plan` 调用：
`queryUserInfo()`、`queryFitnessAssessmentOverview()`、`queryRecoveryStatus()`、`queryTrainingLoadAssessment(days=30)`、`queryTrainingSchedule()`、最近 60-90 天 `querySportRecords`，并对最长跑、马配/节奏跑、间歇课和最近高负荷跑调用 `queryActivityLapData()`。需要判断补给或环境时读取 `references/fueling.md` 和 `references/environment-sources.md`。

`data-inventory`：调用所有相关 COROS 工具，包括用户资料、设备、健康、睡眠、HRV、心率、压力、恢复、体能评估、运动记录、活动详情、训练负荷和训练计划。

## 按需读取的参考

- 工具参数、运动类型和 `coros-mcp` CLI 兜底命令：`references/coros-tools.md`。
- 数据覆盖度、时效性、来源置信度：`references/data-quality.md`。
- 个人 7/28/56 天基线：`references/personal-baselines.md`。
- 恢复、负荷和 readiness 门控：`references/metrics.md`。
- 跑步圈速、分段、间歇、马配和长跑深挖：`references/coros-analytics.md`。
- 目标周期：5K/10K/半马/全马/维持/恢复/减脂：`references/training-goals.md`；全马专项细节：`references/marathon-framework.md`。
- 疼痛、疲劳和伤病风险：`references/injury-risk.md`。
- 天气与时间段修正：`references/environment.md`；天气来源与置信度：`references/environment-sources.md`。
- 长距离、比赛和热湿补给：`references/fueling.md`。
- 计划-执行-复盘闭环：`references/plan-feedback-loop.md`。
- 输出格式：`references/output-templates.md`。

## 训练判断规则

- 区分观察和建议：先说数据说明什么，再说该怎么做。
- 不要用单个指标下强结论；尽量至少用两个信号互相验证。
- 将 COROS 预测成绩视为体能信号，不当作必然结果。
- 配速建议要绑定阈值配速、近期活动配速、目标成绩或同类训练；不确定时用体感/心率建议。
- 长距离、质量课、减量期和比赛计划必须结合近期负荷、长跑占比、质量课密度、关键活动漂移和今日恢复。
- 对高温、高湿、风、降水、地形和时间段做配速与强度修正。不要把热影响导致的配速下降直接判断为体能下降。
- 数据缺失时，明确缺失项、降低置信度，并给保守选项。

## 输出要求

除非用户要求“所有细节”，否则保持简洁。训练建议必须包含：

- 数据置信度
- 结论
- 依据
- 训练安排
- 停止规则
- 降级选项
- 风险或调整点
- 完成后反馈问题
- 下一次检查点

全面列数据时，使用紧凑表格，并写清日期范围、时区、覆盖的工具和缺失数据。

## 可复用脚本

- `scripts/build_coros_summary.py`：把 COROS MCP 文本结果整理为结构化训练上下文，包含 coverage、baseline、risk 和 activity_profile。
- `scripts/analyze_laps.py`：分析 `queryActivityLapData()` JSON，输出分段、漂移、间歇候选、快速段衰减和长跑风险。
- `scripts/evaluate_context.py`：读取结构化摘要 JSON，输出 readiness、baseline、risk 和 next_action。
- `scripts/save_report.py`：用户要求保存或归档时，生成带时间戳的 Markdown 报告。

## 可选归档

如果用户要求保存或归档报告，创建 Markdown 报告。需要写入文件时，使用 `scripts/save_report.py` 生成带时间戳的文件。
