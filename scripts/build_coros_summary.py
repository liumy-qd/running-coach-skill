#!/usr/bin/env python3
"""将常见 COROS MCP 文本结果整理为紧凑摘要。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from statistics import mean
from typing import Any


def read_text(path: str | None) -> str:
    if path:
        return Path(path).expanduser().read_text(encoding="utf-8")
    return sys.stdin.read()


def parse_fitness(text: str) -> dict[str, Any]:
    patterns = {
        "vo2max": r"^VO2max:\s*([0-9.]+)",
        "running_level": r"^Running Level:\s*([0-9.]+)",
        "threshold_pace": r"^Threshold Pace:\s*([0-9:]+)\s*/km",
        "prediction_5k": r"^5 km Prediction:\s*([0-9:]+)",
        "prediction_10k": r"^10 km Prediction:\s*([0-9:]+)",
        "prediction_half_marathon": r"^Half Marathon Prediction:\s*([0-9:]+)",
        "prediction_marathon": r"^Marathon Prediction:\s*([0-9:]+)",
    }
    result: dict[str, Any] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            result[key] = match.group(1)
    return result


def parse_recovery(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    recovery = re.search(r"^Recovery:\s*([0-9.]+)%", text, re.MULTILINE)
    level = re.search(r"^Level:\s*([^\n]+)", text, re.MULTILINE)
    full = re.search(r"^Estimated Full Recovery:\s*([^\n]+)", text, re.MULTILINE)
    if recovery:
        result["recovery_percent"] = float(recovery.group(1))
    if level:
        result["level"] = level.group(1).strip()
    if full:
        result["estimated_full_recovery"] = full.group(1).strip()
    return result


def parse_training_load(text: str) -> list[dict[str, Any]]:
    blocks = re.split(r"\n(?=\d{4}-\d{2}-\d{2}\n)", text)
    rows: list[dict[str, Any]] = []
    for block in blocks:
        date = re.search(r"(\d{4}-\d{2}-\d{2})", block)
        if not date:
            continue
        row: dict[str, Any] = {"date": date.group(1)}
        for key, pattern in {
            "comment": r"Comment:\s*([^\n]+)",
            "short_term_load": r"Short-Term Load:\s*([0-9.]+)",
            "long_term_load": r"Long-Term Load:\s*([0-9.]+)",
            "load_ratio": r"Load Ratio:\s*([0-9.]+)",
        }.items():
            match = re.search(pattern, block)
            if not match:
                continue
            value: Any = match.group(1).strip()
            if key != "comment":
                value = float(value)
            row[key] = value
        rows.append(row)
    return rows


def parse_sport_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    chunks = re.split(r"\n(?=\d+\.\s)", text)
    for chunk in chunks:
        header = re.search(r"\d+\.\s*(.+?)\s+(?:—|-)\s+(\d{4}-\d{2}-\d{2})", chunk)
        if not header:
            continue
        record: dict[str, Any] = {"sport": header.group(1).strip(), "date": header.group(2)}
        fields = {
            "location": r"Location:\s*([^\n]+)",
            "distance_km": r"Distance:\s*([0-9.]+)\s*km",
            "duration": r"Duration:\s*([^|]+)",
            "average_pace": r"Average Pace:\s*([0-9:]+)\s*/km",
            "avg_hr": r"Avg HR:\s*([0-9.]+)\s*bpm",
            "label_id": r"LabelId:\s*([0-9]+)",
            "sport_type": r"SportType:\s*([0-9]+)",
            "start_timestamp": r"startTimestamp=([0-9]+)",
            "end_timestamp": r"endTimestamp=([0-9]+)",
        }
        for key, pattern in fields.items():
            match = re.search(pattern, chunk)
            if not match:
                continue
            value: Any = match.group(1).strip()
            if key in {"distance_km", "avg_hr"}:
                value = float(value)
            elif key in {"sport_type", "start_timestamp", "end_timestamp"}:
                value = int(value)
            record[key] = value
        records.append(record)
    return records


def pace_to_seconds(value: str | None) -> int | None:
    if not value:
        return None
    parts = value.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return None


def parse_duration_minutes(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    hms = re.search(r"(?:(\d+):)?(\d+):(\d+)", value)
    if hms:
        hours = int(hms.group(1) or 0)
        minutes = int(hms.group(2))
        seconds = int(hms.group(3))
        return round(hours * 60 + minutes + seconds / 60, 1)
    minutes = re.search(r"([0-9.]+)\s*min", value, re.IGNORECASE)
    if minutes:
        return float(minutes.group(1))
    return None


def infer_activity_type(record: dict[str, Any], threshold_pace: str | None = None) -> str:
    distance = record.get("distance_km") or 0
    duration_min = parse_duration_minutes(record.get("duration"))
    pace_seconds = pace_to_seconds(record.get("average_pace"))
    threshold_seconds = pace_to_seconds(threshold_pace)
    title = " ".join(str(record.get(key, "")) for key in ("sport", "location")).lower()
    if any(keyword in title for keyword in ("interval", "间歇", "track", "田径")):
        return "workout"
    if any(keyword in title for keyword in ("race", "比赛")):
        return "race"
    if distance >= 18 or (duration_min is not None and duration_min >= 90):
        return "long_run"
    if threshold_seconds and pace_seconds and pace_seconds <= threshold_seconds * 1.05:
        return "quality"
    if distance >= 12:
        return "medium_long"
    return "easy_or_general"


def build_activity_profile(records: list[dict[str, Any]], fitness: dict[str, Any]) -> dict[str, Any]:
    if not records:
        return {"count": 0, "total_distance_km": 0, "quality_count": 0, "long_run_count": 0}
    threshold_pace = fitness.get("threshold_pace")
    distances = [float(record.get("distance_km") or 0) for record in records]
    durations = [parse_duration_minutes(record.get("duration")) for record in records]
    typed_records: list[dict[str, Any]] = []
    for record in records:
        enriched = dict(record)
        enriched["duration_min"] = parse_duration_minutes(record.get("duration"))
        enriched["activity_type"] = infer_activity_type(record, threshold_pace)
        typed_records.append(enriched)
    quality_count = sum(1 for record in typed_records if record["activity_type"] in {"workout", "quality", "race"})
    long_run_count = sum(1 for record in typed_records if record["activity_type"] == "long_run")
    longest = max(typed_records, key=lambda item: item.get("distance_km") or 0)
    total_distance = sum(distances)
    return {
        "count": len(records),
        "total_distance_km": round(total_distance, 2),
        "avg_distance_km": round(mean(distances), 2) if distances else 0,
        "total_duration_min": round(sum(item for item in durations if item is not None), 1),
        "longest_run_km": max(distances, default=0),
        "longest_run": {
            "date": longest.get("date"),
            "distance_km": longest.get("distance_km"),
            "average_pace": longest.get("average_pace"),
            "avg_hr": longest.get("avg_hr"),
            "label_id": longest.get("label_id"),
            "sport_type": longest.get("sport_type"),
        },
        "quality_count": quality_count,
        "long_run_count": long_run_count,
        "records": typed_records,
    }


def build_coverage(summary: dict[str, Any]) -> dict[str, Any]:
    present: list[str] = []
    missing: list[str] = []
    expected = {
        "fitness": "体能评估",
        "recovery": "恢复状态",
        "training_load": "训练负荷",
        "sport_records": "运动记录",
    }
    for key, label in expected.items():
        if summary.get(key):
            present.append(label)
        else:
            missing.append(label)
    score = len(present) / len(expected)
    if score >= 0.75:
        level = "high"
    elif score >= 0.5:
        level = "medium"
    else:
        level = "low"
    return {
        "level": level,
        "present": present,
        "missing": missing,
        "score": round(score, 2),
    }


def build_baseline(summary: dict[str, Any]) -> dict[str, Any]:
    activity_profile = summary.get("activity_profile") or {}
    loads = summary.get("training_load") or []
    latest_load = loads[-1] if loads else {}
    records = activity_profile.get("records") or []
    avg_hr_values = [float(record["avg_hr"]) for record in records if isinstance(record.get("avg_hr"), (int, float))]
    return {
        "activity_window_count": activity_profile.get("count", 0),
        "total_distance_km": activity_profile.get("total_distance_km", 0),
        "longest_run_km": activity_profile.get("longest_run_km", 0),
        "quality_count": activity_profile.get("quality_count", 0),
        "long_run_count": activity_profile.get("long_run_count", 0),
        "avg_activity_hr": round(mean(avg_hr_values), 1) if avg_hr_values else None,
        "latest_load_ratio": latest_load.get("load_ratio"),
    }


def build_risk(summary: dict[str, Any]) -> dict[str, Any]:
    flags: list[dict[str, str]] = []
    recovery = summary.get("recovery") or {}
    load_rows = summary.get("training_load") or []
    activity_profile = summary.get("activity_profile") or {}
    latest_load = load_rows[-1] if load_rows else {}
    load_ratio = latest_load.get("load_ratio")
    if isinstance(load_ratio, (int, float)):
        if load_ratio > 1.5:
            flags.append({"severity": "high", "code": "load_ratio_high", "detail": "短期/长期负荷比高于 1.5。"})
        elif load_ratio > 1.3:
            flags.append({"severity": "medium", "code": "load_ratio_caution", "detail": "短期/长期负荷比高于 1.3。"})
    recovery_percent = recovery.get("recovery_percent")
    if isinstance(recovery_percent, (int, float)) and recovery_percent < 50:
        flags.append({"severity": "medium", "code": "recovery_low", "detail": "恢复百分比偏低。"})
    quality_count = activity_profile.get("quality_count") or 0
    if quality_count >= 3:
        flags.append({"severity": "medium", "code": "quality_density", "detail": "近期质量课或比赛密度偏高。"})
    longest = activity_profile.get("longest_run_km") or 0
    total = activity_profile.get("total_distance_km") or 0
    if total > 0 and longest / total > 0.35 and longest >= 12:
        flags.append({"severity": "medium", "code": "long_run_share", "detail": "最长跑占近期总跑量比例偏高。"})
    readiness = "green"
    if any(item["severity"] == "high" for item in flags):
        readiness = "red"
    elif flags:
        readiness = "yellow"
    return {"readiness_hint": readiness, "flags": flags}


def build_summary(text: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    fitness = parse_fitness(text)
    recovery = parse_recovery(text)
    loads = parse_training_load(text)
    records = parse_sport_records(text)
    if fitness:
        summary["fitness"] = fitness
    if recovery:
        summary["recovery"] = recovery
    if loads:
        summary["training_load"] = loads
    if records:
        total_distance = sum(record.get("distance_km", 0) for record in records)
        summary["sport_records"] = {
            "count": len(records),
            "total_distance_km": round(total_distance, 2),
            "longest_run_km": max((record.get("distance_km", 0) for record in records), default=0),
            "records": records,
        }
    summary["activity_profile"] = build_activity_profile(records, fitness)
    summary["coverage"] = build_coverage(summary)
    summary["baseline"] = build_baseline(summary)
    summary["risk"] = build_risk(summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="整理 COROS MCP 文本结果，输出 JSON 摘要。")
    parser.add_argument("--input", help="输入文本文件；省略时从 stdin 读取。")
    args = parser.parse_args()

    text = read_text(args.input)
    if not text.strip():
        parser.error("需要提供 COROS MCP 文本")
    print(json.dumps(build_summary(text), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
