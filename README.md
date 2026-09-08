# PHANTOM

The normative requirements are in `docs/PHANTOM_SPECIFICATION.md`. This tree
contains the Stage 1/2 software foundation: generated protocol/config
contracts, Quest observation runtime and pure logic, fail-closed EV3 runtime,
PC simulator, tracking replay and build/test/deployment gates.

Host tooling is declared in `toolchains/host-tools.json` and resolved by
`tools/toolchain.ps1`. Override any of it without editing scripts:
`PHANTOM_UNITY_ROOT`, `PHANTOM_ADB`, `PHANTOM_WSL_DISTRO`, `PHANTOM_GIT_BASH`.
The Unity version itself is pinned by `PhantomQuest/ProjectSettings/ProjectVersion.txt`.
See `docs/PHANTOM/ENGINEERING.md` §8.1.1.

Quick checks on Windows:

```powershell
python tools/specgen.py --check
python tools/docindex.py --check
python tools/doclint.py
python tools/protocolgen.py --check
python tools/configgen.py --check
python tools/implementation_map_check.py
python tools/test_jcs.py
python tools/test_ipc_contract.py
python tools/test_configgen.py
python tools/security_scan.py
powershell -File tools/quest_validation/compile_and_smoke.ps1
powershell -File tools/quest_validation/run_udp_integration.ps1
powershell -File scripts/quest-test.ps1
powershell -File scripts/quest-build.ps1 -Profile Release -Output build/quest/PhantomQuest-release.apk
powershell -File scripts/quest-build.ps1 -Profile Diagnostic -Output build/quest/PhantomQuest-diagnostic.apk
powershell -File scripts/ev3-host-build.ps1 -Profile Release
powershell -File scripts/ev3-armel-docker.ps1
powershell -File scripts/ev3-package.ps1
powershell -File scripts/pre-install-auto.ps1
```

Физические операции запускаются отдельно и не пересобирают artifacts. INSTALL проверяет
выбранные bytes и не требует предыдущих локальных reports; DEVICE AUTO требует exact
PRE-INSTALL PASS:

```powershell
powershell -File scripts/quest-install.ps1 -Apk <artifact.apk>
powershell -File scripts/quest-start.ps1 -Apk <artifact.apk>
powershell -File scripts/quest-device-auto.ps1 -Apk <artifact.apk>
powershell -File scripts/ev3-transfer.ps1 -Address <actual-ip-or-rndis-address> -Package <package.tar.gz>
powershell -File scripts/ev3-install.ps1 -Address <actual-ip-or-rndis-address> -BuildId <ev3_build_id>
powershell -File scripts/ev3-start.ps1 -Address <actual-ip-or-rndis-address> -BuildId <ev3_build_id>
powershell -File scripts/ev3-device-auto.ps1 -Address <actual-ip-or-rndis-address> -BuildId <ev3_build_id>
```

Before a Quest can open an authenticated CONTROL session it needs its control PSK
provisioned out of band (`docs/PHANTOM/ENGINEERING.md` §8.11.1):

```powershell
powershell -File scripts/quest-provision-credential.ps1 -KeyFile <path outside the repository>
```

The armel build uses the pinned
`ev3dev/debian-stretch-cross@sha256:819ea744...176a29f` image for both Release
and Diagnostic. `PRE-INSTALL AUTO` is the post-build gate and expects both
Quest APK profiles to exist with matching manifests.

No checked-in configuration authorizes physical movement. All safety-critical
`MEASURED` values, the Quest P0 qualification, EV3 DEVICE AUTO, mechanical
inspection and HIL must be completed on the named physical artifacts before
`READY`; see `mechanical/safety-inspection.md`.
