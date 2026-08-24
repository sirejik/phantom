# Coordinated two-motor validation

All conclusions are limited to free Medium outA + Large outB at 50 Hz persistent FD. Motor results are intentionally separate.

| TEST | RESULT | VERDICT | CONFIDENCE | RUN_IDS | ARCHITECTURAL_IMPLICATION |
|---|---|---|---|---|---|
| D1 simultaneous free run | speed drop vs single: ev3-ports:outA duty 30: 82.4%; ev3-ports:outB duty 30: 7.0%; ev3-ports:outA duty 50: -40.0%; ev3-ports:outB duty 50: -77.9%; ev3-ports:outA duty 70: -34.7%; ev3-ports:outB duty 70: 29.0%; ev3-ports:outA: dt p99<= 33849.94us, misses=36; ev3-ports:outB: dt p99<= 33849.94us, misses=36 | MEASURED | medium | d1_20260824T140000Z, d1batch_30_0_20260824T141000Z (+18 more; raw filenames) | Separates electrical/motor interaction from loop timing. |
| D2 staggered start/stop | max other-motor delta=n/a counts/s; ev3-ports:outA: dt p99<= 35168.26us, misses=7; ev3-ports:outB: dt p99<= 35168.26us, misses=7 | MEASURED | medium | d2_20260824T142400Z | Start/reverse transients must be considered in multi-axis control. |
| D3 simultaneous reversal | ev3-ports:outA: dt p99<= 26035.07us, misses=6; ev3-ports:outB: dt p99<= 26035.07us, misses=6 | MEASURED | medium | d3_0_20260824T143000Z, d3_1_20260824T143000Z (+2 more; raw filenames) | Ramp reversal is evaluated separately from point-arrival tuning. |
| D4 continuous trajectories | ev3-ports:outA: dt p99<= 23624.86us, misses=1; ev3-ports:outB: dt p99<= 23624.86us, misses=1 | MEASURED | medium | d4_20260824T143300Z | Continuous streams are judged by tracking, not discrete arrival rate. |
| D5 custom synchronized P2P | arrival-axis rate=22.86%; p95 skew=54.01 ms; ev3-ports:outA: dt p99<= 23418.18us, misses=1; ev3-ports:outB: dt p99<= 23418.18us, misses=1 | MEASURED | medium | d5_20260824T143600Z, d5pair_0_20260824T145000Z, d5pair_1_20260824T145000Z | Compare planner/controller behavior without conflating the two. |
| D6 built-in baseline | arrival-axis rate=36.00%; p95 skew=1864.99 ms; ev3-ports:outA: dt p99<= 21724.52us, misses=0; ev3-ports:outB: dt p99<= 21724.52us, misses=0 | MEASURED | medium | d6_20260824T143900Z | Compare planner/controller behavior without conflating the two. |
| D7 latest-target-wins | target replacements logged=0; no raw rows | NOT_MEASURED | medium | n/a | New target replaces the previous reference; no waypoint queue is used. |
| D8 active 50 Hz loop | ev3-ports:outA: dt p99<= 21849.14us, misses=0; ev3-ports:outB: dt p99<= 21849.14us, misses=0; PARTIAL 1/3 files | PARTIAL_OR_NOT_MEASURED | medium | d8_1_20260824T144500Z | Direct evidence for active two-controller loop only; re-test with mechanics/4 motors/Wi-Fi. |
