# COROS MCP 工具参考

用户在中国或工作区时区为中国时，默认使用 `Asia/Shanghai`。日期范围工具使用 `yyyyMMdd`。

## 调用方式

优先使用 agent 原生的 `coros` MCP tools。若当前 agent 没有直接 MCP tool bridge，但本机安装了 `coros-mcp`，使用 CLI 兜底：

```bash
coros-mcp list-tools --refresh
coros-mcp call-tool --tool queryRecoveryStatus --arguments-json '{}'
coros-mcp call-tool --tool queryDailyHealthData --arguments-json '{"days":7,"timezone":"Asia/Shanghai"}'
```

复杂参数也放在 `--arguments-json` 中，字段名保持英文。不要输出或记录 token。若 CLI 返回 `invalid_grant`、`run login first` 或授权过期，提示需要重新登录，并优先切回原生 MCP；不要把 access token、OAuth state 或回调参数写入报告。

## 用户资料与设备

- `queryUserInfo()`：身高、体重、生日、性别、昵称。
- `queryDevices()`：绑定设备、序列号、保修信息。

## 日常健康

- `queryDailyHealthData(days, timezone)`：每日步数、热量、运动分钟、平均压力和睡眠摘要。
- `querySleepData(days, startDate, endDate, timezone)`：睡眠分数、主睡眠时长、睡眠窗口、深睡/浅睡/REM/清醒比例、清醒时长与次数、小睡。
- `queryAvgHeartRate(days, timezone)`：每日平均、最低、最高心率。
- `queryRestingHeartRate(days, timezone)`：每日静息心率。
- `queryHrvAssessment(days, timezone)`：HRV 平均值、基线、正常范围和评估。
- `queryStressLevel(days, timezone)`：每日平均压力和可用的压力分类。

## 恢复与体能

- `queryRecoveryStatus()`：当前恢复百分比、恢复等级、预计完全恢复时间。
- `queryFitnessAssessmentOverview()`：VO2max、跑力、阈值配速、比赛预测。
- `queryTrainingLoadAssessment(days)`：短期负荷、长期负荷、负荷比和评价。
- `queryTrainingSchedule(startDate, endDate, timezone)`：日期范围内的计划训练。

## 运动记录

调用 `querySportRecords` 获取活动列表。重要参数：

- `startDate`、`endDate`：`yyyyMMdd`。
- `limit`：日常检查用 20，周复盘用 50，长期趋势用 100。
- `sportTypeCodes`：跑步用 `[100,101,102,103]`，所有运动用 `[65535]`。
- `timezone`：通常使用 `Asia/Shanghai`。
- 如果工具 schema 要求可选过滤字段，未使用的文本字段填空字符串，未使用的数字范围填 `0`。

跑步运动类型：

- `100`：户外跑
- `101`：室内跑
- `102`：越野跑
- `103`：田径场跑
- `104`：徒步

## 活动详情

对重要跑步调用 `getActivityDetail(labelId, sportType)`。可能返回：

- 训练时长
- 距离
- 平均配速、移动配速、调整配速
- 最快公里
- 平均心率
- 步频
- 步幅
- 爬升/下降
- 热量
- 训练负荷
- 表现评价

只有当用户要求针对配速稳定性、速度、心率等重点做教练式分析时，才调用 `analyzeActivityDetail(labelId, sportType, focus)`。

## 圈速、分段和 FIT

马拉松训练分析中，活动列表和平均值不够用。以下场景必须补充深层活动数据：

- 长距离：调用 `queryActivityLapData(labelId, sportType)`，分析 5 km、10 km、后半程和最后 20-30 分钟的配速、心率、步频、功率变化。
- 马拉松配速课：调用 `queryActivityLapData()`；若用户指定“最后 N 分钟”“第 X 段马配”或活动有明确时间窗，调用 `queryCustomActivityLapData(labelId, sportType, startTimestamp, endTimestamp)`。
- 间歇课：调用 `queryActivityLapData()`，识别快速段、恢复段、重复次数、最快/最慢差异、心率恢复和末段衰减。
- 比赛或关键训练：若 MCP 客户端支持二进制资源，可调用 `downloadActivityFitFiles()`；否则使用 `queryActivityFitFileDownloadUrls()` 作为 FIT 文件兜底，但不要在不需要时消耗每日下载额度。

从 `querySportRecords` 获取 `labelId`、`sportType`、`startTimestamp`、`endTimestamp` 后，再调用圈速和自定义分段工具。若用户只问普通日常建议，不要过度抓取 FIT。

圈速 JSON 可交给 `scripts/analyze_laps.py` 生成紧凑摘要；MCP 文本结果可交给 `scripts/build_coros_summary.py` 归一化。

## 常用查询窗口

- 今日建议：最近 7 天。
- 周复盘：最近 7-14 天。
- 训练负荷判断：最近 7-14 天。
- 比赛计划：最近 60-90 天，加当前恢复、30 天负荷、训练计划、体能评估、关键活动圈速。
- 全面列数据：最近 7 天健康/睡眠/恢复，加最近 7-14 天运动；用户另有要求时按用户范围。
