#!/usr/bin/env python3
"""Pure regressions for the EV3 installed-runtime integration runner."""
import importlib.util,json,pathlib,sys,tempfile,types,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
if sys.platform=="win32":sys.modules.setdefault("grp",types.ModuleType("grp"))
SPEC=importlib.util.spec_from_file_location("phantom_ev3_device_integration",str(ROOT/"deploy/scripts/device-integration-test.py"))
RUNNER=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(RUNNER)

class RunnerLogicTests(unittest.TestCase):
    def test_unsynchronised_but_plausible_clock_requires_host_correlation(self):
        status,_,evidence=RUNNER.wall_clock_state(1788706800,"NTP synchronized: no\n")
        self.assertEqual("PASS",status);self.assertEqual("HOST_CORRELATION_REQUIRED",evidence["chronology_trust"])
    def test_uninitialised_calendar_fails(self):
        self.assertEqual("FAIL",RUNNER.wall_clock_state(42,"NTP synchronized: no\n")[0])
    def test_status_json_failure_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"status.json"
            value,evidence=RUNNER.read_json_object(path);self.assertIsNone(value);self.assertEqual("MISSING",evidence["category"])
            path.write_text("",encoding="utf-8");self.assertEqual("EMPTY",RUNNER.read_json_object(path)[1]["category"])
            path.write_text("{",encoding="utf-8");self.assertEqual("MALFORMED",RUNNER.read_json_object(path)[1]["category"])
            path.write_text(json.dumps({"ok":True}),encoding="utf-8");self.assertEqual({"ok":True},RUNNER.read_json_object(path)[0])
    def test_boot_id_validation(self):
        self.assertFalse(RUNNER.valid_boot_id(""));self.assertFalse(RUNNER.valid_boot_id("gg"*16));self.assertTrue(RUNNER.valid_boot_id("42"*16))
    def test_zero_state_rejects_motion_or_coast(self):
        class Node:
            def __init__(self,values):self.values=values
            def __truediv__(self,name):return self.values[name]
        stationary={"duty_cycle_sp":"0","duty_cycle":"0","speed":"0","state":"","stop_action":"brake"};original=RUNNER.text
        try:
            RUNNER.text=lambda value:value
            self.assertTrue(RUNNER.zero_state({"outA":Node(dict(stationary))})[0])
            for field,bad in (("speed","1"),("duty_cycle","1"),("state","running"),("stop_action","coast")):
                values=dict(stationary);values[field]=bad;self.assertFalse(RUNNER.zero_state({"outA":Node(values)})[0],field)
        finally:RUNNER.text=original
    def test_runner_uses_observed_zero_output(self):
        source=(ROOT/"deploy/scripts/device-integration-test.py").read_text(encoding="utf-8")
        self.assertIn("zero_state(motors)",source);self.assertIn("motor_write_attempts_rejected",source)
        self.assertNotIn('counters.get("nonzero_motor_writes")',source)

if __name__=="__main__":unittest.main()
