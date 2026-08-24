import importlib.util
import math
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("ev3_analyze", str(MODULE_PATH))
analyze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyze)


def row(test, time_us, dt, **extra):
    value = {
        "test_id": test, "monotonic_time_us": float(time_us), "loop_dt_us": float(dt),
        "cpu_time_us": float(time_us / 10), "motor_address": "outA", "motor_driver": "lego-ev3-l-motor",
        "command_mode": "persistent", "duty_cycle_sp": 20.0, "duty_cycle": 20.0,
        "position": 0.0, "speed": 0.0, "target_position": 0.0, "goal_position": 0.0,
        "position_error": 0.0, "battery_voltage": 7.5, "state_flags": "running",
        "event": "", "fault": "", "target_speed": 0.0, "_file": "e1_run_persistent_50hz.csv",
        "work_time_us": 100.0,
    }
    value.update(extra)
    return value


class AnalyzeTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertEqual(analyze.percentile([0, 10], 0.5), 5)
        self.assertTrue(math.isnan(analyze.percentile([], 0.5)))

    def test_jitter_deadline_and_cpu(self):
        rows = [row("E1", i * 20_000, 20_000) for i in range(10)]
        rows.append(row("E1", 230_000, 50_000))
        summary = analyze.jitter(rows)[0]
        self.assertEqual(summary["rate"], 50)
        self.assertEqual(summary["missed"], 1)
        self.assertAlmostEqual(summary["cpu"], 10.0)

    def test_duty_curve_and_floor(self):
        rows = [row("E2", i * 20_000, 20_000, duty_cycle_sp=10.0, speed=s, command_mode="run-direct") for i, s in enumerate([6, 7, 8])]
        curve = analyze.duty_curves(rows)
        self.assertAlmostEqual(curve[0]["speed"], 7)
        self.assertEqual(analyze.reliable_floor(curve)["outA"], 10)

    def test_stall_sweep_needs_stall_data(self):
        self.assertEqual(analyze.e7_sweep([]), [])

    def test_absolute_target_drift(self):
        rows = []
        for i in range(10):
            rows.append(row("E5", i * 20_000, 20_000, event="target_hold",
                            target_position=90 if i % 2 else -90, position_error=i * 0.1,
                            _file="e5.csv"))
        result = analyze.e5_drift(rows)[0]
        self.assertAlmostEqual(result["slope"], 0.1)


if __name__ == "__main__":
    unittest.main()
