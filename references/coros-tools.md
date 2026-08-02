# COROS MCP 工具参考

用户在中国或工作区时区为中国时，默认使用 `Asia/Shanghai`。日期范围工具使用 `yyyyMMdd`。

## 调用方式

优先使用 agent 原生的 `coros` MCP tools。若当前 agent 没有直接 MCP tool bridge，但本机安装了 `coros-mcp`，使用 CLI 兜底：

```bash
coros-mcp list-tools --refresh
coros-mcp call-tool --tool queryRecoveryStatus --arguments-json '{}'
coros-mcp call-tool --tool queryDailyHealthData --arguments-json '{"days":7}'
```

复杂参数也放在 `--arguments-json` 中，字段名保持英文。不要输出或记录 token、OAuth state、poll token、授权链接或回调参数。若 CLI 返回授权错误，读取 `references/coros-auth.md` 并使用授权脚本。

## 用户资料与设备

- `queryUserInfo()`：身高、体重、生日、性别、昵称。
- `queryDevices()`：绑定设备、序列号、保修信息。

## 日常健康

- `queryDailyHealthData(days)`：每日步数、热量、运动分钟、平均压力和睡眠摘要。
- `querySleepData(startDate, endDate, days)`：睡眠分数、主睡眠时长、睡眠窗口、深睡/浅睡/REM/清醒比例、清醒时长与次数、小睡。睡眠按醒来日期归属。
- `queryAvgHeartRate(startDate, endDate, days)`：每日平均心率。
- `queryRestingHeartRate(days)`：每日静息心率。
- `querySleepHrv(startDate, endDate, days)`：官方睡眠 HRV 评估、基线、正常范围和原始点；不要自己从原始点重算官方日均值。
- `queryStressLevel(days)`：每日平均压力。
- `queryHealthCheckTimeSeries(startDate, endDate, days)`：健康检测的心率、HRV、压力、呼吸率和 SpO2 时序。
- `queryStressTimeSeries(startDate, endDate, days)`：压力、压力 HRV 和压力心率原始时序。

## 恢复与体能

- `queryRecoveryStatus()`：当前恢复百分比、恢复等级、预计完全恢复时间。
- `queryFitnessAssessmentOverview()`：VO2max、跑力、阈值配速、比赛预测。
- `queryTrainingLoadAssessment(days)`：短期负荷、长期负荷、负荷比和评价。
- `queryTrainingSchedule(startDate, endDate)`：日期范围内的计划训练。内部 Plan ID 只用于后续工具调用，不展示给用户。

## 运动记录

调用 `querySportRecords` 获取活动列表。重要参数：

- `startDate`、`endDate`：`yyyyMMdd`。
- `limit`：日常检查用 20，周复盘用 50，长期趋势用 100。
- `sportTypeCodes`：跑步用 `[100,101,102,103]`，所有运动用 `[65535]`。
- 日期使用用户 COROS 时区；工具不接受 `timezone` 字段，报告中注明实际时区。
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
