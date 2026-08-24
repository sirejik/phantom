# EV3 architecture recommendations

This file does not modify PHANTOM_SPECIFICATION. Every recommendation below is traceable to captured free-bench rows.

## 1. Motor loop rate

MEASURED: E1_MINIMAL 50.000 Hz completed 3 stationary runs with p99 <= 21879.76 us, max <= 29331.00 us, and 0 missed periods.
RECOMMENDED: use 50.000 Hz as the present free-bench candidate rate, with telemetry/logging outside the control critical section.
CONFIDENCE: medium: three two-motor stationary repeats; untested with mechanics, load, or four motors.
EVIDENCE: E1_MINIMAL run ID 20260824T061932Z, repeats 1-3 at the listed rate.

## 2. Persistent FD

MEASURED: 25 Hz: persistent work p99=30718.27 us vs reopen=45841.54 us; misses=10 vs 78; 50 Hz: persistent work p99=28234.48 us vs reopen=36413.78 us; misses=350 vs 1060.
RECOMMENDED: use persistent FDs for the motor wrapper; they improved p99 work time and missed-period count in both alternating three-run samples.
CONFIDENCE: medium for this EV3/free two-motor scope.
EVIDENCE: e1alt_25hz_20260824T065803Z and e1alt_50hz_20260824T071034Z, persistent/reopen alternating runs 1-6.

## 3. Worst-case latency cause

MEASURED: in E1.5, logger flush p99=30776.88 us, logger enqueue p99=8415.76 us, battery-read p99=12054.96 us, while diagnostic tick-work p99=106072.88 us and dt p99=113970.99 us.
RECOMMENDED: keep battery reads, state/duty diagnostics, CSV formatting, and filesystem flushing outside the fast loop. E1.5 does not establish a separate scheduling/descheduling cause because its dt tail was comparable to measured in-tick work.
CONFIDENCE: high for the measured diagnostic workload; medium for extrapolation to the minimal loop.
EVIDENCE: e1_5_20260824T061706Z_persistent_50hz_stationary_decomposition.csv (run 20260824T061706Z).

## 4. Telemetry and logging placement

MEASURED: E1_MINIMAL excludes battery reads, CSV formatting, filesystem logging, and diagnostics from the critical section; its 50 Hz three-run sample had zero missed periods. E1.5 measures costly logger and battery operations when they are included.
RECOMMENDED: retain the preallocated post-test buffer strategy (or a separately measured writer) and prohibit telemetry/file I/O in the control critical section.
CONFIDENCE: medium-high for stationary scheduling; no claim for network telemetry or loaded mechanics.
EVIDENCE: E1_MINIMAL run ID 20260824T061932Z; E1.5 run ID 20260824T061706Z.

## 5. run-direct local controller

MEASURED: C2 re-tested P/PD with C1 static feed-forward (best RMSE=6.56 counts). In C4, 100 ±90-degree cycles produced arrival rates ev3-ports:outA=0.0%; ev3-ports:outB=36.5%.
RECOMMENDED: do not reject run-direct based on E4/E8 dead-zone-limited gains. The present V2 tuning is NOT CONFIRMED because C4 did not reach 95% arrival on both motors; re-tune with the real mechanism.
CONFIDENCE: medium for this precise free-motor failure result.
EVIDENCE: C1 c1_20260824T120500Z; C2 c2_20260824T122000Z; C4 c4_20260824T124000Z.

## 6. Separate safety supervisor

MEASURED: C6 performed n=10 each for SIGKILL, SIGSTOP, SIGTERM, abort, and the no-supervisor external-watchdog baseline on free Large.
RECOMMENDED: retain a separate heartbeat supervisor. Its fault detection is repeatably measured; loaded stopping travel remains unmeasured.
CONFIDENCE: medium for this free Large/current 100 ms heartbeat scope.
EVIDENCE: c6_20260824T130500Z plus c6 retry/baseline raw rows.

## 7. Medium motor-side proportional gripper

MEASURED: C5 V2 2-second sine/triangle strokes yielded p95 position error run-direct-pd-v2-sine=7.08; run-direct-pd-v2-triangle=9.65.
RECOMMENDED: this is a measured motor-only trajectory result, not gripper confirmation. Retest after gearing/linkage/backlash/gravity are present.
CONFIDENCE: medium for free Medium only.
EVIDENCE: c5_20260824T130000Z.

## 8. Measured tuning seeds

MEASURED: C1 99% start/sustain thresholds: ev3-ports:outA - start99=24%, sustain=15%; ev3-ports:outA + start99=24%, sustain=17%; ev3-ports:outB - start99=16%, sustain=10%; ev3-ports:outB + start99=11%, sustain=10%.
RECOMMENDED: use only the conservative free-shaft seeds (Medium 24%; Large 16%) for initial V2 friction compensation; do not freeze them as loaded thresholds.
EVIDENCE: c1_20260824T120500Z, 10 randomized trials per duty/direction.

## 9. Still requires ready mechanics

- C4 arrival/drift after controller retuning with actual gearing/load.
- Loaded duty/speed, acceleration, stopping travel, backlash, compliance, gravity, and thermal behavior.
- Real gripper linkage/contact behaviour and labelled stall controls (E7).
- Loaded emergency stop travel and heartbeat timeout validation; four-motor and Wi-Fi remeasurement.

## Coordinated two-motor evidence

- D1: complete; see `COORDINATED_TWO_MOTOR_VALIDATION.md`. Do not generalize any partial protocol to production.
- D2: complete; see `COORDINATED_TWO_MOTOR_VALIDATION.md`. Do not generalize any partial protocol to production.
- D3: complete; see `COORDINATED_TWO_MOTOR_VALIDATION.md`. Do not generalize any partial protocol to production.
- D4: complete; see `COORDINATED_TWO_MOTOR_VALIDATION.md`. Do not generalize any partial protocol to production.
- D5: complete; see `COORDINATED_TWO_MOTOR_VALIDATION.md`. Do not generalize any partial protocol to production.
- D6: complete; see `COORDINATED_TWO_MOTOR_VALIDATION.md`. Do not generalize any partial protocol to production.
- D7: partial 0/1; see `COORDINATED_TWO_MOTOR_VALIDATION.md`. Do not generalize any partial protocol to production.
- D8: partial 1/3; see `COORDINATED_TWO_MOTOR_VALIDATION.md`. Do not generalize any partial protocol to production.