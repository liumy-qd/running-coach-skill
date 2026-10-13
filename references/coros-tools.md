# COROS MCP 工具参考

用户在中国或工作区时区为中国时，默认使用 `Asia/Shanghai`。日期范围工具使用 `yyyyMMdd`。

## 调用方式

数据接入有两条等价通路：`agents/openai.yaml` 声明的远程 COROS MCP（供支持依赖清单的 harness 自动配置），和本机 `coros-mcp` CLI（通用兜底）。优先使用 agent 原生的 `coros` MCP tools；没有 bridge 时用 CLI：

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
- 比赛深度复盘（`race-review`）：调用 `queryActivityFitFileDownloadUrls(labelId, sportType)` 获取 FIT 下载地址，按 `references/fit-deep-review.md` 的临时目录流程下载、用 `scripts/analyze_fit.py` 解析、解析后立即删除。下载地址是短期签名凭证，不要回显。
- 其他场景不要消耗 FIT 每日下载额度。

从 `querySportRecords` 获取 `labelId`、`sportType`、`startTimestamp`、`endTimestamp` 后，再调用圈速和自定义分段工具。若用户只问普通日常建议，不要过度抓取 FIT。

圈速 JSON 可交给 `scripts/analyze_laps.py` 生成紧凑摘要；MCP 文本结果可交给 `scripts/build_coros_summary.py` 归一化（V1 过渡方案，结构化 bundle 优先用 `scripts/build_athlete_context.py`）。

## 已知数据局限

实测中以下端点或字段经常缺失，调用时按此预期：

- `queryHealthCheckTimeSeries`：多数账号无数据。空结果不重试超过一次，改用 `querySleepHrv`、`queryStressLevel` 或 `queryStressTimeSeries` 覆盖同样需求。
- 左右触地平衡/步态对称：COROS 数据源目前不提供，跑姿分析中明确标注缺失，不要虚构。
- 日常健康数据密度：心率每日仅 1 个均值，HRV 约每 10 分钟 1 点，压力约每 5 分钟 1 点；做不了日内心率曲线时改用 FIT（仅 race-review）或直接标注密度限制。

## 常用查询窗口

- 今日建议：最近 7 天。
- 周复盘：最近 7-14 天。
- 训练负荷判断：最近 7-14 天。
- 比赛计划：最近 60-90 天，加当前恢复、30 天负荷、训练计划、体能评估、关键活动圈速。
- 全面列数据：最近 7 天健康/睡眠/恢复，加最近 7-14 天运动；用户另有要求时按用户范围。
