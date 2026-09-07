#!/usr/bin/env python3
"""Stage-3 EV3 DEVICE AUTO: real network/security checks with zero actuator scope."""
import hashlib
import json
import os
import pathlib
import platform
import grp
import socket
import struct
import subprocess
import sys
import time

CURRENT = pathlib.Path("/opt/phantom/current")
REPORT = pathlib.Path("/var/lib/phantom/device-auto.json")
checks = []
report_manifest = {}


def add(test_id, status, detail, evidence=None, introduced_at_stage=2):
    item = {"test_id": test_id, "introduced_at_stage": introduced_at_stage,
            "applicable_to_stage": 3, "status": status, "detail": detail}
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


def semantic_hash(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def wall_clock_state(wall_epoch, timedate_output, timedate_query_status="PASS"):
    """Record wall-clock trust without making it part of deterministic build identity."""
    ntp = "unknown"
    for line in timedate_output.splitlines():
        key, separator, value = line.strip().partition(":")
        if separator and key.strip().lower() == "ntp synchronized":
            ntp = value.strip().lower()
            break
    evidence = {
        "wall_clock_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(wall_epoch)),
        "ntp_synchronized": ntp,
        "timedate_query_status": timedate_query_status,
        "chronology_trust": "NTP_SYNCHRONIZED" if ntp == "yes" else "HOST_CORRELATION_REQUIRED",
    }
    plausible = wall_epoch >= 946684800  # 2000-01-01; catches an uninitialised EV3 calendar.
    status = "PASS" if plausible else "FAIL"
    detail = "wall-clock/NTP state recorded; external host correlation is required unless NTP is synchronized"
    return status, detail, evidence


def motor_nodes():
    result = {}
    for node in pathlib.Path("/sys/class/tacho-motor").glob("motor*"):
        result[text(node / "address").split(":")[-1].lower()] = node
    return result


def sensor_nodes():
    result = {}
    for node in pathlib.Path("/sys/class/lego-sensor").glob("sensor*"):
        result[text(node / "address").split(":")[-1].lower()] = node
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


def read_json_object(path):
    """Return structured evidence instead of throwing on a missing/partial status write."""
    if not path.is_file():
        return None, {"category": "MISSING", "path": str(path)}
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        return None, {"category": "READ_ERROR", "path": str(path), "detail": str(error)}
    if not raw.strip():
        return None, {"category": "EMPTY", "path": str(path)}
    try:
        value = json.loads(raw)
    except ValueError as error:
        return None, {"category": "MALFORMED", "path": str(path), "detail": str(error)}
    if not isinstance(value, dict):
        return None, {"category": "NOT_OBJECT", "path": str(path)}
    return value, None


def valid_boot_id(value):
    if len(value) != 32:
        return False
    try:
        return len(bytes.fromhex(value)) == 16
    except ValueError:
        return False


def dns_name(name):
    return b"".join(bytes([len(label)]) + label.encode("ascii") for label in name.split(".")) + b"\0"


def mdns_probe(robot_id, boot_id):
    needle = dns_name("_phantom-ev3._udp")[:-1].lower()
    query = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) + dns_name("_phantom-ev3._udp.local") + struct.pack(">HH", 12, 1)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", 5353))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                    socket.inet_aton("224.0.0.251") + socket.inet_aton("0.0.0.0"))
    sock.settimeout(.4)
    sock.sendto(query, ("224.0.0.251", 5353))
    deadline = time.monotonic() + 3.0
    packets = []
    try:
        while time.monotonic() < deadline:
            try:
                packet, source = sock.recvfrom(4096)
            except socket.timeout:
                sock.sendto(query, ("224.0.0.251", 5353))
                continue
            packets.append((packet, source[0]))
            low = packet.lower()
            if needle in low and ("robot_id=" + robot_id).encode("ascii") in packet and ("controller_boot_id=" + boot_id).encode("ascii") in packet:
                return True, {"responses": len(packets), "source": source[0], "service": "_phantom-ev3._udp.local",
                              "robot_id": robot_id, "controller_boot_id_matches": True}
    finally:
        sock.close()
    return False, {"responses": len(packets), "service": "_phantom-ev3._udp.local", "controller_boot_id_matches": False}


def protocol_probe(root, config, boot_hex, motors):
    sys.path.insert(0, str(root / "bin"))
    import phantom_protocol as wire
    raw = pathlib.Path("/var/lib/phantom/secrets/control.psk").read_bytes().strip()
    key = bytes.fromhex(raw.decode("ascii")) if len(raw) == 64 else raw
    boot = bytes.fromhex(boot_hex)
    endpoint = ("127.0.0.1", int(config["network"]["listen_port_udp"]))
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(.25)
    nonce = os.urandom(16)
    hello = wire.encode(1, wire.hello_payload(config["robot_id"], 0, 0, nonce), key,
                        wire.ZERO_ID, boot, 0, int(time.monotonic() * 1000000))
    client.sendto(hello, endpoint)
    deadline = time.monotonic() + 2.0
    ack = None
    while time.monotonic() < deadline and ack is None:
        try:
            packet, unused = client.recvfrom(1024)
        except socket.timeout:
            continue
        decoded = wire.decode(packet, key)
        if decoded["message"] == "HELLO_ACK":
            ack = decoded
    if ack is None or ack["payload"][:16] != nonce:
        raise ValueError("HELLO_ACK missing")
    session = ack["session_id"]
    ping_payload = struct.pack("<QQ", 7341, 0x12345678)
    ping = wire.encode(768, ping_payload, key, session, boot, 1, int(time.monotonic() * 1000000))
    client.sendto(ping, endpoint)
    got_pong = got_telemetry = False
    telemetry = None
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not (got_pong and got_telemetry):
        try:
            packet, unused = client.recvfrom(1024)
        except socket.timeout:
            continue
        decoded = wire.decode(packet, key, expected_session=session, expected_boot=boot)
        if decoded["message"] == "PONG" and decoded["payload"] == ping_payload:
            got_pong = True
        if decoded["message"] == "TELEMETRY":
            got_telemetry = True
            telemetry = decoded["payload"]
    before_safe, unused = zero_state(motors)
    command = wire.encode(256, wire.command_payload(5, [.1, .2, .3], .4), key,
                          session, boot, 2, int(time.monotonic() * 1000000))
    client.sendto(command, endpoint)
    corrupt = bytearray(wire.encode(768, ping_payload, key, session, boot, 3, 1)); corrupt[-1] ^= 1
    client.sendto(bytes(corrupt), endpoint)
    client.sendto(ping, endpoint)
    time.sleep(.15)
    after_safe, zero_evidence = zero_state(motors)
    client.close()
    state = struct.unpack_from("<H", telemetry, 128)[0] if telemetry else None
    q = struct.unpack_from("<3f", telemetry, 164) if telemetry else ()
    grip = struct.unpack_from("<f", telemetry, 188)[0] if telemetry else None
    return got_pong and got_telemetry and before_safe and after_safe and state == 3 and q == (0.0, 0.0, 0.0) and grip == 0.0, {
        "hello_ack": ack is not None, "session_id_server_generated": session != wire.ZERO_ID,
        "pong": got_pong, "telemetry": got_telemetry, "telemetry_state": state,
        "canonical_out_of_scope_q": list(q), "canonical_out_of_scope_grip": grip,
        "authenticated_command_zero_output": after_safe, "zero_state": zero_evidence}


def write_report(manifest):
    status = "PASS" if all(item["status"] in ("PASS", "N_A") for item in checks) else "FAIL"
    payload = {"schema_version": 2, "gate": "DEVICE AUTO", "stage": 3,
               "status": status, "git_commit": manifest.get("git_commit"),
               "build_id": manifest.get("build_id"), "config_hash": manifest.get("config_hash"),
               "commissioning_bundle_hash": manifest.get("commissioning_bundle_hash"),
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
    global report_manifest
    if os.geteuid() != 0:
        add("device-auto-root", "FAIL", "root is required for sysfs takeover checks")
        return write_report({})
    root = CURRENT.resolve()
    manifest = json.loads((root / "build-manifest.json").read_text(encoding="utf-8-sig"))
    report_manifest = manifest
    config = json.loads((root / "config.generated.json").read_text(encoding="utf-8-sig"))
    bundle = json.loads((root / "commissioning-bundle.generated.json").read_text(encoding="utf-8-sig"))
    profile_ok = (config.get("build_profile") == "Diagnostic" and config.get("qualification_only") is True and
                  config.get("actuator_scope_mask") == 0 and bundle.get("qualification_only") is True and
                  bundle.get("actuator_scope_mask") == 0)
    add("ev3-stage3-profile", "PASS" if profile_ok else "FAIL",
        "Diagnostic qualification_only with authoritative actuator_scope_mask=0x00",
        {"build_profile": config.get("build_profile"), "qualification_only": config.get("qualification_only"),
         "actuator_scope_mask": config.get("actuator_scope_mask")}, 3)

    systemd = run(["systemctl", "--version"], 5).stdout.splitlines()
    platform_evidence = {"machine": platform.machine(), "kernel": platform.release(),
                         "python": platform.python_version(), "systemd": systemd[0] if systemd else "unknown"}
    platform_ok = platform_evidence["machine"].startswith("armv5") and sys.version_info[:2] >= (3, 5)
    add("ev3-platform-compatibility", "PASS" if platform_ok else "FAIL", "pinned Stretch runtime compatibility", platform_evidence)
    wall_epoch = time.time()
    try:
        timedate = run(["timedatectl", "status"], 5)
        query_status = "PASS" if timedate.returncode == 0 else "EXIT_" + str(timedate.returncode)
        timedate_output = timedate.stdout
    except subprocess.TimeoutExpired:
        query_status, timedate_output = "TIMEOUT", ""
    clock_status, clock_detail, clock_evidence = wall_clock_state(
        wall_epoch, timedate_output, query_status)
    add("ev3-wall-clock", clock_status, clock_detail, clock_evidence)
    integrity = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=str(root), stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, universal_newlines=True, timeout=30)
    add("installed-artifact-integrity", "PASS" if integrity.returncode == 0 else "FAIL", integrity.stdout.strip())
    config_hash = sha256(root / "config.generated.json")
    add("installed-config-hash", "PASS" if config_hash == manifest.get("config_hash") else "FAIL",
        "installed config bytes match manifest", {"config_hash": config_hash,
                                                   "expected_config_hash": manifest.get("config_hash")})
    bundle_hash = semantic_hash(bundle)
    add("installed-bundle-hash", "PASS" if bundle_hash == manifest.get("commissioning_bundle_hash") else "FAIL",
        "installed bundle semantics match manifest", {"commissioning_bundle_hash": bundle_hash,
                                                       "expected_commissioning_bundle_hash": manifest.get("commissioning_bundle_hash")}, 3)

    usb_devices = []
    for node in pathlib.Path("/sys/bus/usb/devices").iterdir():
        vendor, product = node / "idVendor", node / "idProduct"
        if vendor.is_file() and product.is_file():
            usb_devices.append(text(vendor) + ":" + text(product))
    wireless = [node.name for node in pathlib.Path("/sys/class/net").iterdir() if (node / "wireless").exists()]
    modules = run(["lsmod"], 5).stdout
    wna_ok = "0846:9030" in usb_devices and "ath9k_htc" in modules and len(wireless) == 1
    add("ev3-wna1100", "PASS" if wna_ok else "FAIL", "USB 0846:9030, ath9k_htc and one discovered wireless interface",
        {"vid_pid": "0846:9030" if "0846:9030" in usb_devices else None, "driver": "ath9k_htc" if "ath9k_htc" in modules else None,
         "interfaces": wireless}, 3)
    wifi = wireless[0] if wireless else ""
    ip_output = run(["ip", "-o", "-4", "addr", "show", "dev", wifi], 5).stdout if wifi else ""
    carrier_path = pathlib.Path("/sys/class/net") / wifi / "carrier"
    carrier = text(carrier_path) if wifi and carrier_path.is_file() else "0"
    wifi_ok = carrier == "1" and " inet " in ip_output
    add("ev3-wifi-dhcp", "PASS" if wifi_ok else "FAIL", "wireless association and DHCP IPv4",
        {"interface": wifi, "carrier": carrier, "ipv4_present": " inet " in ip_output}, 3)

    motors = motor_nodes()
    motor_evidence = {address: {"driver": text(node / "driver_name"), "count_per_rot": text(node / "count_per_rot"), "reason": "OUT_OF_SCOPE"}
                      for address, node in sorted(motors.items())}
    add("ev3-motor-discovery", "N_A", "network-only actuator_scope_mask=0x00; no motor I/O required", motor_evidence, 3)
    sensors = sensor_nodes()
    sensor_evidence = {address: {"driver": text(node / "driver_name"), "reason": "OUT_OF_SCOPE"} for address, node in sorted(sensors.items())}
    add("ev3-local-safety-inputs", "N_A", "network-only actuator_scope_mask=0x00; motor safety inputs not required", sensor_evidence, 3)
    battery_path = pathlib.Path("/sys/class/power_supply/lego-ev3-battery/voltage_now")
    voltage = int(text(battery_path)) if battery_path.is_file() else 0
    add("ev3-battery-telemetry", "PASS" if voltage > 0 else "FAIL", str(voltage))

    for binary in ("phantom-controller", "phantom-safety"):
        result = run([str(root / "bin" / binary), "--self-test"], 15)
        add(binary + "-on-device-self-test", "PASS" if result.returncode == 0 else "FAIL", result.stdout.strip())
    units = ("phantom-safety.service", "phantom-wifi-autoconnect.service", "phantom-controller.service", "phantom-network.service", "phantom-mdns.service")
    service_states = {unit: active(unit) for unit in units}
    services_ok = all(service_states.values())
    add("ev3-systemd-startup", "PASS" if services_ok else "FAIL", "all Stage-3 services active", service_states)
    identities={unit:run(["systemctl","show","-p","User","-p","Group",unit],5).stdout.strip() for unit in ("phantom-controller.service","phantom-network.service","phantom-mdns.service")}
    identity_ok="User=phantom-ctrl" in identities["phantom-controller.service"] and "User=phantom-net" in identities["phantom-network.service"] and "User=phantom-mdns" in identities["phantom-mdns.service"]
    add("ev3-runtime-identities", "PASS" if identity_ok else "FAIL", "controller/network/mDNS use distinct service identities", identities, 3)
    controller_ipc=pathlib.Path("/run/phantom/controller/network.sock");network_ipc=pathlib.Path("/run/phantom/network/controller.sock")
    ipc_evidence={}
    for path in (controller_ipc,network_ipc):
        if path.exists():
            info=path.stat();ipc_evidence[str(path)]={"mode":oct(info.st_mode&0o777),"group":grp.getgrgid(info.st_gid).gr_name}
    ipc_ok=len(ipc_evidence)==2 and all(item["mode"]=="0o660" and item["group"]=="phantom-ipc" for item in ipc_evidence.values())
    add("ev3-controller-network-ipc-permissions", "PASS" if ipc_ok else "FAIL", "fixed datagram endpoints mode 0660 group phantom-ipc", ipc_evidence, 3)
    access_checks={
        "phantom-net-motor-write-denied":run(["runuser","-u","phantom-net","--","test","!","-w","/run/phantom/motor-control.lock"],5).returncode==0,
        "phantom-ctrl-psk-read-denied":run(["runuser","-u","phantom-ctrl","--","test","!","-r","/var/lib/phantom/secrets/control.psk"],5).returncode==0,
        "phantom-mdns-psk-read-denied":run(["runuser","-u","phantom-mdns","--","test","!","-r","/var/lib/phantom/secrets/control.psk"],5).returncode==0,
    }
    add("ev3-privilege-separation", "PASS" if all(access_checks.values()) else "FAIL", "motor and PSK DAC domains are disjoint", access_checks, 3)
    safe, safe_evidence = zero_state(motors)
    add("ev3-zero-output-startup", "PASS" if safe else "FAIL", "all physically present motors stationary/BRAKE", safe_evidence)

    boot_before_path = pathlib.Path("/run/phantom/controller/boot-id")
    boot_before = text(boot_before_path) if boot_before_path.is_file() else ""
    if services_ok and profile_ok and safe:
        log_path = pathlib.Path("/var/log/phantom/safety-emergency.log")
        before = log_path.stat().st_size if log_path.exists() else 0
        killed = run(["systemctl", "kill", "--signal=SIGKILL", "--kill-who=main", "phantom-controller.service"], 5).returncode == 0
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and (not log_path.exists() or log_path.stat().st_size <= before):
            time.sleep(.1)
        safe_after, takeover_evidence = zero_state(motors)
        logged = log_path.exists() and log_path.stat().st_size > before
        add("ev3-supervisor-takeover", "PASS" if killed and safe_after and logged else "FAIL", "controller SIGKILL detected and BRAKE retained", takeover_evidence)
        restart = run(["systemctl", "restart", "phantom.target"], 120)
        recovered = restart.returncode == 0 and all(active(unit) for unit in units)
        time.sleep(.5)
        boot_after = text(boot_before_path) if boot_before_path.is_file() else ""
        add("ev3-safe-restart", "PASS" if recovered else "FAIL", restart.stdout.strip())
        add("ev3-controller-boot-id-rotation", "PASS" if recovered and boot_after and boot_after != boot_before else "FAIL",
            "controller restart creates a fresh identity and invalidates prior sessions", {"changed": boot_after != boot_before}, 3)
    else:
        prerequisite = {"services_active": services_ok, "profile_valid": profile_ok, "zero_output": safe}
        add("ev3-supervisor-takeover", "NOT_RUN", "prerequisite startup/profile/zero-output check failed", prerequisite)
        add("ev3-safe-restart", "NOT_RUN", "takeover was not run", prerequisite)
        add("ev3-controller-boot-id-rotation", "NOT_RUN", "restart was not run", prerequisite, 3)
        boot_after = boot_before

    probe_service_states = {unit: active(unit) for unit in units}
    runtime_services_ok = all(probe_service_states.values())
    if not runtime_services_ok:
        prerequisite = {"services": probe_service_states, "controller_boot_id_valid": valid_boot_id(boot_after)}
        add("ev3-dns-sd-stage3", "NOT_RUN", "systemd startup prerequisite failed", prerequisite, 3)
        add("ev3-udp-session-stage3", "NOT_RUN", "systemd startup prerequisite failed", prerequisite, 3)
        add("ev3-network-security-stage3", "NOT_RUN", "systemd startup prerequisite failed", prerequisite, 3)
    elif not valid_boot_id(boot_after):
        prerequisite = {"controller_boot_id_valid": False, "observed_length": len(boot_after)}
        add("ev3-dns-sd-stage3", "FAIL", "controller boot identity is invalid", prerequisite, 3)
        add("ev3-udp-session-stage3", "NOT_RUN", "valid controller boot identity is required", prerequisite, 3)
        add("ev3-network-security-stage3", "NOT_RUN", "valid controller boot identity is required", prerequisite, 3)
    else:
        mdns_ok, mdns_evidence = mdns_probe(config["robot_id"], boot_after)
        add("ev3-dns-sd-stage3", "PASS" if mdns_ok else "FAIL", "live multicast DNS-SD response", mdns_evidence, 3)
        try:
            protocol_ok, protocol_evidence = protocol_probe(root, config, boot_after, motors)
            protocol_completed = True
        except Exception as error:
            protocol_ok, protocol_evidence = False, {"category": type(error).__name__, "detail": str(error)}
            protocol_completed = False
        add("ev3-udp-session-stage3", "PASS" if protocol_ok else "FAIL", "HELLO/HELLO_ACK, PING/PONG, TELEMETRY and authenticated COMMAND with scope zero", protocol_evidence, 3)
        if not protocol_completed:
            add("ev3-network-security-stage3", "NOT_RUN", "protocol probe did not reach the security cases", protocol_evidence, 3)
        else:
            time.sleep(1.1)
            network_status_path = pathlib.Path("/run/phantom/network-status.json")
            network_status, status_error = read_json_object(network_status_path)
            counters = network_status.get("counters", {}) if network_status is not None else {}
            security_ok = status_error is None and counters.get("hmac_fail", 0) >= 1 and counters.get("replay_reject", 0) >= 1
            security_evidence = counters if status_error is None else status_error
            add("ev3-network-security-stage3", "PASS" if security_ok else "FAIL", "invalid HMAC and replay rejected", security_evidence, 3)
    final_safe, final_evidence = zero_state(motors)
    # The old proof was a counter the network worker incremented nowhere, so it
    # read zero whether or not the process could drive a motor. Real evidence is
    # observed sysfs state on every present motor, a network process outside the
    # motor-I/O DAC domain, and a rejection counter that is actually written.
    rejected = counters.get("motor_write_attempts_rejected")
    audit = {"sysfs": final_evidence,
             "motor_write_attempts_rejected": rejected,
             "phantom_net_motor_write_denied": access_checks["phantom-net-motor-write-denied"],
             "controller_state": network_status.get("controller_state")}
    zero_output_ok = (final_safe
                      and isinstance(rejected, int)
                      and access_checks["phantom-net-motor-write-denied"])
    add("ev3-stage3-zero-output-audit", "PASS" if zero_output_ok else "FAIL",
        "no motor output and no network motor-write authority across startup/session/command/replay/restart",
        audit, 3)
    return write_report(manifest)


if __name__ == "__main__":
    try:
        sys.exit(0 if main() == "PASS" else 1)
    except Exception as error:
        add("device-auto-runner", "FAIL", repr(error))
        try:
            write_report(report_manifest)
        finally:
            raise
