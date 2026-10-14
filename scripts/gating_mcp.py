#!/usr/bin/env python3
"""把 running-coach 的确定性门控脚本封装为本地 stdio MCP server。

目的：让 WorkBuddy 等桌面 harness 经 MCP 连接器直接获得代码级安全门控，
用户无需会跑脚本（只需一次性安装 Python 与 `pip install mcp`）。
数据全程留在本机；不提供远程托管形态（健康数据不出机）。

调度核心 dispatch() 不依赖 MCP SDK，可独立测试（tests/test_gating_mcp.py、
--selfcheck 均不需要安装 SDK）。

暴露的 tools（与脚本能力一一对应）：
- build_athlete_context  bundle(+可选 profile) -> AthleteContext V2
- evaluate_context       context -> readiness 评估与下一步行动
- validate_prescription  prescription(+context) -> 安全校验结果
- archive_snapshot       write/show/stats 本地数据档案（写入前脱敏扫描）
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

SCRIPTS_DIR = Path(__file__).resolve().parent
_module_cache: dict[str, Any] = {}


def load_sibling(name: str) -> Any:
    if name not in _module_cache:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _module_cache[name] = module
    return _module_cache[name]


# ---------------------------------------------------------------------------
# 调度核心（无 SDK 依赖）
# ---------------------------------------------------------------------------

def tool_build_athlete_context(args: dict[str, Any]) -> dict[str, Any]:
    bundle = args.get("bundle")
    if not isinstance(bundle, dict):
        raise ValueError("build_athlete_context 需要 bundle 对象")
    profile = args.get("profile") if isinstance(args.get("profile"), dict) else None
    return load_sibling("build_athlete_context").build_context(bundle, profile)


def tool_evaluate_context(args: dict[str, Any]) -> dict[str, Any]:
    summary = args.get("summary") or args.get("context")
    if not isinstance(summary, dict):
        raise ValueError("evaluate_context 需要 summary/context 对象")
    module = load_sibling("evaluate_context")
    evaluation = module.build_evaluation(summary)
    if args.get("markdown"):
        evaluation["markdown"] = module.build_markdown(evaluation)
    return evaluation


def tool_validate_prescription(args: dict[str, Any]) -> dict[str, Any]:
    prescription = args.get("prescription")
    if not isinstance(prescription, dict):
        raise ValueError("validate_prescription 需要 prescription 对象")
    context = args.get("context") if isinstance(args.get("context"), dict) else None
    return load_sibling("validate_prescription").validate(prescription, context)


def tool_archive_snapshot(args: dict[str, Any]) -> dict[str, Any]:
    module = load_sibling("archive_snapshot")
    action = args.get("action", "write")
    archive_dir = Path(args["archive_dir"]).expanduser() if args.get("archive_dir") else module.resolve_archive_dir(None)
    if action == "write":
        record = module.build_record(
            args.get("bundle") if isinstance(args.get("bundle"), dict) else None,
            args.get("context") if isinstance(args.get("context"), dict) else None,
            args.get("prescription") if isinstance(args.get("prescription"), dict) else None,
            args.get("analysis") if isinstance(args.get("analysis"), dict) else None,
            str(args.get("record_type") or "daily_check"),
            args.get("date"),
            args.get("notes"),
        )
        violations = module.scan_violations(record)
        if violations:
            return {"archived": False, "tool": "archive_snapshot", "errors": violations}
        result = module.upsert(archive_dir, record)
        return {"archived": True, "tool": "archive_snapshot", **result,
                "date": record["date"], "record_type": record["record_type"]}
    if action == "show":
        return {"records": module.read_archive(archive_dir, max(int(args.get("days") or 28), 1),
                                               args.get("record_type"))}
    if action == "stats":
        records = module.read_archive(archive_dir, max(int(args.get("days") or 28), 1))
        return module.archive_stats(records)
    raise ValueError(f"未知 archive action：{action}（支持 write/show/stats）")


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "build_athlete_context": tool_build_athlete_context,
    "evaluate_context": tool_evaluate_context,
    "validate_prescription": tool_validate_prescription,
    "archive_snapshot": tool_archive_snapshot,
}


def dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """单一入口：按工具名调度，异常转为结构化错误而不是抛出。"""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {"error": f"未知工具：{name}", "available": sorted(TOOL_HANDLERS)}
    try:
        return handler(arguments or {})
    except Exception as exc:  # noqa: BLE001 - MCP 工具错误需返回给客户端而非中断 server
        return {"error": f"{type(exc).__name__}: {exc}", "tool": name}


# ---------------------------------------------------------------------------
# 自检（不需要 MCP SDK）
# ---------------------------------------------------------------------------

def selfcheck() -> int:
    bundle = {
        "as_of": "2026-10-13T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "sleep": [{"date": "2026-10-12", "duration_hours": 7.0, "score": 75}],
        "sleep_hrv": [{"date": "2026-10-12", "average_hrv": 50}],
        "resting_hr": [{"date": "2026-10-12", "resting_hr": 52}],
        "stress": [{"date": "2026-10-12", "stress": 30}],
        "training_load": [{"date": "2026-10-12", "load_ratio": 1.0}],
        "recovery": {"recovery_percent": 80},
        "activities": [{"labelId": "s1", "date": "2026-10-12", "distance_km": 8}],
    }
    results: dict[str, str] = {}
    context = dispatch("build_athlete_context", {"bundle": bundle})
    results["build_athlete_context"] = "ok" if context.get("schema_version") == "2.0" else "fail"
    evaluation = dispatch("evaluate_context", {"summary": context})
    results["evaluate_context"] = "ok" if "readiness" in evaluation else "fail"
    prescription = {
        "decision": "as_planned", "readiness": "green", "confidence": 0.8,
        "evidence_window": {"start": "2026-10-06", "end": "2026-10-13"},
        "session": {"type": "easy_run", "duration_min": 30, "intensity": "easy"},
        "stop_rules": ["胸痛头晕立即停止"], "downshift_option": "改为 20 分钟快走",
        "missing_data": [], "feedback_questions": ["RPE 多少？"],
        "next_checkpoint": "明晨",
    }
    check = dispatch("validate_prescription", {"prescription": prescription, "context": context})
    results["validate_prescription"] = "ok" if check.get("valid") else "fail"
    with tempfile.TemporaryDirectory() as tmp:
        archived = dispatch("archive_snapshot", {
            "action": "write", "bundle": bundle, "context": context,
            "prescription": prescription, "archive_dir": tmp,
        })
        stats = dispatch("archive_snapshot", {"action": "stats", "days": 30, "archive_dir": tmp})
        refused = dispatch("archive_snapshot", {
            "action": "write", "bundle": {"as_of": "2026-10-13T08:00:00+08:00"},
            "context": context, "archive_dir": tmp, "notes": None, "date": "2026-10-13",
            "record_type": "daily_check", "analysis": {"summary": {"start_latitude": 24.5}},
        })
    results["archive_snapshot"] = ("ok" if archived.get("archived") and stats.get("records")
                                   and not refused.get("archived") else "fail")
    print(json.dumps({"status": "ok" if all(v == "ok" for v in results.values()) else "fail",
                      "tools": results}, ensure_ascii=False))
    return 0 if all(v == "ok" for v in results.values()) else 1


# ---------------------------------------------------------------------------
# MCP 管道（FastMCP，可选依赖）
# ---------------------------------------------------------------------------

def run_server() -> int:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("MCP 管道需要官方 SDK：pip install mcp（调度与自检不需要）", file=sys.stderr)
        return 4
    mcp = FastMCP("running-coach-gating")

    @mcp.tool()
    def build_athlete_context(bundle: dict, profile: dict | None = None) -> dict:
        """把手表数据 bundle 归一为 AthleteContext V2（覆盖度、基线、readiness、风险标记）。"""
        return dispatch("build_athlete_context", {"bundle": bundle, "profile": profile})

    @mcp.tool()
    def evaluate_context(summary: dict, markdown: bool = False) -> dict:
        """评估 readiness 与风险，输出下一步行动、停止规则与降级选项。"""
        return dispatch("evaluate_context", {"summary": summary, "markdown": markdown})

    @mcp.tool()
    def validate_prescription(prescription: dict, context: dict | None = None) -> dict:
        """校验训练处方是否违反安全上限（red/yellow 强度约束）；失败时返回保守 fallback。"""
        return dispatch("validate_prescription", {"prescription": prescription, "context": context})

    @mcp.tool()
    def archive_snapshot(action: str = "write", bundle: dict | None = None, context: dict | None = None,
                         prescription: dict | None = None, analysis: dict | None = None,
                         record_type: str = "daily_check", date: str | None = None,
                         notes: str | None = None, days: int = 28,
                         archive_dir: str | None = None) -> dict:
        """本地数据档案：write 写入瘦身快照（写入前脱敏扫描），show 查询，stats 统计基线。"""
        return dispatch("archive_snapshot", {
            "action": action, "bundle": bundle, "context": context, "prescription": prescription,
            "analysis": analysis, "record_type": record_type, "date": date, "notes": notes,
            "days": days, "archive_dir": archive_dir,
        })

    mcp.run()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="running-coach 门控 MCP server（本地 stdio）。")
    parser.add_argument("--selfcheck", action="store_true", help="不依赖 SDK 的工具自检。")
    args = parser.parse_args()
    if args.selfcheck:
        return selfcheck()
    return run_server()


if __name__ == "__main__":
    raise SystemExit(main())
