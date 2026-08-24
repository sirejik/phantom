# EV3 measurement pipeline fix report

## Observed failure

The first environment capture succeeded, but `results/ev3/raw` contained no CSV files and the analyzer reported `CSV rows: 0`.

## Root cause

The first E1 invocation ran as user `robot` and exited before it could create a `CsvLog`. `MotorSysfs` opens the motor `command` attribute for writing during construction; ev3dev returned:

```text
open /sys/class/tacho-motor/motor1/command: Permission denied
```

Therefore no bench process reached its loop or normal logger flush. SCP pulled the correct remote raw directory; it was empty because no CSV had been created. The analyzer then incorrectly treated zero rows as an ordinary all-inconclusive report.

## Corrections

- Runner commands execute the bench binary through `sudo -n`.
- `scripts/ev3-bench-setup-sudo` installs a passwordless sudo rule restricted to the exact bench binary path; it does not grant general passwordless sudo.
- Defaults now match the measured bench: Large=`outB` / `lego-ev3-l-motor`, Medium=`outA` / `lego-ev3-m-motor`. The runner verifies `driver_name` after address discovery.
- `ev3-bench smoke` writes a 10-second, 50 Hz, two-motor stationary CSV before any motor test. The runner displays remote `ls`, `wc -l`, `head`, and `tail`.
- CSV rows are buffered in RAM and appended about once per second; normal exit, `SIGINT`, `SIGTERM`, and `SIGHUP` close the remaining buffer. The follow-up smoke run `20260824T060728Z` produced 1,000 data rows after this change.
- The analyzer now exits non-zero and writes `ERROR: NO RAW MEASUREMENTS` when no valid raw row exists. Architecture recommendations are blocked in that state.

## Required proof before E1+

1. `smoke` must create approximately 1000 motor rows on the EV3.
2. Pull must place that CSV in `results/ev3/raw`.
3. The analyzer must report a non-zero CSV row count and an `E_SMOKE` run ID.
