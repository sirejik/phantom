#!/usr/bin/env python3
"""Stage-2 EV3 DEVICE AUTO: real Brick checks with zero commanded motion."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

CURRENT = pathlib.Path("/opt/phantom/current")
REPORT = pathlib.Path("/var/lib/phantom/device-auto.json")
checks = []


def add(test_id, status, detail, evidence=None, introduced_at_stage=2):
    item = {"test_id": test_id, "introduced_at_stage": introduced_at_stage,
            "applicable_to_stage": 2, "status": status, "detail": detail}
    if evidence is not None:
        item["evidence"] = evidence
    checks.append(item)


def run(command, timeout=20):
    return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True, timeout=timeout)


def text(path):
    return path.read_text(encoding="ascii").strip()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def motor_nodes():
    result = {}
    for node in pathlib.Path("/sys/class/tacho-motor").glob("motor*"):
        address = text(node / "address").split(":")[-1].lower()
        result[address] = node
    return result


def sensor_nodes():
    result = {}
    for node in pathlib.Path("/sys/class/lego-sensor").glob("sensor*"):
        address = text(node / "address").split(":")[-1].lower()
        result[address] = node
    return result


def zero_state(nodes):
    evidence = {}
    ok = True
    for address, node in sorted(nodes.items()):
        values = {name: text(node / name) for name in
                  ("duty_cycle_sp", "duty_cycle", "speed", "state", "stop_action")}
        evidence[address] = values
        ok = ok and values["duty_cycle_sp"] == "0" and values["duty_cycle"] == "0"
        ok = ok and values["speed"] == "0" and values["state"] == ""
        ok = ok and values["stop_action"] == "brake"
    return ok, evidence


def active(unit):
    return run(["systemctl", "is-active", "--quiet", unit], 5).returncode == 0


def write_report(manifest):
    status = "PASS" if all(item["status"] in ("PASS", "N_A") for item in checks) else "FAIL"
    payload = {"schema_version": 1, "gate": "DEVICE AUTO", "stage": 2,
               "status": status, "git_commit": manifest.get("git_commit"),
               "build_id": manifest.get("build_id"),
               "artifact_sha256": {"controller": manifest.get("controller_sha256"),
                                     "safety": manifest.get("safety_sha256")},
               "monotonic_finished_us": int(time.monotonic() * 1000000), "checks": checks}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(REPORT))
    print(json.dumps(payload, sort_keys=True))
    return status


def main():
    if os.geteuid() != 0:
        add("device-auto-root", "FAIL", "root is required for sysfs takeover checks")
        return write_report({})
    root = CURRENT.resolve()
    manifest = json.loads((root / "build-manifest.json").read_text(encoding="utf-8-sig"))
    # sha256sum must run relative to the release root.
    integrity = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=str(root),
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               universal_newlines=True, timeout=30)
    add("installed-artifact-integrity", "PASS" if integrity.returncode == 0 else "FAIL",
        integrity.stdout.strip())
    config_hash = sha256(root / "config.generated.json")
    add("installed-config-hash", "PASS" if config_hash == manifest.get("config_hash") else "FAIL",
        config_hash)

    expected_motors = {"outa": "lego-ev3-l-motor", "outb": "lego-ev3-l-motor",
                       "outc": "lego-ev3-l-motor", "outd": "lego-ev3-m-motor"}
    motors = motor_nodes()
    motor_evidence = {address: {"driver": text(node / "driver_name"),
                                "count_per_rot": text(node / "count_per_rot")}
                      for address, node in sorted(motors.items())}
    motor_ok = set(motors) == set(expected_motors)
    motor_ok = motor_ok and all(motor_evidence[a]["driver"] == driver and
                                motor_evidence[a]["count_per_rot"] == "360"
                                for a, driver in expected_motors.items())
    add("ev3-motor-discovery", "PASS" if motor_ok else "FAIL", "address/driver/count_per_rot", motor_evidence)

    sensors = sensor_nodes()
    sensor_evidence = {a: {"driver": text(n / "driver_name"), "value0": text(n / "value0")}
                       for a, n in sorted(sensors.items())}
    sensor_ok = all(a in sensors and sensor_evidence[a]["driver"] == "lego-ev3-touch"
                    for a in ("in3", "in4"))
    sensor_ok = sensor_ok and sensor_evidence["in4"]["value0"] == "0"
    add("ev3-local-safety-inputs", "PASS" if sensor_ok else "FAIL",
        "GRIPPER_HOME in3 present; LOCAL_STOP in4 present and released", sensor_evidence)

    battery_path = pathlib.Path("/sys/class/power_supply/lego-ev3-battery/voltage_now")
    voltage = int(text(battery_path)) if battery_path.is_file() else 0
    add("ev3-battery-telemetry", "PASS" if voltage > 0 else "FAIL", str(voltage))

    for binary in ("phantom-controller", "phantom-safety"):
        result = run([str(root / "bin" / binary), "--self-test"], 15)
        add(binary + "-on-device-self-test", "PASS" if result.returncode == 0 else "FAIL",
            result.stdout.strip())

    services_ok = active("phantom-safety.service") and active("phantom-controller.service")
    add("ev3-systemd-startup", "PASS" if services_ok else "FAIL", "controller and safety active")
    safe, safe_evidence = zero_state(motors)
    add("ev3-zero-output-startup", "PASS" if safe else "FAIL", "all motors stationary/brake", safe_evidence)

    if services_ok and motor_ok and sensor_ok:
        log_path = pathlib.Path("/var/log/phantom/safety-emergency.log")
        before = log_path.stat().st_size if log_path.exists() else 0
        killed = run(["systemctl", "kill", "--signal=SIGKILL", "--kill-who=main",
                      "phantom-controller.service"], 5).returncode == 0
        time.sleep(0.35)
        safe_after, takeover_evidence = zero_state(motors)
        logged = log_path.exists() and log_path.stat().st_size > before
        add("ev3-supervisor-takeover", "PASS" if killed and safe_after and logged else "FAIL",
            "controller SIGKILL detected and BRAKE retained", takeover_evidence)
        restart = run(["systemctl", "restart", "phantom.target"], 15)
        recovered = restart.returncode == 0 and active("phantom-safety.service") and active("phantom-controller.service")
        add("ev3-safe-restart", "PASS" if recovered else "FAIL", restart.stdout.strip())
    else:
        add("ev3-supervisor-takeover", "FAIL", "prerequisite startup/topology check failed")
        add("ev3-safe-restart", "FAIL", "takeover was not run")

    add("ev3-dns-sd-stage3", "N_A", "introduced at stage 3", introduced_at_stage=3)
    add("ev3-udp-session-stage3", "N_A", "introduced at stage 3", introduced_at_stage=3)
    return write_report(manifest)


if __name__ == "__main__":
    try:
        sys.exit(0 if main() == "PASS" else 1)
    except Exception as error:
        add("device-auto-runner", "FAIL", repr(error))
        try:
            write_report({})
        finally:
            raise
