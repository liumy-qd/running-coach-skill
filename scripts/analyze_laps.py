#!/usr/bin/env python3
"""分析 COROS queryActivityLapData 返回的圈速 JSON。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any


def read_text(path: str | None) -> str:
    if path:
        return Path(path).expanduser().read_text(encoding="utf-8")
    return sys.stdin.read()


def pace_text(seconds_per_km: float | None) -> str:
    if seconds_per_km is None or not math.isfinite(seconds_per_km):
        return "-"
    minutes = int(seconds_per_km // 60)
    seconds = int(round(seconds_per_km - minutes * 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/km"


def km(distance_value: float | int | None) -> float:
    if distance_value is None:
        return 0.0
    return float(distance_value) / 100000.0


def lap_pace(lap: dict[str, Any]) -> float | None:
    value = lap.get("avgPace")
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    distance_km = km(lap.get("distance"))
    time_seconds = lap.get("time")
    if distance_km > 0 and isinstance(time_seconds, (int, float)):
        return float(time_seconds) / distance_km
    return None


def find_group(data: dict[str, Any], target_type: int | None = None) -> dict[str, Any] | None:
    groups = data.get("lapGroups") or []
    if target_type is not None:
        for group in groups:
            if group.get("type") == target_type and group.get("laps"):
                return group
    groups_with_laps = [group for group in groups if group.get("laps")]
    if not groups_with_laps:
        return None
    return max(groups_with_laps, key=lambda group: len(group.get("laps") or []))


def summarize_laps(laps: list[dict[str, Any]]) -> dict[str, Any]:
    distances = [km(lap.get("distance")) for lap in laps]
    times = [float(lap.get("time") or 0) for lap in laps]
    heart_rates = [float(lap.get("avgHr")) for lap in laps if isinstance(lap.get("avgHr"), (int, float))]
    paces = [pace for pace in (lap_pace(lap) for lap in laps) if pace is not None]
    total_distance = sum(distances)
    total_time = sum(times)
    avg_pace = total_time / total_distance if total_distance > 0 else None
    return {
        "lap_count": len(laps),
        "distance_km": round(total_distance, 2),
        "duration_seconds": round(total_time, 1),
        "avg_pace_seconds_per_km": round(avg_pace, 2) if avg_pace else None,
        "avg_pace": pace_text(avg_pace),
        "avg_hr": round(mean(heart_rates), 1) if heart_rates else None,
        "pace_std_seconds": round(pstdev(paces), 1) if len(paces) > 1 else 0,
        "avg_cadence": round(mean([float(lap.get("avgCadence")) for lap in laps if isinstance(lap.get("avgCadence"), (int, float))]), 1)
        if any(isinstance(lap.get("avgCadence"), (int, float)) for lap in laps)
        else None,
        "avg_power": round(mean([float(lap.get("avgPower")) for lap in laps if isinstance(lap.get("avgPower"), (int, float))]), 1)
        if any(isinstance(lap.get("avgPower"), (int, float)) for lap in laps)
        else None,
    }


def split_halves(laps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    total_distance = sum(km(lap.get("distance")) for lap in laps)
    midpoint = total_distance / 2
    first: list[dict[str, Any]] = []
    second: list[dict[str, Any]] = []
    current = 0.0
    for lap in laps:
        current += km(lap.get("distance"))
        if current <= midpoint:
            first.append(lap)
        else:
            second.append(lap)
    return first, second


def detect_fast_laps(laps: list[dict[str, Any]], overall_pace: float | None) -> list[dict[str, Any]]:
    if overall_pace is None:
        return []
    fast: list[dict[str, Any]] = []
    for lap in laps:
        pace = lap_pace(lap)
        distance = km(lap.get("distance"))
        if pace is None or distance < 0.2:
            continue
        if pace <= overall_pace * 0.86:
            fast.append(
                {
                    "lap_index": lap.get("lapIndex"),
                    "distance_km": round(distance, 2),
                    "pace": pace_text(pace),
                    "avg_hr": lap.get("avgHr"),
                    "max_hr": lap.get("maxHr"),
                    "avg_cadence": lap.get("avgCadence"),
                    "avg_power": lap.get("avgPower"),
                }
            )
    return fast


def drift_analysis(first_summary: dict[str, Any], second_summary: dict[str, Any]) -> dict[str, Any]:
    first_hr = first_summary.get("avg_hr")
    second_hr = second_summary.get("avg_hr")
    first_pace = first_summary.get("avg_pace_seconds_per_km")
    second_pace = second_summary.get("avg_pace_seconds_per_km")
    hr_delta = round(second_hr - first_hr, 1) if isinstance(first_hr, (int, float)) and isinstance(second_hr, (int, float)) else None
    pace_delta = (
        round(second_pace - first_pace, 1)
        if isinstance(first_pace, (int, float)) and isinstance(second_pace, (int, float))
        else None
    )
    level = "unknown"
    notes: list[str] = []
    if hr_delta is not None:
        if hr_delta >= 6:
            notes.append(f"后半程平均心率高出 {hr_delta} bpm。")
        elif hr_delta >= 3:
            notes.append(f"后半程平均心率高出 {hr_delta} bpm，轻度漂移。")
    if pace_delta is not None:
        if pace_delta >= 10:
            notes.append(f"后半程配速慢 {pace_delta:.1f} 秒/km。")
        elif pace_delta <= -10:
            notes.append(f"后半程配速快 {abs(pace_delta):.1f} 秒/km，可能是渐进跑。")
    if (hr_delta is not None and hr_delta >= 6) and (pace_delta is not None and pace_delta >= 10):
        level = "severe_fade"
    elif hr_delta is not None and hr_delta >= 6:
        level = "cardiac_drift"
    elif pace_delta is not None and pace_delta >= 10:
        level = "pace_fade"
    elif pace_delta is not None and pace_delta <= -10:
        level = "progression"
    elif (hr_delta is not None and hr_delta >= 3) or (pace_delta is not None and pace_delta >= 5):
        level = "mild_drift"
    elif hr_delta is not None or pace_delta is not None:
        level = "stable"
    return {
        "level": level,
        "hr_delta_bpm": hr_delta,
        "pace_delta_seconds_per_km": pace_delta,
        "notes": notes,
    }


def segment_stability(group: dict[str, Any] | None) -> dict[str, Any]:
    laps = group.get("laps", []) if group else []
    paces = [pace for pace in (lap_pace(lap) for lap in laps) if pace is not None]
    if len(paces) < 2:
        return {"available": False, "segment_count": len(paces)}
    avg_pace = mean(paces)
    spread = max(paces) - min(paces)
    std = pstdev(paces)
    spread_pct = spread / avg_pace * 100 if avg_pace else 0
    if spread_pct <= 3:
        rating = "stable"
    elif spread_pct <= 6:
        rating = "moderate_variation"
    else:
        rating = "unstable"
    return {
        "available": True,
        "segment_count": len(paces),
        "avg_pace": pace_text(avg_pace),
        "pace_std_seconds": round(std, 1),
        "pace_spread_seconds": round(spread, 1),
        "pace_spread_percent": round(spread_pct, 1),
        "rating": rating,
    }


def detect_interval_candidates(laps: list[dict[str, Any]]) -> dict[str, Any]:
    pace_values = [pace for pace in (lap_pace(lap) for lap in laps) if pace is not None]
    if len(pace_values) < 4:
        return {"available": False, "reason": "laps_insufficient", "fast_repetitions": []}
    threshold = median(pace_values) * 0.9
    repetitions: list[dict[str, Any]] = []
    for lap in laps:
        pace = lap_pace(lap)
        distance = km(lap.get("distance"))
        if pace is None or distance < 0.15:
            continue
        if pace <= threshold:
            repetitions.append(
                {
                    "lap_index": lap.get("lapIndex"),
                    "distance_km": round(distance, 2),
                    "pace_seconds_per_km": round(pace, 1),
                    "pace": pace_text(pace),
                    "avg_hr": lap.get("avgHr"),
                    "max_hr": lap.get("maxHr"),
                }
            )
    if len(repetitions) < 2:
        return {"available": False, "reason": "no_repeated_fast_segments", "fast_repetitions": repetitions}
    paces = [item["pace_seconds_per_km"] for item in repetitions]
    first_half = paces[: max(1, len(paces) // 2)]
    second_half = paces[max(1, len(paces) // 2) :]
    fade_seconds = round(mean(second_half) - mean(first_half), 1) if second_half else 0
    fade_percent = round(fade_seconds / mean(first_half) * 100, 1) if first_half and mean(first_half) else 0
    if fade_percent >= 5:
        fade_rating = "clear_fade"
    elif fade_percent >= 3:
        fade_rating = "mild_fade"
    elif fade_percent <= -3:
        fade_rating = "progressive"
    else:
        fade_rating = "stable"
    return {
        "available": True,
        "threshold_pace": pace_text(threshold),
        "repeat_count": len(repetitions),
        "pace_spread_seconds": round(max(paces) - min(paces), 1),
        "fade_seconds": fade_seconds,
        "fade_percent": fade_percent,
        "fade_rating": fade_rating,
        "fast_repetitions": repetitions,
    }


def risk_flags(
    lap_summary: dict[str, Any],
    drift: dict[str, Any],
    intervals: dict[str, Any],
    five_km_stability: dict[str, Any],
) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    distance = lap_summary.get("distance_km") or 0
    if distance >= 18 and drift.get("level") in {"cardiac_drift", "pace_fade", "severe_fade"}:
        flags.append({"severity": "medium", "code": "long_run_drift", "detail": "长距离后半程出现漂移或掉速。"})
    if drift.get("level") == "severe_fade":
        flags.append({"severity": "high", "code": "severe_fade", "detail": "后半程同时心率上升和配速下降。"})
    if intervals.get("available") and intervals.get("fade_rating") in {"mild_fade", "clear_fade"}:
        flags.append({"severity": "medium", "code": "interval_fade", "detail": "快速段后半组出现衰减。"})
    if five_km_stability.get("available") and five_km_stability.get("rating") == "unstable" and distance >= 10:
        flags.append({"severity": "low", "code": "segment_variation", "detail": "5 km 分段波动偏大，需结合地形和天气解释。"})
    return flags


def build_analysis(data: dict[str, Any]) -> dict[str, Any]:
    one_km_group = find_group(data, 2) or find_group(data, 10)
    five_km_group = find_group(data, 11)
    selected_group = one_km_group or find_group(data)
    laps = selected_group.get("laps", []) if selected_group else []
    total_group = find_group(data, -1)
    total_laps = total_group.get("laps", []) if total_group else laps
    total_summary = summarize_laps(total_laps or laps)
    lap_summary = summarize_laps(laps)
    first_half, second_half = split_halves(laps)
    first_summary = summarize_laps(first_half)
    second_summary = summarize_laps(second_half)
    overall_pace = lap_summary.get("avg_pace_seconds_per_km")
    drift = drift_analysis(first_summary, second_summary)
    fast_laps = detect_fast_laps(laps, float(overall_pace) if overall_pace else None)
    intervals = detect_interval_candidates(laps)
    one_km_stability = segment_stability(one_km_group)
    five_km_stability = segment_stability(five_km_group)
    return {
        "schema_version": "2.0",
        "activity": {"labelId": data.get("labelId"), "sportType": data.get("sportType")},
        "summary": lap_summary,
        "total_summary": total_summary,
        "first_half": first_summary,
        "second_half": second_summary,
        "drift": drift,
        "fast_laps": fast_laps,
        "interval_candidates": intervals,
        "segment_stability": {"one_km": one_km_stability, "five_km": five_km_stability},
        "risk_flags": risk_flags(lap_summary, drift, intervals, five_km_stability),
    }


def build_markdown(data: dict[str, Any]) -> str:
    analysis = build_analysis(data)
    total_summary = analysis["total_summary"]
    lap_summary = analysis["summary"]
    first_summary = analysis["first_half"]
    second_summary = analysis["second_half"]
    fast_laps = analysis["fast_laps"]
    drift = analysis["drift"]
    intervals = analysis["interval_candidates"]
    segment_stability_result = analysis["segment_stability"]
    risk_items = analysis["risk_flags"]

    lines = [
        "# COROS 圈速分析",
        "",
        f"- 活动：labelId `{data.get('labelId', '-')}`，sportType `{data.get('sportType', '-')}`",
        f"- 总览：{total_summary['distance_km']} km，均速 {total_summary['avg_pace']}，平均心率 {total_summary['avg_hr']}",
        f"- 圈速样本：{lap_summary['lap_count']} 圈，均速 {lap_summary['avg_pace']}，配速标准差 {lap_summary['pace_std_seconds']} 秒",
        "",
        "## 前后半程",
        "",
        f"- 前半程：{first_summary['distance_km']} km，{first_summary['avg_pace']}，平均心率 {first_summary['avg_hr']}",
        f"- 后半程：{second_summary['distance_km']} km，{second_summary['avg_pace']}，平均心率 {second_summary['avg_hr']}",
        f"- 漂移判断：{drift['level']}，心率变化 {drift['hr_delta_bpm']} bpm，配速变化 {drift['pace_delta_seconds_per_km']} 秒/km",
    ]
    if drift["notes"]:
        lines.extend(["", "## 风险标记", ""])
        lines.extend(f"- {note}" for note in drift["notes"])
    if risk_items:
        lines.extend(f"- [{item['severity']}] {item['detail']}" for item in risk_items)
    if segment_stability_result["five_km"].get("available"):
        item = segment_stability_result["five_km"]
        lines.extend(["", "## 5 km 分段稳定性", ""])
        lines.append(
            f"- {item['segment_count']} 段，均速 {item['avg_pace']}，配速波动 {item['pace_spread_seconds']} 秒，评级 {item['rating']}"
        )
    if intervals.get("available"):
        lines.extend(["", "## 间歇候选", ""])
        lines.append(
            f"- 快速段 {intervals['repeat_count']} 个，阈值 {intervals['threshold_pace']}，"
            f"后半衰减 {intervals['fade_seconds']} 秒（{intervals['fade_rating']}）"
        )
    if fast_laps:
        lines.extend(["", "## 快速段候选", ""])
        for item in fast_laps[:12]:
            lines.append(
                f"- 圈 {item['lap_index']}：{item['distance_km']} km，{item['pace']}，"
                f"平均心率 {item['avg_hr']}，最大心率 {item['max_hr']}"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="分析 COROS 圈速 JSON，并输出中文 Markdown 摘要。")
    parser.add_argument("--input", help="输入 JSON 文件；省略时从 stdin 读取。")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON。")
    args = parser.parse_args()

    text = read_text(args.input).strip()
    if not text:
        parser.error("需要提供 queryActivityLapData 的 JSON 内容")
    data = json.loads(text)
    if args.json:
        print(json.dumps(build_analysis(data), ensure_ascii=False, indent=2))
    else:
        print(build_markdown(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
