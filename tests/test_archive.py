#!/usr/bin/env python3
"""archive_snapshot.py 归档测试：upsert 去重、活动合并、脱敏拒绝、查询统计。"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


archive = load("archive_snapshot")


def bundle(**overrides):
    base = {
        "as_of": "2026-10-13T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "sleep": [{"date": "2026-10-12", "duration_hours": 6.1, "score": 62}],
        "sleep_hrv": [{"date": "2026-10-12", "average_hrv": 48, "baseline": 52}],
        "resting_hr": [{"date": "2026-10-12", "resting_hr": 52}],
        "stress": [{"date": "2026-10-12", "stress": 32}],
        "training_load": [{"date": "2026-10-12", "load_ratio": 1.1}],
        "recovery": {"recovery_percent": 78},
        "activities": [
            {"labelId": "a1", "sportType": 100, "date": "2026-10-12", "distanceKm": 16.2, "durationMin": 82, "avgHr": 148},
        ],
    }
    base.update(overrides)
    return base


def context(level="green", flags=None):
    return {
        "schema_version": "2.0",
        "as_of": "2026-10-13T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "readiness": {"level": level, "action": "as_planned", "flags": flags or []},
        "risk_flags": flags or [],
    }


class TestBuildRecord(unittest.TestCase):
    def test_slim_extraction(self):
        record = archive.build_record(bundle(), context(), None, None, "daily_check", None, None)
        self.assertEqual(record["date"], "2026-10-13")
        self.assertEqual(record["health"]["sleep"]["duration_hours"], 6.1)
        self.assertEqual(record["health"]["hrv"]["value"], 48)
        self.assertEqual(record["health"]["load_ratio"], 1.1)
        self.assertEqual(record["recovery"]["percent"], 78)
        self.assertEqual(record["activities"][0]["label_id"], "a1")
        self.assertEqual(record["readiness"]["level"], "green")

    def test_date_override(self):
        record = archive.build_record(bundle(), None, None, None, "daily_check", "2026-09-01", None)
        self.assertEqual(record["date"], "2026-09-01")

    def test_prescription_and_notes(self):
        rx = {"decision": "as_planned", "readiness": "green", "confidence": 0.8,
              "session": {"type": "easy_run", "duration_min": 40, "intensity": "easy"}}
        record = archive.build_record(bundle(), context(), rx, None, "daily_check", None, "田径场，课间停表")
        self.assertEqual(record["prescription"]["session"]["type"], "easy_run")
        self.assertEqual(record["notes"], "田径场，课间停表")


class TestUpsert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_and_upsert_same_day(self):
        first = archive.build_record(bundle(), context(), None, None, "daily_check", "2026-10-13", None)
        result = archive.upsert(self.dir, first)
        self.assertTrue(result["file"].endswith("2026-10.jsonl"))
        self.assertFalse(result["replaced"])

        second = archive.build_record(bundle(), context("yellow"), None, None, "daily_check", "2026-10-13", None)
        result = archive.upsert(self.dir, second)
        self.assertTrue(result["replaced"])
        self.assertEqual(result["records_in_month"], 1)

        rows = archive.load_month(self.dir / "2026-10.jsonl")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["revision"], 2)
        self.assertEqual(rows[0]["readiness"]["level"], "yellow")

    def test_activities_merge_by_label(self):
        first = archive.build_record(bundle(), context(), None, None, "activity_review", "2026-10-13", None)
        archive.upsert(self.dir, first)
        more = archive.build_record(
            bundle(activities=[
                {"labelId": "a1", "date": "2026-10-12", "distanceKm": 16.4, "avgHr": 150},
                {"labelId": "a2", "date": "2026-10-12", "distanceKm": 5.0},
            ]),
            context(), None, None, "activity_review", "2026-10-13", None,
        )
        archive.upsert(self.dir, more)
        rows = archive.load_month(self.dir / "2026-10.jsonl")
        merged = {a["label_id"]: a for a in rows[0]["activities"]}
        self.assertEqual(sorted(merged), ["a1", "a2"])
        self.assertEqual(merged["a1"]["distance_km"], 16.4)  # 新值覆盖
        self.assertEqual(merged["a1"]["avg_hr"], 150)

    def test_distinct_types_and_months_do_not_collide(self):
        archive.upsert(self.dir, archive.build_record(bundle(), context(), None, None, "daily_check", "2026-10-13", None))
        archive.upsert(self.dir, archive.build_record(bundle(), context(), None, None, "race_review", "2026-10-13", None))
        archive.upsert(self.dir, archive.build_record(bundle(), context(), None, None, "daily_check", "2026-09-28", None))
        self.assertEqual(len(archive.load_month(self.dir / "2026-10.jsonl")), 2)
        self.assertEqual(len(archive.load_month(self.dir / "2026-09.jsonl")), 1)


class TestRedaction(unittest.TestCase):
    def test_unknown_bundle_fields_are_dropped_by_slimming(self):
        record = archive.build_record(
            bundle(recovery={"recovery_percent": 78, "accessToken": "xyz"}), context(), None, None, "daily_check", None, None,
        )
        self.assertNotIn("accessToken", json.dumps(record), "瘦身层应丢弃未知字段")

    def test_refuses_passthrough_gps_keys(self):
        # analysis 是透传面：其中的坐标必须被脱敏扫描拦截
        record = archive.build_record(
            bundle(), context(), None,
            {"tool": "analyze_fit", "summary": {"distance_km": 10, "start_latitude": 24.47, "route_longitude": 118.09}},
            "race_review", None, None,
        )
        violations = archive.scan_violations(record)
        self.assertTrue(any("latitude" in v or "longitude" in v for v in violations), "应拒绝透传坐标字段")

    def test_refuses_menstrual_fields(self):
        bad = archive.build_record(bundle(), context(), None, None, "daily_check", None, None)
        bad["menstrual_cycle"] = {"day": 14}
        violations = archive.scan_violations(bad)
        self.assertTrue(any("menstrual" in v.lower() for v in violations), "经期数据不得入档")

    def test_refuses_long_numeric_arrays(self):
        bad = archive.build_record(bundle(), context(), None, None, "daily_check", None, None)
        bad["hr_series"] = [120.0] * 600
        violations = archive.scan_violations(bad)
        self.assertTrue(any("hr_series" in v for v in violations), "逐秒数值序列不得入档")

    def test_clean_record_passes(self):
        record = archive.build_record(bundle(), context(), None, None, "daily_check", None, None)
        self.assertEqual(archive.scan_violations(record), [])


class TestQuery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for day in range(1, 5):
            archive.upsert(self.dir, archive.build_record(
                bundle(sleep=[{"date": f"2026-10-0{day}", "duration_hours": 6.0 + day * 0.1}]),
                context(), None, None, "daily_check", f"2026-10-0{day}", None,
            ))

    def tearDown(self):
        self.tmp.cleanup()

    def test_show_filters_by_window_and_type(self):
        records = archive.read_archive(self.dir, days=1, record_type="daily_check", today="2026-10-04")
        self.assertEqual(len(records), 1)
        records = archive.read_archive(self.dir, days=30, record_type="race_review", today="2026-10-04")
        self.assertEqual(records, [])

    def test_stats_summary(self):
        records = archive.read_archive(self.dir, days=30, today="2026-10-04")
        stats = archive.archive_stats(records)
        self.assertEqual(stats["days"], 4)
        self.assertEqual(stats["metrics"]["sleep_duration_hours"]["days_present"], 4)
        self.assertAlmostEqual(stats["metrics"]["sleep_duration_hours"]["max"], 6.4, places=2)


if __name__ == "__main__":
    unittest.main()
