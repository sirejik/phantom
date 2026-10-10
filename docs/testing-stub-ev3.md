# Stub EV3 для тестов

Run from the repository root:

```powershell
python sim/ev3-simulator/phantom_simulator.py --scenario normal
```

Available deterministic scenarios: `normal`, `latency100`, `loss5`, `burst_loss`,
`stale`, `wrong_session`, `disconnect`, and `fault`. The simulator implements the
same bounded, little-endian, HMAC-SHA-256-authenticated protocol v1 as Quest. It accepts absolute joint
targets only and models joint/velocity/acceleration limits, lag, watchdog HOLD, and
gripper lag. It never performs IK.

Quest must be configured with the PC's LAN address; `127.0.0.1` only works when both
processes run on the same host (for Editor/integration work). Allow inbound UDP 30470
in the host firewall when testing from a headset.
