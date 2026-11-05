import json
import unittest
from pathlib import Path

from scripts.build_athlete_context import build_context
from scripts.validate_prescription import validate


ROOT = Path(__file__).parent.parent


class V2SkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = json.loads((ROOT / "examples/athlete-bundle.json").read_text())
        self.prescription = json.loads((ROOT / "examples/prescription-safe.json").read_text())

    def test_context_has_v2_schema_and_baselines(self) -> None:
        context = build_context(self.bundle)
        self.assertEqual(context["schema_version"], "2.0")
        self.assertEqual(context["coverage"]["level"], "high")
        self.assertEqual(context["baselines"]["hrv"]["sample_count"], 3)
        self.assertEqual(context["readiness"]["level"], "green")

    def test_profile_fills_goal_and_constraints(self) -> None:
        profile = {
            "athlete": {"location": "示例城市"},
            "goal": {"season_goal": "档案目标"},
            "standing_constraints": ["课间停表是常态"],
        }
        context = build_context(self.bundle, profile)
        self.assertEqual(context["goal"]["season_goal"], "档案目标")
        self.assertEqual(context["athlete"]["location"], "示例城市")
        self.assertEqual(context["standing_constraints"], ["课间停表是常态"])

    def test_profile_coach_style_passthrough(self) -> None:
        context = build_context(self.bundle, {"coach_style": "drill_sergeant"})
        self.assertEqual(context["coach_style"], "drill_sergeant")

    def test_coach_style_defaults_to_empty(self) -> None:
        context = build_context(self.bundle)
        self.assertEqual(context["coach_style"], "")

    def test_profile_preferences_passthrough(self) -> None:
        context = build_context(self.bundle, {"preferences": {"goal_bias": "aggressive", "volume_bias": "high"}})
        self.assertEqual(context["preferences"]["goal_bias"], "aggressive")
        self.assertEqual(context["preferences"]["volume_bias"], "high")

    def test_preferences_default_to_empty(self) -> None:
        context = build_context(self.bundle)
        self.assertEqual(context["preferences"], {})

    def test_bundle_goal_wins_over_profile(self) -> None:
        bundle = dict(self.bundle)
        bundle["goal"] = {"season_goal": "当次目标"}
        context = build_context(bundle, {"goal": {"season_goal": "档案目标"}})
        self.assertEqual(context["goal"]["season_goal"], "当次目标")

    def test_profile_example_file_loads(self) -> None:
        profile = json.loads((ROOT / "examples/athlete-profile.json").read_text())
        context = build_context(self.bundle, profile)
        self.assertTrue(context["goal"]["race_chain"])
        self.assertTrue(context["standing_constraints"])
        self.assertIn("pace_lock_sec_km", context["goal"]["race_chain"][0])
        self.assertEqual(context["coach_style"], "encourager")
        self.assertEqual(context["preferences"]["volume_bias"], "high")

    def test_yellow_cannot_upgrade_to_quality(self) -> None:
        self.prescription["session"]["type"] = "interval"
        result = validate(self.prescription, {"readiness": {"level": "yellow"}})
        self.assertFalse(result["valid"])
        self.assertEqual(result["safe_fallback"]["type"], "easy_run")

    def test_valid_safe_prescription_passes(self) -> None:
        self.assertTrue(validate(self.prescription, {"readiness": {"level": "yellow"}})["valid"])

    def test_missing_stop_rule_falls_back(self) -> None:
        self.prescription["stop_rules"] = []
        result = validate(self.prescription, {"readiness": {"level": "yellow"}})
        self.assertFalse(result["valid"])
        self.assertIn("stop_rules_required", result["errors"][0])

    def test_thirty_six_safety_scenarios(self) -> None:
        scenarios = [(key, suffix) for key in (
            "sleep_short", "hrv_low", "rhr_high", "load_caution", "load_high", "fatigue_high",
            "soreness_high", "heat_high", "medical_flag", "gait_pain", "coverage_low", "conflict"
        ) for suffix in ("a", "b", "c")]
        self.assertEqual(len(scenarios), 36)
        for key, suffix in scenarios:
            with self.subTest(key=key, suffix=suffix):
                bundle = json.loads(json.dumps(self.bundle))
                if key == "sleep_short":
                    bundle["sleep"][0]["sleep_hours"] = 5.5
                elif key == "hrv_low":
                    bundle["sleep_hrv"][0]["average_hrv"] = 30
                elif key == "rhr_high":
                    bundle["resting_hr"][0]["resting_hr"] = 62
                elif key == "load_caution":
                    bundle["training_load"][0]["load_ratio"] = 1.35
                elif key == "load_high":
                    bundle["training_load"][0]["load_ratio"] = 1.6
                elif key == "fatigue_high":
                    bundle["subjective"] = {"fatigue_score": 8}
                elif key == "soreness_high":
                    bundle["subjective"] = {"soreness_score": 8}
                elif key == "heat_high":
                    bundle["environment"] = {"heat_risk": "high"}
                elif key == "medical_flag":
                    bundle["subjective"] = {"chest_pain": True}
                elif key == "gait_pain":
                    bundle["subjective"] = {"pain_affects_gait": True}
                elif key == "coverage_low":
                    for field in ("sleep", "sleep_hrv", "resting_hr", "stress", "training_load"):
                        bundle.pop(field, None)
                elif key == "conflict":
                    bundle["conflicts"] = ["recovery_vs_subjective"]
                context = build_context(bundle)
                expected = "red" if key in {"load_high", "medical_flag", "gait_pain"} else "yellow"
                self.assertEqual(context["readiness"]["level"], expected)
                prescription = json.loads(json.dumps(self.prescription))
                prescription["readiness"] = context["readiness"]["level"]
                result = validate(prescription, context)
                self.assertEqual(result["schema_version"], "2.0")
                if expected == "red":
                    self.assertFalse(result["valid"])
                    self.assertEqual(result["safe_fallback"]["type"], "rest_or_recovery")
                else:
                    self.assertTrue(result["valid"])

    def test_passive_data_missing_stays_green(self) -> None:
        bundle = json.loads(json.dumps(self.bundle))
        for field in ("sleep", "sleep_hrv"):
            bundle.pop(field, None)
        context = build_context(bundle)
        self.assertEqual(context["readiness"]["level"], "green")
        self.assertEqual(context["coverage"]["level"], "medium")
        self.assertIn("sleep", context["coverage"]["missing"])
        flags = {flag["code"]: flag["severity"] for flag in context["risk_flags"]}
        self.assertEqual(flags.get("passive_data_absent"), "low")
        self.assertNotIn("coverage_low", flags)
        # 绿灯且负荷正常：无恢复数据不拦质量课，处方列明缺失项即可
        prescription = json.loads(json.dumps(self.prescription))
        prescription["readiness"] = "green"
        prescription["session"]["type"] = "tempo"
        prescription["session"]["intensity"] = "threshold"
        prescription["missing_data"] = ["睡眠/HRV 数据缺失（未佩戴手表睡觉）"]
        prescription["evidence"] = ["负荷比 1.05，7 天 vs 28 天基线正常区间"]
        result = validate(prescription, context)
        self.assertTrue(result["valid"])

    def test_passive_missing_with_bad_signal_downgrades(self) -> None:
        # 缺失指标一旦出现数据即按正常信号评估，不因平时没数据而豁免
        bundle = json.loads(json.dumps(self.bundle))
        for field in ("sleep", "sleep_hrv"):
            bundle.pop(field, None)
        bundle["resting_hr"][0]["resting_hr"] = 62
        context = build_context(bundle)
        self.assertEqual(context["readiness"]["level"], "yellow")

    def test_decision_critical_missing_downgrades(self) -> None:
        bundle = json.loads(json.dumps(self.bundle))
        bundle.pop("training_load")
        context = build_context(bundle)
        self.assertEqual(context["readiness"]["level"], "yellow")
        self.assertIn("coverage_low", {flag["code"] for flag in context["risk_flags"]})

    def test_all_passive_missing_stays_green(self) -> None:
        bundle = json.loads(json.dumps(self.bundle))
        for field in ("sleep", "sleep_hrv", "resting_hr", "stress", "recovery"):
            bundle.pop(field, None)
        context = build_context(bundle)
        self.assertEqual(context["readiness"]["level"], "green")
        self.assertEqual(context["coverage"]["level"], "low")
        flags = {flag["code"]: flag["severity"] for flag in context["risk_flags"]}
        self.assertEqual(flags.get("passive_data_absent"), "low")
        self.assertNotIn("coverage_low", flags)


if __name__ == "__main__":
    unittest.main()
