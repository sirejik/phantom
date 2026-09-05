#!/usr/bin/env python3
"""Publish the current controller identity through the existing Avahi daemon."""
from __future__ import print_function
import argparse
import json
import os
import pathlib
import signal
import sys
import time

import dbus

AVAHI = "org.freedesktop.Avahi"
SERVER = "org.freedesktop.Avahi.Server"
ENTRY_GROUP = "org.freedesktop.Avahi.EntryGroup"


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def txt(records):
    return dbus.Array([dbus.ByteArray(item.encode("utf-8")) for item in records], signature="ay")


def publish(bus, name, service_type, domain, port, records):
    server = dbus.Interface(bus.get_object(AVAHI, "/"), SERVER)
    path = server.EntryGroupNew()
    group = dbus.Interface(bus.get_object(AVAHI, path), ENTRY_GROUP)
    group.AddService(dbus.Int32(-1), dbus.Int32(0), dbus.UInt32(0), name,
                     service_type, domain, "", dbus.UInt16(port), txt(records))
    group.Commit()
    return group


def systemd_ready(status):
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return
    if address.startswith("@"):
        address = "\0" + address[1:]
    import socket
    notify = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        notify.connect(address)
        notify.sendall(("READY=1\nSTATUS=" + status).encode("utf-8"))
    finally:
        notify.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/opt/phantom/current/config.generated.json")
    parser.add_argument("--manifest", default="/opt/phantom/current/build-manifest.json")
    parser.add_argument("--boot-id", default="/run/phantom/controller/boot-id")
    args = parser.parse_args()
    config = read_json(args.config)
    manifest = read_json(args.manifest)
    network = config.get("network", {})
    if config.get("build_profile") != "Diagnostic" or config.get("actuator_scope_mask") != 0 or config.get("safety_observation_mask") != 0:
        raise SystemExit("mDNS Stage-3 publisher requires network-only Diagnostic profile")
    if (network.get("discovery_service_type"), network.get("discovery_domain"), network.get("ip_family")) != ("_phantom-ev3._udp", "local.", "IPV4"):
        raise SystemExit("mDNS service type/domain/IP family mismatch")
    bus = dbus.SystemBus()
    current = None
    group = None
    stopping = [False]
    signal.signal(signal.SIGTERM, lambda unused_a, unused_b: stopping.__setitem__(0, True))
    signal.signal(signal.SIGINT, lambda unused_a, unused_b: stopping.__setitem__(0, True))
    while not stopping[0]:
        try:
            boot = pathlib.Path(args.boot_id).read_text(encoding="ascii").strip()
            if len(boot) != 32:
                raise ValueError("boot id")
            if boot != current:
                if group is not None:
                    group.Reset()
                records = ["robot_id=" + config["robot_id"], "protocol_major=1",
                           "controller_boot_id=" + boot, "build_id=" + manifest["build_id"]]
                group = publish(bus, "PHANTOM-" + config["robot_id"], network["discovery_service_type"], network["discovery_domain"], int(network["listen_port_udp"]), records)
                current = boot
                print(json.dumps({"event": "DNS_SD_PUBLISHED", "robot_id": config["robot_id"],
                                  "port": int(network["listen_port_udp"]), "service_type": network["discovery_service_type"], "domain": network["discovery_domain"], "ip_family": network["ip_family"]}), flush=True)
                systemd_ready("DNS-SD service published")
        except (OSError, ValueError, dbus.DBusException) as error:
            print(json.dumps({"event": "DNS_SD_PUBLICATION_FAILED", "category": type(error).__name__}), flush=True)
        time.sleep(.25)
    if group is not None:
        group.Reset()


if __name__ == "__main__":
    main()
