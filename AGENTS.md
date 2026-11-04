# AGENTS.md

给在这个仓库里工作的 AI 编码代理（Codex、ZCode、Claude Code 等）的速查指南。更多信息：使用与安装见 [README.md](README.md)，完整 pre-PR 清单见 [CONTRIBUTING.md](CONTRIBUTING.md)，隐私姿态见 [PRIVACY.md](PRIVACY.md)，技能运行时行为见 [SKILL.md](SKILL.md) 本身。

## 这个仓库是什么

一个面向跑步者的 **Agent Skill**（agentskills.io 开放格式），技能名固定为 `running-coach`。它不是传统应用，而是「技能入口 + 教练规则库 + 确定性脚本」三件套：安装进 agent harness 的 skills 目录（如 `~/.agents/skills/running-coach`）后，由 agent 按教练流程消费用户手表数据（高驰 COROS / 佳明 Garmin），产出可校验的训练建议。

核心管线（数据流）：

```text
手表数据（COROS MCP / coros-mcp CLI / garmin_to_bundle.py）
  → bundle JSON
  → build_athlete_context.py   → AthleteContext V2（覆盖度、7/28/56 天基线、风险标记）
  → evaluate_context.py        → readiness（green/yellow/red）+ 保守基础处方
  → 模型综合环境/补给/伤病修正  → TrainingPrescription
  → validate_prescription.py   → 校验安全上限（失败则采用返回的 safe_fallback）
  → 输出建议 + 停止规则
  → archive_snapshot.py        → 脱敏快照写入仓库外本地档案（默认 ~/.running-coach/archive/）
```

设计哲学：**数值聚合、趋势、门控与校验全部交给脚本（确定性），模型只做语义综合**。`references/metrics.md` 是全 skill 数值阈值的唯一来源。

## 仓库布局

| 路径 | 作用 |
| --- | --- |
| `SKILL.md` | 技能入口：核心流程、最小取数、安全边界、输出契约。只写核心工作流 |
| `references/` | 20 篇按需加载文档：阈值（`metrics.md`）、数据接入（`coros-tools.md`/`garmin-tools.md`/`coros-auth.md`）、分析规则（`coros-analytics.md`/`fit-deep-review.md`）、Schema（`v2-schemas.md`）、输出模板、教练性格（`coach-personas.md`）、本地档案、门控 MCP 等 |
| `scripts/` | 11 个 Python 脚本：管线工具 + `gating_mcp.py`（本地 stdio MCP server） |
| `agents/openai.yaml` | harness 依赖清单：声明远程 COROS MCP（streamable_http） |
| `examples/` | 合成数据 + 示例 prompts/outputs，用于端到端回放 |
| `tests/` | 6 个测试文件、95 个用例；fixture 由 `make_fixtures.py` 生成 |
| `.github/workflows/ci.yml` | CI：编译 + 单测 + 合成示例回放 + SKILL.md 元数据校验 + 垃圾/敏感文件扫描 |

## 脚本速查

| 脚本 | 职责 |
| --- | --- |
| `build_athlete_context.py` | 结构化 bundle → AthleteContext V2；`--profile` 合并本地运动员档案 |
| `build_coros_summary.py` | 旧版 COROS MCP 文本 → V1 摘要（过渡方案，bundle 稳定后废弃） |
| `evaluate_context.py` | readiness 评估 + 保守基础处方 |
| `validate_prescription.py` | 校验 TrainingPrescription 安全上限，违规时给出保守 `safe_fallback` |
| `analyze_laps.py` | 圈速分段、心率漂移、间歇稳定性、后段衰减 |
| `analyze_fit.py` | FIT 细粒度复盘（GAP、坡度-配速-心率耦合、爆点、HRR；唯一允许用 `fitdecode` 的脚本） |
| `garmin_to_bundle.py` | 佳明数据归一为标准 bundle（`--login` 重建 garth token，存 `~/.garmintokens`） |
| `coros_auth_bootstrap.py` | COROS 授权引导与只读接口验证 |
| `gating_mcp.py` | 门控与档案工具封装为本地 stdio MCP server（`--selfcheck` 自检，无需 SDK） |
| `archive_snapshot.py` | 瘦身脱敏快照归档（按月 JSONL、upsert 去重）+ `--show/--stats` 查询 |
| `save_report.py` | 仅在用户明确要求时保存 Markdown 报告 |

## 硬性约束（违反会被 CI 或审查打回）

1. **分层纪律**：核心流程变更才动 `SKILL.md`；教练规则细节进 `references/`；确定性可复用逻辑进 `scripts/`。
2. **阈值唯一来源**：数值阈值（readiness 降档条件、负荷比区间、静息心率偏移等）只改 `references/metrics.md`；其他文档只引用结论，不复制数值。
3. **Python ≥3.8 标准库 only**：`fitdecode` 仅限 `analyze_fit.py` 的 FIT 二进制路径；每个脚本保留 `from __future__ import annotations`。
4. **只用合成数据**：examples/tests 禁止真实健康导出、token、OAuth 回调 URL、密码、私有活动文件。CI 按文件名扫描 `.fit/.gpx/.tcx/*token*/*secret*/*password*`。
5. **用户本地状态永远在仓库外**：档案与归档在 `~/.running-coach/`，garth token 在 `~/.garmintokens`；测试不得指向真实路径。
6. **隐私红线**：不输出/不保存 token、OAuth state、授权链接、GPS 轨迹坐标、原始逐秒数据；FIT 原件仅 race-review 时下载到临时目录、解析后立即删除。
7. **技能元数据**：SKILL.md frontmatter 的 `name: running-coach` 不可改（CI 校验）；CI 还要求一批关键文件存在（见 `ci.yml` 的 Validate skill metadata 步骤，新增/重命名关键文件后同步该清单）。

## 常用命令

```bash
# 最小验证（改完任何脚本后必跑）
PYTHONPYCACHEPREFIX=/tmp/rc-pycache python3 -m py_compile scripts/*.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/gating_mcp.py --selfcheck

# 合成示例端到端回放（完整清单见 CONTRIBUTING.md，与 CI 步骤一致）
python3 scripts/analyze_laps.py --input examples/laps.json --json
python3 scripts/build_athlete_context.py --input examples/athlete-bundle.json --profile examples/athlete-profile.json > /tmp/athlete-context.json
python3 scripts/validate_prescription.py --input examples/prescription-safe.json --context /tmp/athlete-context.json
python3 scripts/archive_snapshot.py --input examples/athlete-bundle.json --context /tmp/athlete-context.json --archive-dir /tmp/rc-archive
```

提示：本地跑 Python 会生成 `__pycache__`（已 gitignore，但 CI 的垃圾检查是物理 `find`）。导出 `PYTHONPYCACHEPREFIX=/tmp/rc-pycache` 与 CI 行为一致，保持工作区干净。

## 测试结构

| 文件 | 覆盖 |
| --- | --- |
| `tests/test_scripts.py` | 圈速分析、FIT 分析、上下文构建/评估、处方校验、报告保存 |
| `tests/test_v2.py` | V2 Schema 端到端（bundle → context → 评估） |
| `tests/test_archive.py` | 档案记录构建、upsert 去重、脱敏扫描、查询 |
| `tests/test_garmin.py` | 佳明 fixture 归一化与管线回归（含字段变体、fetch/login 模拟，不触网） |
| `tests/test_coros_auth.py` | COROS 认证脚本：脱敏、错误分类、退出码、登录流程（stub subprocess，无网络） |
| `tests/test_gating_mcp.py` | MCP 工具分发与档案工具 |

fixture 由 `tests/make_fixtures.py` 生成（`tests/fixtures/garmin_raw.json` 除外，为手工维护）；改 fixture 格式时同步重新生成。

## 双位置工作流（维护者本机）

开发仓库（本仓库）与安装副本分离，安装副本是 harness 实际加载的位置（如 `~/.agents/skills/running-coach`）：

- **修改并推送后必须同步安装副本**（在副本目录 `git pull`），否则 harness 用的还是旧版。
- `gating_mcp.py` 引用的是安装副本目录下的脚本，skill 升级后无需重配置连接器，重启 harness 子进程即生效。

## 风格

- 提交信息：英文祈使句单行标题（参考 `git log`，如 "Add Garmin adapter: normalize Connect data into the shared pipeline"）。
- 文档语言：`SKILL.md` 与 `references/` 以中文为主，README 中英双语；新文档跟随所在目录的既有语言。
- 脚本 CLI 文案中英混合已有先例（usage 英文、功能描述中文），保持各脚本内部一致即可。
