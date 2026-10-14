# 门控 MCP Server（本地 stdio）

`scripts/gating_mcp.py` 把确定性门控脚本封装为标准 MCP server，供 WorkBuddy 等桌面 harness 经连接器直接获得代码级安全门控——用户不需要会跑 Python 脚本，只需一次性安装 Python 和 `pip install mcp`。

## 关键属性

- **纯本地 stdio**：由 harness 作为子进程拉起，无服务器、无端口、无远程部署；数据全程不出本机。
- **不提供远程托管形态**：云端平台（扣子等）的连接器只支持公网 URL，接不了 stdio；为它们做远程版意味着健康数据出本机，与 PRIVACY.md 姿态冲突，明确不做。云端平台维持"知识库降级模式"。
- 调度核心不依赖 SDK；只有 server 管道需要 `pip install mcp`。

## 安装与自检

```bash
pip install mcp
python3 scripts/gating_mcp.py --selfcheck
# {"status": "ok", "tools": {"build_athlete_context": "ok", ...}}
```

自检不需要 SDK；四项全 ok 说明调度层、安全校验、档案读写与脱敏拒绝都正常。

## 暴露的 Tools

| Tool | 输入 | 输出 |
|---|---|---|
| `build_athlete_context` | `bundle`（手表数据归一后的 JSON）、可选 `profile`（运动员档案对象） | AthleteContext V2（覆盖度、基线、readiness、风险标记） |
| `evaluate_context` | `summary`（AthleteContext）、可选 `markdown` | readiness 评估、下一步行动、停止规则、降级选项 |
| `validate_prescription` | `prescription`（TrainingPrescription）、可选 `context` | 校验结果；违反安全上限时带保守 `safe_fallback` |
| `archive_snapshot` | `action: write/show/stats` + 对应字段（同 `archive_snapshot.py` CLI） | 档案写入（写入前脱敏扫描，命中即 `archived: false` + 原因）、查询或基线统计 |

错误处理：所有工具异常都转为结构化 `{"error": ...}` 返回给客户端，server 不中断。

## 连接器配置

配置本质相同：命令 `python3`，参数为脚本绝对路径。

<details>
<summary>ZCode / Codex / Claude Desktop 风格（mcpServers JSON）</summary>

```json
{
  "mcpServers": {
    "running-coach-gating": {
      "command": "python3",
      "args": ["/path/to/skills/running-coach/scripts/gating_mcp.py"]
    }
  }
}
```

</details>

<details>
<summary>WorkBuddy 连接器</summary>

在「连接器」中添加本地 MCP（stdio 类型），命令填 `python3`，参数填脚本绝对路径。具体入口名称以 WorkBuddy 当前版本为准。

</details>

脚本路径用绝对路径（如 `~/.agents/skills/running-coach/scripts/gating_mcp.py`）；档案默认仍写 `~/.running-coach/archive/`（可用每次调用的 `archive_dir` 参数覆盖）。

## 与 COROS 数据接入的关系

本 server 只做**门控与档案**，不做取数。COROS 数据仍经 COROS MCP 或 `coros-mcp` CLI 获取，佳明经 `garmin_to_bundle.py`。一个常见的组合配置是：连接器里同时挂 COROS MCP（取数）+ 本 server（门控归档），agent 负责在两者之间传递 bundle。

## 升级

skill 更新后（`git pull`）server 无需重配置——它引用的是同一目录下的脚本，下次 harness 重启子进程即生效。
