#!/usr/bin/env python3
"""Offline analysis for Phantom EV3 bench CSV logs (standard-library only)."""

import argparse
import csv
import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path


NUMERIC = {
    "monotonic_time_us", "battery_voltage", "duty_cycle_sp", "duty_cycle",
    "position", "speed", "loop_dt_us", "target_position", "position_error", "goal_position",
    "target_speed", "cpu_time_us", "heartbeat_age_us", "detection_latency_us", "stop_command_latency_us", "work_time_us",
    "rate_hz", "operation_duration_us", "tick_start_us",
    "trial_index", "cycle_index", "started_100ms", "started_200ms", "started_300ms", "started_500ms",
}


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def finite(values):
    return [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]


def mean(values):
    values = finite(values)
    return statistics.mean(values) if values else math.nan


def stdev(values):
    values = finite(values)
    return statistics.stdev(values) if len(values) > 1 else (0.0 if values else math.nan)


def percentile(values, p):
    values = sorted(finite(values))
    if not values:
        return math.nan
    index = (len(values) - 1) * p
    lo, hi = int(math.floor(index)), int(math.ceil(index))
    return values[lo] if lo == hi else values[lo] * (hi - index) + values[hi] * (index - lo)


def fmt(value, digits=2):
    return "n/a" if not isinstance(value, (int, float)) or not math.isfinite(value) else f"{value:.{digits}f}"


def md_escape(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def load_logs(raw):
    rows, errors = [], []
    for path in sorted(raw.rglob("*.csv")):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                for index, row in enumerate(csv.DictReader(stream), 2):
                    if not row.get("test_id"):
                        continue
                    for key in NUMERIC:
                        if key in row:
                            row[key] = number(row[key])
                    row["_file"] = str(path)
                    row["_line"] = index
                    rows.append(row)
        except Exception as exc:  # preserve partial reports if one run was interrupted/corrupt
            errors.append(f"{path}: {exc}")
    return rows, errors


def environment(raw):
    candidates = [raw.parent / "environment.json", raw / "environment.json"]
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8")), path
            except Exception:
                pass
    return {}, None


def group(rows, *keys):
    result = defaultdict(list)
    for row in rows:
        result[tuple(row.get(key, "") for key in keys)].append(row)
    return result


def rate_from_path(path, dts):
    match = re.search(r"_(25|50|75|100|200)hz", path)
    if match:
        return int(match.group(1))
    median = percentile([x for x in dts if x > 1000], 0.5)
    return int(round(1_000_000 / median)) if math.isfinite(median) and median > 0 else 0


def jitter(rows):
    records = []
    for (path, mode), items in group([r for r in rows if r["test_id"].upper() in ("E1", "E12", "E1_MINIMAL")], "_file", "command_mode").items():
        # E1 emits one identical dt per motor. Use unique (time, dt) pairs.
        pairs = {(r["monotonic_time_us"], r["loop_dt_us"], r.get("cpu_time_us", math.nan)) for r in items}
        ordered = sorted(pairs)
        dts = [p[1] for p in ordered if p[1] > 1000]
        work = [r.get("work_time_us", math.nan) for r in items if r.get("work_time_us", 0) > 0]
        start = min(r["monotonic_time_us"] for r in items)
        end = max(r["monotonic_time_us"] for r in items)
        volts = finite([r["battery_voltage"] for r in items])
        recorded_rate = mean([r.get("rate_hz", math.nan) for r in items])
        rate = recorded_rate if math.isfinite(recorded_rate) and recorded_rate > 0 else rate_from_path(path, dts)
        period = 1_000_000 / rate if rate else math.nan
        cpu = math.nan
        if len(ordered) > 1:
            wall = ordered[-1][0] - ordered[0][0]
            cpu_delta = ordered[-1][2] - ordered[0][2]
            if wall > 0 and math.isfinite(cpu_delta):
                cpu = 100 * cpu_delta / wall
        records.append({
            "test": items[0]["test_id"].upper(), "file": Path(path).name, "mode": mode,
            "run_id": ", ".join(sorted({r.get("run_id", "") for r in items if r.get("run_id", "")})) or "n/a",
            "rows": len(items), "duration_s": (end - start) / 1000000,
            "motors_seen": ", ".join(sorted({f"{r.get('motor_address')} ({r.get('motor_driver')})" for r in items})),
            "battery_range": f"{fmt(min(volts), 3)}-{fmt(max(volts), 3)}" if volts else "n/a",
            "motor_count": len({r.get("motor_address") for r in items if r.get("motor_address") not in ("", "both")}) or (2 if items[0]["test_id"].upper() == "E12" else 0),
            "rate": rate, "n": len(dts), "mean": mean(dts), "p50": percentile(dts, .5),
            "p95": percentile(dts, .95), "p99": percentile(dts, .99),
            "max": max(dts) if dts else math.nan,
            "work_mean": mean(work), "work_p50": percentile(work, .5), "work_p95": percentile(work, .95),
            "work_p99": percentile(work, .99), "work_max": max(work) if work else math.nan,
            "missed": sum(dt > period * 1.5 for dt in dts) if rate else 0,
            "cpu": cpu,
        })
    return records


def latency_decomposition(rows):
    source = [r for r in rows if r["test_id"].upper() == "E1_5" and r.get("operation")]
    operations = []
    for (path, operation), items in group(source, "_file", "operation").items():
        values = [r.get("operation_duration_us", math.nan) for r in items]
        operations.append({"file": Path(path).name, "run_id": items[0].get("run_id", "n/a"),
                           "operation": operation, "n": len(items), "mean": mean(values),
                           "p50": percentile(values, .5), "p95": percentile(values, .95),
                           "p99": percentile(values, .99), "max": max(finite(values), default=math.nan)})
    ticks = []
    for (path, tick_start), items in group(source, "_file", "tick_start_us").items():
        if not math.isfinite(number(tick_start)):
            continue
        total = next((r.get("operation_duration_us", math.nan) for r in items if r.get("operation") == "tick_total"), math.nan)
        dt = items[0].get("loop_dt_us", math.nan)
        ticks.append({"file": Path(path).name, "tick": number(tick_start), "dt": dt, "work": total})
    attribution = []
    for (path,), items in group(ticks, "file").items():
        dts = [x["dt"] for x in items if x["dt"] > 1000]
        work = [x["work"] for x in items]
        if not dts or not work:
            continue
        period = 1_000_000 / mean([r.get("rate_hz", math.nan) for r in source if Path(r["_file"]).name == path])
        tail = [x for x in items if x["dt"] > period * 1.5]
        attribution.append({"file": path, "dt_p99": percentile(dts, .99), "dt_max": max(dts),
                            "work_p99": percentile(work, .99), "work_max": max(work),
                            "tail_ticks": len(tail),
                            "tail_work_max": max([x["work"] for x in tail], default=math.nan),
                            "period": period})
    return operations, attribution


def minimal_repeatability(jit):
    records = [x for x in jit if x["test"] == "E1_MINIMAL" and x["mode"] == "persistent-minimal"]
    result = []
    for (rate,), items in group(records, "rate").items():
        period = 1_000_000 / rate
        result.append({"rate": rate, "runs": len(items), "p50": mean([x["p50"] for x in items]),
                       "p95_worst": max(x["p95"] for x in items), "p99_worst": max(x["p99"] for x in items),
                       "max_worst": max(x["max"] for x in items), "work_p50": mean([x["work_p50"] if "work_p50" in x else x["work_mean"] for x in items]),
                       "work_p95": max(x["work_p95"] if "work_p95" in x else x["work_p99"] for x in items),
                       "work_p99": max(x["work_p99"] for x in items), "work_max": max(x["work_max"] for x in items),
                       "missed": sum(x["missed"] for x in items), "cpu": mean([x["cpu"] for x in items]),
                       "candidate": len(items) >= 3 and sum(x["missed"] for x in items) == 0 and max(x["max"] for x in items) < period * 1.5})
    return sorted(result, key=lambda x: x["rate"])


def alternating_summary(jit):
    records = [x for x in jit if x["test"] == "E1" and "e1alt_" in x["run_id"]]
    result = []
    for (rate, mode), items in group(records, "rate", "mode").items():
        result.append({"rate": rate, "mode": mode, "runs": len(items),
                       "dt_p50": mean([x["p50"] for x in items]), "dt_p95": mean([x["p95"] for x in items]),
                       "dt_p99": mean([x["p99"] for x in items]), "dt_max": max(x["max"] for x in items),
                       "work_p50": mean([x["work_p50"] for x in items]), "work_p95": mean([x["work_p95"] for x in items]),
                       "work_p99": mean([x["work_p99"] for x in items]), "work_max": max(x["work_max"] for x in items),
                       "missed": sum(x["missed"] for x in items),
                       "evidence": ", ".join(f"{x['file']} ({x['run_id']})" for x in items)})
    return sorted(result, key=lambda x: (x["rate"], x["mode"]))


def duty_curves(rows, test="E2"):
    result = []
    source = [r for r in rows if r["test_id"].upper() == test and r.get("command_mode") == "run-direct"]
    for (address, driver, duty), items in group(source, "motor_address", "motor_driver", "duty_cycle_sp").items():
        speeds = [r["speed"] for r in items]
        volts = [r["battery_voltage"] for r in items]
        result.append({"address": address, "driver": driver, "duty": duty,
                       "speed": mean(speeds), "std": stdev(speeds), "voltage": mean(volts), "n": len(items)})
    return sorted(result, key=lambda x: (x["address"], x["duty"]))


def reliable_floor(curve):
    result = {}
    for address in sorted({x["address"] for x in curve}):
        values = [x for x in curve if x["address"] == address and abs(x["speed"]) >= 5 and x["std"] <= max(5, abs(x["speed"]) * .5)]
        result[address] = min((abs(x["duty"]) for x in values), default=math.nan)
    return result


def asymmetry(curve):
    result = {}
    by_motor = group(curve, "address")
    for (address,), items in by_motor.items():
        positive = {abs(x["duty"]): abs(x["speed"]) for x in items if x["duty"] > 0}
        negative = {abs(x["duty"]): abs(x["speed"]) for x in items if x["duty"] < 0}
        diffs = [100 * abs(positive[d] - negative[d]) / max((positive[d] + negative[d]) / 2, 1) for d in positive.keys() & negative.keys()]
        result[address] = mean(diffs)
    return result


def stable_moving_curve(curve):
    """Exclude failed starts and noisy near-zero points from direction matching."""
    return [x for x in curve if abs(x["speed"]) >= 10 and x["std"] <= max(10, abs(x["speed"]) * .35)]


def c1_start_summary(rows):
    results = []
    source = [r for r in rows if r["test_id"].upper() == "C1" and r.get("event") == "trial_result"]
    for (address, duty), items in group(source, "motor_address", "duty_cycle_sp").items():
        stable = [r for r in rows if r["test_id"].upper() == "C1" and r.get("event") == "stable_measurement"
                  and r.get("motor_address") == address and r.get("duty_cycle_sp") == duty]
        results.append({"address": address, "duty": duty, "trials": len(items),
                        "p100": mean([r.get("started_100ms", math.nan) for r in items]),
                        "p200": mean([r.get("started_200ms", math.nan) for r in items]),
                        "p300": mean([r.get("started_300ms", math.nan) for r in items]),
                        "p500": mean([r.get("started_500ms", math.nan) for r in items]),
                        "steady_speed": mean([abs(r["speed"]) for r in stable]),
                        "battery": mean([r["battery_voltage"] for r in items])})
    return sorted(results, key=lambda x: (x["address"], x["duty"]))


def c1_thresholds(summary):
    result = {}
    for address in sorted({x["address"] for x in summary}):
        for sign in (-1, 1):
            items = sorted([x for x in summary if x["address"] == address and x["duty"] * sign > 0], key=lambda x: abs(x["duty"]))
            start = next((abs(x["duty"]) for x in items if x["trials"] >= 10 and x["p300"] >= .99), math.nan)
            sustain = next((abs(x["duty"]) for x in items if x["trials"] >= 10 and x["steady_speed"] >= 10), math.nan)
            result[(address, sign)] = {"start99": start, "sustain": sustain}
    return result


def linear_slope(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 2:
        return math.nan
    xbar, ybar = mean([p[0] for p in pairs]), mean([p[1] for p in pairs])
    denominator = sum((x - xbar) ** 2 for x, _ in pairs)
    return sum((x - xbar) * (y - ybar) for x, y in pairs) / denominator if denominator else math.nan


def controller_summary(rows, test):
    result = []
    for (path, address, mode), items in group([r for r in rows if r["test_id"].upper() == test], "_file", "motor_address", "command_mode").items():
        items = sorted(items, key=lambda r: r["monotonic_time_us"])
        errors = [r["position_error"] for r in items]
        duties = [abs(r["duty_cycle_sp"]) for r in items]
        target_range = max([r["target_position"] for r in items], default=0) - min([r["target_position"] for r in items], default=0)
        positions = [r["position"] for r in items]
        targets = [r["target_position"] for r in items]
        lag_candidates = []
        for lag in range(min(11, max(1, len(items) // 10))):
            pairs = list(zip(targets[:-lag or None], positions[lag:]))
            lag_candidates.append((math.sqrt(mean([(a-b) ** 2 for a,b in pairs])), lag))
        best_lag = min(lag_candidates)[1] if lag_candidates else 0
        median_dt = percentile([r["loop_dt_us"] for r in items if r["loop_dt_us"] > 1000], .5)
        deltas = [abs(b-a) for a,b in zip(positions, positions[1:]) if b != a]
        speed_changes = [b-a for a,b in zip([r["speed"] for r in items], [r["speed"] for r in items][1:])]
        rise_times, settling_times, overshoots = [], [], []
        segments, current = [], []
        last_goal = None
        for row in items:
            goal = row.get("goal_position", row["target_position"])
            if last_goal is not None and goal != last_goal and current:
                segments.append(current); current = []
            current.append(row); last_goal = goal
        if current: segments.append(current)
        for segment in segments:
            goal = segment[0].get("goal_position", segment[-1]["target_position"])
            start_pos = segment[0]["position"]
            distance = goal - start_pos
            if abs(distance) < 1: continue
            sign = 1 if distance > 0 else -1
            start_time = segment[0]["monotonic_time_us"]
            t10 = next((r for r in segment if sign * (r["position"] - start_pos) >= .1 * abs(distance)), None)
            t90 = next((r for r in segment if sign * (r["position"] - start_pos) >= .9 * abs(distance)), None)
            if t10 and t90: rise_times.append((t90["monotonic_time_us"] - t10["monotonic_time_us"]) / 1000)
            tolerance = max(2, .02 * abs(distance))
            settle = None
            for index, row in enumerate(segment):
                if all(abs(goal - future["position"]) <= tolerance for future in segment[index:]):
                    settle = (row["monotonic_time_us"] - start_time) / 1000; break
            if settle is not None: settling_times.append(settle)
            extreme = max(sign * (r["position"] - goal) for r in segment)
            overshoots.append(max(0, 100 * extreme / abs(distance)))
        arrivals = {r.get("trial_index") for r in items if r.get("event") == "arrival" and r.get("trial_index", -1) >= 0}
        expected = {r.get("trial_index") for r in items if r.get("trial_index", -1) >= 0}
        result.append({"file": Path(path).name, "address": address, "mode": mode,
                       "rmse": math.sqrt(mean([e * e for e in errors])), "steady": mean(errors[-max(1, len(errors)//10):]),
                       "p95_error": percentile([abs(e) for e in errors], .95),
                       "arrivals": len(arrivals) if expected else sum(r.get("event") == "arrival" for r in items),
                       "arrival_rate": len(arrivals) / len(expected) if expected else min(1.0, sum(r.get("event") == "arrival" for r in items) / max(1, len(segments))),
                       "max_duty": max(duties) if duties else math.nan, "target_range": target_range,
                       "speed_max": max([abs(r["speed"]) for r in items], default=math.nan),
                       "lag_ms": best_lag * median_dt / 1000 if math.isfinite(median_dt) else math.nan,
                       "min_increment": min(deltas) if deltas else math.nan, "smoothness": stdev(speed_changes),
                       "rise_ms": mean(rise_times), "settling_ms": mean(settling_times), "overshoot": mean(overshoots)})
    return result


def dual_timing(rows, test):
    """Timing is one shared tick; retain each motor's tracking metrics separately."""
    source = [r for r in rows if r["test_id"].upper() == test]
    result = []
    for (path,), items in group(source, "_file").items():
        ticks = sorted({(r["monotonic_time_us"], r["loop_dt_us"], r.get("work_time_us", math.nan), r.get("cpu_time_us", math.nan)) for r in items})
        dts = [x[1] for x in ticks if x[1] > 1000]
        work = [x[2] for x in ticks if x[2] > 0]
        rate = mean([r.get("rate_hz", math.nan) for r in items])
        period = 1_000_000 / rate if math.isfinite(rate) and rate else math.nan
        volts = [r["battery_voltage"] for r in items]
        for (address,), motor_rows in group(items, "motor_address").items():
            errors = [r["position_error"] for r in motor_rows]
            duties = [abs(r["duty_cycle_sp"]) for r in motor_rows]
            result.append({"test": test, "file": Path(path).name, "run_id": motor_rows[0].get("run_id", "n/a"), "address": address,
                           "rows": len(motor_rows), "rmse": math.sqrt(mean([x*x for x in errors])), "p95_error": percentile([abs(x) for x in errors], .95),
                           "max_speed": max([abs(r["speed"]) for r in motor_rows], default=math.nan), "max_duty": max(duties, default=math.nan),
                           "saturation_pct": 100 * mean([d >= 64 for d in duties]), "battery_min": min(finite(volts), default=math.nan), "battery_max": max(finite(volts), default=math.nan),
                           "dt_p50": percentile(dts,.5), "dt_p95": percentile(dts,.95), "dt_p99": percentile(dts,.99), "dt_max": max(dts,default=math.nan),
                           "work_p50": percentile(work,.5), "work_p95": percentile(work,.95), "work_p99": percentile(work,.99), "work_max": max(work,default=math.nan),
                           "missed": sum(x > period*1.5 for x in dts) if math.isfinite(period) else 0})
    return result


def d1_effect(rows):
    source = [r for r in rows if r["test_id"].upper() == "D1" and r.get("event") == "steady"]
    buckets = defaultdict(list)
    for row in source:
        name = Path(row["_file"]).name
        match = re.search(r"_m(-?\d+)_l(-?\d+)_r", name)
        if not match: continue
        md, ld = int(match.group(1)), int(match.group(2))
        commanded = md if row["motor_address"].endswith("outA") else ld
        other = ld if row["motor_address"].endswith("outA") else md
        buckets[(row["motor_address"], commanded, other)].append(abs(row["speed"]))
    result=[]
    for (address,duty,other), speeds in buckets.items():
        result.append({"address":address,"duty":duty,"other":other,"speed":mean(speeds),"battery":math.nan})
    return result


def d2_transients(rows):
    source=[r for r in rows if r["test_id"].upper()=="D2"]
    result=[]
    for (path,), items in group(source,"_file").items():
        for event in ("medium_start","large_start","medium_brake","medium_reverse","large_reverse"):
            trigger=next((r for r in sorted(items,key=lambda x:x["monotonic_time_us"]) if r.get("event")==event),None)
            if not trigger: continue
            other="outB" if event.startswith("medium") else "outA"
            before=[r["speed"] for r in items if r["motor_address"].endswith(other) and trigger["monotonic_time_us"]-100000 <= r["monotonic_time_us"] < trigger["monotonic_time_us"]]
            for window in (100,200,500):
                after=[r["speed"] for r in items if r["motor_address"].endswith(other) and trigger["monotonic_time_us"] <= r["monotonic_time_us"] < trigger["monotonic_time_us"]+window*1000]
                result.append({"file":Path(path).name,"event":event,"other":other,"window":window,"delta":mean(after)-mean(before)})
    return result


def p2p_summary(rows, test):
    result=[]
    source=[r for r in rows if r["test_id"].upper()==test]
    for (path,), items in group(source,"_file").items():
        arrivals={}
        for (address,), motor_rows in group(items, "motor_address").items():
            ordered=sorted(motor_rows,key=lambda r:r["monotonic_time_us"])
            hold=next((r for r in ordered if r.get("event") in ("planned_hold","builtin_tracking")), ordered[0] if ordered else None)
            arrived=next((r for r in ordered if hold and r["monotonic_time_us"]>=hold["monotonic_time_us"] and abs(r["position_error"])<=3 and abs(r["speed"])<=5),None)
            arrivals[address]=arrived["monotonic_time_us"] if arrived else math.nan
        values=finite(list(arrivals.values()))
        result.append({"test":test,"file":Path(path).name,"medium_arrival":arrivals.get("ev3-ports:outA",math.nan),"large_arrival":arrivals.get("ev3-ports:outB",math.nan),
                       "skew_ms":abs(arrivals.get("ev3-ports:outA",math.nan)-arrivals.get("ev3-ports:outB",math.nan))/1000 if len(values)==2 else math.nan,
                       "arrival_rate":len(values)/2})
    return result


def e5_drift(rows, test="E5"):
    results = []
    events = ("arrival",) if test.upper() == "C4" else ("target_hold", "arrival")
    for (path, address), items in group([r for r in rows if r["test_id"].upper() == test and r.get("event") in events], "_file", "motor_address").items():
        # Last sample for every contiguous absolute target hold.
        arrivals, last_target = [], None
        for row in items:
            target = row["target_position"]
            if last_target is None or target != last_target:
                arrivals.append(row)
            else:
                arrivals[-1] = row
            last_target = target
        errors = [r["position_error"] for r in arrivals]
        results.append({"file": Path(path).name, "address": address, "n": len(errors),
                        "mean": mean(errors), "std": stdev(errors),
                        "slope": linear_slope(list(range(len(errors))), errors)})
    return results


def dynamic_summary(rows):
    result = []
    for (path, address), items in group([r for r in rows if r["test_id"].upper() == "E3"], "_file", "motor_address").items():
        accel = sorted([r for r in items if r.get("event") == "acceleration"], key=lambda r: r["monotonic_time_us"])
        if accel:
            speeds = [abs(r["speed"]) for r in accel]
            steady = mean(speeds[-max(3, len(speeds)//5):])
            start = accel[0]["monotonic_time_us"]
            times = {}
            for level in (0.1, 0.5, 0.9):
                hit = next((r for r in accel if abs(r["speed"]) >= abs(steady) * level), None)
                times[level] = (hit["monotonic_time_us"] - start) / 1000 if hit else math.nan
            overshoot = 100 * (max(speeds) - steady) / max(abs(steady), 1)
            acceleration = .9 * steady / (times[.9] / 1000) if times[.9] > 0 else math.nan
            result.append({"file": Path(path).name, "address": address, "kind": "step",
                           "mode": accel[0].get("duty_cycle_sp", ""), "t10": times[.1], "t50": times[.5],
                           "t90": times[.9], "acceleration": acceleration, "overshoot": overshoot,
                           "stop_ms": math.nan, "travel": math.nan})
        for mode in ("coast", "brake", "hold"):
            stop = sorted([r for r in items if r.get("event") == "stop" and r.get("command_mode") == mode], key=lambda r: r["monotonic_time_us"])
            if not stop: continue
            initial_speed, start_time, start_pos = abs(stop[0]["speed"]), stop[0]["monotonic_time_us"], stop[0]["position"]
            threshold = max(5, initial_speed * .05)
            zero = next((r for r in stop if abs(r["speed"]) <= threshold), stop[-1])
            result.append({"file": Path(path).name, "address": address, "kind": "stop", "mode": mode,
                           "t10": math.nan, "t50": math.nan, "t90": math.nan, "acceleration": math.nan,
                           "overshoot": math.nan, "stop_ms": (zero["monotonic_time_us"] - start_time) / 1000,
                           "travel": zero["position"] - start_pos})
    return result


def emergency_summary(rows):
    result = []
    for (path, address), items in group([r for r in rows if r["test_id"].upper() == "E10"], "_file", "motor_address").items():
        ordered = sorted(items, key=lambda r: r["monotonic_time_us"])
        command = next((r for r in ordered if r.get("event") == "stop_write"), None)
        after = [r for r in ordered if command and r["monotonic_time_us"] >= command["monotonic_time_us"]]
        zero = next((r for r in after if abs(r["speed"]) <= 5), after[-1] if after else None)
        result.append({"file": Path(path).name, "address": address,
                       "write_us": command.get("stop_command_latency_us", math.nan) if command else math.nan,
                       "zero_ms": (zero["monotonic_time_us"] - command["monotonic_time_us"]) / 1000 if zero and command else math.nan,
                       "travel": zero["position"] - command["position"] if zero and command else math.nan})
    return result


def moving_stop_summary(rows):
    """Measured moving-stop data from C7; do not mix it with stationary E10."""
    result = []
    for (path, address), items in group([r for r in rows if r["test_id"].upper() == "C7"], "_file", "motor_address").items():
        ordered = sorted(items, key=lambda r: r["monotonic_time_us"])
        command = next((r for r in ordered if r.get("event") == "stop_write"), None)
        after = [r for r in ordered if command and r["monotonic_time_us"] >= command["monotonic_time_us"]]
        zero = next((r for r in after if abs(r["speed"]) <= 5), after[-1] if after else None)
        pre = next((r for r in reversed(ordered[:ordered.index(command)]) if abs(r["speed"]) > 5), None) if command else None
        result.append({"file": Path(path).name, "address": address,
                       "pre_speed": abs(pre["speed"]) if pre else math.nan,
                       "write_us": command.get("stop_command_latency_us", math.nan) if command else math.nan,
                       "zero_ms": (zero["monotonic_time_us"] - command["monotonic_time_us"]) / 1000 if zero and command else math.nan,
                       "travel": zero["position"] - command["position"] if zero and command else math.nan})
    return result


def crash_summary(rows):
    result = []
    for (path, fault, address), items in group([r for r in rows if r["test_id"].upper() == "E9"], "_file", "fault", "motor_address").items():
        ordered = sorted(items, key=lambda r: r["monotonic_time_us"])
        injected = next((r for r in ordered if r.get("event") == "fault_injected"), None)
        stopped = next((r for r in ordered if r.get("event") in ("supervisor_stop", "external_watchdog_stop")), None)
        final = ordered[-1] if ordered else None
        result.append({"file": Path(path).name, "fault": fault, "address": address,
                       "heartbeat_age_ms": stopped.get("heartbeat_age_us", math.nan) / 1000 if stopped else math.nan,
                       "detection_ms": stopped.get("detection_latency_us", math.nan) / 1000 if stopped else math.nan,
                       "write_us": stopped.get("stop_command_latency_us", math.nan) if stopped else math.nan,
                       "travel_to_stop": stopped["position"] - injected["position"] if stopped and injected else math.nan,
                       "travel_total": final["position"] - injected["position"] if final and injected else math.nan})
    return result


def c6_safety_statistics(rows):
    """All C6 repetitions, matched in temporal order per fault/file."""
    source = [r for r in rows if r["test_id"].upper() == "E9" and str(r.get("run_id", "")).startswith("c6")]
    result = []
    for (fault, address), items in group(source, "fault", "motor_address").items():
        ordered = sorted(items, key=lambda r: r["monotonic_time_us"])
        injected = [r for r in ordered if r.get("event") == "fault_injected"]
        stops = [r for r in ordered if r.get("event") in ("supervisor_stop", "external_watchdog_stop")]
        pairs = list(zip(injected, stops))
        detection = []
        for _, stopped in pairs:
            latency = stopped.get("detection_latency_us", math.nan)
            # The no-supervisor baseline logs its independently measured outer
            # watchdog interval in loop_dt_us rather than a supervisor field.
            if fault == "baseline" or not math.isfinite(latency):
                latency = stopped.get("loop_dt_us", math.nan)
            detection.append(latency / 1000)
        writes = [math.nan if fault == "baseline" else s.get("stop_command_latency_us", math.nan) for _, s in pairs]
        travel = [s["position"] - i["position"] for i, s in pairs]
        result.append({"file": "C6 aggregate", "fault": fault, "address": address,
                       "n": len(pairs), "detection_p50": percentile(detection, .50),
                       "detection_p95": percentile(detection, .95), "detection_p99": percentile(detection, .99),
                       "detection_max": max(detection, default=math.nan), "write_p95": percentile(writes, .95),
                       "travel_p95": percentile(travel, .95), "travel_max": max(travel, default=math.nan)})
    return result


def e7_sweep(rows):
    source = [r for r in rows if r["test_id"].upper() == "E7"]
    if not source:
        return []
    controls = [r for r in rows if r["test_id"].upper() in ("E2", "E6") and r.get("command_mode") == "run-direct"]
    candidates = []
    def detection(items, duty_min, speed_max, duration_ms):
        items = sorted(items, key=lambda r: r["monotonic_time_us"])
        start = None
        for row in items:
            condition = abs(row["duty_cycle_sp"]) >= duty_min and abs(row["speed"]) <= speed_max
            start = row["monotonic_time_us"] if condition and start is None else (start if condition else None)
            if start is not None and row["monotonic_time_us"] - start >= duration_ms * 1000:
                return (row["monotonic_time_us"] - items[0]["monotonic_time_us"]) / 1000
        return None
    for duty_min in (15, 20, 25):
        for speed_max in (2, 5, 10, 20):
            for duration_ms in (50, 100, 150, 200):
                detections = []
                for (path,), items in group(source, "_file").items():
                    detected = detection(items, duty_min, speed_max, duration_ms)
                    if detected is not None:
                        detections.append(detected)
                false_positives = sum(detection(items, duty_min, speed_max, duration_ms) is not None for items in group(controls, "_file").values())
                candidates.append((len(detections), false_positives, mean(detections), duty_min, speed_max, duration_ms))
    return sorted(candidates, key=lambda x: (-x[0], x[1], x[2] if math.isfinite(x[2]) else math.inf))[:8]


def battery_summary(rows):
    result = []
    for (test, address, duty), items in group([r for r in rows if r["test_id"].upper() in ("E2", "E6")], "test_id", "motor_address", "duty_cycle_sp").items():
        volts = [r["battery_voltage"] for r in items]
        speeds = [abs(r["speed"]) for r in items]
        if len(set(round(v, 2) for v in finite(volts))) >= 2:
            result.append({"test": test, "address": address, "condition": f"duty {duty:.0f}", "metric": "abs speed / V", "slope": linear_slope(volts, speeds),
                           "vmin": min(finite(volts)), "vmax": max(finite(volts))})
    controller_runs = []
    for (path, address), items in group([r for r in rows if r["test_id"].upper() == "E4"], "_file", "motor_address").items():
        controller_runs.append((address, mean([r["battery_voltage"] for r in items]),
                                math.sqrt(mean([r["position_error"] ** 2 for r in items]))))
    for address in {x[0] for x in controller_runs}:
        points = [x for x in controller_runs if x[0] == address]
        volts, rmses = [x[1] for x in points], [x[2] for x in points]
        if len(set(round(v, 2) for v in finite(volts))) >= 2:
            result.append({"test": "E4", "address": address, "condition": "controller runs", "metric": "RMSE counts / V",
                           "slope": linear_slope(volts, rmses), "vmin": min(volts), "vmax": max(volts)})
    floor_runs = []
    for (run_id, address), items in group([r for r in rows if r["test_id"].upper() == "E6" and r.get("command_mode") == "run-direct"], "run_id", "motor_address").items():
        curve = []
        for (duty,), samples in group(items, "duty_cycle_sp").items():
            curve.append({"address": address, "duty": duty, "speed": mean([x["speed"] for x in samples]),
                          "std": stdev([x["speed"] for x in samples])})
        floor = reliable_floor(curve).get(address, math.nan)
        floor_runs.append((address, mean([r["battery_voltage"] for r in items]), floor))
    for address in {x[0] for x in floor_runs}:
        points = [x for x in floor_runs if x[0] == address and math.isfinite(x[2])]
        volts, floors = [x[1] for x in points], [x[2] for x in points]
        if len(set(round(v, 2) for v in finite(volts))) >= 2:
            result.append({"test": "E6", "address": address, "condition": "run floor", "metric": "minimum duty % / V",
                           "slope": linear_slope(volts, floors), "vmin": min(volts), "vmax": max(volts)})
    return result


def svg_speed_plot(curve, address, output):
    points = [x for x in curve if x["address"] == address and math.isfinite(x["speed"])]
    if not points:
        return None
    width, height, pad = 760, 440, 55
    xs, ys = [x["duty"] for x in points], [x["speed"] for x in points]
    xmin, xmax = min(xs), max(xs); ymin, ymax = min(ys), max(ys)
    if ymin == ymax: ymin, ymax = ymin - 1, ymax + 1
    sx = lambda x: pad + (x - xmin) / (xmax - xmin) * (width - 2 * pad)
    sy = lambda y: height - pad - (y - ymin) / (ymax - ymin) * (height - 2 * pad)
    poly = " ".join(f"{sx(x['duty']):.1f},{sy(x['speed']):.1f}" for x in points)
    circles = "".join(f'<circle cx="{sx(x["duty"]):.1f}" cy="{sy(x["speed"]):.1f}" r="4"/>' for x in points)
    title = f"{points[0]['driver']} ({address}) free-run speed vs duty"
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/><g stroke="#333" fill="none"><line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}"/><line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}"/></g>
<text x="{width/2}" y="28" text-anchor="middle" font-family="sans-serif" font-size="18">{title}</text>
<text x="{width/2}" y="{height-12}" text-anchor="middle" font-family="sans-serif">duty cycle (%)</text>
<text x="16" y="{height/2}" transform="rotate(-90 16 {height/2})" text-anchor="middle" font-family="sans-serif">speed (counts/s)</text>
<g stroke="#1769aa" stroke-width="2" fill="#1769aa"><polyline points="{poly}" fill="none"/>{circles}</g>
<text x="{pad}" y="{height-pad+20}" font-family="sans-serif" font-size="11">{xmin:.0f}</text><text x="{width-pad}" y="{height-pad+20}" text-anchor="end" font-family="sans-serif" font-size="11">{xmax:.0f}</text>
<text x="{pad-8}" y="{height-pad}" text-anchor="end" font-family="sans-serif" font-size="11">{ymin:.0f}</text><text x="{pad-8}" y="{pad}" text-anchor="end" font-family="sans-serif" font-size="11">{ymax:.0f}</text></svg>'''
    output.write_text(svg, encoding="utf-8")
    return output.name


def status(condition, available=True):
    if not available:
        return "INCONCLUSIVE"
    return "CONFIRMED" if condition else "REJECTED"


def make_report(raw, rows, errors, env, env_path, output):
    tests = defaultdict(list)
    for row in rows:
        tests[row["test_id"].upper()].append(row)
    jit = jitter(rows)
    operation_latency, latency_attribution = latency_decomposition(rows)
    minimal_rates = minimal_repeatability(jit)
    alternating = alternating_summary(jit)
    curve = duty_curves(rows)
    low_curve = duty_curves(rows, "E6")
    floor = reliable_floor(low_curve or curve)
    stable_curve = stable_moving_curve(curve)
    asym = asymmetry(stable_curve)
    c1 = c1_start_summary(rows)
    c1_limits = c1_thresholds(c1)
    e4 = controller_summary(rows, "E4")
    e5 = e5_drift(rows)
    e8 = controller_summary(rows, "E8")
    c2 = controller_summary(rows, "C2")
    c3 = controller_summary(rows, "C3")
    c4_tracking = controller_summary(rows, "C4")
    c4 = e5_drift(rows, "C4")
    c5 = controller_summary(rows, "C5")
    dynamics = dynamic_summary(rows)
    emergency = emergency_summary(rows)
    moving_stops = moving_stop_summary(rows)
    crashes = crash_summary(rows)
    c6 = c6_safety_statistics(rows)
    coordinated = {test: dual_timing(rows, test) for test in ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8")}
    d1 = d1_effect(rows)
    d2 = d2_transients(rows)
    stalls = e7_sweep(rows)
    battery = battery_summary(rows)
    motors = env.get("motors", []) if env else []
    output.parent.mkdir(parents=True, exist_ok=True)

    plots = []
    for address in sorted({x["address"] for x in curve}):
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", address) + "_speed_duty.svg"
        generated = svg_speed_plot(curve, address, output.parent / name)
        if generated: plots.append(generated)

    provenance = f"Input: `{raw.as_posix()}`; CSV rows: {len(rows)}; "
    provenance += f"Environment: `{env_path.as_posix()}`" if env_path else "Environment: not captured"
    lines = ["# EV3 validation report", "", provenance, "",
             "> Measurements describe free motors on this brick. They do not establish loaded-arm torque, gearing, gravity compensation, backlash, loaded speed, or four-motor performance.", ""]
    if errors:
        lines += ["## Input warnings", ""] + [f"- {e}" for e in errors] + [""]

    lines += ["## E0 environment and sysfs capabilities", ""]
    if env:
        lines += [f"- `uname`: `{env.get('uname', 'n/a')}`", f"- Architecture: `{env.get('architecture', 'n/a')}`; kernel: `{env.get('kernel', 'n/a')}`; libc: `{env.get('libc', 'n/a')}`",
                  f"- Battery at capture: {env.get('battery_voltage', 'n/a')} V", "",
                  "| path | address | driver | count_per_rot | max_speed | commands | stop_actions | polarity | state |",
                  "|---|---|---|---:|---:|---|---|---|---|"]
        for motor in motors:
            lines.append("| " + " | ".join(md_escape(motor.get(key, "")) for key in
                         ("path", "address", "driver_name", "count_per_rot", "max_speed", "commands", "stop_actions", "polarity", "state")) + " |")
        supplies = env.get("power_supplies", [])
        if supplies:
            lines += ["", "Power-supply attributes:", ""]
            for supply in supplies:
                attrs = ", ".join(f"`{k}={v}`" for k,v in supply.get("attributes", {}).items())
                lines.append(f"- {supply.get('name', 'unknown')}: {attrs}")
    else:
        lines.append("Environment has not been captured on the EV3.")
    manual = tests["E0"]
    if manual:
        lines += ["", "Interactive encoder checks:", "", "| address | one-turn measured counts | expected count_per_rot | reset position | position after manual post-reset motion | states observed |",
                  "|---|---:|---:|---:|---:|---|"]
        for (address,), items in group(manual, "motor_address").items():
            by_event = {r.get("event"): r for r in items}
            start = by_event.get("manual_start", {}).get("position", math.nan)
            turn = by_event.get("one_revolution", {}).get("position", math.nan)
            expected = next((m.get("count_per_rot") for m in motors if m.get("address") == address), math.nan)
            states = sorted({r.get("state_flags", "") for r in items})
            lines.append(f"| {address} | {fmt(turn-start,0)} | {fmt(number(expected),0)} | {fmt(by_event.get('position_reset', {}).get('position', math.nan),0)} | {fmt(by_event.get('post_reset_manual_motion', {}).get('position', math.nan),0)} | {', '.join(states)} |")
    lines += [""]

    smoke = tests["E_SMOKE"]
    lines += ["## Pipeline smoke verification", ""]
    if smoke:
        lines += ["| run_id | rows | duration s | motor address / driver | battery range V | loop dt p50 / p99 us |",
                  "|---|---:|---:|---|---:|---:|"]
        for (run_id,), items in group(smoke, "run_id").items():
            start = min(r["monotonic_time_us"] for r in items)
            end = max(r["monotonic_time_us"] for r in items)
            motors_seen = ", ".join(sorted({f"{r.get('motor_address')} ({r.get('motor_driver')})" for r in items}))
            battery_values = finite([r["battery_voltage"] for r in items])
            dt = [r["loop_dt_us"] for r in items if r["loop_dt_us"] > 1000]
            battery_range = f"{fmt(min(battery_values),3)}–{fmt(max(battery_values),3)}" if battery_values else "n/a"
            lines.append(f"| {run_id} | {len(items)} | {(end-start)/1000000:.3f} | {motors_seen} | {battery_range} | {fmt(percentile(dt,.5))} / {fmt(percentile(dt,.99))} |")
    else:
        lines.append("ERROR: no E_SMOKE rows were found. Do not interpret later bench results until the smoke pipeline passes.")
    lines += [""]

    lines += ["## Captured run inventory", "",
              "This evidence index keeps motor-specific results and individual runs separate.", "",
              "| source CSV | run ID | test | rows | duration s | motor address / driver | battery range V |",
              "|---|---|---|---:|---:|---|---:|"]
    for (path,), items in sorted(group(rows, "_file").items()):
        start = min(r["monotonic_time_us"] for r in items)
        end = max(r["monotonic_time_us"] for r in items)
        run_ids = ", ".join(sorted({r.get("run_id", "") for r in items if r.get("run_id", "")})) or "n/a"
        test_ids = ", ".join(sorted({r.get("test_id", "") for r in items if r.get("test_id", "")}))
        motor_details = ", ".join(sorted({f"{r.get('motor_address')} ({r.get('motor_driver')})" for r in items}))
        volts = finite([r["battery_voltage"] for r in items])
        voltage = f"{fmt(min(volts), 3)}-{fmt(max(volts), 3)}" if volts else "n/a"
        lines.append(f"| {Path(path).name} | {run_ids} | {test_ids} | {len(items)} | {(end-start)/1000000:.3f} | {motor_details} | {voltage} |")
    lines += [""]

    lines += ["## Hypotheses", "", "| hypothesis | measured result | verdict | evidence | implication |",
              "|---|---|---|---|---|"]
    best50 = [x for x in jit if x["test"] == "E1" and x["rate"] == 50 and x["mode"] == "persistent"]
    measured50 = [x for x in jit if x["test"] in ("E1", "E12") and x["rate"] == 50 and x["mode"] == "persistent"]
    naive50 = [x for x in jit if x["test"] == "E1" and x["rate"] == 50 and x["mode"] == "naive"]
    current_candidate = max([x for x in minimal_rates if x["candidate"]], key=lambda x: x["rate"], default=None)
    alternating_pairs = {(x["rate"], x["mode"]): x for x in alternating}
    persistent_confirmed = all(
        (rate, "persistent") in alternating_pairs and (rate, "naive") in alternating_pairs
        and alternating_pairs[(rate, "persistent")]["runs"] >= 3
        and alternating_pairs[(rate, "naive")]["runs"] >= 3
        and alternating_pairs[(rate, "persistent")]["work_p99"] < alternating_pairs[(rate, "naive")]["work_p99"]
        and alternating_pairs[(rate, "persistent")]["missed"] < alternating_pairs[(rate, "naive")]["missed"]
        for rate in (25.0, 50.0)
    )
    e4_ok = bool(e4) and max(x["rmse"] for x in e4) <= 15
    # A no-drift decision needs a usable arrival series for every connected
    # motor.  A single target-hold sample is evidence of neither tracking nor
    # drift, even when another motor completed the requested cycles.
    drift_ready = len({x["address"] for x in e5}) >= 2 and all(
        x["n"] >= 100 and math.isfinite(x["slope"]) for x in e5
    )
    drift_ok = drift_ready and max(abs(x["slope"]) for x in e5) <= 0.05
    e9 = tests["E9"]
    e9_stop = [r for r in e9 if r.get("event") == "supervisor_stop"]
    hypotheses = [
        ("Brick ABI was measured", f"{env.get('uname', 'not measured')}; libc {env.get('libc', 'n/a')}", status(bool(env), bool(env)), "environment.json", "Pin production compatibility only after capture."),
        ("Required motor sysfs features exist", f"{len(motors)} motor nodes captured", status(len(motors) >= 2, bool(env)), "E0 motor capability list", "Wrapper must use only observed commands/actions."),
        ("Large/Medium count_per_rot is known", "; ".join(f"{m.get('address')}: {m.get('count_per_rot')}" for m in motors) or "not measured", status(all(m.get("count_per_rot", 0) > 0 for m in motors) and len(motors) >= 2, bool(env)), "E0", "Use observed encoder scale."),
        ("50 Hz free two-motor minimal loop is the current candidate", f"three 120 s E1_MINIMAL runs: p99<={fmt(current_candidate['p99_worst'] if current_candidate else math.nan)} us, max<={fmt(current_candidate['max_worst'] if current_candidate else math.nan)} us, misses={current_candidate['missed'] if current_candidate else 'n/a'}", "CONFIRMED_AS_CURRENT_CANDIDATE" if current_candidate and abs(current_candidate['rate'] - 50) < .01 else "INCONCLUSIVE", "E1_MINIMAL production-like 50 Hz repeats", "Current free-bench candidate only; revalidate under mechanics and four motors."),
        ("Persistent FD improves over reopen", "; ".join(f"{fmt(rate,0)} Hz: p99 work persistent={fmt(alternating_pairs[(rate, 'persistent')]['work_p99'])} vs reopen={fmt(alternating_pairs[(rate, 'naive')]['work_p99'])} us; misses {alternating_pairs[(rate, 'persistent')]['missed']} vs {alternating_pairs[(rate, 'naive')]['missed']}" for rate in (25.0, 50.0) if (rate, 'persistent') in alternating_pairs and (rate, 'naive') in alternating_pairs) or "not measured", "CONFIRMED" if persistent_confirmed else "INCONCLUSIVE", "E1ALT alternating persistent/reopen x3 at 25 and 50 Hz", "Use persistent FD for the current EV3/free two-motor scope."),
        ("Free-run speed is characterized", f"{len(curve)} motor/duty/direction points", status(bool(curve), bool(curve)), "E2", "Feed-forward estimates remain no-load only."),
        ("Reliable low-duty floor is known", "; ".join(f"{k}: {fmt(v,0)}%" for k,v in floor.items()) or "not measured", status(bool(floor), bool(floor)), "E2/E6", "Set conservative homing/contact duty above measured floor."),
        ("Direction response is symmetric", "; ".join(f"{k}: stable-moving mismatch {fmt(v)}%" for k,v in asym.items()) or "not measured", status(bool(asym) and max(asym.values()) <= 10, bool(asym)), "E2 paired signs after failed-start/noisy points excluded", "Outliers are reported separately; compensate direction only if stable-moving mismatch is repeatable."),
        ("Duty-step dynamics are measured", f"{len(tests['E3'])} samples", status(bool(tests['E3']), bool(tests['E3'])), "E3", "Use rise/stop data for trajectory bounds."),
        ("coast/brake/hold were compared", f"modes: {', '.join(sorted(set(r.get('command_mode','') for r in tests['E3'])))}" if tests['E3'] else "not measured", status(bool(tests['E3']), bool(tests['E3'])), "E3 stop events", "Choose stop action from travel/latency, not assumption."),
        ("Custom run-direct P/PD is feasible", f"E4 best RMSE={fmt(min([x['rmse'] for x in e4], default=math.nan))} counts; low outputs were below C1 start region", "NEEDS_RETEST_WITH_FRICTION_COMPENSATION", "E4 plus C1", "Do not reject the architecture before C2 applies static-friction feed-forward."),
        ("Absolute targets have no software drift", f"max trend={fmt(max([abs(x['slope']) for x in e5], default=math.nan),4)} counts/cycle; usable arrivals=" + "; ".join(f"{x['address']}:{x['n']}" for x in e5) if e5 else "not measured", status(drift_ok, drift_ready), "E5 arrivals", "Keep the absolute target path as a feasibility candidate; repeat any motor lacking 100 usable arrivals."),
        ("Stall/contact detection is characterized", f"{len(stalls)} offline detector candidates; kernel flags observed={sum('stalled' in r.get('state_flags','') for r in tests['E7'])}", "INCONCLUSIVE" if tests['E7'] else "WAITING_FOR_PHYSICAL_FIXTURE", "E7 raw log plus E2/E6 controls; no independent contact timestamp" if tests['E7'] else "E7 not run: no short LEGO lever with fixed soft stop", "Validate thresholds against labelled contact and false-positive runs." if tests['E7'] else "Install the specified fixture; never create a stall with fingers."),
        ("Medium dynamics suit proportional gripper", f"E8 best RMSE={fmt(min([x['rmse'] for x in e8], default=math.nan))} counts; max duty below C1 start region", "NEEDS_RETEST_WITH_CONTROLLER_V2", "E8 plus C1", "Do not reject motor-side suitability before C5 applies V2 feed-forward."),
        ("run-direct crash behavior is known", f"{len(e9)} samples; baseline={any(r.get('fault') == 'baseline' for r in e9)}", status(bool(e9), bool(e9)), "E9 faults", "Never depend on controller teardown alone."),
        ("Safety heartbeat stops within configured bound", f"{len(e9_stop)} supervisor stops; max detection={fmt(max([r.get('detection_latency_us', math.nan)/1000 for r in e9_stop], default=math.nan))} ms", status(bool(e9_stop), bool(e9_stop)), "E9", "Select timeout from measured detection plus stopping travel."),
        ("Battery sensitivity is quantified", f"{len(battery)} grouped points; voltage range is narrow and test conditions are confounded", "INCONCLUSIVE", "E2/E4/E6 grouped by voltage", "Repeat only across naturally distinct voltage bins with comparable conditions; do not discharge solely for test."),
        ("Loaded arm behavior is resolved", "No gear train/load in current hardware", "INCONCLUSIVE", "bench scope", "Torque, gravity, backlash, loaded speed and four-motor test remain open."),
    ]
    for h in hypotheses:
        lines.append("| " + " | ".join(md_escape(x) for x in h) + " |")

    lines += ["", "## E1/E12 scheduler and sysfs timing", "", "`loop_dt` measures cadence; `work` measures the preceding tick's sysfs + buffered-logging execution time.", "",
              "| source CSV | run ID | test | mode | motors | rate | rows | duration s | motor address / driver | battery V | dt mean | dt p50 | dt p95 | dt p99 | dt max | work mean | work p50 | work p95 | work p99 | work max | missed | CPU % |",
              "|---|---|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in sorted(jit, key=lambda r: (r["test"], r["rate"], r["mode"], r["file"])):
        lines.append(f"| {x['file']} | {x['run_id']} | {x['test']} | {x['mode']} | {x['motor_count']} | {fmt(x['rate'],3)} | {x['rows']} | {fmt(x['duration_s'],3)} | {x['motors_seen']} | {x['battery_range']} | {fmt(x['mean'])} | {fmt(x['p50'])} | {fmt(x['p95'])} | {fmt(x['p99'])} | {fmt(x['max'])} | {fmt(x['work_mean'])} | {fmt(x['work_p50'])} | {fmt(x['work_p95'])} | {fmt(x['work_p99'])} | {fmt(x['work_max'])} | {x['missed']} | {fmt(x['cpu'])} |")
    if not jit: lines.append("| — | — | — | — | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
    logged = [x for x in jit if x["test"] == "E1" and x["mode"] == "persistent" and x["rate"] == 50]
    timing = [x for x in jit if x["test"] == "E1" and x["mode"] == "timing-only" and x["rate"] == 50]
    if logged and timing:
        lines += ["", f"Buffered telemetry/row-serialization impact at 50 Hz (work p99): {fmt(mean([x['work_p99'] for x in logged]) - mean([x['work_p99'] for x in timing]))} µs. `timing-only` still performs position/speed reads and duty writes but defers other telemetry and CSV row construction."]
    single = [x for x in jit if x["test"] == "E1" and x["mode"] == "persistent" and x["rate"] == 50 and x["motor_count"] == 1]
    dual = [x for x in jit if x["test"] == "E12" and x["rate"] == 50]
    if single and dual:
        increment = mean([x["work_mean"] for x in dual]) - mean([x["work_mean"] for x in single])
        lines += ["", f"Observed two-motor minus one-motor mean tick work: {fmt(increment)} µs. This is a cautious incremental-I/O estimate, not a four-motor guarantee."]

    lines += ["", "## E1_MINIMAL repeatability and candidate rate", "", "The control critical section contains only two position reads, two speed reads, minimal arithmetic, and two duty writes. CSV formatting and filesystem writes happen only after the control run.", "",
              "| rate Hz | runs | dt p50 mean us | worst dt p95 us | worst dt p99 us | worst dt max us | work p50 us | worst work p95 us | worst work p99 us | worst work max us | missed | CPU % | candidate |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for x in minimal_rates:
        lines.append(f"| {fmt(x['rate'],3)} | {x['runs']} | {fmt(x['p50'])} | {fmt(x['p95_worst'])} | {fmt(x['p99_worst'])} | {fmt(x['max_worst'])} | {fmt(x['work_p50'])} | {fmt(x['work_p95'])} | {fmt(x['work_p99'])} | {fmt(x['work_max'])} | {x['missed']} | {fmt(x['cpu'])} | {'YES' if x['candidate'] else 'NO'} |")
    if not minimal_rates:
        lines.append("| n/a | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | no data |")
    candidates = [x for x in minimal_rates if x['candidate']]
    if candidates:
        lines.append(f"- Selected conservative candidate from this data: {fmt(max(candidates, key=lambda item: item['rate'])['rate'],3)} Hz. This is conditional on all three stationary repeats; it is not a four-motor or loaded-arm guarantee.")
    elif minimal_rates:
        lines.append("- No tested rate met the stated three-repeat, no-missed-deadline criterion.")

    lines += ["", "## E1 persistent versus reopen: alternating repeatability", "", "Each rate is run persistent/reopen/persistent/reopen/persistent/reopen; summaries retain one distribution per run in the scheduler table above.", "",
              "| rate Hz | mode | completed runs | dt p50 us | dt p95 us | dt p99 us | worst dt max us | work p50 us | work p95 us | work p99 us | worst work max us | missed |",
              "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in alternating:
        lines.append(f"| {fmt(x['rate'],3)} | {x['mode']} | {x['runs']} | {fmt(x['dt_p50'])} | {fmt(x['dt_p95'])} | {fmt(x['dt_p99'])} | {fmt(x['dt_max'])} | {fmt(x['work_p50'])} | {fmt(x['work_p95'])} | {fmt(x['work_p99'])} | {fmt(x['work_max'])} | {x['missed']} |")
    if not alternating:
        lines.append("| n/a | n/a | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
    for rate in sorted({x['rate'] for x in alternating}):
        paired = {x['mode']: x for x in alternating if x['rate'] == rate}
        if paired.get('persistent') and paired.get('naive') and paired['persistent']['runs'] >= 3 and paired['naive']['runs'] >= 3:
            p, n = paired['persistent'], paired['naive']
            if p['work_p99'] < n['work_p99'] and p['dt_p99'] <= n['dt_p99']:
                verdict = "persistent is better in this three-run alternating sample"
            elif p['work_p99'] > n['work_p99'] and p['dt_p99'] >= n['dt_p99']:
                verdict = "reopen is better in this three-run alternating sample"
            else:
                verdict = "difference is inconclusive: the metrics disagree"
            lines.append(f"- {fmt(rate,3)} Hz: {verdict}.")

    lines += ["", "## E1.5 sysfs latency decomposition", "", "Every listed duration was captured around the individual operation in a stationary persistent-FD run.", "",
              "| source CSV | run ID | operation | n | mean us | p50 us | p95 us | p99 us | max us |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in sorted(operation_latency, key=lambda item: (item["file"], item["operation"])):
        lines.append(f"| {x['file']} | {x['run_id']} | {x['operation']} | {x['n']} | {fmt(x['mean'])} | {fmt(x['p50'])} | {fmt(x['p95'])} | {fmt(x['p99'])} | {fmt(x['max'])} |")
    if not operation_latency:
        lines.append("| - | - | not measured | 0 | n/a | n/a | n/a | n/a | n/a |")
    lines += ["", "| source CSV | dt p99 us | dt max us | measured tick-work p99 us | measured tick-work max us | tail ticks (>1.5 period) | max measured work in tail tick us |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for x in latency_attribution:
        lines.append(f"| {x['file']} | {fmt(x['dt_p99'])} | {fmt(x['dt_max'])} | {fmt(x['work_p99'])} | {fmt(x['work_max'])} | {x['tail_ticks']} | {fmt(x['tail_work_max'])} |")
    if not latency_attribution:
        lines.append("| - | n/a | n/a | n/a | n/a | 0 | n/a |")
    if latency_attribution:
        for x in latency_attribution:
            if x["dt_max"] > x["work_max"] + x["period"]:
                lines.append(f"- {x['file']}: the worst cadence gap exceeds the largest measured in-tick work by more than one nominal period; this is direct evidence of delay outside the measured sysfs/logging operations (sleep/scheduling deschedule), not an attribution to a specific sysfs call.")
            else:
                lines.append(f"- {x['file']}: worst cadence gap is comparable to measured in-tick work; inspect the operation table before attributing it to scheduling.")

    lines += ["", "## E2/E6 duty, speed and low-speed control", "", "| address | driver | duty % | mean speed | std | battery V | n |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for x in curve:
        lines.append(f"| {x['address']} | {x['driver']} | {fmt(x['duty'],0)} | {fmt(x['speed'])} | {fmt(x['std'])} | {fmt(x['voltage'],3)} | {x['n']} |")
    if not curve: lines.append("| — | — | — | not measured | — | — | 0 |")
    if low_curve:
        lines += ["", "E6 near-threshold sweep:", "", "| address | duty % | mean speed | speed std | n |", "|---|---:|---:|---:|---:|"]
        for x in low_curve:
            lines.append(f"| {x['address']} | {fmt(x['duty'],0)} | {fmt(x['speed'])} | {fmt(x['std'])} | {x['n']} |")
    lines += ["", "Stable-moving direction matching excludes failed-start/noisy curve points.",
              f"Excluded E2 points: {len(curve) - len(stable_curve)} of {len(curve)}.",
              "", "## C1 start/sustain repeatability", "",
              "| address | duty % | trials | P(start <=100ms) | <=200ms | <=300ms | <=500ms | steady speed | battery V |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in c1:
        lines.append(f"| {x['address']} | {fmt(x['duty'],0)} | {x['trials']} | {fmt(x['p100'],3)} | {fmt(x['p200'],3)} | {fmt(x['p300'],3)} | {fmt(x['p500'],3)} | {fmt(x['steady_speed'])} | {fmt(x['battery'],3)} |")
    if not c1: lines.append("| — | — | 0 | n/a | n/a | n/a | n/a | n/a | n/a |")
    if c1_limits:
        lines += ["", "| motor/direction | START_DUTY_99 | SUSTAIN_DUTY |", "|---|---:|---:|"]
        for (address, sign), x in sorted(c1_limits.items()):
            lines.append(f"| {address} {'+' if sign > 0 else '-'} | {fmt(x['start99'],0)} | {fmt(x['sustain'],0)} |")
    max_speed_by_address = {str(m.get("address", "")): number(m.get("max_speed")) for m in motors}
    measured_peaks = {address: max(abs(x["speed"]) for x in curve if x["address"] == address) for address in {x["address"] for x in curve}}
    if measured_peaks:
        lines += ["", "Measured peak relation to sysfs `max_speed`:", ""]
        for address, peak in sorted(measured_peaks.items()):
            configured = max_speed_by_address.get(address, math.nan)
            relation = 100 * peak / configured if math.isfinite(configured) and configured else math.nan
            lines.append(f"- {address}: {fmt(peak)} counts/s = {fmt(relation)}% of `max_speed` ({fmt(configured,0)}).")
    if plots:
        lines += [""] + [f"![speed/duty plot]({name})" for name in plots]

    lines += ["", "## Controller and built-in-reference results", "", "| test/file | address | mode | RMSE | p95 error | steady error | arrival rate | max duty | rise ms | settle ms | overshoot % | smoothness |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for x in e4 + e8 + c2 + c3 + c4_tracking + c5:
        lines.append(f"| {x['file']} | {x['address']} | {x['mode']} | {fmt(x['rmse'])} | {fmt(x['p95_error'])} | {fmt(x['steady'])} | {fmt(x['arrival_rate'])} | {fmt(x['max_duty'])} | {fmt(x['rise_ms'])} | {fmt(x['settling_ms'])} | {fmt(x['overshoot'])} | {fmt(x['smoothness'])} |")
    for x in e5:
        lines.append(f"| E5 drift ({x['file']}) | {x['address']} | absolute targets | — | {fmt(x['mean'])} ± {fmt(x['std'])} | — | — | — | — | — | — | trend {fmt(x['slope'],4)}/cycle | — |")
    for x in c4:
        lines.append(f"| C4 V2 drift ({x['file']}) | {x['address']} | accepted arrivals only, n={x['n']} | — | {fmt(x['mean'])} +/- {fmt(x['std'])} | — | — | — | — | — | — | trend {fmt(x['slope'],4)}/arrival | — |")
    if not (e4 or e5 or e8): lines.append("| — | — | — | not measured | — | — | — | — | — | — | — | — | — |")
    medium_cpr = next((m.get("count_per_rot", 0) for m in motors if "medium" in m.get("driver_name", "").lower() or str(m.get("address", "")).lower().endswith("outd")), 0)
    medium_speed = max([x["speed_max"] for x in e8], default=math.nan)
    if medium_cpr and math.isfinite(medium_speed) and medium_speed > 0:
        lines += ["", "Hypothetical 90° output stroke estimates (not measured gripper results):", "", "| reduction | estimated time at measured peak motor speed |", "|---:|---:|"]
        for ratio in (1, 3, 5, 9):
            seconds = medium_cpr * ratio / 4 / medium_speed
            lines.append(f"| {ratio}:1 | {seconds:.3f} s |")

    lines += ["", "## E3 acceleration and stopping", "", "| file/address | phase | mode/duty | t10 ms | t50 ms | t90 ms | accel counts/s² | overshoot % | stop ms | travel counts |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in dynamics:
        lines.append(f"| {x['file']} / {x['address']} | {x['kind']} | {x['mode']} | {fmt(x['t10'])} | {fmt(x['t50'])} | {fmt(x['t90'])} | {fmt(x['acceleration'])} | {fmt(x['overshoot'])} | {fmt(x['stop_ms'])} | {fmt(x['travel'])} |")
    if not dynamics: lines.append("| — | — | — | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")

    lines += ["", "## E10 local emergency path", "", "| file/address | trigger-to-sysfs-write us | speed-to-zero ms | encoder travel |",
              "|---|---:|---:|---:|"]
    for x in emergency:
        lines.append(f"| {x['file']} / {x['address']} | {fmt(x['write_us'])} | {fmt(x['zero_ms'])} | {fmt(x['travel'])} |")
    if not emergency: lines.append("| — | n/a | n/a | n/a |")

    lines += ["", "## C7 moving local stop", "", "| file/address | pre-trigger speed | trigger-to-sysfs-write us | speed-to-zero ms | encoder travel |",
              "|---|---:|---:|---:|---:|"]
    for x in moving_stops:
        lines.append(f"| {x['file']} / {x['address']} | {fmt(x['pre_speed'])} | {fmt(x['write_us'])} | {fmt(x['zero_ms'])} | {fmt(x['travel'])} |")
    if not moving_stops: lines.append("| — | n/a | n/a | n/a | n/a |")

    lines += ["", "## E9 process-fault safety", "", "| file | fault | address | heartbeat age ms | injection-to-detection ms | stop write us | travel at stop command | total post-fault travel |",
              "|---|---|---|---:|---:|---:|---:|---:|"]
    for x in crashes:
        lines.append(f"| {x['file']} | {x['fault']} | {x['address']} | {fmt(x['heartbeat_age_ms'])} | {fmt(x['detection_ms'])} | {fmt(x['write_us'])} | {fmt(x['travel_to_stop'])} | {fmt(x['travel_total'])} |")
    if not crashes: lines.append("| — | — | — | n/a | n/a | n/a | n/a | n/a |")

    lines += ["", "## C6 repeated safety-supervisor statistics", "", "| file | fault | address | n | detection p50/p95/p99/max ms | write p95 us | travel p95/max |",
              "|---|---|---|---:|---|---:|---:|"]
    for x in c6:
        detection = "/".join(fmt(x[key]) for key in ("detection_p50", "detection_p95", "detection_p99", "detection_max"))
        lines.append(f"| {x['file']} | {x['fault']} | {x['address']} | {x['n']} | {detection} | {fmt(x['write_p95'])} | {fmt(x['travel_p95'])}/{fmt(x['travel_max'])} |")
    if not c6: lines.append("| — | — | — | 0 | n/a | n/a | n/a |")

    lines += ["", "## E7 offline contact detector candidates", "", "These candidates are evaluated from one raw run. Without an independently labelled physical-contact timestamp and non-contact controls, detection quality remains inconclusive.", "",
              "| stall detections | control false positives | mean from run start ms | DUTY_MIN | SPEED_MAX | T ms |", "|---:|---:|---:|---:|---:|---:|"]
    for count, false_positives, latency, duty_min, speed_max, duration in stalls:
        lines.append(f"| {count} | {false_positives} | {fmt(latency)} | {duty_min} | {speed_max} | {duration} |")
    if not stalls: lines.append("| 0 | 0 | n/a | n/a | n/a | n/a |")

    lines += ["", "## E11 battery-voltage sensitivity", "", "Runs are merged by test, motor and condition. A slope is emitted only when at least two voltage bins (0.01 V) exist.", "",
              "| test | address | condition | metric | slope | voltage range V |", "|---|---|---|---|---:|---:|"]
    for x in battery:
        lines.append(f"| {x['test']} | {x['address']} | {x['condition']} | {x['metric']} | {fmt(x['slope'],4)} | {fmt(x['vmin'],3)}–{fmt(x['vmax'],3)} |")
    if not battery: lines.append("| — | — | — | not enough voltage variation | n/a | n/a |")

    lines += ["", "## Required architectural answers", ""]
    for index, h in enumerate(hypotheses, 1):
        lines.append(f"{index}. **{h[0]}:** {h[1]} — **{h[2]}**. {h[4]}")
    lines += ["", "## Measurement gaps", "", "- E0 manual one-revolution/reset results must be interpreted against the physical action.",
              "- E3 detailed 10/50/90 rise, overshoot and per-action stop travel require complete step/stop logs; raw samples are retained for deeper fitting.",
              "- E7 cannot establish false-positive rates without labelled free-start and low-duty control intervals.",
              "- E8 estimates motor-side full-stroke behavior only; no measured gripper exists.",
              "- E12 with two motors permits a cautious incremental-I/O estimate, not a guarantee for four motors.",
              "- No free-motor result closes questions involving gearing, load, gravity, backlash or structural compliance.", ""]
    lines += ["## Current decision matrix", "",
              "| question | measured | decision | confidence | run IDs |",
              "|---|---|---|---|---|"]
    if current_candidate:
        lines.append(f"| Current free two-motor loop rate | 50 Hz E1_MINIMAL: 3 x 120 s, p99 <= {fmt(current_candidate['p99_worst'])} us, max <= {fmt(current_candidate['max_worst'])} us, 0 misses | CONFIRMED_AS_CURRENT_CANDIDATE: 50 Hz minimal fast loop | medium | 20260824T061932Z repeats 1-3 |")
    else:
        lines.append("| Current free two-motor loop rate | no qualifying three-repeat minimal test | INCONCLUSIVE | low | n/a |")
    lines.append(f"| Persistent FD | alternating E1 at 25 and 50 Hz, x3 per mode; p99 work and misses lower for persistent | {'CONFIRMED' if persistent_confirmed else 'INCONCLUSIVE'} for current EV3/free two-motor scope | medium | e1alt_25hz_20260824T065803Z; e1alt_50hz_20260824T071034Z |")
    lines.append("| Tail-latency mitigation | E1.5 measures costly battery, diagnostic, enqueue, and flush work; E1_MINIMAL removes them from fast loop | CONFIRMED: keep those outside fast critical section | medium-high | 20260824T061706Z; 20260824T061932Z |")
    lines.append(f"| Free duty/speed and low-duty floor | Medium floor {fmt(floor.get('ev3-ports:outA', math.nan),0)}%; Large floor {fmt(floor.get('ev3-ports:outB', math.nan),0)}% | CONFIRMED free-motor only | medium | e2_retry_20260824T111500Z; e6_20260824T112100Z |")
    lines.append(f"| Stop behaviour / local stop path | E3 coast/brake/hold plus E10 sysfs write {fmt(max([x['write_us'] for x in emergency], default=math.nan),0)} us worst | CONFIRMED free-motor only | medium | e3_20260824T112700Z; e10_20260824T115600Z |")
    c4_rates = "; ".join(f"{x['address']}={fmt(100*x['arrival_rate'],1)}%" for x in c4_tracking)
    c4_ok = len(c4_tracking) >= 2 and all(x['arrival_rate'] >= .95 for x in c4_tracking)
    lines.append(f"| run-direct P/PD V2 | C2 used C1 static feed-forward; C4 100-cycle arrival rates: {c4_rates} | {'CONFIRMED' if c4_ok else 'NEEDS_RETUNE; NOT REJECTED'} | medium | c2_20260824T122000Z; c4_20260824T124000Z |")
    lines.append(f"| Absolute target drift | C4 accepted arrivals only: " + "; ".join(f"{x['address']}={x['n']}" for x in c4) + " | CONTROLLER_FAILURE_BEFORE_DRIFT_ASSESSMENT | medium | c4_20260824T124000Z |")
    lines.append(f"| Medium proportional trajectory | C5 V2 p95 error at 2 s strokes: " + "; ".join(f"{x['mode']}={fmt(x['p95_error'])}" for x in c5 if 'stroke2' in x['file']) + " | MEASURED_MOTOR_ONLY; RETEST_AFTER_GEARING | medium | c5_20260824T130000Z |")
    lines.append(f"| Crash supervisor | C6 has " + "; ".join(f"{x['fault']} n={x['n']} p99={fmt(x['detection_p99'])} ms" for x in c6 if x['fault'] != 'baseline') + " | CONFIRMED free Large/current 100 ms heartbeat scope | medium | c6_20260824T130500Z |")
    lines.append("| Stall/contact | no controlled fixture run | WAITING_FOR_PHYSICAL_FIXTURE | n/a | n/a |")
    lines += ["", "## CONFIRMED ARCHITECTURE", "", "- 50 Hz is the current candidate only for the production-like free two-motor minimal loop.", "- Persistent FD is preferred for the current EV3/free two-motor scope.", "- Battery, diagnostics, CSV, filesystem logging, and telemetry do not belong in the fast control critical section.", "- C6 repeatedly confirmed supervisor detection for SIGKILL/SIGSTOP/SIGTERM/abort on the free Large motor; loaded travel is not confirmed.", "",
              "## MEASURED TUNING SEEDS", "", "- C1 99% start seeds: Medium +/−24%; Large +11%/−16%. Use the conservative Large seed 16% only as a free-bench starting point.", "- V2 gains tested: Kp=0.35, Kd=0.006, limit=65%; these are not production gains because C4 did not meet arrival acceptance.", "",
              "## RETEST AFTER GEARING", "", "- Medium C5 V2 trajectory and all controller/gripper claims with the actual linkage, inertia, backlash and gravity.", "",
              "## RETEST AFTER LOAD", "", "- Duty/speed, acceleration, stopping travel, C4 arrival/drift, and crash/safety travel.", "",
              "## RETEST WITH 4 MOTORS", "", "- Four-motor scheduler margin and I/O scaling.", "",
              "## RETEST WITH WIFI", "", "- Network telemetry impact and reconnect behaviour; Wi-Fi is absent on this bench.", ""]
    active_d8 = coordinated["D8"]
    lines += ["", "## Coordinated two-motor validation", "", "| test | motor | RMSE | p95 error | dt p95/p99/max us | work p95/p99/max us | misses | battery V |",
              "|---|---|---:|---:|---|---|---:|---|"]
    for test in ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"):
        for x in coordinated[test]:
            lines.append(f"| {test} | {x['address']} | {fmt(x['rmse'])} | {fmt(x['p95_error'])} | {fmt(x['dt_p95'])}/{fmt(x['dt_p99'])}/{fmt(x['dt_max'])} | {fmt(x['work_p95'])}/{fmt(x['work_p99'])}/{fmt(x['work_max'])} | {x['missed']} | {fmt(x['battery_min'],3)}-{fmt(x['battery_max'],3)} |")
    if not any(coordinated.values()): lines.append("| D1-D8 | — | not measured | — | — | — | — | — |")
    output.write_text("\n".join(lines), encoding="utf-8")
    return {"jitter": jit, "curve": curve, "floor": floor, "e4": e4, "e5": e5, "c2": c2, "c3": c3, "c4": c4, "c4_tracking": c4_tracking, "c5": c5,
            "e9_stop": e9_stop, "dynamics": dynamics, "operation_latency": operation_latency,
            "latency_attribution": latency_attribution, "minimal_rates": minimal_rates, "alternating": alternating,
            "e8": e8, "floor": floor, "dynamics": dynamics, "emergency": emergency, "moving_stops": moving_stops,
            "crashes": crashes, "c6": c6, "c1_limits": c1_limits, "coordinated": coordinated, "d1": d1, "d2": d2}


def make_legacy_recommendations(metrics, output):
    lines = ["# EV3 architecture recommendations", "", "These are measured-bench recommendations only; they do not modify the production specification. Each decision identifies its evidence and confidence.", ""]
    jit = metrics["jitter"]
    best50 = [x for x in jit if x["test"] == "E1" and x["rate"] == 50 and x["mode"] == "persistent"]
    if best50:
        missed, p99, maximum = sum(x["missed"] for x in best50), mean([x["p99"] for x in best50]), max(x["max"] for x in best50)
        if missed == 0 and maximum < 20_000:
            lines.append(f"- Keep 50 Hz as the initial local-loop target for this two-motor/free-bench scope (p99 {fmt(p99)} µs, max {fmt(maximum)} µs, no >1.5-period misses). Re-test four motors before production commitment.")
        else:
            lines.append(f"- Do not yet commit to 50 Hz: observed p99 {fmt(p99)} µs, max {fmt(maximum)} µs, missed deadlines {missed}. Investigate load and scheduling first.")
    else:
        lines.append("- Loop rate remains open: no complete persistent-FD 50 Hz run was found.")
    naive = [x for x in jit if x["test"] == "E1" and x["rate"] == 50 and x["mode"] == "naive"]
    if best50 and naive:
        if mean([x["work_p99"] for x in best50]) < mean([x["work_p99"] for x in naive]):
            lines.append("- Use a persistent-FD sysfs wrapper; paired E1 tick-work p99 is lower than reopen/read/close.")
        else:
            lines.append("- Persistent FD was not faster at p99 in this capture; inspect run pairing and repeat before choosing the wrapper solely for speed.")
    floor = metrics["floor"]
    for address, duty in floor.items():
        if math.isfinite(duty): lines.append(f"- For {address}, start later homing/contact experiments above the measured free-run floor of {duty:.0f}% plus an explicit safety margin; remeasure under load.")
    e4 = metrics["e4"]
    if e4:
        best = min(e4, key=lambda x: x["rmse"])
        lines.append(f"- Retain `run-direct` with a local P/PD controller as a feasibility candidate: best free-motor run was {best['file']} at RMSE {fmt(best['rmse'])} counts. Treat its gains as seed values only.")
    stops = metrics["e9_stop"]
    if stops:
        ages = finite([r.get("heartbeat_age_us", math.nan) / 1000 for r in stops])
        heartbeat_age = max(ages) if ages else math.nan
        scheduler_margin = max([x["p99"] / 1000 for x in best50], default=0)
        if math.isfinite(heartbeat_age):
            candidate = math.ceil((heartbeat_age + scheduler_margin) / 10) * 10
            lines.append(f"- Keep a separate safety supervisor. Worst heartbeat age at detection was {heartbeat_age:.2f} ms and 50 Hz p99 scheduling margin was {scheduler_margin:.2f} ms; {candidate:.0f} ms is a bench-derived candidate timeout, pending loaded stop-travel validation.")
        else:
            lines.append("- Keep a separate safety supervisor, but repeat E9 with the current log schema before selecting a heartbeat timeout.")
    else:
        lines.append("- Safety heartbeat timeout remains open. A separate supervisor is still a safety hypothesis, not a measured production setting.")
    stop_modes = [x for x in metrics["dynamics"] if x["kind"] == "stop" and math.isfinite(x["travel"])]
    if stop_modes:
        by_mode = defaultdict(list)
        for x in stop_modes: by_mode[x["mode"]].append(abs(x["travel"]))
        best_mode = min(by_mode, key=lambda mode: mean(by_mode[mode]))
        lines.append(f"- Prefer `{best_mode}` for the next free-motor safety prototype: it had the lowest mean post-command encoder travel ({mean(by_mode[best_mode]):.2f} counts). Re-evaluate under load; `hold` is not accepted automatically.")
    rejected = []
    if best50 and (sum(x["missed"] for x in best50) or max(x["max"] for x in best50) >= 20_000):
        rejected.append("The assumption that a 50 Hz loop has comfortable worst-case margin was rejected by E1.")
    if best50 and naive and mean([x["work_p99"] for x in best50]) >= mean([x["work_p99"] for x in naive]):
        rejected.append("The assumption that persistent FDs necessarily improve p99 was rejected in this capture.")
    if metrics["e5"] and max(abs(x["slope"]) for x in metrics["e5"]) > .05:
        rejected.append("The no-drift absolute-target hypothesis was rejected; inspect local state before production use.")
    lines += ["", "## Rejected assumptions", ""]
    lines += [f"- {item}" for item in rejected] if rejected else ["- None can be rejected without additional measured evidence."]
    lines += ["", "## Mandatory remeasurement after mechanics/full hardware", "", "- Four-motor 50 Hz scheduler/I/O stress.",
              "- Loaded duty/speed curves, thermal behavior and battery sensitivity.", "- Gear backlash, compliance, gravity feed-forward and homing repeatability.",
              "- Loaded emergency-stop travel and watchdog timing.", "- Real gripper contact labels, false positives and proportional full-stroke response.", ""]
    output.write_text("\n".join(lines), encoding="utf-8")


def make_previous_recommendations(metrics, output):
    """Write only decisions that can be traced to an actual captured run."""
    jit = metrics["jitter"]
    persistent_50 = [x for x in jit if x["test"] in ("E1", "E12") and x["rate"] == 50 and x["mode"] == "persistent"]
    naive_50 = [x for x in jit if x["test"] == "E1" and x["rate"] == 50 and x["mode"] == "naive"]
    lines = ["# EV3 architecture recommendations", "",
             "This file does not modify the production specification. It contains only recommendations traceable to captured free-bench measurements.", ""]

    if persistent_50:
        worst_p99 = max(x["p99"] for x in persistent_50)
        worst_max = max(x["max"] for x in persistent_50)
        missed = sum(x["missed"] for x in persistent_50)
        evidence = ", ".join(f"{x['file']} (run {x['run_id']})" for x in persistent_50)
        lines += ["## Motor loop", "",
                  f"MEASURED: persistent 50 Hz two-motor runs had worst p99={fmt(worst_p99)} us, worst max={fmt(worst_max)} us, and {missed} missed periods.",
                  "RECOMMENDED: do not commit to a 50 Hz production loop yet; reduce tail latency and remeasure with the intended mechanics and four motors.",
                  "CONFIDENCE: high for the stated free-bench runs; low for extrapolation to the full robot.",
                  f"EVIDENCE: {evidence}.", ""]
    else:
        lines += ["## Motor loop", "", "MEASURED: no complete persistent 50 Hz run.", "RECOMMENDED: leave the control-rate decision open.", "CONFIDENCE: low.", "EVIDENCE: none.", ""]

    if persistent_50 and naive_50:
        p = next(x for x in persistent_50 if x["test"] == "E1")
        n = naive_50[0]
        lines += ["## Sysfs access strategy", "",
                  f"MEASURED: at E1 50 Hz, persistent mean work={fmt(p['work_mean'])} us vs reopen={fmt(n['work_mean'])} us; persistent p99={fmt(p['work_p99'])} us vs reopen={fmt(n['work_p99'])} us.",
                  "RECOMMENDED: keep both implementations available for now; repeat paired runs before selecting one for performance. Persistent FD remains functionally useful, but its tail-time advantage is not established.",
                  "CONFIDENCE: low (one paired capture, conflicting mean and p99 metrics).",
                  f"EVIDENCE: {p['file']} (run {p['run_id']}), {n['file']} (run {n['run_id']}).", ""]

    lines += ["## Safety and mechanics", "",
              "MEASURED: no free-spin, loaded, crash-safety, stall-fixture, or gear-train measurements have been captured in this data set.",
              "RECOMMENDED: keep motor-motion decisions, watchdog timeout, stop-action choice, duty floor, controller gains, and gripper/arm claims open until their guarded tests are run.",
              "CONFIDENCE: high that these questions remain unmeasured.",
              "EVIDENCE: captured inventory contains only E_SMOKE, E1, and stationary E12 rows.", "",
              "## Required later remeasurement", "",
              "- Four-motor 50 Hz scheduler/I/O stress.",
              "- Free and loaded duty/speed curves, acceleration, and stop travel.",
              "- Gear backlash, compliance, gravity compensation, and homing repeatability.",
              "- Emergency-stop travel, heartbeat timing, and labelled stall/contact behavior.",
              "- Real gripper mechanism response; free-medium results cannot establish linkage performance.", ""]
    output.write_text("\n".join(lines), encoding="utf-8")


def make_recommendations(metrics, output):
    """Recommendations limited to the complete, run-addressable scheduler evidence."""
    minimal = metrics["minimal_rates"]
    alternating = metrics["alternating"]
    ops = metrics["operation_latency"]
    attribution = metrics["latency_attribution"]
    candidates = [x for x in minimal if x["candidate"]]
    candidate = max(candidates, key=lambda x: x["rate"]) if candidates else None
    by_rate_mode = {(x["rate"], x["mode"]): x for x in alternating}
    lines = ["# EV3 architecture recommendations", "",
             "This file does not modify PHANTOM_SPECIFICATION. Every recommendation below is traceable to captured free-bench rows.", ""]

    if candidate:
        lines += ["## 1. Motor loop rate", "",
                  f"MEASURED: E1_MINIMAL {fmt(candidate['rate'],3)} Hz completed {candidate['runs']} stationary runs with p99 <= {fmt(candidate['p99_worst'])} us, max <= {fmt(candidate['max_worst'])} us, and {candidate['missed']} missed periods.",
                  f"RECOMMENDED: use {fmt(candidate['rate'],3)} Hz as the present free-bench candidate rate, with telemetry/logging outside the control critical section.",
                  "CONFIDENCE: medium: three two-motor stationary repeats; untested with mechanics, load, or four motors.",
                  "EVIDENCE: E1_MINIMAL run ID 20260824T061932Z, repeats 1-3 at the listed rate.", ""]
    else:
        lines += ["## 1. Motor loop rate", "", "MEASURED: no tested minimal-loop rate passed three repeats.", "RECOMMENDED: leave loop rate open.", "CONFIDENCE: low.", "EVIDENCE: E1_MINIMAL inventory.", ""]

    persistent_lines = []
    for rate in (25.0, 50.0):
        p, n = by_rate_mode.get((rate, "persistent")), by_rate_mode.get((rate, "naive"))
        if p and n and p["runs"] >= 3 and n["runs"] >= 3:
            persistent_lines.append(f"{fmt(rate,0)} Hz: persistent work p99={fmt(p['work_p99'])} us vs reopen={fmt(n['work_p99'])} us; misses={p['missed']} vs {n['missed']}")
    if persistent_lines:
        evidence = "; ".join(persistent_lines)
        lines += ["## 2. Persistent FD", "", f"MEASURED: {evidence}.",
                  "RECOMMENDED: use persistent FDs for the motor wrapper; they improved p99 work time and missed-period count in both alternating three-run samples.",
                  "CONFIDENCE: medium for this EV3/free two-motor scope.",
                  "EVIDENCE: e1alt_25hz_20260824T065803Z and e1alt_50hz_20260824T071034Z, persistent/reopen alternating runs 1-6.", ""]

    op_by_name = {x["operation"]: x for x in ops}
    flush = op_by_name.get("logger_flush_write")
    battery = op_by_name.get("battery_read")
    enqueue = op_by_name.get("logger_enqueue")
    if flush and battery and enqueue and attribution:
        attr = attribution[0]
        lines += ["## 3. Worst-case latency cause", "",
                  f"MEASURED: in E1.5, logger flush p99={fmt(flush['p99'])} us, logger enqueue p99={fmt(enqueue['p99'])} us, battery-read p99={fmt(battery['p99'])} us, while diagnostic tick-work p99={fmt(attr['work_p99'])} us and dt p99={fmt(attr['dt_p99'])} us.",
                  "RECOMMENDED: keep battery reads, state/duty diagnostics, CSV formatting, and filesystem flushing outside the fast loop. E1.5 does not establish a separate scheduling/descheduling cause because its dt tail was comparable to measured in-tick work.",
                  "CONFIDENCE: high for the measured diagnostic workload; medium for extrapolation to the minimal loop.",
                  f"EVIDENCE: {flush['file']} (run {flush['run_id']}).", ""]

    e4 = metrics["e4"]
    e5 = metrics["e5"]
    e8 = metrics["e8"]
    c2 = metrics["c2"]
    c4_tracking = metrics["c4_tracking"]
    c5 = metrics["c5"]
    c6 = metrics["c6"]
    c1_limits = metrics["c1_limits"]
    floor = metrics["floor"]
    emergency = metrics["emergency"]
    moving_stops = metrics["moving_stops"]
    crashes = metrics["crashes"]
    lines += ["## 4. Telemetry and logging placement", "",
              "MEASURED: E1_MINIMAL excludes battery reads, CSV formatting, filesystem logging, and diagnostics from the critical section; its 50 Hz three-run sample had zero missed periods. E1.5 measures costly logger and battery operations when they are included.",
              "RECOMMENDED: retain the preallocated post-test buffer strategy (or a separately measured writer) and prohibit telemetry/file I/O in the control critical section.",
              "CONFIDENCE: medium-high for stationary scheduling; no claim for network telemetry or loaded mechanics.",
              "EVIDENCE: E1_MINIMAL run ID 20260824T061932Z; E1.5 run ID 20260824T061706Z.", "",
              "## 5. run-direct local controller", "",
              f"MEASURED: C2 re-tested P/PD with C1 static feed-forward (best RMSE={fmt(min([x['rmse'] for x in c2], default=math.nan))} counts). In C4, 100 ±90-degree cycles produced arrival rates " + "; ".join(f"{x['address']}={fmt(100*x['arrival_rate'],1)}%" for x in c4_tracking) + ".",
              "RECOMMENDED: do not reject run-direct based on E4/E8 dead-zone-limited gains. The present V2 tuning is NOT CONFIRMED because C4 did not reach 95% arrival on both motors; re-tune with the real mechanism.",
              "CONFIDENCE: medium for this precise free-motor failure result.",
              "EVIDENCE: C1 c1_20260824T120500Z; C2 c2_20260824T122000Z; C4 c4_20260824T124000Z.", "",
              "## 6. Separate safety supervisor", "",
              "MEASURED: C6 performed n=10 each for SIGKILL, SIGSTOP, SIGTERM, abort, and the no-supervisor external-watchdog baseline on free Large.",
              "RECOMMENDED: retain a separate heartbeat supervisor. Its fault detection is repeatably measured; loaded stopping travel remains unmeasured.",
              "CONFIDENCE: medium for this free Large/current 100 ms heartbeat scope.",
              "EVIDENCE: c6_20260824T130500Z plus c6 retry/baseline raw rows.", "",
              "## 7. Medium motor-side proportional gripper", "",
              f"MEASURED: C5 V2 2-second sine/triangle strokes yielded p95 position error " + "; ".join(f"{x['mode']}={fmt(x['p95_error'])}" for x in c5 if 'stroke2' in x['file']) + ".",
              "RECOMMENDED: this is a measured motor-only trajectory result, not gripper confirmation. Retest after gearing/linkage/backlash/gravity are present.",
              "CONFIDENCE: medium for free Medium only.",
              "EVIDENCE: c5_20260824T130000Z.", "",
              "## 8. Measured tuning seeds", "",
              "MEASURED: C1 99% start/sustain thresholds: " + "; ".join(f"{address} {'+' if sign > 0 else '-'} start99={fmt(v['start99'],0)}%, sustain={fmt(v['sustain'],0)}%" for (address, sign), v in sorted(c1_limits.items())) + ".",
              "RECOMMENDED: use only the conservative free-shaft seeds (Medium 24%; Large 16%) for initial V2 friction compensation; do not freeze them as loaded thresholds.",
              "EVIDENCE: c1_20260824T120500Z, 10 randomized trials per duty/direction.", "",
              "## 9. Still requires ready mechanics", "",
              "- C4 arrival/drift after controller retuning with actual gearing/load.",
              "- Loaded duty/speed, acceleration, stopping travel, backlash, compliance, gravity, and thermal behavior.",
              "- Real gripper linkage/contact behaviour and labelled stall controls (E7).",
              "- Loaded emergency stop travel and heartbeat timeout validation; four-motor and Wi-Fi remeasurement.", ""]
    coordinated = metrics.get("coordinated", {})
    expected = {"D1": 90, "D2": 20, "D3": 80, "D4": 15, "D5": 25, "D6": 25, "D7": 1, "D8": 3}
    lines += ["## Coordinated two-motor evidence", ""]
    for test in ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"):
        records = coordinated.get(test, [])
        files = len(records) // 2
        status_text = "complete" if files >= expected[test] else f"partial {files}/{expected[test]}"
        lines.append(f"- {test}: {status_text}; see `COORDINATED_TWO_MOTOR_VALIDATION.md`. Do not generalize any partial protocol to production.")
    output.write_text("\n".join(lines), encoding="utf-8")


def make_coordinated_report(rows, output):
    coordinated={test: dual_timing(rows,test) for test in ("D1","D2","D3","D4","D5","D6","D7","D8")}
    d1=d1_effect(rows); d2=d2_transients(rows); d5=p2p_summary(rows,"D5"); d6=p2p_summary(rows,"D6")
    lines=["# Coordinated two-motor validation", "", "All conclusions are limited to free Medium outA + Large outB at 50 Hz persistent FD. Motor results are intentionally separate.", "",
           "| TEST | RESULT | VERDICT | CONFIDENCE | RUN_IDS | ARCHITECTURAL_IMPLICATION |", "|---|---|---|---|---|---|"]
    def ids(test):
        values = sorted({x["run_id"] for x in coordinated[test]})
        if len(values) <= 3:
            return ", ".join(values) or "n/a"
        return ", ".join(values[:2]) + f" (+{len(values) - 2} more; raw filenames)"
    expected_files={"D1":90,"D2":20,"D3":80,"D4":15,"D5":25,"D6":25,"D7":1,"D8":3}
    def timing(test):
        values=coordinated[test]
        parts=[]
        for address in sorted({x['address'] for x in values}):
            xs=[x for x in values if x['address']==address]
            parts.append(f"{address}: dt p99<= {fmt(max(x['dt_p99'] for x in xs))}us, misses={sum(x['missed'] for x in xs)}")
        suffix="" if len(values)>=expected_files[test]*2 else f"; PARTIAL {len(values)//2}/{expected_files[test]} files"
        return "; ".join(parts)+suffix if parts else "no raw rows"
    def verdict(test): return "MEASURED" if len(coordinated[test])>=expected_files[test]*2 else "PARTIAL_OR_NOT_MEASURED"
    single={(x["address"],x["duty"]):x["speed"] for x in d1 if x["other"]==0}
    drops=[]
    for x in d1:
        if x["duty"] > 0 and x["other"] > 0 and (x["address"],x["duty"]) in single and single[(x["address"],x["duty"])]>0:
            drops.append(f"{x['address']} duty {x['duty']}: {100*(single[(x['address'],x['duty'])]-x['speed'])/single[(x['address'],x['duty'])]:.1f}%")
    lines.append(f"| D1 simultaneous free run | speed drop vs single: {'; '.join(drops) or 'not available'}; {timing('D1')} | {verdict('D1')} | medium | {ids('D1')} | Separates electrical/motor interaction from loop timing. |")
    delta=max([abs(x['delta']) for x in d2],default=math.nan)
    lines.append(f"| D2 staggered start/stop | max other-motor delta={fmt(delta)} counts/s; {timing('D2')} | {verdict('D2')} | medium | {ids('D2')} | Start/reverse transients must be considered in multi-axis control. |")
    lines.append(f"| D3 simultaneous reversal | {timing('D3')} | {verdict('D3')} | medium | {ids('D3')} | Ramp reversal is evaluated separately from point-arrival tuning. |")
    lines.append(f"| D4 continuous trajectories | {timing('D4')} | {verdict('D4')} | medium | {ids('D4')} | Continuous streams are judged by tracking, not discrete arrival rate. |")
    for name, values in (("D5 custom synchronized P2P",d5),("D6 built-in baseline",d6)):
        arrival=mean([x['arrival_rate'] for x in values]); skew=percentile([x['skew_ms'] for x in values],.95)
        test=name[:2]
        lines.append(f"| {name} | arrival-axis rate={fmt(100*arrival)}%; p95 skew={fmt(skew)} ms; {timing(test)} | {verdict(test)} | medium | {ids(test)} | Compare planner/controller behavior without conflating the two. |")
    d7_events=sum(r.get("event")=="target_replaced" for r in rows if r["test_id"].upper()=="D7")
    lines.append(f"| D7 latest-target-wins | target replacements logged={d7_events}; {timing('D7')} | {verdict('D7') if d7_events else 'NOT_MEASURED'} | medium | {ids('D7')} | New target replaces the previous reference; no waypoint queue is used. |")
    d8=coordinated["D8"]; misses=sum(x['missed'] for x in d8)
    lines.append(f"| D8 active 50 Hz loop | {timing('D8')} | {'CONFIRMED_FREE_TWO_MOTOR' if len(d8) >= expected_files['D8']*2 and misses==0 else 'PARTIAL_OR_NOT_MEASURED'} | medium | {ids('D8')} | Direct evidence for active two-controller loop only; re-test with mechanics/4 motors/Wi-Fi. |")
    output.write_text("\n".join(lines)+"\n",encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path, help="results/ev3/raw directory")
    parser.add_argument("--output", type=Path, help="report path (default: sibling summaries directory)")
    args = parser.parse_args()
    if not args.raw.is_dir():
        parser.error(f"not a directory: {args.raw}")
    rows, errors = load_logs(args.raw)
    env, env_path = environment(args.raw)
    output = args.output or args.raw.parent / "summaries" / "EV3_VALIDATION_REPORT.md"
    if not rows:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join([
            "# EV3 validation report", "", "## ERROR: NO RAW MEASUREMENTS", "",
            f"Input directory: `{args.raw.as_posix()}`", "",
            "The analyzer found zero valid CSV rows. It intentionally did not generate validation conclusions.", "",
            "Required recovery: run `ev3-bench smoke`, verify the CSV on the EV3 and after pull, then rerun this analyzer.", ""
        ]), encoding="utf-8")
        recommendations = output.parent / "ARCHITECTURE_RECOMMENDATIONS.md"
        recommendations.write_text("# ARCHITECTURE RECOMMENDATIONS BLOCKED\n\nERROR: NO RAW MEASUREMENTS. No recommendations may be generated until `ev3-bench smoke` produces pulled CSV rows.\n", encoding="utf-8")
        print(f"ERROR: NO RAW MEASUREMENTS. Wrote {output}")
        return 2
    metrics = make_report(args.raw, rows, errors, env, env_path, output)
    recommendations = output.parent / "ARCHITECTURE_RECOMMENDATIONS.md"
    make_recommendations(metrics, recommendations)
    coordinated = output.parent / "COORDINATED_TWO_MOTOR_VALIDATION.md"
    make_coordinated_report(rows, coordinated)
    print(f"Wrote {output}")
    print(f"Wrote {recommendations}")
    print(f"Wrote {coordinated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
