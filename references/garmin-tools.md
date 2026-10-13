# 佳明 Garmin 数据接入

佳明用户经 `scripts/garmin_to_bundle.py` 把数据归一为标准 bundle 后，走与 COROS 完全相同的门控、处方、归档流程。本文档只讲佳明侧的差异。

## 接入方式（三选一）

1. **脚本直连（推荐）**：`pip install garminconnect garth` 后：
   ```bash
   python3 scripts/garmin_to_bundle.py --login          # 首次登录（交互式，支持 MFA），token 存 ~/.garmintokens
   python3 scripts/garmin_to_bundle.py --fetch --days 7 --output /tmp/garmin-bundle.json
   ```
2. **社区 garmin MCP server**：把 MCP 工具返回的原始 JSON 按本页映射表组装后，用 `--input` 归一。
3. **手动粘贴**：从 Garmin Connect 导出的 JSON 片段同样走 `--input`（字段名见映射表，缺失项容忍）。

凭证只保存在本机 garth token 目录；不输出、不入库。

## 字段映射表

| bundle 键 | 佳明来源 | 归一逻辑 |
|---|---|---|
| `sleep` | `get_sleep_data` 的 `dailySleepValues` | `sleepTimeSeconds`→时长小时；`sleepScores.overall`→分数 |
| `sleep_hrv` | `get_hrv_data` 的 `hrvSummary` | `lastNightAvg`→HRV 值；`baseline`→基线（rMSSD 口径） |
| `resting_hr` | RHR 接口（按 garminconnect 版本取可用者） | `restingHeartRate` |
| `stress` | `get_stress_data` | 有日均值用日均值；否则 `stressValuesArray` 求均值 |
| `training_load` | `get_training_status.currentTrainingLoad` | 有 `acute`/`chronic` 则算负荷比；缺负荷时走 metrics.md 的替代路径 |
| `recovery` | `get_training_readiness`（或 Body Battery） | `score`→恢复百分比，`source` 标明语义来源 |
| `activities` | `get_activities_by_date` | `activityId`、`typeKey`、米→公里、秒→分钟、`averageHR` |
| `fitness` | `training_status` 等 | `vO2Max`（按可得性） |

## 语义差异（必须向用户说明）

- **Training Readiness ≠ COROS 恢复度**：佳明的"训练准备度"混合了睡眠、负荷史、HRV 状态、压力等多因素；COROS 恢复度更接近短期恢复。门控阈值通用，但对比历史时只与佳明自己的纵向比较。
- **HRV 口径**：佳明为睡眠 rMSSD（毫秒）。数值体系与 COROS、苹果 SDNN 不可横向比较；换表后基线必须重建（见 `personal-baselines.md` 多数据源基线）。
- **比赛预测**：佳明 Connect 的预测不在 `garmin_to_bundle` 输出里；配速建议绑定阈值、近期同类训练或心率/RPE 的规则不变。
- **训练负荷缺失时的降级**：负荷比拿不到时按 metrics.md 用频率、时长、长距离、质量课密度替代，并降低置信度。

## 比赛深度复盘（FIT 复用）

race-review 不用重新造轮子：佳明活动可直接下载 FIT，喂给现有管线：

```python
garmin.download_activity(activity_id, dl_fmt=garmin.FIT)  # 得到 .fit 文件
```

再按 `references/fit-deep-review.md` 的临时目录流程交给 `scripts/analyze_fit.py --fit`（需 `pip install fitdecode`），用后即删。圈速分析可用 `get_activity_splits` 的输出手工组装后交 `analyze_laps.py`（佳明分段结构与 COROS lapGroups 不同，暂无自动转换）。

## 已知局限

- `get_resting_hr` 等端点名称随 garminconnect 版本变动；`--fetch` 对每个端点独立容错，单端点失败不影响其余数据，缺失项按数据质量规则降级。
- 佳明官方无 MCP；社区 server（garmin_mcp 等）输出结构不稳定，优先用脚本直连。
- 活动列表不含轨迹坐标；坐标只会出现在 FIT 原件里，按隐私规则处理。
