#!/usr/bin/env python3
"""Build a compact, versioned AthleteContext from a structured COROS bundle."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any


def read_json(path: str | None) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("bundle must be a JSON object")
    return value


def records(bundle: dict[str, Any], *names: str) -> list[dict[str, Any]]:
    for name in names:
        value = bundle.get(name)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = value.get("records") or value.get("data")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def chronological(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: date_key(row) or "")


def as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def values(rows: list[dict[str, Any]], *keys: str) -> list[float]:
    result: list[float] = []
    for row in rows:
        for key in keys:
            number = as_float(row.get(key))
            if number is not None:
                result.append(number)
                break
    return result


def summarize_metric(rows: list[dict[str, Any]], *keys: str) -> dict[str, Any]:
    nums = values(rows, *keys)
    if not nums:
        return {"sample_count": 0, "median": None, "min": None, "max": None}
    return {"sample_count": len(nums), "median": round(median(nums), 2), "min": min(nums), "max": max(nums)}


def date_key(row: dict[str, Any]) -> str | None:
    for key in ("date", "metricDate", "day", "startDate"):
        value = row.get(key)
        if value:
            return str(value)[:10]
    return None


def trend(rows: list[dict[str, Any]], *keys: str) -> str:
    dated = [(date_key(row), values([row], *keys)[0] if values([row], *keys) else None) for row in rows]
    nums = [item[1] for item in dated if item[1] is not None]
    if len(nums) < 3:
        return "insufficient_data"
    half = max(1, len(nums) // 2)
    delta = median(nums[-half:]) - median(nums[:half])
    scale = max(abs(median(nums[:half])), 1.0)
    if abs(delta) <= scale * 0.03:
        return "stable"
    return "rising" if delta > 0 else "falling"


def coverage(bundle: dict[str, Any], health: list[dict[str, Any]], activities: list[dict[str, Any]]) -> dict[str, Any]:
    required = {
        "sleep": bool(records(bundle, "sleep", "sleep_data")),
        "sleep_hrv": bool(records(bundle, "sleep_hrv", "hrv", "hrv_data")),
        "resting_hr": bool(records(bundle, "resting_hr", "resting_heart_rate")),
        "stress": bool(records(bundle, "stress", "stress_data")),
        "recovery": bool(bundle.get("recovery") or bundle.get("recovery_status")),
        "training_load": bool(records(bundle, "training_load", "training_load_data")),
        "activities": bool(activities),
    }
    present = [key for key, found in required.items() if found]
    missing = [key for key, found in required.items() if not found]
    score = round(len(present) / len(required), 2)
    level = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    stale = list(bundle.get("stale") or []) if isinstance(bundle.get("stale"), list) else []
    conflicts = list(bundle.get("conflicts") or []) if isinstance(bundle.get("conflicts"), list) else []
    return {"level": level, "score": score, "present": present, "missing": missing, "stale": stale, "conflicts": conflicts}


def build_context(bundle: dict[str, Any]) -> dict[str, Any]:
    health = records(bundle, "daily_health", "health", "daily_metrics")
    sleep = chronological(records(bundle, "sleep", "sleep_data"))
    hrv = chronological(records(bundle, "sleep_hrv", "hrv", "hrv_data"))
    rhr = chronological(records(bundle, "resting_hr", "resting_heart_rate"))
    stress = chronological(records(bundle, "stress", "stress_data"))
    load = chronological(records(bundle, "training_load", "training_load_data"))
    activities = chronological(records(bundle, "activities", "sport_records", "activity_records"))
    latest_recovery = bundle.get("recovery") or bundle.get("recovery_status") or {}
    if not isinstance(latest_recovery, dict):
        latest_recovery = {}
    coverage_data = coverage(bundle, health, activities)
    risk_flags: list[dict[str, str]] = [dict(item) for item in bundle.get("risk_flags", []) if isinstance(item, dict)]
    load_ratio = next((as_float(row.get("load_ratio") or row.get("loadRatio")) for row in reversed(load) if as_float(row.get("load_ratio") or row.get("loadRatio")) is not None), None)
    if load_ratio is not None and load_ratio > 1.5:
        risk_flags.append({"code": "load_ratio_high", "severity": "high", "detail": "短期/长期负荷比高于 1.5。"})
    elif load_ratio is not None and load_ratio > 1.3:
        risk_flags.append({"code": "load_ratio_caution", "severity": "medium", "detail": "短期/长期负荷比高于 1.3。"})
    recovery_percent = as_float(latest_recovery.get("recovery_percent") or latest_recovery.get("recoveryPercentage"))
    if recovery_percent is not None and recovery_percent < 50:
        risk_flags.append({"code": "recovery_low", "severity": "medium", "detail": "恢复百分比偏低。"})
    if coverage_data["level"] == "low":
        risk_flags.append({"code": "coverage_low", "severity": "medium", "detail": "关键数据覆盖不足。"})
    if coverage_data["conflicts"]:
        risk_flags.append({"code": "data_conflict", "severity": "medium", "detail": "关键数据源或主客观信号存在冲突。"})
    sleep_values = values(sleep, "duration_hours", "sleep_hours", "mainSleepDuration")
    if sleep_values and sleep_values[-1] < 6:
        risk_flags.append({"code": "sleep_short", "severity": "medium", "detail": "最近一次主睡眠少于 6 小时。"})
    hrv_values = values(hrv, "average_hrv", "avgHrv", "hrv")
    if len(hrv_values) >= 3 and hrv_values[-1] < median(hrv_values[:-1]) * 0.9:
        risk_flags.append({"code": "hrv_below_baseline", "severity": "medium", "detail": "最新睡眠 HRV 明显低于近期基线。"})
    rhr_values = values(rhr, "resting_hr", "restingHeartRate", "rhr")
    if len(rhr_values) >= 3 and rhr_values[-1] >= median(rhr_values[:-1]) + 5:
        risk_flags.append({"code": "resting_hr_elevated", "severity": "medium", "detail": "最新静息心率比近期基线高至少 5 bpm。"})
    subjective = bundle.get("subjective") if isinstance(bundle.get("subjective"), dict) else {}
    if any(subjective.get(key) for key in ("chest_pain", "fainting", "abnormal_breathing", "abnormal_heart_rhythm")):
        risk_flags.append({"code": "medical_red_flag", "severity": "high", "detail": "存在需要停止训练并寻求专业评估的警讯。"})
    if subjective.get("pain_affects_gait"):
        risk_flags.append({"code": "gait_altering_pain", "severity": "high", "detail": "疼痛已经影响步态。"})
    if (as_float(subjective.get("fatigue_score")) or 0) >= 8 or (as_float(subjective.get("soreness_score")) or 0) >= 8:
        risk_flags.append({"code": "subjective_fatigue_high", "severity": "medium", "detail": "主观疲劳或酸痛评分偏高。"})
    environment = bundle.get("environment") if isinstance(bundle.get("environment"), dict) else {}
    if environment.get("heat_risk") in {"high", "extreme"}:
        risk_flags.append({"code": "heat_risk", "severity": "medium", "detail": "计划时段热应激风险较高。"})
    long_distances = [as_float(row.get("distance_km") or row.get("distanceKm")) or 0 for row in activities]
    total_distance = sum(long_distances)
    longest = max(long_distances, default=0)
    if total_distance and longest >= 12 and longest / total_distance > 0.35:
        risk_flags.append({"code": "long_run_share", "severity": "medium", "detail": "最长跑占活动窗口总跑量比例偏高。"})
    max_severity = max((flag["severity"] for flag in risk_flags), key=lambda x: {"low": 1, "medium": 2, "high": 3}.get(x, 0), default="low")
    readiness = "red" if max_severity == "high" else "yellow" if risk_flags or coverage_data["level"] != "high" else "green"
    return {
        "schema_version": "2.0",
        "as_of": bundle.get("as_of") or datetime.now(timezone.utc).isoformat(),
        "timezone": bundle.get("timezone") or "Asia/Shanghai",
        "request_type": bundle.get("request_type") or "daily-check",
        "windows": bundle.get("windows") or {},
        "sources": bundle.get("sources") or [{"name": "coros", "status": "provided"}],
        "coverage": coverage_data,
        "baselines": {
            "sleep": {**summarize_metric(sleep, "duration_hours", "sleep_hours", "mainSleepDuration"), "trend": trend(sleep, "duration_hours", "sleep_hours", "mainSleepDuration")},
            "hrv": {**summarize_metric(hrv, "average_hrv", "avgHrv", "hrv"), "trend": trend(hrv, "average_hrv", "avgHrv", "hrv")},
            "resting_hr": {**summarize_metric(rhr, "resting_hr", "restingHeartRate", "rhr"), "trend": trend(rhr, "resting_hr", "restingHeartRate", "rhr")},
            "stress": {**summarize_metric(stress, "stress", "average_stress", "avgStress"), "trend": trend(stress, "stress", "average_stress", "avgStress")},
            "training": {"activity_count": len(activities), "total_distance_km": round(total_distance, 2), "longest_run_km": longest, "latest_load_ratio": load_ratio, "load_trend": trend(load, "load_ratio", "loadRatio")},
        },
        "current_state": {"recovery": latest_recovery, "health": health[-1] if health else {}, "subjective": subjective, "environment": environment},
        "fitness": bundle.get("fitness") or {},
        "goal": bundle.get("goal") or {},
        "training_history": {"activities": activities, "training_load": load},
        "risk_flags": risk_flags,
        "readiness": {"level": readiness, "action": "rest_or_recovery" if readiness == "red" else "downshift" if readiness == "yellow" else "as_planned"},
        "evidence": bundle.get("evidence") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build AthleteContext V2 from a structured COROS bundle.")
    parser.add_argument("--input", help="JSON bundle path; defaults to stdin.")
    args = parser.parse_args()
    try:
        print(json.dumps(build_context(read_json(args.input)), ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
