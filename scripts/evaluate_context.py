#!/usr/bin/env python3
"""从结构化 COROS 摘要评估 readiness、风险和下一步行动。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def read_text(path: str | None) -> str:
    if path:
        return Path(path).expanduser().read_text(encoding="utf-8")
    return sys.stdin.read()


def risk_rank(severity: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(severity, 0)


def choose_readiness(summary: dict[str, Any]) -> dict[str, Any]:
    coverage = summary.get("coverage") or {}
    risk = summary.get("risk") or {}
    recovery = summary.get("recovery") or {}
    flags = list(risk.get("flags") or [])
    reasons: list[str] = []

    if coverage.get("level") == "low":
        flags.append({"severity": "medium", "code": "coverage_low", "detail": "关键数据覆盖不足。"})
    elif coverage.get("level") == "medium":
        flags.append({"severity": "low", "code": "coverage_medium", "detail": "部分关键数据缺失。"})

    recovery_percent = recovery.get("recovery_percent")
    existing_codes = {flag.get("code") for flag in flags}
    if isinstance(recovery_percent, (int, float)):
        if recovery_percent < 40:
            if "recovery_very_low" not in existing_codes:
                flags.append({"severity": "high", "code": "recovery_very_low", "detail": "恢复百分比很低。"})
        elif recovery_percent < 60 and "recovery_low" not in existing_codes:
            flags.append({"severity": "medium", "code": "recovery_low", "detail": "恢复百分比偏低。"})

    max_risk = max((risk_rank(flag.get("severity", "")) for flag in flags), default=0)
    if max_risk >= 3:
        level = "red"
        action = "rest_or_recovery"
        training = "取消高强度，优先休息、快走或 20-30 分钟恢复跑。"
    elif max_risk == 2:
        level = "yellow"
        action = "downshift"
        training = "保留出门习惯，但降低强度和总量；避免间歇、阈值和长距离。"
    else:
        level = "green"
        action = "as_planned"
        training = "可按计划执行；仍保留体感和心率停止规则。"

    for flag in flags:
        detail = flag.get("detail")
        if detail:
            reasons.append(detail)

    return {
        "level": level,
        "action": action,
        "training_guidance": training,
        "reasons": reasons,
        "flags": flags,
    }


def build_evaluation(summary: dict[str, Any]) -> dict[str, Any]:
    readiness = choose_readiness(summary)
    baseline = summary.get("baseline") or {}
    coverage = summary.get("coverage") or {}
    return {
        "coverage": coverage,
        "baseline": baseline,
        "readiness": readiness,
        "risk": summary.get("risk") or {},
        "next_action": {
            "primary": readiness["training_guidance"],
            "stop_rule": "若疼痛影响步态、心率异常飙升、头晕胸痛、热湿不适或连续两段无法完成目标，立即停止质量课并改为回家恢复。",
            "downshift_option": "降级为 20-40 分钟轻松跑、快走或完全休息；明天再看睡眠、HRV、静息心率和主观疲劳。",
            "feedback_questions": [
                "实际完成了多少距离或时长？",
                "平均心率和主观 RPE 是多少？",
                "后半程是否掉速、心率漂移或疼痛加重？",
                "补水、补给和天气是否影响表现？",
            ],
        },
    }


def build_markdown(evaluation: dict[str, Any]) -> str:
    coverage = evaluation["coverage"]
    readiness = evaluation["readiness"]
    next_action = evaluation["next_action"]
    lines = [
        "# Running Context Evaluation",
        "",
        "## 数据置信度",
        "",
        f"- 等级：{coverage.get('level', 'unknown')}",
        f"- 覆盖：{', '.join(coverage.get('present') or []) or '-'}",
        f"- 缺失：{', '.join(coverage.get('missing') or []) or '-'}",
        "",
        "## Readiness",
        "",
        f"- 等级：{readiness['level']}",
        f"- 动作：{readiness['action']}",
        f"- 建议：{readiness['training_guidance']}",
    ]
    if readiness["reasons"]:
        lines.extend(["", "## 风险依据", ""])
        lines.extend(f"- {item}" for item in readiness["reasons"])
    lines.extend(
        [
            "",
            "## 下一步",
            "",
            f"- 主要行动：{next_action['primary']}",
            f"- 停止规则：{next_action['stop_rule']}",
            f"- 降级选项：{next_action['downshift_option']}",
            "- 完成后反馈问题：",
        ]
    )
    lines.extend(f"  - {item}" for item in next_action["feedback_questions"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="评估结构化 COROS 摘要，输出 readiness 和下一步行动。")
    parser.add_argument("--input", help="输入 JSON 文件；省略时从 stdin 读取。")
    parser.add_argument("--markdown", action="store_true", help="输出 Markdown；默认输出 JSON。")
    args = parser.parse_args()

    text = read_text(args.input).strip()
    if not text:
        parser.error("需要提供 build_coros_summary.py 输出的 JSON")
    summary = json.loads(text)
    evaluation = build_evaluation(summary)
    if args.markdown:
        print(build_markdown(evaluation))
    else:
        print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
