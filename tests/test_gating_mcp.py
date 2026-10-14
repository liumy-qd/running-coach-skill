#!/usr/bin/env python3
"""gating_mcp.py 测试：工具调度、错误转换、档案写入/脱敏拒绝/统计（无需 MCP SDK）。"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gating = load("gating_mcp")


def sample_bundle():
    return {
        "as_of": "2026-10-13T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "sleep": [{"date": "2026-10-12", "duration_hours": 6.9, "score": 72}],
        "sleep_hrv": [{"date": "2026-10-12", "average_hrv": 49, "baseline": 52}],
        "resting_hr": [{"date": "2026-10-12", "resting_hr": 53}],
        "stress": [{"date": "2026-10-12", "stress": 31}],
        "training_load": [{"date": "2026-10-12", "load_ratio": 1.05}],
        "recovery": {"recovery_percent": 76},
        "activities": [{"labelId": "g1", "date": "2026-10-12", "distance_km": 10}],
    }


def safe_prescription():
    return {
        "decision": "as_planned", "readiness": "green", "confidence": 0.8,
        "evidence_window": {"start": "2026-10-06", "end": "2026-10-13"},
        "session": {"type": "easy_run", "duration_min": 30, "intensity": "easy"},
        "stop_rules": ["胸痛头晕立即停止"], "downshift_option": "改为 20 分钟快走",
        "missing_data": [], "feedback_questions": ["RPE 多少？"], "next_checkpoint": "明晨",
    }


class TestDispatch(unittest.TestCase):
    def test_all_tools_registered(self):
        self.assertEqual(sorted(gating.TOOL_HANDLERS),
                         ["archive_snapshot", "build_athlete_context",
                          "evaluate_context", "validate_prescription"])

    def test_unknown_tool_returns_error_not_raise(self):
        result = gating.dispatch("nope", {})
        self.assertIn("error", result)
        self.assertIn("available", result)

    def test_build_athlete_context(self):
        context = gating.dispatch("build_athlete_context", {"bundle": sample_bundle()})
        self.assertEqual(context["schema_version"], "2.0")
        self.assertIn("readiness", context)

    def test_build_athlete_context_requires_bundle(self):
        result = gating.dispatch("build_athlete_context", {})
        self.assertIn("error", result)

    def test_evaluate_context(self):
        context = gating.dispatch("build_athlete_context", {"bundle": sample_bundle()})
        evaluation = gating.dispatch("evaluate_context", {"summary": context})
        self.assertIn("readiness", evaluation)
        self.assertIn("stop_rule", evaluation["next_action"])
        detailed = gating.dispatch("evaluate_context", {"summary": context, "markdown": True})
        self.assertIn("markdown", detailed)

    def test_validate_prescription_gates_yellow_quality(self):
        rx = safe_prescription()
        rx["readiness"] = "yellow"
        rx["session"]["type"] = "interval"
        result = gating.dispatch("validate_prescription", {"prescription": rx})
        self.assertFalse(result["valid"])
        self.assertEqual(result["safe_fallback"]["type"], "easy_run")

    def test_validate_prescription_accepts_safe(self):
        result = gating.dispatch("validate_prescription",
                                 {"prescription": safe_prescription()})
        self.assertTrue(result["valid"])


class TestArchiveTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_then_stats(self):
        context = gating.dispatch("build_athlete_context", {"bundle": sample_bundle()})
        written = gating.dispatch("archive_snapshot", {
            "action": "write", "bundle": sample_bundle(), "context": context,
            "prescription": safe_prescription(), "archive_dir": self.dir,
        })
        self.assertTrue(written["archived"])
        stats = gating.dispatch("archive_snapshot",
                                {"action": "stats", "days": 30, "archive_dir": self.dir})
        self.assertEqual(stats["records"], 1)
        shown = gating.dispatch("archive_snapshot",
                                {"action": "show", "days": 30, "archive_dir": self.dir})
        self.assertEqual(len(shown["records"]), 1)

    def test_redaction_refusal_is_structured(self):
        context = gating.dispatch("build_athlete_context", {"bundle": sample_bundle()})
        result = gating.dispatch("archive_snapshot", {
            "action": "write",
            "bundle": {"as_of": "2026-10-13T08:00:00+08:00"},
            "context": context, "archive_dir": self.dir, "date": "2026-10-13",
            "record_type": "daily_check",
            "analysis": {"summary": {"start_latitude": 24.47}},
        })
        self.assertFalse(result["archived"])
        self.assertTrue(any("latitude" in item for item in result["errors"]))

    def test_invalid_action_returns_error(self):
        result = gating.dispatch("archive_snapshot",
                                 {"action": "boom", "archive_dir": self.dir})
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
