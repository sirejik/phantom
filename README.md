# PHANTOM

The normative requirements are in `docs/PHANTOM_SPECIFICATION.md`. This tree
contains the Stage 1/2 software foundation: generated protocol/config
contracts, Quest observation runtime and pure logic, fail-closed EV3 runtime,
PC simulator, tracking replay and build/test/deployment gates.

Quick checks on Windows:

```powershell
python tools/protocolgen.py --check
python tools/configgen.py --check
powershell -File tools/quest_validation/compile_and_smoke.ps1
powershell -File tools/quest_validation/run_udp_integration.ps1
powershell -File scripts/quest-test.ps1
powershell -File scripts/quest-build.ps1 -Profile Release -Output build/quest/PhantomQuest-release.apk
powershell -File scripts/quest-build.ps1 -Profile Diagnostic -Output build/quest/PhantomQuest-diagnostic.apk
powershell -File scripts/ev3-host-build.ps1 -Profile Release
powershell -File scripts/ev3-armel-docker.ps1
powershell -File scripts/pre-install-auto.ps1
powershell -File scripts/quest-device-auto.ps1
powershell -File scripts/ev3-package.ps1
```

The armel build uses the pinned
`ev3dev/debian-stretch-cross@sha256:819ea744...176a29f` image for both Release
and Diagnostic. `PRE-INSTALL AUTO` is the post-build gate and expects both
Quest APK profiles to exist with matching manifests.

No checked-in configuration authorizes physical movement. All safety-critical
`MEASURED` values, the Quest P0 qualification, EV3 DEVICE AUTO, mechanical
inspection and HIL must be completed on the named physical artifacts before
`READY`; see `mechanical/safety-inspection.md`.
