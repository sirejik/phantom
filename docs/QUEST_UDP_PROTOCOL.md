# Phantom Quest UDP protocol

All multi-byte values are little-endian. Every datagram starts with the ASCII
magic `PHNT`, represented as the little-endian `uint32` value `0x544E4850`.
The CRC-32 is calculated over the complete datagram except its final four CRC
bytes. A new random `session_id` is generated for each Quest application run.

## Target datagram (Quest to simulator/robot)

The packet is 48 bytes:

| Offset | Type | Field |
|---:|---|---|
| 0 | `uint32` | magic |
| 4 | `uint8` | protocol version (`1`) |
| 5 | `uint8` | message type (`1`, target) |
| 6 | `uint16` | flags (`bit 0 = enable`, `bit 1 = safe hold`) |
| 8 | `uint32` | session ID |
| 12 | `uint32` | sequence number |
| 16 | `uint64` | sender monotonic time, microseconds |
| 24 | `float32[3]` | target joints `q0..q2`, radians |
| 36 | `float32` | target gripper, normalized `0..1` |
| 40 | `uint32` | reserved (`0`) |
| 44 | `uint32` | CRC-32 |

Targets are absolute. The receiver must never integrate them as per-frame
deltas. Sequence comparisons are wrap-safe; duplicate and older packets are
ignored.

## HELLO and HELLO_ACK

HELLO uses the target packet envelope with message type `2`. HELLO_ACK uses
message type `3` and is 84 bytes. In addition to the common header it reports
protocol/capability flags, three joint minima, three joint maxima, maximum
velocity, maximum acceleration, watchdog timeout and CRC-32.

The Quest side does not enter `TRACKING` until a valid ACK for the current
session has been received. A session mismatch, invalid CRC or unsupported
protocol keeps networking unready.

## Telemetry datagram (robot/simulator to Quest)

Telemetry uses message type `4` and is 84 bytes. It contains the common
session/sequence header, actual joints, commanded joints, actual gripper,
robot status flags, last accepted target sequence, reserved bytes and CRC-32.

The Quest client rejects invalid CRC, wrong-session and duplicate/old
telemetry. Missing telemetry beyond the configured timeout removes network
readiness and drives the runtime into latched `SAFE_HOLD`; resumption requires
readiness recovery followed by an explicit user release and a new absolute
anchor.
