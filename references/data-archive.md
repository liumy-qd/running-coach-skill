# 本地数据档案

每次从 COROS 取到的真实数据在回答后即丢失，导致：基线只能靠当次取数窗口、时区/日期问题要事后修、分析结论容易滞后。数据档案把每次取数抽成**瘦身快照**落盘，随时间积累成个人历史。

## 位置与格式

- 默认目录：`~/.running-coach/archive/`。可用 `--archive-dir` 或环境变量 `RUNNING_COACH_ARCHIVE` 覆盖（例如指向 `~/KnowledgeBase/raw/running-coach/`）。
- 档案**必须位于仓库外**；本仓库是公开的，健康数据绝不能进版本库（`.gitignore` 中的 `archive/` 只是防御性兜底）。
- 格式：按月一个 JSONL 文件（`2026-10.jsonl`），每行一条记录。

## 记录内容（瘦身指标）

每条记录按 `(date, record_type)` 唯一，重复检查同一天是 upsert 更新（`revision` 递增），不是堆积：

- `health`：睡眠时长/分数、HRV 值/基线、静息心率、压力均值、负荷比。
- `recovery`：恢复百分比与等级。
- `activities`：活动摘要（labelId、类型、日期、距离、时长、配速、心率、负荷），按 labelId 去重合并。
- `readiness`：等级、动作、风险 flag 代码。
- `prescription`：已校验处方的决策与课表摘要。
- `analysis`：`analyze_laps`/`analyze_fit` 的摘要与 flags（不含逐公里明细）。
- `notes`：主观备注（疲劳、场地、补给）。

## 脱敏规则（硬约束，违反即拒绝写入）

`archive_snapshot.py` 写入前扫描整条记录，命中即报错退出、不落盘：

- 字段名包含 token/secret/oauth/password/authorization、坐标（latitude/longitude/position/gps）、经期相关字样。
- 长度超过 500 的纯数值数组（逐秒原始数据启发式）。
- 瘦身层本身只保留白名单字段，未知字段直接丢弃。

FIT 原件、GPS 轨迹、逐秒数据一律不入档；经期数据按 SKILL.md 规则从不进入长期档案。

## 使用方式

```bash
# 归档一次检查（bundle 是 build_athlete_context.py 的输入）
python3 scripts/archive_snapshot.py --input bundle.json --context context.json \
  --prescription rx.json --type daily_check --notes "田径场，课间停表"

# 查询与统计
python3 scripts/archive_snapshot.py --show --days 28
python3 scripts/archive_snapshot.py --stats --days 28

# 试写（不落盘）；补录历史指定日期
python3 scripts/archive_snapshot.py --input bundle.json --dry-run
python3 scripts/archive_snapshot.py --input bundle.json --date 2026-09-28
```

## 与训练闭环的关系

- 归档发生在回答之后：先完成取数、门控、处方和校验，再落档。
- 积累数周后，7/28/56 天个人基线优先从档案计算（`--stats`），当次取数窗口只作补充；档案与当次数据冲突时说明冲突，不静默覆盖。
- 周复盘前先 `--show --days 7`，检查执行率、超纲和恢复趋势，再对照本周计划。
- 用户明确要求删除时，删除对应月份文件即可（按月文件，无外部索引）。
