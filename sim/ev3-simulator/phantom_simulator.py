#!/usr/bin/env python3
"""Production-protocol EV3 stand-in for Phantom Quest validation."""
import argparse
import heapq
import json
import math
import random
import socket
import struct
import time
import zlib

MAGIC = 0x544E4850
VERSION = 1
TARGET = struct.Struct("<IHHQIQffffI")
HELLO_ACK_BODY = struct.Struct("<IHHQII12fB3xI")
TELEMETRY_BODY = struct.Struct("<IHHQIIIQ11f")
FLAG_HELLO, FLAG_TRACKING, FLAG_HOLD, FLAG_SAFE_HOLD = 1, 2, 4, 8
STATE_HOLD, STATE_TRACKING, STATE_FAULT = 1, 2, 3

SCENARIOS = {
    "normal": dict(loss=0.0, delay_ms=0, jitter_ms=0, burst=0),
    "latency100": dict(loss=0.0, delay_ms=100, jitter_ms=0, burst=0),
    "loss5": dict(loss=0.05, delay_ms=0, jitter_ms=0, burst=0),
    "burst_loss": dict(loss=0.0, delay_ms=0, jitter_ms=0, burst=40),
    "stale": dict(loss=0.0, delay_ms=0, jitter_ms=0, burst=0),
    "wrong_session": dict(loss=0.0, delay_ms=0, jitter_ms=0, burst=0),
    "disconnect": dict(loss=0.0, delay_ms=0, jitter_ms=0, burst=0),
    "fault": dict(loss=0.0, delay_ms=0, jitter_ms=0, burst=0),
}

def crc_packet(body):
    return body + struct.pack("<I", zlib.crc32(body) & 0xffffffff)

def is_newer(candidate, reference):
    delta = (candidate - reference) & 0xffffffff
    return candidate != reference and delta < 0x80000000

def decode_target(data):
    if len(data) != TARGET.size:
        return None
    values = TARGET.unpack(data)
    if values[0] != MAGIC or values[1] != VERSION or zlib.crc32(data[:-4]) & 0xffffffff != values[-1]:
        return None
    if not all(math.isfinite(v) for v in values[6:10]):
        return None
    return dict(flags=values[2], session=values[3], seq=values[4], client_us=values[5], q=list(values[6:9]), grip=values[9])

class Simulator:
    q_min = [-2.8, -1.2, 0.0]
    q_max = [2.8, 1.4, 2.8]
    max_vel = [1.8, 1.4, 1.6]
    max_acc = [5.0, 4.0, 4.0]

    def __init__(self, scenario="normal", seed=7341):
        self.scenario = scenario
        self.options = SCENARIOS[scenario]
        self.random = random.Random(seed)
        self.session = None
        self.client = None
        self.last_seq = 0
        self.have_seq = False
        self.q = [0.0, 0.0, 0.5]
        self.speed = [0.0, 0.0, 0.0]
        self.target = list(self.q)
        self.duty = [0.0, 0.0, 0.0]
        self.grip_target = self.grip = 0.0
        self.state = STATE_HOLD
        self.fault = 0
        self.last_command = time.monotonic()
        self.started = time.monotonic()
        self.queue = []
        self.received = self.invalid = self.stale = self.dropped = 0

    def queue_datagram(self, data, address, now):
        self.received += 1
        if self.random.random() < self.options["loss"]:
            self.dropped += 1
            return
        elapsed = now - self.started
        if self.options["burst"] and 3.0 <= elapsed % 8.0 <= 4.0:
            self.dropped += 1
            return
        delay = (self.options["delay_ms"] + self.random.uniform(-self.options["jitter_ms"], self.options["jitter_ms"])) / 1000.0
        heapq.heappush(self.queue, (now + max(0, delay), data, address))

    def drain(self, now):
        replies = []
        while self.queue and self.queue[0][0] <= now:
            _, data, address = heapq.heappop(self.queue)
            packet = decode_target(data)
            if packet is None:
                self.invalid += 1
                continue
            if packet["flags"] & FLAG_HELLO:
                self.session, self.client = packet["session"], address
                self.last_seq, self.have_seq = packet["seq"], True
                self.last_command = now
                replies.append((self.hello_ack(), address))
                continue
            if packet["session"] != self.session:
                continue
            if self.have_seq and not is_newer(packet["seq"], self.last_seq):
                self.stale += 1
                continue
            self.last_seq, self.have_seq, self.last_command = packet["seq"], True, now
            self.target = [max(lo, min(hi, q)) for q, lo, hi in zip(packet["q"], self.q_min, self.q_max)]
            self.grip_target = max(0.0, min(1.0, packet["grip"]))
            self.state = STATE_TRACKING if packet["flags"] & FLAG_TRACKING else STATE_HOLD
        return replies

    def update(self, dt, now):
        if now - self.last_command > 0.25:
            self.state = STATE_HOLD
        if self.scenario == "fault" and now - self.started > 3:
            self.state, self.fault = STATE_FAULT, 1
        for i in range(3):
            desired = max(-self.max_vel[i], min(self.max_vel[i], (self.target[i] - self.q[i]) * 8.0)) if self.state == STATE_TRACKING else 0.0
            dv = max(-self.max_acc[i] * dt, min(self.max_acc[i] * dt, desired - self.speed[i]))
            self.speed[i] += dv
            self.q[i] = max(self.q_min[i], min(self.q_max[i], self.q[i] + self.speed[i] * dt))
            self.duty[i] = self.speed[i] / self.max_vel[i]
        self.grip += (self.grip_target - self.grip) * min(1, dt * 8)

    def hello_ack(self):
        body = HELLO_ACK_BODY.pack(MAGIC, VERSION, 1, self.session, self.last_seq, 0,
            *(self.q_min + self.q_max + self.max_vel + self.max_acc), 1, 0x45563301)
        return crc_packet(body)

    def telemetry(self, now):
        session = self.session
        seq = self.last_seq
        if self.scenario == "wrong_session" and now - self.started > 3:
            session ^= 0x55
        if self.scenario == "stale" and now - self.started > 3:
            seq = (seq - 5) & 0xffffffff
        body = TELEMETRY_BODY.pack(MAGIC, VERSION, 2, session, seq, self.state, self.fault,
            int((now - self.started) * 1_000_000), *(self.q + self.speed + self.duty + [self.grip, (now - self.last_command) * 1000]))
        return crc_packet(body)

def run(args):
    sim = Simulator(args.scenario, args.seed)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))
    sock.setblocking(False)
    print(json.dumps({"event":"listening","bind":args.bind,"port":args.port,"scenario":args.scenario}), flush=True)
    previous = telemetry_at = status_at = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            try:
                while True:
                    data, address = sock.recvfrom(2048)
                    sim.queue_datagram(data, address, now)
            except BlockingIOError:
                pass
            for data, address in sim.drain(now):
                sock.sendto(data, address)
            sim.update(min(0.05, now - previous), now)
            previous = now
            disconnected = args.scenario == "disconnect" and 3 <= (now - sim.started) <= 6
            if sim.client and now >= telemetry_at and not disconnected:
                sock.sendto(sim.telemetry(now), sim.client)
                telemetry_at = now + 0.02
            if now >= status_at:
                print(json.dumps({"event":"status","session":sim.session,"last_seq":sim.last_seq,"state":sim.state,"q_actual":sim.q,"received":sim.received,"dropped":sim.dropped,"stale":sim.stale,"invalid":sim.invalid}), flush=True)
                status_at = now + 1
            time.sleep(0.002)
    except KeyboardInterrupt:
        print(json.dumps({"event":"stopped","received":sim.received,"dropped":sim.dropped,"stale":sim.stale,"invalid":sim.invalid}), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=31337)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="normal")
    parser.add_argument("--seed", type=int, default=7341)
    run(parser.parse_args())

if __name__ == "__main__":
    main()
