---
name: running-coach
description: 个人跑步数据管理、跨平台授权、每日恢复门控、活动分析、训练处方、周复盘、比赛深度复盘和目标赛事计划工作流，支持高驰 COROS 与佳明 Garmin 手表。Use when the user asks about COROS/高驰 or Garmin/佳明 watch data or login, daily readiness, sleep HRV, resting heart rate, stress, recovery, training load, running fitness, race predictions, FIT/lap/segment analysis, weekly review, race deep review, running form or gait analysis, injury or fatigue risk, weather or fueling impact, or 5K/10K/half-marathon/marathon planning. Also trigger on 今天能不能跑、要不要跑步、膝盖疼还能跑吗、配速怎么样、比赛复盘、深度复盘一场比赛、看看我的跑姿.
---

# Running Coach

## 核心流程

数据接入按手表品牌选择通路：COROS 优先使用 `coros` MCP，当前 agent 没有原生 bridge 时用 `coros-mcp call-tool`；佳明用 `scripts/garmin_to_bundle.py` 抓取或归一（见 `references/garmin-tools.md`）。不要输出或保存 token、OAuth state、poll token、授权链接、回调参数或真实健康导出。FIT 原件仅在 `race-review` 时下载到临时目录、解析后立即删除（流程见 `references/fit-deep-review.md`）；任何时候不输出 GPS 轨迹坐标和原始逐秒数据。

1. 将请求分类为 `daily-check`、`weekly-review`、`activity-review`、`race-review`、`form-review`、`race-plan`、`data-inventory` 或 `coros-auth`。
2. 获取完成任务所需的最小数据，按手表品牌读取对应接入文档：COROS 读 `references/coros-tools.md` 并严格按实时工具 Schema 传参；佳明读 `references/garmin-tools.md` 用 `scripts/garmin_to_bundle.py` 归一后走同一流程。目标链、锁定配速、场地与停表习惯等长期上下文优先读本地运动员档案（`references/athlete-profile.md`），缺项再问用户。
3. 遇到未登录、授权过期或 `401` 时按品牌处理：COROS 读 `references/coros-auth.md` 并运行 `scripts/coros_auth_bootstrap.py --mode auto`；佳明运行 `scripts/garmin_to_bundle.py --login` 重建本地 token（存 `~/.garmintokens`）。验证通过后继续原任务。
4. 将工具结果整理成紧凑上下文。结构化 bundle 使用 `scripts/build_athlete_context.py`；旧版 MCP 文本可继续使用 `scripts/build_coros_summary.py`。
5. 先执行确定性恢复与风险门控，再进行语义综合。数值聚合、趋势、负荷比、漂移和处方约束交给脚本，不让模型凭长文本估算。
6. 普通日常建议和周复盘不下载 FIT。仅 `race-review` 按临时下载流程解析 FIT 做细粒度分析；`race-plan` 仍以圈速为主。
7. 生成 `TrainingPrescription`，再用 `scripts/validate_prescription.py` 校验。模型不得把 `yellow/red` 的安全上限升级为高强度。
8. 输出观察、推断、行动和不确定性；提供停止规则、降级选项、反馈问题与下一检查点。
9. 回答完成后，按 `references/data-archive.md` 用 `scripts/archive_snapshot.py` 把本次取数归档为瘦身快照（默认 `~/.running-coach/archive/`，仓库外）。归档在输出之后进行，失败不阻塞回答，但必须告知用户。

## 最小取数

- `daily-check`：近 7 天睡眠、睡眠 HRV、静息心率、压力、恢复、训练负荷和运动记录；有主观疲劳、疼痛或环境信息时一并纳入。
- `weekly-review`：追加体能评估；对最长跑、质量课、比赛和最近高负荷跑读取详情与圈速。
- `activity-review`：先定位活动，再读取详情和圈速；指定最后 N 分钟或精确时间段时使用自定义分段。
- `race-review`：定位比赛或关键活动，下载并解析 FIT（临时目录、用后即删），补充目标与计划配速、补给计划、用户分段记忆和当天天气；再结合近 30-90 天训练史解读。
- `form-review`：定位活动读取详情（步频/步幅/触地时间若有）与圈速；照片由用户提供；有 FIT 解析结果时结合步频衰减与 HRR。分析规则见 `references/coros-analytics.md`，结论当日归档。
- `race-plan`：体能评估、恢复、30 天负荷、训练日程、60-90 天活动和关键活动圈速；按需读取天气、补给和全马参考。
- `data-inventory`：列出覆盖范围、日期、时区、数据源和缺失项；不要为“全面”而默认下载 FIT。

月经周期数据只在用户明确提出周期相关问题时临时查询；不要纳入默认检查、长期上下文或报告归档。

## 判断与安全边界

- 先用个人 7/28/56 天基线，再参考通用阈值。关键数据不足时降低置信度，不伪造基线。
- 至少使用两个相互支持的信号下强结论；信号冲突时明确冲突并采用保守选项。
- `red`：只允许休息、步行或恢复活动；`yellow`：最高为轻松强度；`green`：仍需满足计划、训练史和环境约束才允许质量课。
- 胸痛、晕厥、异常呼吸/心律、影响步态的疼痛或热病表现优先停止训练并建议专业评估。不要进行医疗诊断。
- 厂商预测成绩（COROS、佳明等）仅作体能信号。配速建议必须绑定阈值、近期同类训练、目标或心率/RPE。

## 输出契约

输出分两档：

- 快答（`daily-check` 等日常快问）：一句话结论 + readiness + 关键依据 + 停止规则 + 下一检查点。
- 完整（`weekly-review`、`race-review`、`race-plan`、`data-inventory`，或用户要求详细时）：数据置信度、结论、证据窗口、观察、推断、训练处方、停止规则、降级选项、缺失数据、反馈问题和下一检查点。

两档都必须遵守 yellow/red 强度上限。所有回答先用一句话重述所问问题（时间、事件、数字用原词），多子问题逐条对应；详见 `references/output-templates.md` 通用守则。结构化输出遵循 `references/v2-schemas.md`。处方校验失败时，使用校验器返回的保守方案，并说明失败原因。

## 按需参考

- COROS 工具与参数：`references/coros-tools.md`
- 佳明数据接入（映射、语义差异、FIT 复用）：`references/garmin-tools.md`
- 门控 MCP Server（本地 stdio，供 WorkBuddy 等桌面连接器）：`references/mcp-server.md`
- 授权和远程环境：`references/coros-auth.md`
- V2 上下文与处方 Schema：`references/v2-schemas.md`
- 覆盖度和来源置信度：`references/data-quality.md`
- 7/28/56 天个人基线：`references/personal-baselines.md`
- 本地运动员档案（目标链、锁定配速、长期约束）：`references/athlete-profile.md`
- readiness、负荷和安全门控（所有数值阈值的唯一来源）：`references/metrics.md`
- 圈速、漂移、间歇和关键活动：`references/coros-analytics.md`
- 比赛深度复盘与 FIT 细粒度分析：`references/fit-deep-review.md`
- 目标周期与全马：`references/training-goals.md`、`references/marathon-framework.md`
- 伤病风险、环境与补给：`references/injury-risk.md`、`references/environment.md`、`references/environment-sources.md`、`references/fueling.md`
- 计划执行复盘与输出模板：`references/plan-feedback-loop.md`、`references/output-templates.md`
- 本地数据档案（位置、脱敏、查询）：`references/data-archive.md`

## 可复用脚本

- `build_athlete_context.py`：将结构化数据 bundle 归一为 AthleteContext V2；`--profile` 可合并本地运动员档案（目标链、长期约束）。
- `build_coros_summary.py`：兼容旧版 COROS MCP 文本输入，输出 V1 字段加 V2 版本标记（过渡方案；coros-mcp 稳定输出结构化 bundle 后废弃）。
- `analyze_laps.py`：确定性分析分段、漂移、间歇稳定性和后段衰减。
- `analyze_fit.py`：FIT 细粒度复盘：公里分段与 GAP、坡度-配速-心率关联、同配速漂移、爆点、爬坡段、心率区间、心率恢复（HRR）。
- `evaluate_context.py`：评估 readiness 并生成保守的基础训练处方。
- `validate_prescription.py`：校验 LLM 或脚本生成的训练处方是否符合安全上限。
- `garmin_to_bundle.py`：把佳明 Garmin 数据（garminconnect 抓取或保存的原始 JSON）归一为标准 bundle，接入同一门控与归档流程。
- `coros_auth_bootstrap.py`：跨平台引导 COROS 授权并验证只读接口。
- `gating_mcp.py`：把门控与处方校验封装为本地 stdio MCP server（WorkBuddy 等桌面连接器用；管道需 `pip install mcp`，调度与自检不需要）。
- `save_report.py`：仅在用户要求保存时写入 Markdown 报告。
- `archive_snapshot.py`：把每次取数抽成瘦身快照归档到仓库外本地档案（按月 JSONL、upsert 去重、写入前脱敏扫描），并支持 `--show/--stats` 查询。

## 测试

`tests/test_scripts.py`、`tests/test_v2.py`、`tests/test_archive.py`、`tests/test_garmin.py` 覆盖全部脚本（含 36 个处方安全场景、FIT/圈速/佳明 fixture 回归与档案脱敏/upsert）。修改脚本或阈值后运行：

```bash
python3 -m unittest discover -s tests
```
