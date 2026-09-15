# 比赛/关键训练深度复盘（FIT 细粒度）

普通周复盘用活动列表和圈速就够。只有用户明确要求深度复盘一场比赛或关键训练（`race-review`）时才走本流程。分析框架见本文，确定性计算交给 `scripts/analyze_fit.py`。

## 数据获取与隐私红线

1. `queryActivityFitFileDownloadUrls()` 拿下载地址；地址是带签名的短期凭证，不要回显、不要写进报告。
2. 下载到临时目录，解析完成后立即删除；不要保留 FIT 原件。

```bash
TMP=$(mktemp -d)
curl -sL "<下载地址>" -o "$TMP/activity.fit"
python3 scripts/analyze_fit.py --fit "$TMP/activity.fit" --threshold-hr 170
rm -rf "$TMP"
```

3. 只保留派生统计（分段、漂移、爬升、区间分布）。不输出 GPS 轨迹坐标、不输出原始逐秒数据、不把 FIT 内容写入归档。
4. 拿不到 FIT 时降级：用 `queryActivityLapData()` + 活动详情做有限复盘，并明确说明"无 FIT，坡度关联/同配速漂移/跑姿衰减等结论不可用"，置信度按 `data-quality.md` 降低。

## FIT 记录里有什么

FIT 的 record message 通常每秒一条，关键字段：

- `timestamp`、`distance`（累计米）、`speed`（m/s）
- `heart_rate`、`cadence`、`power`（跑步功率，视设备）
- `enhanced_altitude`/`altitude`（米）、`grade`（%，注意换算成小数）、`vertical_speed`
- `temperature`（摄氏度，手表估温）
- `position_lat/long`：**一律忽略**，分析不需要坐标
- lap 触发事件：手动/自动分段的边界

字段可能不全（IGPS 丢失、无功率计、无温度传感器）。分析输出里必须报告字段覆盖度，缺字段的结论降级。

## 归一化 JSON 格式

`analyze_fit.py --input` 接受的格式（也方便自测）：

```json
{
  "meta": {"name": "...", "sport": "marathon", "start_time": "..."},
  "records": [
    {"ts": 1726368000, "dist": 1000.0, "speed": 3.1, "hr": 155,
     "cad": 178, "alt": 52.0, "grade": 0.02, "temp": 22, "power": 240}
  ]
}
```

除 `ts` 外全部可选；缺 `dist` 或 `speed` 时脚本会从另一个积分/差分补齐。

## 脚本已经算好的（不要手工重算）

| 输出 | 含义 |
|---|---|
| `splits` | 每公里配速、GAP、心率、爬升、坡度、停表秒数 |
| `balance` | 前后半程配速差、分段离散度 CV、最快/最慢公里 |
| `grade_bins` | 坡度分桶的时间、配速、GAP、心率 |
| `climbs` | 前 3 大持续爬坡段：位置、长度、爬升、均坡、配速、心率 |
| `drift` | 同配速（速度分箱）前后半程心率漂移 |
| `efficiency` | 平路效率因子 EF = 速度/心率，前 1/3 vs 后 1/3 |
| `blowups` | 爆点：相邻公里配速骤降 >8% 且心率接近峰值（自动排除含停表的分段） |
| `stops` | 停表/步行时段：位置和时长 |
| `cadence` | 前 1/3 vs 后 1/3 步频衰减 |
| `hr_zones` | 心率区间时间分布（给 `--threshold-hr` 更准，否则按最高心率估算） |
| `flags` | 规则化标记（split_imbalance / hr_drift / ef_decay / blowup / temp_drift 等） |

GAP 是 Minetti 能量成本多项式换算的估计配速，用于解释"配速变慢是不是坡造成的"，不是实测能力。

## 关联性解读规则

单指标异常先找解释，再下结论：

- **配速掉 = 坡度掉？** 对比每公里 `pace` 和 `gap`：GAP 平稳而实际配速变慢，是坡的代价，不是能力问题；GAP 也同步变差才是真的掉速。
- **心率升 = 疲劳还是热？** `drift` 显示同配速心率上升后，交叉看 `temp_start→temp_end`：温度升 ≥5°C 时热解释优先，但仍要结合补给反馈（脱水也表现为漂移）。爬坡段的心率升高不算漂移。
- **爆点定位要三问**：爆点前 2 km 是否有长爬坡（`gain_prev2_m`）？附近是否有停表/补给（`stops`）？爆点时 `gap` 是否同步恶化（真崩）还是只有 `pace` 恶化（坡）？三问之后再谈"糖原耗尽/配速策略失误"。
- **下坡恢复能力**：陡下坡分桶里 GAP 应明显快于平路且心率回落；下坡配速快不起来、心率居高，提示股四头肌离心疲劳或下坡技术保守。
- **EF 下降的含义**：平路 EF 后 1/3 下降 ≥8% 属于明确的经济性/疲劳衰减；结合步频衰减区分"腿断了"（步频掉）和"心肺顶不住"（心率顶格）。
- **时间分配**：`hr_zones` 若 Z5 占比异常高，说明前半程透支——对照 `balance` 的前半程配速差确认是否起跑过快。

## 综合输出要求

1. 先给 3-5 条"这个结果说明什么"的核心结论，每条回指具体分段/漂移/爆点数据。
2. 把失败或超常归因拆成：配速策略、坡度策略、补给策略、环境、训练准备，各自给证据等级（FIT 实测 / 用户反馈 / 推测）。
3. 每条归因给出下一训练周期的可执行改动（例如：坡度专项课、30 km 后的补给演练、前半程纪律目标配速）。
4. 若复盘后要给后续训练处方，仍然走 `TrainingPrescription` + `validate_prescription.py` 流程。
5. 输出模板见 `output-templates.md` 的"比赛深度复盘"。
