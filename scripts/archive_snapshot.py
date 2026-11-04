#!/usr/bin/env python3
"""把每次取到的真实数据抽成瘦身快照，归档为本地按月 JSONL 档案。

档案默认位于仓库外（~/.running-coach/archive/），可用 --archive-dir 或环境变量
RUNNING_COACH_ARCHIVE 覆盖。写入前做脱敏扫描：token/坐标/经期字段/超长数值序列
一律拒绝，FIT 原件与逐秒数据不入档。同 (date, record_type) 的记录按 upsert
合并，活动按 label_id 去重，重复检查更新而不是堆积。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

DEFAULT_ARCHIVE_DIR = Path.home() / ".running-coach" / "archive"
RECORD_SCHEMA_VERSION = "1.0"
TZ = timezone(timedelta(hours=8))  # Asia/Shanghai；写入时统一归属日期

# 禁止入档的字段名（小写子串匹配，只扫 key 不扫值）
FORBIDDEN_KEY_PATTERNS = re.compile(
    r"token|secret|oauth|password|authorization|latitude|longitude|"
    r"position_lat|position_long|\bgps\b|coordinate|menstrua|ovulat|pregnan",
    re.IGNORECASE,
)
# 逐秒原始数据启发式：数值数组超过该长度视为原始流水，拒绝入档
MAX_NUMERIC_ARRAY = 500


def read_json(path: str | None) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"{path or 'stdin'} 必须是 JSON 对象")
    return value


def as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row.get(key)
    return None


def date_of(row: dict[str, Any]) -> str | None:
    value = pick(row, "date", "metricDate", "day", "startDate")
    return str(value)[:10] if value else None


def rows_of(bundle: dict[str, Any], *names: str) -> list[dict[str, Any]]:
    for name in names:
        value = bundle.get(name)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = value.get("records") or value.get("data")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    dated = sorted((row for row in rows if date_of(row)), key=date_of)
    return dated[-1] if dated else None


# ---------------------------------------------------------------------------
# 脱敏扫描
# ---------------------------------------------------------------------------

def scan_violations(node: Any, path: str = "$") -> list[str]:
    violations: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}"
            if FORBIDDEN_KEY_PATTERNS.search(str(key)):
                violations.append(f"敏感字段: {child}")
            violations.extend(scan_violations(value, child))
    elif isinstance(node, list):
        if len(node) > MAX_NUMERIC_ARRAY and all(isinstance(v, (int, float)) for v in node):
            violations.append(f"疑似逐秒/原始数值序列: {path}（{len(node)} 个数值）")
        for index, value in enumerate(node):
            violations.extend(scan_violations(value, f"{path}[{index}]"))
    return violations


# ---------------------------------------------------------------------------
# 瘦身记录抽取
# ---------------------------------------------------------------------------

def slim_sleep(bundle: dict[str, Any]) -> dict[str, Any]:
    row = latest(rows_of(bundle, "sleep", "sleep_data")) or {}
    out: dict[str, Any] = {}
    for field, keys in {
        "duration_hours": ("duration_hours", "sleep_hours", "mainSleepDuration"),
        "score": ("score", "sleepScore"),
    }.items():
        value = as_float(pick(row, *keys))
        if value is not None:
            out[field] = value
    return {"sleep": out} if out else {}


def slim_hrv(bundle: dict[str, Any]) -> dict[str, Any]:
    row = latest(rows_of(bundle, "sleep_hrv", "hrv", "hrv_data")) or {}
    out: dict[str, Any] = {}
    for field, keys in {
        "value": ("average_hrv", "avgHrv", "hrv"),
        "baseline": ("baseline", "hrvBaseline"),
    }.items():
        value = as_float(pick(row, *keys))
        if value is not None:
            out[field] = value
    return {"hrv": out} if out else {}


def slim_metric(bundle: dict[str, Any], names: tuple[str, ...], keys: tuple[str, ...], field: str) -> dict[str, Any]:
    row = latest(rows_of(bundle, *names)) or {}
    value = as_float(pick(row, *keys))
    return {field: value} if value is not None else {}


def slim_activities(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows_of(bundle, "activities", "sport_records", "activity_records"):
        slim: dict[str, Any] = {}
        for field, keys in {
            "label_id": ("labelId", "label_id"),
            "sport_type": ("sportType", "sport_type"),
            "date": ("date", "startDate"),
            "distance_km": ("distance_km", "distanceKm"),
            "duration_min": ("duration_min", "durationMin"),
            "avg_pace_sec_km": ("avg_pace_sec_km", "avgPace"),
            "avg_hr": ("avg_hr", "avgHr", "average_hr"),
            "training_load": ("training_load", "trainingLoad", "load"),
        }.items():
            value = pick(row, *keys)
            if value is not None:
                slim[field] = value
        if slim.get("distance_km") is not None or slim.get("label_id") is not None:
            out.append(slim)
    return out


def slim_prescription(rx: dict[str, Any]) -> dict[str, Any]:
    session = rx.get("session") if isinstance(rx.get("session"), dict) else {}
    return {
        "decision": rx.get("decision"),
        "readiness": rx.get("readiness"),
        "confidence": rx.get("confidence"),
        "session": {
            key: session.get(key)
            for key in ("type", "purpose", "duration_min", "distance_km", "intensity")
            if session.get(key) is not None
        },
    }


def slim_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"tool": analysis.get("tool")}
    for key in ("summary", "flags", "drift", "stops", "interval_candidates"):
        value = analysis.get(key)
        if value is not None:
            out[key] = value
    return {key: value for key, value in out.items() if value is not None}


def build_record(
    bundle: dict[str, Any] | None,
    context: dict[str, Any] | None,
    prescription: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
    record_type: str,
    date_override: str | None,
    notes: str | None,
) -> dict[str, Any]:
    bundle = bundle or {}
    context = context or {}
    as_of = context.get("as_of") or bundle.get("as_of") or datetime.now(TZ).isoformat()
    record_date = date_override or str(as_of)[:10]
    now = datetime.now(TZ).isoformat(timespec="seconds")

    record: dict[str, Any] = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "record_type": record_type,
        "date": record_date,
        "timezone": context.get("timezone") or bundle.get("timezone") or "Asia/Shanghai",
        "archived_at": now,
        "revision": 1,
    }
    sources = [
        str(source.get("name"))
        for source in (bundle.get("sources") or [])
        if isinstance(source, dict) and source.get("name")
    ]
    if sources:
        record["sources"] = sources

    health: dict[str, Any] = {}
    for part in (
        slim_sleep(bundle),
        slim_hrv(bundle),
        slim_metric(bundle, ("resting_hr", "resting_heart_rate"), ("resting_hr", "restingHeartRate", "rhr"), "resting_hr"),
        slim_metric(bundle, ("stress", "stress_data"), ("stress", "average_stress", "avgStress"), "stress_avg"),
    ):
        health.update(part)
    load_row = latest(rows_of(bundle, "training_load", "training_load_data")) or {}
    load_ratio = as_float(pick(load_row, "load_ratio", "loadRatio"))
    if load_ratio is not None:
        health["load_ratio"] = load_ratio
    if health:
        record["health"] = health

    recovery = bundle.get("recovery") or bundle.get("recovery_status") or (context.get("current_state") or {}).get("recovery")
    if isinstance(recovery, dict) and recovery:
        slim: dict[str, Any] = {}
        percent = as_float(pick(recovery, "recovery_percent", "recoveryPercentage"))
        if percent is not None:
            slim["percent"] = percent
        level = pick(recovery, "level", "recoveryLevel")
        if level is not None:
            slim["level"] = level
        if slim:
            record["recovery"] = slim

    activities = slim_activities(bundle)
    if activities:
        record["activities"] = activities

    fitness = bundle.get("fitness") or context.get("fitness")
    if isinstance(fitness, dict) and fitness:
        record["fitness"] = {
            key: fitness.get(key)
            for key in ("vo2max", "run_capacity", "threshold_pace_sec_km", "predictions")
            if fitness.get(key) is not None
        }

    readiness = context.get("readiness")
    if isinstance(readiness, dict):
        record["readiness"] = {
            "level": readiness.get("level"),
            "action": readiness.get("action"),
            "flag_codes": [flag.get("code") for flag in (readiness.get("flags") or context.get("risk_flags") or []) if isinstance(flag, dict) and flag.get("code")],
        }
    if prescription:
        record["prescription"] = slim_prescription(prescription)
    if analysis:
        record["analysis"] = slim_analysis(analysis)
    if notes:
        record["notes"] = notes
    return record


# ---------------------------------------------------------------------------
# 档案读写（upsert + 原子落盘）
# ---------------------------------------------------------------------------

def month_file(archive_dir: Path, record_date: str) -> Path:
    return archive_dir / f"{record_date[:7]}.jsonl"


def load_month(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 跳过损坏行，不让单行问题阻塞整个档案
    return records


def merge_activities(old: list[Any], new: list[Any]) -> list[Any]:
    by_id: dict[Any, dict[Any, Any]] = {}
    for row in old + new:
        if isinstance(row, dict):
            key = row.get("label_id") or row.get("date")
            merged = dict(by_id.get(key) or {})
            merged.update(row)
            by_id[key] = merged
    return sorted(by_id.values(), key=lambda row: str(row.get("date") or ""))


def upsert(archive_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    path = month_file(archive_dir, record["date"])
    existing = load_month(path)
    replaced = False
    for index, row in enumerate(existing):
        if row.get("date") == record["date"] and row.get("record_type") == record["record_type"]:
            merged = dict(row)
            merged.update(record)
            merged["revision"] = int(row.get("revision") or 1) + 1
            merged["archived_at"] = row.get("archived_at") or record["archived_at"]
            merged["updated_at"] = record["archived_at"]
            if "activities" in merged:
                merged["activities"] = merge_activities(row.get("activities") or [], record.get("activities") or [])
            existing[index] = merged
            replaced = True
            break
    if not replaced:
        existing.append(record)
    existing.sort(key=lambda row: (str(row.get("date")), str(row.get("record_type"))))
    archive_dir.mkdir(parents=True, exist_ok=True)
    temp = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=archive_dir, delete=False, suffix=".tmp")
    try:
        for row in existing:
            temp.write(json.dumps(row, ensure_ascii=False) + "\n")
        temp.close()
        os.replace(temp.name, path)
    finally:
        if not temp.closed:
            temp.close()
        if Path(temp.name).exists():
            Path(temp.name).unlink()
    return {"file": str(path), "replaced": replaced, "records_in_month": len(existing)}


def read_archive(archive_dir: Path, days: int, record_type: str | None = None, today: str | None = None) -> list[dict[str, Any]]:
    if not archive_dir.exists():
        return []
    anchor = (datetime.fromisoformat(today) if today else datetime.now(TZ)).date()
    cutoff = (anchor - timedelta(days=days - 1)).isoformat()
    records: list[dict[str, Any]] = []
    for path in sorted(archive_dir.glob("*.jsonl")):
        for row in load_month(path):
            if str(row.get("date")) >= cutoff and (record_type is None or row.get("record_type") == record_type):
                records.append(row)
    return records


def archive_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    metric_paths = {
        "sleep_duration_hours": lambda r: as_float((r.get("health") or {}).get("sleep", {}).get("duration_hours")) if isinstance(r.get("health"), dict) else None,
        "hrv": lambda r: as_float((r.get("health") or {}).get("hrv", {}).get("value")) if isinstance(r.get("health"), dict) else None,
        "resting_hr": lambda r: as_float((r.get("health") or {}).get("resting_hr")) if isinstance(r.get("health"), dict) else None,
        "recovery_percent": lambda r: as_float((r.get("recovery") or {}).get("percent")) if isinstance(r.get("recovery"), dict) else None,
    }
    stats: dict[str, Any] = {"days": len({r.get("date") for r in records}), "records": len(records), "metrics": {}}
    for name, getter in metric_paths.items():
        samples = [(str(r.get("date")), getter(r)) for r in records]
        samples = [(d, v) for d, v in samples if v is not None]
        if samples:
            values_ = [v for _, v in samples]
            stats["metrics"][name] = {
                "days_present": len({d for d, _ in samples}),
                "last_date": max(d for d, _ in samples),
                "min": min(values_),
                "median": round(median(values_), 2),
                "max": max(values_),
            }
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def resolve_archive_dir(flag: str | None) -> Path:
    return Path(flag or os.environ.get("RUNNING_COACH_ARCHIVE") or DEFAULT_ARCHIVE_DIR).expanduser()


def main() -> int:
    parser = argparse.ArgumentParser(description="归档/查询本地训练数据档案（按月 JSONL，upsert 去重）。")
    parser.add_argument("--input", help="结构化 bundle JSON（build_athlete_context 的输入）；省略时从 stdin 读取")
    parser.add_argument("--context", help="AthleteContext V2 JSON（提供 readiness/risk flags）")
    parser.add_argument("--prescription", help="已校验的 TrainingPrescription JSON")
    parser.add_argument("--analysis", help="analyze_laps/analyze_fit 输出 JSON（只保留摘要与 flags）")
    parser.add_argument("--type", default="daily_check", dest="record_type",
                        help="记录类型：daily_check/activity_review/race_review/weekly_review/race_plan")
    parser.add_argument("--date", help="归属日期 YYYY-MM-DD；默认取 context/bundle 的 as_of")
    parser.add_argument("--notes", help="自由备注（主观疲劳、场地、补给等）")
    parser.add_argument("--archive-dir", help="档案目录；默认 $RUNNING_COACH_ARCHIVE 或 ~/.running-coach/archive")
    parser.add_argument("--dry-run", action="store_true", help="只打印将写入的记录，不落盘")
    parser.add_argument("--show", action="store_true", help="查询模式：打印档案记录")
    parser.add_argument("--stats", action="store_true", help="统计模式：打印近 N 天档案覆盖与指标分布")
    parser.add_argument("--days", type=int, default=28, help="查询/统计窗口天数，默认 28")
    args = parser.parse_args()

    archive_dir = resolve_archive_dir(args.archive_dir)

    if args.show or args.stats:
        records = read_archive(archive_dir, max(args.days, 1))
        if args.stats:
            print(json.dumps(archive_stats(records), ensure_ascii=False, indent=2))
        else:
            for row in records:
                print(json.dumps(row, ensure_ascii=False))
        return 0

    piped = args.input is None and not sys.stdin.isatty()
    if piped and not any((args.context, args.prescription, args.analysis, args.date)):
        parser.error("写入模式需要 --input（或管道 bundle），或至少提供 --context/--prescription/--analysis 之一")

    bundle = json.loads(sys.stdin.read()) if piped else (read_json(args.input) if args.input else None)
    if bundle is None and not any((args.context, args.prescription, args.analysis, args.date)):
        parser.error("没有任何输入：提供 --input/--context/--prescription/--analysis/--date 之一")
    context = read_json(args.context) if args.context else None
    prescription = read_json(args.prescription) if args.prescription else None
    analysis = read_json(args.analysis) if args.analysis else None
    record = build_record(bundle, context, prescription, analysis, args.record_type, args.date, args.notes)

    violations = scan_violations(record)
    if violations:
        print("拒绝入档，命中脱敏规则：", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps(record, ensure_ascii=False, indent=2))
        print(f"dry-run：将写入 {month_file(archive_dir, record['date'])}", file=sys.stderr)
        return 0

    result = upsert(archive_dir, record)
    print(json.dumps({"archived": True, **result, "date": record["date"], "record_type": record["record_type"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
