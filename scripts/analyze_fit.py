#!/usr/bin/env python3
"""比赛/关键训练 FIT 深度复盘：配速、海拔、心率、坡度、跑姿的确定性关联分析。

输入二选一：
- --fit  file.fit        FIT 二进制（需要 fitdecode 或 fitparse）。
- --input records.json   归一化逐秒记录，schema 见 references/fit-deep-review.md。

隐私约束：本脚本只读取时间、距离、速度、心率、步频、海拔、坡度、温度、功率；
position 经纬度字段一律不读取、不输出。仅输出聚合统计，不输出原始逐秒数据。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 归一化记录字段（JSON schema，全部除 ts 外可选）：
#   ts    unix 秒
#   dist  累计距离（米）
#   speed 速度（m/s）
#   hr    心率（bpm）
#   cad   步频（视设备，直接透传）
#   alt   海拔（米）
#   grade 坡度（小数，0.05 = 5%）
#   temp  温度（摄氏度）
#   power 跑步功率（W）
# ---------------------------------------------------------------------------

FLAT_GRADE = 0.015          # |grade| 低于此值视为平路
BLOWUP_PACE_DROP = 0.08     # 相邻公里配速慢 8% 以上才算掉速
BLOWUP_HR_RATIO = 0.96      # 且心率达到至今最高心率的 96%
DRIFT_BINS = 0.5            # 同配速漂移分析的速度分箱宽度（m/s）
CADENCE_DECAY = 5.0         # 后 1/3 步频下降超过该值标记
STOP_SPEED = 0.5            # 速度低于该值视为停表/步行补给（m/s）
STOP_MIN_SEC = 10
CLIMB_GRADE = 0.03
CLIMB_MIN_GAIN = 15.0


def percentile(vals: List[float], pct: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round(pct * (len(s) - 1)))))
    return s[idx]


def moving_avg(vals: List[Optional[float]], window: int) -> List[float]:
    """居中滑动平均；None 视为缺失，用窗口内有效值。"""
    out: List[float] = []
    half = window // 2
    last = 0.0
    for i in range(len(vals)):
        lo, hi = max(0, i - half), min(len(vals), i + half + 1)
        sample = [v for v in vals[lo:hi] if v is not None]
        if sample:
            last = statistics.fmean(sample)
        out.append(last)
    return out


def fmt_pace(sec_per_km: Optional[float]) -> str:
    if not sec_per_km or sec_per_km <= 0 or sec_per_km > 2000:
        return "-"
    m, s = divmod(int(round(sec_per_km)), 60)
    return f"{m}:{s:02d}/km"


def minetti_ratio(grade: float) -> float:
    """Minetti 能量成本比：i 为坡度小数，返回相对平路的耗能倍数，截断 [0.70, 2.50]。"""
    i = max(-0.35, min(0.35, grade))
    cost = (155.4 * i ** 5 - 30.4 * i ** 4 - 43.3 * i ** 3
            + 46.3 * i ** 2 + 19.5 * i + 3.6)
    return max(0.70, min(2.50, cost / 3.6))


# ---------------------------------------------------------------------------
# 输入装载
# ---------------------------------------------------------------------------

def load_records(args: argparse.Namespace) -> Dict[str, Any]:
    if args.fit:
        return load_fit(args.fit)
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    meta = payload.get("meta") or {}
    return {"meta": meta, "records": payload.get("records") or []}


def load_fit(path: str) -> Dict[str, Any]:
    try:
        import fitdecode  # noqa: F401
        return _load_fit_fitdecode(path)
    except ImportError:
        pass
    try:
        return _load_fit_fitparse(path)
    except ImportError:
        raise SystemExit("解析 FIT 二进制需要 pip install fitdecode（或 fitparse）；"
                         "也可以先用归一化 JSON 通过 --input 传入。")


def _load_fit_fitdecode(path: str) -> Dict[str, Any]:
    import fitdecode

    records: List[Dict[str, Any]] = []
    with open(path, "rb") as handle:
        for frame in fitdecode.FitReader(handle):
            if frame.frame_type != fitdecode.FIT_FRAME_DATA or frame.name != "record":
                continue
            row: Dict[str, Any] = {}
            ts = frame.get_value("timestamp")
            if ts is not None:
                row["ts"] = int(ts.timestamp())
            for key, name in (("dist", "distance"), ("speed", "speed"), ("hr", "heart_rate"),
                              ("cad", "cadence"), ("power", "power"), ("temp", "temperature")):
                value = frame.get_value(name)
                if value is not None:
                    row[key] = float(value)
            alt = frame.get_value("enhanced_altitude")
            if alt is None:
                alt = frame.get_value("altitude")
            if alt is not None:
                row["alt"] = float(alt)
            grade = frame.get_value("grade")
            if grade is not None:  # FIT grade 单位是 %，归一化为小数
                row["grade"] = float(grade) / 100.0
            if row:
                records.append(row)
    return {"meta": {"source": "fit", "path": Path(path).name}, "records": records}


def _load_fit_fitparse(path: str) -> Dict[str, Any]:
    import fitparse

    records: List[Dict[str, Any]] = []
    fitfile = fitparse.FitFile(path)
    for msg in fitfile.get_messages("record"):
        row: Dict[str, Any] = {}
        for field in msg.fields:
            if field.value is None:
                continue
            name = field.name
            if name == "timestamp":
                row["ts"] = int(field.value.timestamp())
            elif name == "distance":
                row["dist"] = float(field.value)
            elif name == "speed":
                row["speed"] = float(field.value)
            elif name == "heart_rate":
                row["hr"] = float(field.value)
            elif name == "cadence":
                row["cad"] = float(field.value)
            elif name == "power":
                row["power"] = float(field.value)
            elif name == "temperature":
                row["temp"] = float(field.value)
            elif name in ("enhanced_altitude", "altitude"):
                row.setdefault("alt", float(field.value))
            elif name == "grade":
                row["grade"] = float(field.value) / 100.0
        if row:
            records.append(row)
    return {"meta": {"source": "fit", "path": Path(path).name}, "records": records}


# ---------------------------------------------------------------------------
# 预处理
# ---------------------------------------------------------------------------

def normalize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """补齐缺失的 dist/speed/grade；返回可分析数组。"""
    rows = [dict(r) for r in records if isinstance(r, dict) and r.get("ts") is not None]
    rows.sort(key=lambda r: r["ts"])
    n = len(rows)
    if n < 30:
        raise SystemExit(f"有效记录过少（{n} 条，至少 30 条），无法做细粒度复盘。")

    if rows[0].get("dist") is None:
        acc = 0.0
        rows[0]["dist"] = 0.0
        for i in range(1, n):
            dt = max(0, rows[i]["ts"] - rows[i - 1]["ts"])
            speed = rows[i].get("speed")
            if speed is not None and dt > 0:
                acc += float(speed) * dt
            rows[i]["dist"] = acc

    if rows[0].get("speed") is None:
        for i in range(n):
            lo, hi = max(0, i - 5), min(n - 1, i + 5)
            dd = rows[hi]["dist"] - rows[lo]["dist"]
            dt = rows[hi]["ts"] - rows[lo]["ts"]
            rows[i]["speed"] = dd / dt if dt > 0 else 0.0

    alts = moving_avg([r.get("alt") for r in rows], 15)
    for r, alt in zip(rows, alts):
        r["alt_s"] = alt

    if not any(r.get("grade") is not None for r in rows):
        for i in range(n):
            lo, hi = max(0, i - 8), min(n - 1, i + 8)
            d_alt = rows[hi]["alt_s"] - rows[lo]["alt_s"]
            d_h = max(1.0, rows[hi]["dist"] - rows[lo]["dist"])
            rows[i]["grade"] = max(-0.35, min(0.35, d_alt / d_h))
    else:
        grades = moving_avg([r.get("grade") for r in rows], 9)
        for r, g in zip(rows, grades):
            r["grade"] = max(-0.35, min(0.35, g))

    for r in rows:
        speed = float(r["speed"])
        r["pace"] = 1000.0 / speed if speed > 0.1 else None
        r["gap"] = r["pace"] * minetti_ratio(r["grade"]) if r["pace"] else None
    return {"rows": rows}


def km_marks(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """在每个整公里处线性插值时间，再汇总该公里段的指标。"""
    total = rows[-1]["dist"]
    if total < 500:
        return []
    marks: List[tuple] = [(0.0, rows[0]["ts"])]
    idx = 0
    km = 1000.0
    while km <= total:
        while idx < len(rows) - 1 and rows[idx]["dist"] < km:
            idx += 1
        prev = rows[max(0, idx - 1)]
        cur = rows[idx]
        span = cur["dist"] - prev["dist"]
        frac = (km - prev["dist"]) / span if span > 0 else 0.0
        marks.append((km, prev["ts"] + frac * (cur["ts"] - prev["ts"])))
        km += 1000.0

    splits: List[Dict[str, Any]] = []
    for k in range(1, len(marks)):
        d0, t0 = marks[k - 1]
        d1, t1 = marks[k]
        segment = [r for r in rows if d0 < r["dist"] <= d1]
        if not segment:
            continue
        hrs = [r["hr"] for r in segment if r.get("hr") is not None]
        gains = sum(max(0.0, b["alt_s"] - a["alt_s"])
                    for a, b in zip(segment, segment[1:]) if a.get("alt_s") is not None)
        grades = [abs(r["grade"]) < FLAT_GRADE for r in segment]
        flat = [r for r, is_flat in zip(segment, grades) if is_flat]
        flat_paces = [r["pace"] for r in flat if r.get("pace")]
        splits.append({
            "km": k,
            "pace": (t1 - t0) * 1000.0 / (d1 - d0),
            "gap": statistics.fmean([r["gap"] for r in segment if r.get("gap")]) if any(r.get("gap") for r in segment) else None,
            "hr": statistics.fmean(hrs) if hrs else None,
            "hr_max": max(hrs) if hrs else None,
            "gain": round(gains, 1),
            "grade": statistics.fmean([r["grade"] for r in segment]),
            "stopped_s": sum(1 for r in segment if r["speed"] < STOP_SPEED),
            "flat_pace": statistics.fmean(flat_paces) if flat_paces else None,
            "cad": statistics.fmean([r["cad"] for r in segment if r.get("cad") is not None]) if any(r.get("cad") is not None for r in segment) else None,
        })
    return splits


# ---------------------------------------------------------------------------
# 分析组件
# ---------------------------------------------------------------------------

def analyze_summary(rows: List[Dict[str, Any]], splits: List[Dict[str, Any]]) -> Dict[str, Any]:
    gain = loss = 0.0
    for a, b in zip(rows, rows[1:]):
        delta = b["alt_s"] - a["alt_s"]
        gain += max(0.0, delta)
        loss += max(0.0, -delta)
    hrs = [r["hr"] for r in rows if r.get("hr") is not None]
    temps = [r["temp"] for r in rows if r.get("temp") is not None]
    total_time = rows[-1]["ts"] - rows[0]["ts"]
    return {
        "distance_km": round(rows[-1]["dist"] / 1000.0, 2),
        "duration_min": round(total_time / 60.0, 1),
        "avg_pace": (total_time / (rows[-1]["dist"] / 1000.0)) if rows[-1]["dist"] > 0 else None,
        "hr_avg": round(statistics.fmean(hrs), 1) if hrs else None,
        "hr_max": max(hrs) if hrs else None,
        "elevation_gain_m": round(gain),
        "elevation_loss_m": round(loss),
        "alt_min_m": round(min(r["alt_s"] for r in rows)),
        "alt_max_m": round(max(r["alt_s"] for r in rows)),
        "temp_start": temps[0] if temps else None,
        "temp_end": temps[-1] if temps else None,
        "splits_count": len(splits),
    }


def analyze_balance(splits: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if len(splits) < 4:
        return None
    half = len(splits) // 2
    first = statistics.fmean(s["pace"] for s in splits[:half])
    second = statistics.fmean(s["pace"] for s in splits[half:])
    paces = [s["pace"] for s in splits]
    fastest = min(splits, key=lambda s: s["pace"])
    slowest = max(splits, key=lambda s: s["pace"])
    return {
        "first_half_pace": first,
        "second_half_pace": second,
        "second_half_pct": round((second / first - 1) * 100, 1),
        "pace_cv_pct": round(statistics.pstdev(paces) / statistics.fmean(paces) * 100, 1),
        "fastest_km": fastest["km"],
        "fastest_pace": fastest["pace"],
        "slowest_km": slowest["km"],
        "slowest_pace": slowest["pace"],
    }


def analyze_drift(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """同配速心率漂移：前后半程在相同速度箱内比较平均心率。"""
    hrs = [r for r in rows if r.get("hr") is not None]
    if len(hrs) < 600:
        return None
    mid = hrs[len(hrs) // 2]["dist"]
    first, second = [r for r in hrs if r["dist"] <= mid], [r for r in hrs if r["dist"] > mid]
    bins: List[Dict[str, Any]] = []
    for speed in [x * DRIFT_BINS for x in range(2, 14)]:
        a = [r["hr"] for r in first if speed <= r["speed"] < speed + DRIFT_BINS]
        b = [r["hr"] for r in second if speed <= r["speed"] < speed + DRIFT_BINS]
        if len(a) >= 60 and len(b) >= 60:
            drift = statistics.fmean(b) - statistics.fmean(a)
            bins.append({"speed_mps": round(speed, 1),
                         "pace": fmt_pace(1000.0 / (speed + DRIFT_BINS / 2)),
                         "hr_first": round(statistics.fmean(a), 1),
                         "hr_second": round(statistics.fmean(b), 1),
                         "drift_bpm": round(drift, 1),
                         "samples": len(a) + len(b)})
    if not bins:
        return None
    return {"bins": bins, "overall_drift_bpm": round(statistics.fmean(b["drift_bpm"] for b in bins), 1)}


def analyze_efficiency(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """平路效率因子 EF = 速度(m/min)/心率 的前 1/3 vs 后 1/3。"""
    flat = [r for r in rows
            if r.get("hr") is not None and r["hr"] > 100 and abs(r["grade"]) < FLAT_GRADE and r["speed"] > 1.0]
    if len(flat) < 600:
        return None
    third = len(flat) // 3
    parts = [flat[:third], flat[-third:]]
    efs = [statistics.fmean(r["speed"] * 60.0 / r["hr"] for r in part) for part in parts]
    if efs[0] <= 0:
        return None
    return {"ef_first": round(efs[0], 3), "ef_last": round(efs[1], 3),
            "change_pct": round((efs[1] / efs[0] - 1) * 100, 1)}


def analyze_grade_bins(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    edges = [(-1.0, -0.05, "<-5% 陡下坡"), (-0.05, -0.02, "-5%~-2% 下坡"), (-0.02, 0.02, "±2% 平路"),
             (0.02, 0.05, "2%~5% 缓上坡"), (0.05, 1.0, ">5% 陡上坡")]
    out: List[Dict[str, Any]] = []
    for lo, hi, label in edges:
        bucket = [r for r in rows if lo <= r["grade"] < hi and r.get("pace") and r.get("hr")]
        if len(bucket) < 60:
            continue
        out.append({"bin": label, "time_min": round(len(bucket) / 60.0, 1),
                    "pace": fmt_pace(statistics.fmean(r["pace"] for r in bucket)),
                    "gap": fmt_pace(statistics.fmean(r["gap"] for r in bucket if r.get("gap"))),
                    "hr": round(statistics.fmean(r["hr"] for r in bucket), 1)})
    return out


def analyze_climbs(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """识别持续爬坡段（grade>3%），按爬升量取前 3。"""
    climbs: List[Dict[str, Any]] = []
    start: Optional[int] = None
    gain = 0.0
    for i, r in enumerate(rows):
        climbing = r["grade"] > CLIMB_GRADE
        if climbing and start is None:
            start, gain = i, 0.0
        if start is not None:
            gain += max(0.0, r["alt_s"] - rows[i - 1]["alt_s"]) if i > 0 else 0.0
            if (not climbing and i - start > 30) or i == len(rows) - 1:
                end = i if climbing else i - 30
                if end > start and gain >= CLIMB_MIN_GAIN:
                    seg = rows[start:end + 1]
                    d = seg[-1]["dist"] - seg[0]["dist"]
                    if d > 100:
                        paces = [r["pace"] for r in seg if r.get("pace")]
                        hrs = [r["hr"] for r in seg if r.get("hr") is not None]
                        climbs.append({"start_km": round(seg[0]["dist"] / 1000.0, 1),
                                       "length_m": int(d), "gain_m": int(gain),
                                       "avg_grade_pct": round(gain / d * 100, 1),
                                       "pace": fmt_pace(statistics.fmean(paces)) if paces else "-",
                                       "hr_avg": round(statistics.fmean(hrs), 1) if hrs else None})
                start, gain = None, 0.0
    return sorted(climbs, key=lambda c: -c["gain_m"])[:3]


def analyze_blowup(splits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    hr_max_so_far = 0.0
    for prev, cur in zip(splits, splits[1:]):
        if prev.get("hr_max"):
            hr_max_so_far = max(hr_max_so_far, prev["hr_max"])
        if prev.get("hr"):
            hr_max_so_far = max(hr_max_so_far, prev["hr"])
        if prev.get("stopped_s", 0) >= STOP_MIN_SEC or cur.get("stopped_s", 0) >= STOP_MIN_SEC:
            continue  # 含停表/步行的分段不能证明配速崩掉
        drop = cur["pace"] / prev["pace"] - 1.0
        hot = cur.get("hr_max") and hr_max_so_far and cur["hr_max"] >= BLOWUP_HR_RATIO * hr_max_so_far
        if drop > BLOWUP_PACE_DROP and hot:
            events.append({"km": cur["km"], "pace_drop_pct": round(drop * 100, 1),
                           "prev_pace": fmt_pace(prev["pace"]), "cur_pace": fmt_pace(cur["pace"]),
                           "grade_pct": round(cur["grade"] * 100, 1),
                           "gain_prev2_m": round(prev.get("gain", 0) + cur.get("gain", 0), 0)})
    return events


def analyze_stops(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    stops: List[Dict[str, Any]] = []
    start_idx: Optional[int] = None
    for i, r in enumerate(rows):
        stopped = r["speed"] < STOP_SPEED
        if stopped and start_idx is None:
            start_idx = i
        elif not stopped and start_idx is not None:
            duration = rows[i - 1]["ts"] - rows[start_idx]["ts"]
            if duration >= STOP_MIN_SEC:
                stops.append({"km": round(rows[start_idx]["dist"] / 1000.0, 2),
                              "duration_s": duration})
            start_idx = None
    return {"count": len(stops), "total_min": round(sum(s["duration_s"] for s in stops) / 60.0, 1),
            "stops": stops[:8]}


def analyze_cadence(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    with_cad = [r for r in rows if r.get("cad") is not None]
    if len(with_cad) < 600:
        return None
    third = len(with_cad) // 3
    first = statistics.fmean(r["cad"] for r in with_cad[:third])
    last = statistics.fmean(r["cad"] for r in with_cad[-third:])
    return {"first_third": round(first, 1), "last_third": round(last, 1),
            "decay": round(first - last, 1)}


def analyze_zones(rows: List[Dict[str, Any]], threshold_hr: Optional[int]) -> Optional[List[Dict[str, Any]]]:
    hrs = [r["hr"] for r in rows if r.get("hr") is not None and r["hr"] > 60]
    if not hrs:
        return None
    total = len(hrs)
    if threshold_hr:
        base, basis = threshold_hr, "阈值心率"
        edges = [(0.0, 0.80, "Z1 <80%T"), (0.80, 0.90, "Z2 80-89%T"), (0.90, 0.95, "Z3 90-94%T"),
                 (0.95, 1.00, "Z4 95-100%T"), (1.00, 9.99, "Z5 >阈值")]
    else:
        base, basis = max(hrs), "最高心率估算"
        edges = [(0.0, 0.60, "Z1 <60%MHR"), (0.60, 0.70, "Z2 60-70%MHR"), (0.70, 0.80, "Z3 70-80%MHR"),
                 (0.80, 0.90, "Z4 80-90%MHR"), (0.90, 1.01, "Z5 >90%MHR")]
    zones = []
    for lo, hi, label in edges:
        count = sum(1 for h in hrs if lo * base <= h < hi * base)
        zones.append({"zone": label, "time_min": round(count / 60.0, 1),
                      "pct": round(count / total * 100, 1)})
    return {"basis": basis, "zones": zones}


# ---------------------------------------------------------------------------
# 汇总与输出
# ---------------------------------------------------------------------------

def analyze(payload: Dict[str, Any], threshold_hr: Optional[int]) -> Dict[str, Any]:
    norm = normalize(payload["records"])
    rows = norm["rows"]
    splits = km_marks(rows)
    result: Dict[str, Any] = {"schema_version": "1.0", "meta": payload.get("meta") or {}}

    fields = {k: any(r.get(k) is not None for r in rows)
              for k in ("hr", "cad", "alt", "grade", "temp", "power")}
    result["coverage"] = {"records": len(rows),
                          "fields_present": [k for k, ok in fields.items() if ok],
                          "fields_missing": [k for k, ok in fields.items() if not ok]}

    summary = analyze_summary(rows, splits)
    result["summary"] = summary
    result["splits"] = [{**{k: (fmt_pace(v) if k in ("pace", "gap") else v)
                            for k, v in s.items() if v is not None}} for s in splits]
    result["balance"] = analyze_balance(splits)
    result["drift"] = analyze_drift(rows)
    result["efficiency"] = analyze_efficiency(rows)
    result["grade_bins"] = analyze_grade_bins(rows)
    result["climbs"] = analyze_climbs(rows)
    result["blowups"] = analyze_blowup(splits)
    result["stops"] = analyze_stops(rows)
    result["cadence"] = analyze_cadence(rows)
    result["hr_zones"] = analyze_zones(rows, threshold_hr)

    flags: List[Dict[str, Any]] = []
    balance = result.get("balance")
    if balance and abs(balance["second_half_pct"]) >= 5:
        direction = "后半程明显掉速" if balance["second_half_pct"] > 0 else "后半程明显提速"
        flags.append({"severity": "medium", "code": "split_imbalance",
                      "detail": f"{direction}（后半程配速差 {balance['second_half_pct']:+}%）"})
    drift = result.get("drift")
    if drift and drift["overall_drift_bpm"] >= 4:
        flags.append({"severity": "medium", "code": "hr_drift",
                      "detail": f"同配速心率后半程平均上升 {drift['overall_drift_bpm']} bpm，提示疲劳/热/补给不足"})
    eff = result.get("efficiency")
    if eff and eff["change_pct"] <= -8:
        flags.append({"severity": "medium", "code": "ef_decay",
                      "detail": f"平路效率因子后 1/3 下降 {abs(eff['change_pct'])}%"})
    cad = result.get("cadence")
    if cad and cad["decay"] >= CADENCE_DECAY:
        flags.append({"severity": "low", "code": "cadence_decay",
                      "detail": f"步频后 1/3 下降 {cad['decay']}，提示神经肌肉疲劳"})
    for event in result["blowups"]:
        flags.append({"severity": "high", "code": "blowup",
                      "detail": f"第 {event['km']} km 配速骤降 {event['pace_drop_pct']}%（{event['prev_pace']}→{event['cur_pace']}），"
                                f"当时坡度 {event['grade_pct']}%，心率接近峰值；结合补给/爬升排查"})
    stops = result["stops"]
    if stops["total_min"] >= 1:
        flags.append({"severity": "info", "code": "stops",
                      "detail": f"共 {stops['count']} 次停表/步行，合计 {stops['total_min']} 分钟"})
    temp = summary
    if temp.get("temp_start") is not None and temp.get("temp_end") is not None \
            and temp["temp_end"] - temp["temp_start"] >= 5 and drift and drift["overall_drift_bpm"] >= 4:
        flags.append({"severity": "low", "code": "temp_drift",
                      "detail": f"温度从 {temp['temp_start']}°C 升至 {temp['temp_end']}°C，与心率漂移方向一致"})
    if not fields["alt"]:
        flags.append({"severity": "info", "code": "no_altitude",
                      "detail": "记录缺海拔字段，坡度/爬升相关结论置信度降低"})
    result["flags"] = flags
    return result


def to_markdown(result: Dict[str, Any]) -> str:
    lines: List[str] = ["# FIT 深度复盘", ""]
    cov = result["coverage"]
    lines += [f"- 记录数：{cov['records']}；字段覆盖：{', '.join(cov['fields_present']) or '-'}"
              f"（缺失：{', '.join(cov['fields_missing']) or '-'}）"]
    s = result["summary"]
    lines += [f"- 总览：{s['distance_km']} km / {s['duration_min']} min / 平均配速 {fmt_pace(s['avg_pace'])}"
              f" / 心率均 {s['hr_avg'] or '-'} 最 {s['hr_max'] or '-'}"
              f" / 爬升 {s['elevation_gain_m']} m 下降 {s['elevation_loss_m']} m"]
    if s.get("temp_start") is not None:
        lines.append(f"- 温度：{s['temp_start']}°C → {s['temp_end']}°C")
    lines.append("")

    if result["splits"]:
        lines += ["## 公里分段", "",
                  "| km | 配速 | GAP | 心率 | 爬升 m | 坡度 |", "|---|---|---|---|---|---|"]
        for sp in result["splits"]:
            lines.append(f"| {sp['km']} | {sp.get('pace', '-')} | {sp.get('gap', '-')} "
                         f"| {round(sp['hr']) if sp.get('hr') else '-'} | {sp.get('gain', 0)} "
                         f"| {round(sp.get('grade', 0) * 100, 1)}% |")
        lines.append("")
        lines.append("GAP 为 Minetti 坡度修正估计配速，非实测。")

    b = result.get("balance")
    if b:
        lines += ["", "## 配速执行", "",
                  f"- 前半程 {fmt_pace(b['first_half_pace'])} / 后半程 {fmt_pace(b['second_half_pace'])}"
                  f"（差 {b['second_half_pct']:+}%）",
                  f"- 分段离散度 CV {b['pace_cv_pct']}%；最快 {b['fastest_km']} km（{fmt_pace(b['fastest_pace'])}），"
                  f"最慢 {b['slowest_km']} km（{fmt_pace(b['slowest_pace'])}）"]

    gb = result.get("grade_bins")
    if gb:
        lines += ["", "## 坡度-配速-心率", "", "| 区间 | 时间 min | 配速 | GAP | 心率 |", "|---|---|---|---|---|"]
        lines += [f"| {g['bin']} | {g['time_min']} | {g['pace']} | {g['gap']} | {g['hr']} |" for g in gb]

    climbs = result.get("climbs")
    if climbs:
        lines += ["", "## 关键爬坡段", ""]
        lines += [f"- {c['start_km']} km 起：{c['length_m']} m / 爬 {c['gain_m']} m（均坡 {c['avg_grade_pct']}%），"
                  f"配速 {c['pace']}，心率 {c['hr_avg'] or '-'}" for c in climbs]

    d = result.get("drift")
    if d:
        lines += ["", "## 同配速心率漂移", ""]
        lines += [f"- 综合：后半程同配速心率 {d['overall_drift_bpm']:+} bpm"]
        lines += [f"- {x['pace']}：{x['hr_first']} → {x['hr_second']}（{x['drift_bpm']:+} bpm）"
                  for x in d["bins"]]

    e = result.get("efficiency")
    if e:
        lines += ["", f"- 平路效率因子 EF：{e['ef_first']} → {e['ef_last']}（{e['change_pct']:+}%）"]

    z = result.get("hr_zones")
    if z:
        lines += ["", f"## 心率区间分布（{z['basis']}）", ""]
        lines += [f"- {x['zone']}：{x['time_min']} min（{x['pct']}%）" for x in z["zones"]]

    c = result.get("cadence")
    if c:
        lines += ["", f"- 步频：前 1/3 {c['first_third']} → 后 1/3 {c['last_third']}（{c['decay']:+}）"]

    st = result.get("stops")
    if st and st["count"]:
        marks = ", ".join(f"{x['km']}km({x['duration_s']}s)" for x in st["stops"])
        lines += ["", f"- 停表/步行：{st['count']} 次，共 {st['total_min']} min @ {marks}"]

    if result["flags"]:
        lines += ["", "## 标记", ""]
        lines += [f"- [{f['severity']}] {f['detail']}" for f in result["flags"]]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="比赛/关键训练 FIT 细粒度复盘分析。")
    parser.add_argument("--input", help="归一化记录 JSON；省略时从 stdin 读取。")
    parser.add_argument("--fit", help="FIT 二进制文件（需要 fitdecode 或 fitparse）。")
    parser.add_argument("--threshold-hr", type=int, help="阈值心率，用于更准的心率区间划分。")
    parser.add_argument("--json", action="store_true", help="输出 JSON；默认输出 Markdown。")
    args = parser.parse_args()
    if not args.fit and args.input is None and sys.stdin.isatty():
        parser.error("需要 --fit 或 --input")
    payload = load_records(args)
    result = analyze(payload, args.threshold_hr)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else to_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
