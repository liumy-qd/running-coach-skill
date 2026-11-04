#!/usr/bin/env python3
"""把佳明 Garmin 数据归一为 running-coach 标准 bundle（build_athlete_context.py 的输入）。

三种用法：
- 归一：--input raw.json   把已保存的 garminconnect/MCP 原始 JSON 转为 bundle（纯标准库）。
- 抓取：--fetch --days 7   直接经 garminconnect 拉取后归一（需 pip install garminconnect garth）。
- 首登：--login            交互式完成佳明账号登录（支持 MFA 输入），token 存 ~/.garmintokens。

隐私约束：凭证只保存在本机 garth token 目录；脚本不输出 token；活动不带坐标
（garminconnect 活动列表本身不含轨迹，FIT 下载走 references/fit-deep-review.md 流程）。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

DEFAULT_TOKEN_DIR = Path.home() / ".garmintokens"


def read_json(path: str | None) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("输入必须是 JSON 对象")
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
    value = pick(row, "calendarDate", "date", "day", "startTimeLocal", "startTime")
    return str(value)[:10] if value else None


def rows(raw: dict[str, Any], *names: str) -> list[dict[str, Any]]:
    for name in names:
        value = raw.get(name)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = value.get("records") or value.get("data")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


# ---------------------------------------------------------------------------
# 各指标归一（容忍 garminconnect 响应的字段变体）
# ---------------------------------------------------------------------------

def norm_sleep(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows(raw, "sleep", "sleep_data"):
        inner = row.get("dailySleepValues") if isinstance(row.get("dailySleepValues"), dict) else row
        day = date_of(inner) or date_of(row)
        if not day:
            continue
        seconds = as_float(pick(inner, "sleepTimeSeconds", "sleepSeconds"))
        scores = inner.get("sleepScores") if isinstance(inner.get("sleepScores"), dict) else {}
        score = as_float(pick(scores, "overall") if scores else None) or as_float(
            pick(inner, "overallSleepScore", "sleepScore"))
        entry = {"date": day}
        if seconds is not None:
            entry["duration_hours"] = round(seconds / 3600.0, 2)
        if score is not None:
            entry["score"] = score
        out.append(entry)
    return sorted(out, key=lambda item: item["date"])


def norm_hrv(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows(raw, "hrv", "sleep_hrv", "hrv_data"):
        inner = row.get("hrvSummary") if isinstance(row.get("hrvSummary"), dict) else row
        day = date_of(inner) or date_of(row)
        if not day:
            continue
        entry = {"date": day}
        value = as_float(pick(inner, "lastNightAvg", "average_hrv", "avgHrv", "hrv"))
        baseline = as_float(pick(inner, "baseline", "hrvBaseline"))
        if value is not None:
            entry["average_hrv"] = round(value, 1)
        if baseline is not None:
            entry["baseline"] = round(baseline, 1)
        out.append(entry)
    return sorted(out, key=lambda item: item["date"])


def norm_resting_hr(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows(raw, "resting_hr", "resting_heart_rate", "rhr"):
        day = date_of(row)
        value = as_float(pick(row, "restingHeartRate", "resting_hr", "rhr"))
        if day and value is not None:
            out.append({"date": day, "resting_hr": value})
    return sorted(out, key=lambda item: item["date"])


def stress_average(row: dict[str, Any]) -> float | None:
    direct = as_float(pick(row, "averageStressLevel", "average_stress", "stress"))
    if direct is not None:
        return direct
    values: list[float] = []
    for item in row.get("stressValuesArray") or []:
        if isinstance(item, (int, float)):
            values.append(float(item))
        elif isinstance(item, dict):
            value = as_float(pick(item, "stressLevel", "value", "stress"))
            if value is not None:
                values.append(value)
    return round(sum(values) / len(values), 1) if values else None


def norm_stress(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows(raw, "stress", "stress_data"):
        day = date_of(row)
        average = stress_average(row)
        if day and average is not None:
            out.append({"date": day, "stress": average})
    return sorted(out, key=lambda item: item["date"])


def norm_training_load(raw: dict[str, Any]) -> list[dict[str, Any]]:
    status = raw.get("training_status") if isinstance(raw.get("training_status"), dict) else {}
    load = status.get("currentTrainingLoad") if isinstance(status.get("currentTrainingLoad"), dict) else {}
    if not load:
        load = raw.get("training_load") if isinstance(raw.get("training_load"), dict) else {}
    day = raw.get("as_of") or str(date.today())
    ratio = as_float(pick(load, "loadRatio", "load_ratio"))
    if ratio is None:
        acute = as_float(pick(load, "acuteLoad", "acute", "weeklyLoad"))
        chronic = as_float(pick(load, "chronicLoad", "chronic"))
        if acute is not None and chronic is not None and chronic > 0:
            ratio = round(acute / chronic, 2)
    return [{"date": str(day)[:10], "load_ratio": ratio}] if ratio is not None else []


def norm_recovery(raw: dict[str, Any]) -> dict[str, Any]:
    readiness = raw.get("training_readiness") if isinstance(raw.get("training_readiness"), dict) else {}
    score = as_float(pick(readiness, "score", "level", "readiness"))
    battery = raw.get("body_battery") if isinstance(raw.get("body_battery"), dict) else {}
    if score is None:
        score = as_float(pick(battery, "level", "charged"))
    out: dict[str, Any] = {}
    if score is not None:
        out["recovery_percent"] = score
        out["source"] = "garmin_training_readiness" if readiness else "garmin_body_battery"
    return out


def norm_activities(raw: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows(raw, "activities", "sport_records", "activity_records"):
        day = date_of(row)
        ident = pick(row, "activityId", "activity_id", "labelId")
        if not day and ident is None:
            continue
        entry: dict[str, Any] = {"label_id": str(ident) if ident is not None else None, "date": day}
        kind = row.get("activityType")
        if isinstance(kind, dict):
            entry["sport_type"] = kind.get("typeKey")
        elif isinstance(kind, str):
            entry["sport_type"] = kind
        distance = as_float(pick(row, "distance", "distanceKm"))
        if distance is not None:
            # garminconnect 的 distance 为米；小于 100 的带小数值按已是公里处理
            entry["distance_km"] = round(distance / 1000.0, 2) if distance >= 100 else round(distance, 2)
        duration = as_float(pick(row, "duration", "elapsedDuration", "movingDuration"))
        if duration is not None:
            entry["duration_min"] = round(duration / 60.0, 1)
        hr = as_float(pick(row, "averageHR", "avg_hr", "averageHr"))
        if hr is not None:
            entry["avg_hr"] = hr
        load = as_float(pick(row, "activityTrainingLoad", "training_load"))
        if load is not None:
            entry["training_load"] = load
        pace = as_float(pick(row, "avgPace", "avg_pace"))
        if pace is not None:
            entry["avg_pace_sec_km"] = pace
        out.append(entry)
    return sorted(out, key=lambda item: str(item.get("date")))


def norm_fitness(raw: dict[str, Any]) -> dict[str, Any]:
    candidates = [raw.get("training_status"), raw.get("fitness"), raw.get("training_readiness")]
    out: dict[str, Any] = {}
    for block in candidates:
        if not isinstance(block, dict):
            continue
        vo2 = as_float(pick(block, "vO2Max", "vo2max", "vO2MaxValue"))
        if vo2 is not None:
            out["vo2max"] = vo2
            break
    return out


def build_bundle(raw: dict[str, Any]) -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "schema_version": "2.0",
        "source_device": "garmin",
        "as_of": raw.get("as_of") or datetime.now().isoformat(timespec="seconds"),
        "timezone": raw.get("timezone") or "Asia/Shanghai",
        "sources": [{"name": "garmin", "retrieved_at": raw.get("as_of"), "status": "ok"}],
    }
    sleep = norm_sleep(raw)
    hrv = norm_hrv(raw)
    resting = norm_resting_hr(raw)
    stress = norm_stress(raw)
    load = norm_training_load(raw)
    activities = norm_activities(raw)
    recovery = norm_recovery(raw)
    fitness = norm_fitness(raw)
    if sleep:
        bundle["sleep"] = sleep
    if hrv:
        bundle["sleep_hrv"] = hrv
    if resting:
        bundle["resting_hr"] = resting
    if stress:
        bundle["stress"] = stress
    if load:
        bundle["training_load"] = load
    if activities:
        bundle["activities"] = activities
    if recovery:
        bundle["recovery"] = recovery
    if fitness:
        bundle["fitness"] = fitness
    return bundle


# ---------------------------------------------------------------------------
# 可选：garminconnect 实网抓取
# ---------------------------------------------------------------------------

def login_interactive(token_dir: Path, email: str | None, password: str | None) -> int:
    try:
        import garth
    except ImportError:
        print("需要先安装：pip install garminconnect garth", file=sys.stderr)
        return 4
    if email and password:
        garth.login(email, password)
    else:
        email = input("佳明账号邮箱： ").strip()
        password = prompt_password()
        garth.login(email, password)
    garth.dump(str(token_dir))
    print(f"登录成功，token 已保存到 {token_dir}")
    return 0


def prompt_password() -> str:
    import getpass as _getpass
    return _getpass.getpass("密码： ")


def fetch_raw(days: int, token_dir: Path) -> dict[str, Any]:
    try:
        import garth
        from garminconnect import Garmin
    except ImportError:
        raise SystemExit("抓取模式需要安装：pip install garminconnect garth；"
                         "或改用 --input 归一已保存的原始 JSON")
    try:
        garth.resume(str(token_dir))
        garmin = Garmin(garth=garth)
    except Exception as exc:  # noqa: BLE001 - garth 异常类型不定
        raise SystemExit(f"未登录或 token 失效（{exc}）；先运行 --login 完成佳明登录")

    def call(name: str, *args: Any) -> Any:
        method: Callable[..., Any] | None = getattr(garmin, name, None)
        if method is None:
            return None
        try:
            return method(*args)
        except Exception:  # noqa: BLE001 - 单端点失败不阻塞整体
            return None

    today = date.today()
    starts = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    raw: dict[str, Any] = {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "timezone": "Asia/Shanghai",
        "sleep": [item for day in starts if (item := call("get_sleep_data", day.isoformat()))],
        "hrv": [item for day in starts if (item := call("get_hrv_data", day.isoformat()))],
        "stress": [item for day in starts if (item := call("get_stress_data", day.isoformat()))],
        "resting_hr": [item for day in starts if (item := call("get_resting_hr", day.isoformat()))],
        "training_status": call("get_training_status", today.isoformat()),
        "training_readiness": call("get_training_readiness", today.isoformat()),
        "activities": call("get_activities_by_date",
                           (today - timedelta(days=days - 1)).isoformat(), today.isoformat()) or [],
    }
    return {key: value for key, value in raw.items() if value not in (None, [])}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="佳明 Garmin 数据 → running-coach bundle 归一/抓取。")
    parser.add_argument("--input", help="已保存的 garminconnect/MCP 原始 JSON；省略 stdin。")
    parser.add_argument("--fetch", action="store_true", help="经 garminconnect 实网抓取最近 N 天。")
    parser.add_argument("--login", action="store_true", help="交互式首次登录，保存 garth token。")
    parser.add_argument("--days", type=int, default=7, help="抓取窗口天数，默认 7。")
    parser.add_argument("--email", help="登录邮箱（配合 --login）。")
    parser.add_argument("--password", help="登录密码（配合 --login；建议省略后用安全输入）。")
    parser.add_argument("--token-dir", default=str(DEFAULT_TOKEN_DIR), help="garth token 目录。")
    parser.add_argument("--output", help="bundle 输出文件；默认打印 stdout。")
    args = parser.parse_args()

    if args.login:
        return login_interactive(Path(args.token_dir).expanduser(), args.email, args.password)

    if args.fetch:
        raw = fetch_raw(max(args.days, 1), Path(args.token_dir).expanduser())
    else:
        raw = read_json(args.input)

    bundle = build_bundle(raw)
    text = json.dumps(bundle, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).expanduser().write_text(text + "\n", encoding="utf-8")
        print(f"bundle 已写入 {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
