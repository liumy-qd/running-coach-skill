#!/usr/bin/env python3
"""garmin_to_bundle.py 适配测试：字段映射、单位换算、与 AthleteContext 管线衔接。

归一路径用 fixture 回放；fetch/login 路径注入 fake garth/garminconnect 模块，不触网。
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import types
import unittest
from datetime import date, timedelta
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


@contextlib.contextmanager
def fake_module(name: str, **attrs):
    """临时注入带指定属性的假模块；退出时恢复 sys.modules 原状。"""
    saved = sys.modules.get(name)
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    try:
        yield module
    finally:
        if saved is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved


@contextlib.contextmanager
def blocked_module(name: str):
    """把模块槽位置为 None，强制 `import name` 抛 ImportError（依赖未安装场景）。"""
    saved = sys.modules.get(name)
    sys.modules[name] = None
    try:
        yield
    finally:
        if saved is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved


class TestFieldVariants(unittest.TestCase):
    """锁定 docstring 承诺的字段变体容忍（fixture 只覆盖主键路径）。"""

    AS_OF = "2026-10-13T08:00:00+08:00"

    def test_body_battery_recovery_fallback(self):
        bundle = garmin.build_bundle({"as_of": self.AS_OF, "body_battery": {"level": 64}})
        self.assertEqual(bundle["recovery"],
                         {"recovery_percent": 64, "source": "garmin_body_battery"})

    def test_numeric_stress_array(self):
        raw = {"as_of": self.AS_OF,
               "stress": [{"calendarDate": "2026-10-12", "stressValuesArray": [20, 40, 30]}]}
        self.assertEqual(garmin.build_bundle(raw)["stress"][0]["stress"], 30)

    def test_flat_sleep_row_without_wrapper(self):
        raw = {"as_of": self.AS_OF,
               "sleep": [{"calendarDate": "2026-10-11",
                          "sleepTimeSeconds": 25000, "overallSleepScore": 71}]}
        entry = garmin.build_bundle(raw)["sleep"][0]
        self.assertAlmostEqual(entry["duration_hours"], 6.94, delta=0.01)
        self.assertEqual(entry["score"], 71)

    def test_hrv_variant_keys(self):
        raw = {"as_of": self.AS_OF,
               "hrv": [{"date": "2026-10-12", "avgHrv": 45, "hrvBaseline": 51.0}]}
        entry = garmin.build_bundle(raw)["sleep_hrv"][0]
        self.assertEqual(entry["average_hrv"], 45)
        self.assertEqual(entry["baseline"], 51.0)

    def test_sport_records_with_label_id_and_km_heuristic(self):
        raw = {"as_of": self.AS_OF, "sport_records": [
            {"labelId": "g1", "date": "2026-10-12", "activityType": "running",
             "distance": 5.2, "duration": 1800, "avgPace": 346},
            {"labelId": "g2", "date": "2026-10-11", "activityType": "running",
             "distance": 100, "duration": 600},
        ]}
        acts = garmin.build_bundle(raw)["activities"]  # 按日期排序：10-11 在前
        self.assertEqual(acts[0]["distance_km"], 0.1)  # 恰为 100 仍按米换算
        self.assertEqual(acts[1]["label_id"], "g1")
        self.assertEqual(acts[1]["sport_type"], "running")  # 字符串形式的 activityType
        self.assertEqual(acts[1]["distance_km"], 5.2)       # <100 视为已是公里
        self.assertEqual(acts[1]["duration_min"], 30.0)
        self.assertEqual(acts[1]["avg_pace_sec_km"], 346)

    def test_records_wrapper_shape(self):
        raw = {"as_of": self.AS_OF,
               "sleep_data": {"records": [{"dailySleepValues": {
                   "calendarDate": "2026-10-11", "sleepTimeSeconds": 25000}}]}}
        entry = garmin.build_bundle(raw)["sleep"][0]
        self.assertAlmostEqual(entry["duration_hours"], 6.94, delta=0.01)

    def test_training_load_direct_ratio(self):
        raw = {"as_of": self.AS_OF, "training_load": {"load_ratio": 1.2}}
        self.assertEqual(garmin.build_bundle(raw)["training_load"][0]["load_ratio"], 1.2)


class TestFetchRaw(unittest.TestCase):
    """fetch_raw 组装逻辑：注入 fake garth/garminconnect，模拟认证与端点行为。"""

    @staticmethod
    @contextlib.contextmanager
    def install_garmin(garmin_impl, resume=None):
        garth_resume = resume if resume is not None else (lambda path: None)
        with fake_module("garth", resume=garth_resume), \
                fake_module("garminconnect", Garmin=lambda garth=None: garmin_impl):
            yield

    def test_resume_failure_prompts_login(self):
        def resume(path):
            raise RuntimeError("token expired")
        with self.install_garmin(None, resume=resume):
            with self.assertRaises(SystemExit) as cm:
                garmin.fetch_raw(3, Path("/tmp/rc-unused-tokens"))
        self.assertIn("--login", str(cm.exception))

    def test_missing_dependency_prompts_install(self):
        with blocked_module("garth"), blocked_module("garminconnect"):
            with self.assertRaises(SystemExit) as cm:
                garmin.fetch_raw(3, Path("/tmp/rc-unused-tokens"))
        self.assertIn("pip install", str(cm.exception))

    def test_assembly_tolerates_endpoint_failures(self):
        boom_day = (date.today() - timedelta(days=1)).isoformat()

        class FakeGarmin:
            def get_sleep_data(self, day):
                if day == boom_day:
                    raise RuntimeError("endpoint down")  # 单端点失败不阻塞整体
                return {"dailySleepValues": {"calendarDate": day, "sleepTimeSeconds": 25200}}

            def get_hrv_data(self, day):
                return None  # 端点存在但无数据

            def get_stress_data(self, day):
                return {"calendarDate": day, "averageStressLevel": 30}

            def get_training_status(self, day):
                return {"currentTrainingLoad": {"acuteLoad": 480, "chronicLoad": 420}}

            # get_resting_hr / get_training_readiness / get_activities_by_date 缺失

        with self.install_garmin(FakeGarmin()):
            raw = garmin.fetch_raw(3, Path("/tmp/rc-unused-tokens"))

        self.assertEqual(len(raw["sleep"]), 2)      # 失败那天被丢弃
        self.assertNotIn("hrv", raw)                # 全空端点被剔除
        self.assertIn("stress", raw)
        self.assertIn("training_status", raw)
        self.assertNotIn("resting_hr", raw)         # 方法缺失 → 丢弃
        self.assertNotIn("activities", raw)
        self.assertEqual(raw["timezone"], "Asia/Shanghai")
        self.assertIn("as_of", raw)


class TestLoginInteractive(unittest.TestCase):
    def test_saves_token_to_requested_dir(self):
        calls = []

        with fake_module("garth",
                         login=lambda email, password: calls.append(("login", email)),
                         dump=lambda path: calls.append(("dump", path))), \
                contextlib.redirect_stdout(io.StringIO()):
            code = garmin.login_interactive(Path("/tmp/rc-test-tokens"),
                                            "a@example.com", "pw")
        self.assertEqual(code, 0)
        self.assertEqual(calls, [("login", "a@example.com"), ("dump", "/tmp/rc-test-tokens")])

    def test_missing_dependency_returns_4(self):
        with blocked_module("garth"):
            code = garmin.login_interactive(Path("/tmp/rc-test-tokens"), None, None)
        self.assertEqual(code, 4)


if __name__ == "__main__":
    unittest.main()
