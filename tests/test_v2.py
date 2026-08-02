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


if __name__ == "__main__":
    unittest.main()
