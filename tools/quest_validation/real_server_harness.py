#!/usr/bin/env python3
"""Run the real `ev3/network/phantom_network.py` worker for host interop tests.

The Quest client used to be validated only against `sim/ev3-simulator`, a second
server implementation that does not share the production worker's rate limiter,
pre-HMAC key-slot drop, session staleness or HELLO rejection semantics. This
harness starts the production worker itself on loopback and prints the same
discovery record shape the simulator prints, so the same client harness can be
pointed at either one and the difference is explicit in the report.

It provisions only test material: the checked-in golden test key, a synthetic
build manifest, and a temporary boot id. It never touches deployment paths.
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "protocol"))
import jcs  # noqa: E402
import phantom_protocol as wire  # noqa: E402

TEST_KEY = bytes(range(32))


def prepare(directory):
    """Create the temporary inputs the worker needs and return its argv tail."""
    bundle_path = ROOT / "config" / "generated" / "commissioning_bundle-network-only.generated.json"
    config_path = ROOT / "config" / "generated" / "ev3-network-only.generated.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle_hash = hashlib.sha256(jcs.canonicalize(bundle)).hexdigest()
    protocol_hash = wire.schema_hash().hex()
    protocol_semantics_hash = wire.semantics_hash().hex()
    protocol_contract_hash = wire.contract_hash().hex()

    manifest = {
        "schema_version": 2, "component": "EV3", "build_profile": "Diagnostic",
        "build_id": hashlib.sha256(b"phantom-host-interop").hexdigest(),
        "protocol_schema_hash": protocol_hash,
        "protocol_semantics_hash": protocol_semantics_hash,
        "protocol_contract_hash": protocol_contract_hash,
        "commissioning_bundle_hash": bundle_hash,
    }
    manifest_path = directory / "build-manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    key_path = directory / "control.psk"
    key_path.write_bytes(TEST_KEY)
    if os.name == "posix":
        os.chmod(str(key_path), 0o640)

    boot_id = hashlib.sha256(b"phantom-host-interop-boot").digest()[:16]
    boot_path = directory / "boot-id"
    boot_path.write_text(boot_id.hex() + "\n", encoding="ascii")

    return {
        "config": str(config_path), "bundle": str(bundle_path), "manifest": str(manifest_path),
        "control_key": str(key_path), "boot_id": boot_path, "boot_id_hex": boot_id.hex(),
        "status": str(directory / "network-status.json"), "build_id": manifest["build_id"],
        "bundle_hash": bundle_hash,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--ready-timeout", type=float, default=10.0)
    args = parser.parse_args()

    directory = pathlib.Path(tempfile.mkdtemp(prefix="phantom-real-server-"))
    inputs = prepare(directory)
    worker = subprocess.Popen(
        [sys.executable, str(ROOT / "ev3" / "network" / "phantom_network.py"),
         "--config", inputs["config"], "--bundle", inputs["bundle"],
         "--manifest", inputs["manifest"], "--control-key", inputs["control_key"],
         "--boot-id", str(inputs["boot_id"]), "--status", inputs["status"],
         "--bind", args.bind, "--local-authority"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    port = None
    deadline = time.monotonic() + args.ready_timeout
    try:
        while time.monotonic() < deadline:
            line = worker.stdout.readline()
            if not line:
                break
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("event") == "UDP_LISTENER_STARTED":
                port = int(event["port"])
            if event.get("event") == "NETWORK_READY":
                port = int(event["port"])
                break
        if port is None:
            worker.kill()
            raise SystemExit("production worker did not report NETWORK_READY")
        print(json.dumps({
            "event": "listening", "server": "production-worker",
            "service": "_phantom-ev3._udp.local.", "instance": "PHANTOM-phantom01",
            "robot_id": "phantom01", "protocol_major": "1",
            "controller_boot_id": inputs["boot_id_hex"], "build_id": inputs["build_id"],
            "bundle_hash": inputs["bundle_hash"], "port": port}), flush=True)
        # Keep draining so the worker never blocks on a full stdout pipe.
        while worker.poll() is None:
            if not worker.stdout.readline():
                break
    finally:
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()


if __name__ == "__main__":
    main()
