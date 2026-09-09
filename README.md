# PHANTOM

PHANTOM is a safety-oriented teleoperation system: Meta Quest 3 supplies user intent and
LEGO Mindstorms EV3 remains authoritative for state, safety gates, and motor I/O. The
normative specification is generated as `docs/PHANTOM_SPECIFICATION.md`; engineering
commands and lifecycle rules are owned by `docs/PHANTOM/ENGINEERING.md`.

The lifecycle has explicit, independently invoked phases:

```text
TEST → BUILD → PROVISION → TRANSFER → INSTALL → START → DEBUG
     → DEVICE INTEGRATION TEST → HIL → MANUAL ACCEPTANCE → RECOVERY
```

No phase silently runs another phase. In particular, BUILD does not run tests, INSTALL does
not build or test, START does not provision, and DEVICE INTEGRATION TEST does not install.
`build/**` and `results/**` are disposable local data and are not prerequisites for installing
already selected bytes.

Cleanup is explicit and dry-run by default: `scripts/build-clean.ps1` for build outputs and
`scripts/results-clean.ps1` for local reports; add `-Apply` only after reviewing the targets.

Typical off-device development commands:

```powershell
scripts\phantom.cmd TEST QUEST
scripts\phantom.cmd TEST EV3
scripts\phantom.cmd BUILD QUEST -Profile Diagnostic
scripts\phantom.cmd BUILD EV3 -Profile Diagnostic
```

Provisioning is a separate, infrequent administrative operation. One idempotent fixed-pair
command creates the exact Quest ADB identity, pinned EV3 SSH trust, separate deployment key,
CONTROL credential and maintenance/platform state. Private state lives outside the repository
under `%LOCALAPPDATA%\PHANTOM` by default.

```powershell
scripts\phantom.cmd PROVISION PAIR -HostFingerprint <trusted-SHA256:...>
```

The project is deployed to one designated Quest 3 and one designated EV3. EV3 maintenance
uses the standard ev3dev mDNS hostname `ev3dev.local` directly; the pinned SSH host
fingerprint, not a saved IP address or an extra alias, authenticates the brick. The
private SSH policy accepts the resolved IPv4 or IPv6 transport only when the pinned host key
matches. Routine Quest operations likewise address only the stored exact ADB serial.

Deployment commands consume existing artifacts and installed/provisioned state. See §8.5 of
`docs/PHANTOM/ENGINEERING.md` for exact arguments and error categories.

No checked-in configuration authorizes physical movement. Simulator output, builds, and
software tests are never hardware PASS. Physical DEVICE INTEGRATION TEST, HIL, safety
inspection, and applicable P0/acceptance gates remain required for the named installed
artifacts and physical assembly.
