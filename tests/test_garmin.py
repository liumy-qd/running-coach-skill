#!/usr/bin/env python3
"""garmin_to_bundle.py 适配测试：字段映射、单位换算、与 AthleteContext 管线衔接。"""
from __future__ import annotations

import importlib.util
import json
import sys
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


garmin = load("garmin_to_bundle")
context_builder = load("build_athlete_context")


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestNormalize(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = fixture("garmin_raw.json")
        cls.bundle = garmin.build_bundle(cls.raw)

    def test_sleep_duration_and_score(self):
        self.assertEqual(self.bundle["sleep"][0]["date"], "2026-10-11")
        self.assertAlmostEqual(self.bundle["sleep"][0]["duration_hours"], 6.94, delta=0.01)
        self.assertEqual(self.bundle["sleep"][0]["score"], 71)

    def test_hrv_rmssd_mapping(self):
        self.assertEqual(self.bundle["sleep_hrv"][-1]["average_hrv"], 47)
        self.assertEqual(self.bundle["sleep_hrv"][-1]["baseline"], 52.0)

    def test_stress_from_array_average(self):
        values = {row["date"]: row["stress"] for row in self.bundle["stress"]}
        self.assertEqual(values["2026-10-11"], 27)          # 直接均值
        self.assertEqual(values["2026-10-12"], 30)          # 数组求均值

    def test_load_ratio_from_acute_chronic(self):
        self.assertAlmostEqual(self.bundle["training_load"][0]["load_ratio"], 1.14, places=2)

    def test_recovery_from_training_readiness(self):
        self.assertEqual(self.bundle["recovery"]["recovery_percent"], 76)
        self.assertEqual(self.bundle["recovery"]["source"], "garmin_training_readiness")

    def test_activities_units_and_keys(self):
        run = self.bundle["activities"][0]
        self.assertEqual(run["label_id"], "1001")
        self.assertEqual(run["sport_type"], "running")
        self.assertEqual(run["distance_km"], 11.0)           # 米 → 公里
        self.assertEqual(run["duration_min"], 60.0)
        self.assertEqual(run["avg_hr"], 148)
        self.assertEqual(run["training_load"], 180)

    def test_fitness_vo2max(self):
        self.assertEqual(self.bundle["fitness"]["vo2max"], 51)

    def test_source_device_marked(self):
        self.assertEqual(self.bundle["source_device"], "garmin")
        self.assertEqual(self.bundle["sources"][0]["name"], "garmin")

    def test_missing_sections_tolerated(self):
        bundle = garmin.build_bundle({"as_of": "2026-10-13T08:00:00+08:00"})
        self.assertNotIn("sleep", bundle)
        self.assertNotIn("recovery", bundle)


class TestPipeline(unittest.TestCase):
    def test_bundle_feeds_athlete_context(self):
        bundle = garmin.build_bundle(fixture("garmin_raw.json"))
        context = context_builder.build_context(bundle)
        self.assertEqual(context["schema_version"], "2.0")
        self.assertEqual(context["coverage"]["level"], "high")
        self.assertEqual(context["baselines"]["hrv"]["sample_count"], 2)
        self.assertEqual(context["readiness"]["level"], "green")
        self.assertAlmostEqual(context["baselines"]["training"]["latest_load_ratio"], 1.14, places=2)
        self.assertEqual(context["current_state"]["recovery"]["recovery_percent"], 76)

    def test_no_coordinates_in_bundle(self):
        text = json.dumps(garmin.build_bundle(fixture("garmin_raw.json")))
        for token in ("latitude", "longitude", "position_lat"):
            self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
