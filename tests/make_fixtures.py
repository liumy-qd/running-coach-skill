#!/usr/bin/env python3
"""确定性生成 tests/fixtures 下的测试数据。运行：python3 tests/make_fixtures.py"""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"


# ---------------------------------------------------------------------------
# fit_records.json：一场 10 km 比赛的逐秒合成记录
# 赛段设计：0-4.5km 平路 5:00 → 4.5km 处停表 25s → 5-6.5km 3.5% 爬坡
# → 6.5-8km 下坡 → 8-9.5km 平路硬撑（同配速心率漂移）→ 9.5-10km 掉速爆点
# ---------------------------------------------------------------------------

def make_fit_records() -> dict:
    # (段长 km，0 表示原地停表 25 秒；speed m/s；grade；心率偏移)
    plan = [
        (4.5, 3.333, 0.000, 0),
        (0.0, 0.100, 0.000, 0),      # 4.5 km 补给停表
        (0.5, 3.333, 0.000, 0),
        (1.5, 2.900, 0.035, 8),      # 爬坡
        (1.5, 3.700, -0.030, -4),    # 下坡
        (1.5, 3.333, 0.000, 2),      # 硬撑：同配速但心率随漂移上升
        (0.5, 2.600, 0.000, 18),     # 爆点
    ]
    records = []
    ts = 1726368000
    dist = 0.0
    alt = 50.0
    for seg_km, speed, grade, offset in plan:
        if seg_km == 0.0:
            for _ in range(25):  # 停表：时间流逝，距离不变
                records.append(_record(ts, dist, alt, speed, grade, offset, dist / 10000.0))
                ts += 1
            continue
        target = dist + seg_km * 1000.0
        while dist < target - 1e-6:
            records.append(_record(ts, dist, alt, speed, grade, offset, dist / 10000.0))
            dist += speed
            alt += speed * grade
            ts += 1
    return {
        "meta": {"name": "测试-10km-比赛", "sport": "race", "start_time": "2026-09-06T07:30:00+08:00"},
        "records": records,
    }


def _record(ts: float, dist: float, alt: float, speed: float, grade: float,
            offset: int, frac: float) -> dict:
    drift = 8.0 * frac  # 全程 8 bpm 的同配速心率漂移
    hr = 150 + 6 * (speed - 3.333) + 250 * grade + drift + offset
    return {
        "ts": ts,
        "dist": round(dist, 2),
        "speed": round(speed, 3),
        "hr": int(round(hr)),
        "cad": 178 if frac < 0.5 else 172,
        "alt": round(alt + 0.8 * math.sin(ts / 37.0), 2),
        "grade": grade,
        "temp": round(21 + 6 * frac, 1),
        "power": int(round(230 + 30 * (speed - 3.333) + 120 * frac)),
    }


# ---------------------------------------------------------------------------
# laps.json：queryActivityLapData 形状的间歇/节奏课，后半程明显衰减
# distance 单位与 COROS 一致：值 / 100000 = km
# ---------------------------------------------------------------------------

def make_laps() -> dict:
    paces = [300, 300, 300, 300, 300, 315, 320, 335, 345, 360]  # 秒/km
    hrs = [152, 153, 155, 156, 158, 162, 164, 167, 169, 172]
    laps = []
    for i, (pace, hr) in enumerate(zip(paces, hrs)):
        laps.append({
            "lapIndex": i + 1,
            "distance": 100000,           # 1 km
            "time": pace,                 # 1 km 用时 = pace 秒
            "avgPace": pace,
            "avgHr": hr,
            "maxHr": hr + 6,
            "avgCadence": 178 - i,
            "avgPower": 250 - i * 3,
        })
    return {"labelId": 123456, "sportType": 100, "lapGroups": [{"type": 2, "laps": laps}]}


# ---------------------------------------------------------------------------
# context_bundle.json：触发 red readiness 的最小 bundle
# ---------------------------------------------------------------------------

def make_context_bundle() -> dict:
    health = [
        {"date": f"2026-09-{8 + i:02d}", "sleep_hours": 7.2, "stress": 28}
        for i in range(6)
    ] + [{"date": "2026-09-14", "sleep_hours": 5.4, "stress": 41}]
    return {
        "as_of": "2026-09-15T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "request_type": "daily-check",
        "daily_health": health,
        "sleep": health,
        "resting_hr": [{"date": f"2026-09-{8 + i:02d}", "resting_hr": 52 + (6 if i == 6 else 0)} for i in range(7)],
        "sleep_hrv": [{"date": f"2026-09-{8 + i:02d}", "avgHrv": 72 - (12 if i == 6 else 0)} for i in range(7)],
        "stress": [{"date": f"2026-09-{8 + i:02d}", "average_stress": 30} for i in range(7)],
        "recovery": {"recovery_percent": 38, "level": "poor"},
        "training_load": [{"date": "2026-09-14", "load_ratio": 1.62}],
        "activities": [
            {"date": "2026-09-10", "distance_km": 8.0},
            {"date": "2026-09-12", "distance_km": 26.0},
            {"date": "2026-09-13", "distance_km": 6.0},
        ],
        "subjective": {},
        "environment": {},
    }


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    payloads = {
        "fit_records.json": make_fit_records(),
        "laps.json": make_laps(),
        "context_bundle.json": make_context_bundle(),
    }
    for name, payload in payloads.items():
        path = FIXTURES / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"{path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
