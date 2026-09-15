#!/usr/bin/env python3
"""running-coach 脚本回归测试。运行：python3 -m unittest discover -s tests -v"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


analyze_fit = load("analyze_fit")
validate_prescription = load("validate_prescription")


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestAnalyzeFit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = fixture("fit_records.json")
        cls.result = analyze_fit.analyze(cls.payload, threshold_hr=None)

    def test_summary_distance(self):
        summary = self.result["summary"]
        self.assertAlmostEqual(summary["distance_km"], 10.0, delta=0.2)
        self.assertGreater(summary["elevation_gain_m"], 35)
        self.assertLess(summary["elevation_gain_m"], 90)

    def test_blowup_detected(self):
        events = self.result["blowups"]
        self.assertTrue(events, "应检测到末段掉速爆点")
        self.assertGreaterEqual(events[0]["pace_drop_pct"], 8)
        self.assertGreaterEqual(events[0]["km"], 8)

    def test_drift_detected(self):
        drift = self.result["drift"]
        self.assertIsNotNone(drift, "同配速心率漂移应可检测")
        self.assertGreaterEqual(drift["overall_drift_bpm"], 4)
        self.assertTrue(any(b["speed_mps"] == 3.0 for b in drift["bins"]))

    def test_stops_and_climb(self):
        self.assertGreaterEqual(self.result["stops"]["count"], 1)
        self.assertTrue(self.result["climbs"], "应识别 5-6.5km 的爬坡段")
        self.assertGreaterEqual(self.result["climbs"][0]["gain_m"], 30)

    def test_cadence_decay_flag(self):
        cadence = self.result["cadence"]
        self.assertIsNotNone(cadence)
        self.assertGreaterEqual(cadence["decay"], 5)

    def test_flags_and_markdown(self):
        codes = {f["code"] for f in self.result["flags"]}
        self.assertIn("blowup", codes)
        markdown = analyze_fit.to_markdown(self.result)
        self.assertIn("公里分段", markdown)
        self.assertIn("GAP", markdown)
        self.assertNotIn("position", markdown.lower())  # 隐私：不输出坐标

    def test_minetti_ratio_clamped(self):
        self.assertGreaterEqual(analyze_fit.minetti_ratio(-0.5), 0.70)
        self.assertLessEqual(analyze_fit.minetti_ratio(0.5), 2.50)
        self.assertAlmostEqual(analyze_fit.minetti_ratio(0.0), 1.0, places=6)


class TestValidatePrescription(unittest.TestCase):
    def base(self, **overrides):
        prescription = {
            "schema_version": "2.0",
            "decision": "as_planned",
            "readiness": "green",
            "confidence": 0.8,
            "evidence_window": {"start": "2026-09-08", "end": "2026-09-15"},
            "session": {"type": "workout", "purpose": "马配", "duration_min": 60,
                        "intensity": "threshold", "rpe_low": 6, "rpe_high": 7},
            "stop_rules": ["心率异常飙升立即停止"],
            "downshift_option": "降级为 40 分钟轻松跑",
            "missing_data": [],
            "feedback_questions": ["后半程体感如何？"],
            "next_checkpoint": "明天早上看恢复",
            "evidence": [{"source": "coros", "window": "7d"}],
        }
        prescription.update(overrides)
        return prescription

    def test_valid_green_quality(self):
        report = validate_prescription.validate(self.base())
        self.assertTrue(report["valid"], report.get("errors"))

    def test_valid_red_rest(self):
        prescription = self.base(readiness="red", decision="rest_or_recovery", confidence=0.9,
                                 session={"type": "rest_or_recovery", "intensity": "low"})
        report = validate_prescription.validate(prescription)
        self.assertTrue(report["valid"], report.get("errors"))

    def test_red_rejects_quality(self):
        prescription = self.base(readiness="red")
        report = validate_prescription.validate(prescription)
        self.assertFalse(report["valid"])
        self.assertIn("red_readiness_allows_recovery_only", report["errors"][0])

    def test_yellow_rejects_long_run(self):
        prescription = self.base(readiness="yellow",
                                 session={"type": "long_run", "intensity": "easy"})
        report = validate_prescription.validate(prescription)
        self.assertFalse(report["valid"])
        self.assertTrue(any("yellow_readiness_disallows_quality_or_long" in e for e in report["errors"]))

    def test_yellow_rejects_hard_intensity(self):
        prescription = self.base(readiness="yellow",
                                 session={"type": "easy_run", "intensity": "threshold"})
        report = validate_prescription.validate(prescription)
        self.assertFalse(report["valid"])
        self.assertTrue(any("yellow_readiness_disallows_hard_intensity" in e for e in report["errors"]))

    def test_rejects_bad_decision(self):
        report = validate_prescription.validate(self.base(decision="maybe"))
        self.assertFalse(report["valid"])
        self.assertTrue(any("decision" in e for e in report["errors"]))

    def test_requires_evidence_window_and_missing_data(self):
        prescription = self.base()
        del prescription["evidence_window"]
        del prescription["missing_data"]
        report = validate_prescription.validate(prescription)
        self.assertFalse(report["valid"])
        joined = ";".join(report["errors"])
        self.assertIn("missing:evidence_window", joined)
        self.assertIn("missing:missing_data", joined)

    def test_conservative_fallback_shape(self):
        report = validate_prescription.validate(self.base(readiness="red"))
        self.assertEqual(report["decision"], "rest_or_recovery")
        self.assertEqual(report["safe_fallback"]["type"], "rest_or_recovery")
        self.assertTrue(report["safe_fallback"]["stop_rules"])


class TestAnalyzeLaps(unittest.TestCase):
    def test_fade_detected(self):
        analyze_laps = load("analyze_laps")
        analysis = analyze_laps.build_analysis(fixture("laps.json"))
        self.assertEqual(analysis["drift"]["level"], "severe_fade")
        codes = {f["code"] for f in analysis["risk_flags"]}
        self.assertIn("severe_fade", codes)
        self.assertEqual(analysis["summary"]["lap_count"], 10)


class TestBuildAthleteContext(unittest.TestCase):
    def test_red_readiness(self):
        build_athlete_context = load("build_athlete_context")
        context = build_athlete_context.build_context(fixture("context_bundle.json"))
        self.assertEqual(context["readiness"]["level"], "red")
        codes = {f["code"] for f in context["risk_flags"]}
        self.assertIn("load_ratio_high", codes)
        self.assertIn("sleep_short", codes)
        self.assertEqual(context["coverage"]["level"], "high")


class TestEvaluateContext(unittest.TestCase):
    def test_v2_red_markdown(self):
        evaluate_context = load("evaluate_context")
        summary = fixture("context_bundle.json")
        context = load("build_athlete_context").build_context(summary)
        evaluation = evaluate_context.build_evaluation(context)
        markdown = evaluate_context.build_markdown(evaluation)
        self.assertIn("等级：red", markdown)
        self.assertIn("停止规则", markdown)

    def test_v1_recovery_low(self):
        evaluate_context = load("evaluate_context")
        evaluation = evaluate_context.build_evaluation({"recovery": {"recovery_percent": 30}, "coverage": {"level": "high"}})
        self.assertEqual(evaluation["readiness"]["level"], "red")


class TestSaveReport(unittest.TestCase):
    def test_slugify(self):
        save_report = load("save_report")
        self.assertEqual(save_report.slugify("比赛复盘 深度 Review!"), "比赛复盘-深度-review")
        self.assertEqual(save_report.slugify("!!!"), "running-report")

    def test_cli_saves_markdown(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "save_report.py"),
                 "--title", "比赛复盘", "--output-dir", tmp, "--stdin"],
                input="# 比赛深度复盘\n内容", capture_output=True, text=True, check=True)
            out_path = Path(result.stdout.strip())
            self.assertTrue(out_path.exists())
            self.assertIn("比赛深度复盘", out_path.read_text(encoding="utf-8"))
            self.assertEqual(out_path.suffix, ".md")


if __name__ == "__main__":
    unittest.main()
