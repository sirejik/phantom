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

Provisioning is a separate, infrequent administrative operation. Quest CONTROL credentials
are stored in Android Keystore-backed storage; EV3 SSH trust, maintenance helpers, users, and
the Wi-Fi autoconnect platform unit are provisioned separately from application releases.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/quest-provision-credential.ps1 -KeyFile <outside-repository-path>
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ev3-provision-maintenance.ps1 -Address <actual-ip> -HostFingerprint <SHA256:...>
```

Deployment commands consume existing artifacts and installed/provisioned state. See §8.5 of
`docs/PHANTOM/ENGINEERING.md` for exact arguments and error categories.

No checked-in configuration authorizes physical movement. Simulator output, builds, and
software tests are never hardware PASS. Physical DEVICE INTEGRATION TEST, HIL, safety
inspection, and applicable P0/acceptance gates remain required for the named installed
artifacts and physical assembly.
