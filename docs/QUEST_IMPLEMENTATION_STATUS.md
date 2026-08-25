# Quest Implementation Status

## Implemented

- Pure C# canonical right-handed math (`+X` forward, `+Y` left, `+Z` up), fixed-branch 3-DOF IK/FK, NaN/Inf rejection, workspace and joint projection.
- Absolute wrist/shoulder mapping with engage anchors. It never integrates frame deltas; release freezes and re-engage anchors at the current TCP.
- Robust weighted shoulder sphere fit, provisional plausibility/coverage checks, head-translation-only runtime shoulder model, and calibration-zone/body-translation rejection.
- SDK adapters for right Wrist/Palm and common grasp, and left Touch Plus pose/buttons/grip/haptics.
- Conditional real MRUK adapter for device room load/floor authority and official QR trackables. Six marker payloads feed a stationary 1.0 s calibration window with outlier rejection and pose variance before geometry locks; marker updates are not used as servo feedback after lock.
- Safety state machine with Grip hysteresis, HOLD/SAFE_HOLD, transition logging, and mandatory release before recovery from SAFE_HOLD.
- Explicit 48-byte little-endian UDP target codec with CRC32, session/sequence handling, capability handshake, telemetry, and latest-target-wins client behavior.
- PC EV3 simulator with lag, velocity/acceleration/joint limits, watchdog, packet loss, latency, burst loss, stale/wrong-session/disconnect/fault scenarios.
- JSONL logging to `Application.persistentDataPath`, raw tracking replay source, a right-offset translucent head-locked HUD, and guided Q0-Q14 scenarios with Russian titles, purposes, exact actions, progress counters, and completion markers.
- Analyzer that emits validation, architecture, and user-calibration reports and refuses `CONFIRMED` without Android device data.
- Batch Unity test, Android build, and ADB log-pull helpers.
- MRUK 205.0.0 and Meta XR Core 205.0.0 resolved successfully; the conditional room/QR adapter compiled in Unity.
- Meta XR Platform SDK 205.0.0 is configured with App ID `1405011949353501` for package `dev.phantom.questprototype`.
- A permanent RSA-4096 release keystore is stored under the git-ignored `.secrets/quest-release/` directory and injected only during release builds.

## Device-confirmed

Quest 3 runs have confirmed passthrough, room localization, simultaneous hand/controller operation, physical QR detection, stable memory use, and the normal Quest-to-PC UDP path. The latest analyzed verdicts before v17 are: Q3 and Q4 confirmed; Q1 and Q5 rejected against their current thresholds; Q0, Q2 and Q11 inconclusive; the remaining scenarios are not yet fully measured.

Release v16 reproduced a time-dependent distortion of every rendered XR object (text, hands and rays) while the passthrough image stayed stable. Frame rate remained close to 72 FPS and memory stayed stable, so the symptom is not explained by a managed-memory leak. Release v17 is the physical-validation candidate: it makes XRI the only active pose/render rig, keeps the Meta rig passive for services, disables the duplicate late-latch/foveation path, and changes Android rendering from Vulkan to OpenGL ES 3. This is not considered fixed until a headset run confirms it.

## Simulator-confirmed

- Python simulator protocol tests: 4/4 passed (golden vector, CRC/NaN rejection, stale/wrong-session rejection, response sizes); analyzer tests: 2/2 passed.
- Pure core smoke passed: 10,000 reachable IK/FK cases, 100,001-frame absolute drift test, protocol golden vector, robust sphere fit, and safety recovery latch.
- Real localhost UDP integration passed: C# Quest client → Python simulator handshake/capabilities → absolute target → moving `q_actual`/grip telemetry.
- Pure core, runtime, MRUK adapter, Editor build script, and NUnit test sources compiled against the resolved Unity/package assemblies.
- Unity EditMode Test Runner passed 13/13 tests.
- Android ARM64 IL2CPP development APK built successfully at `build/quest/PhantomQuest.apk` (132,080,463 bytes; SHA-256 `9696636fb1a69b2bbce6772499a5d5d6082a2bcdf20c27ad6d5a488d5afd93af`). APK inspection confirmed API 34, ARM64, GameActivity, OpenXR, hand tracking, and Scene permission.
- Android ARM64 IL2CPP release APK versionCode 17 built successfully at `build/quest/PhantomQuest-release.apk` (99,228,484 bytes; SHA-256 `2b3733ee5de3b30bf6d6b76dfe082cb0c1f250c2fb87d357ae4c4dac4e673913`). It uses package `dev.phantom.questprototype`, OpenGL ES 3, APK Signature Scheme v2, and the permanent release certificate SHA-256 `2374d7eeeaa983ae4b8bf7d24721b4f410d9eb83264b03ca7a6271099c3c1dd7`.

## Waiting for further physical runs

- Install v17, first observe the HUD, hands and rays for several minutes in passthrough, including slow head motion and a Meta-menu round trip. Record whether distortion remains and when it starts.
- If that stability gate passes, execute the complete guided Q0-Q14 set and pull all JSONL files with `scripts/quest-pull-logs.ps1`.
- Q6-Q8 and Q13-Q14 require the corresponding printed marker set and/or physical robot fixture. Tests that need unavailable mechanics remain blocked rather than simulated.

## Rejected assumptions

- “MRUK was already available”: rejected by the original manifest, lock, Assets, and installed package-source inventory. A minimal MRUK dependency was then added and resolved.
- “The originally installed Meta OpenXR stack alone contains a QR trackable API”: rejected by installed-source search. Official QR tracking is supplied by MRUK, not the pre-existing plane/anchor/mesh APIs.
- No tracking-quality, grasp-curve, Wrist-vs-Palm, calibration-threshold, or QR verdict has been rejected or confirmed; those remain unmeasured.

## Still open

- Run Meta Project Setup checks and verify Scene permission/QR support on the actual headset. Base marker fixture offset/Euler values remain device/rig configuration.
- Replace provisional calibration/workspace thresholds only after analyzer results from the required runs.
- Complete the on-device QR and user-calibration runs. Their accepted results are already wired into `PhantomRuntime`; until both pass their provisional quality gates, the runtime deliberately cannot enter READY/TRACKING.
- Upload/install the release-signed Alpha build and execute the physical validation matrix.
- Add controller-driven selection for all validation matrix cells and production spatial UI/ghost/robot overlays after blocker APIs are present.

## Package/version pins

See `results/quest/environment.json`. MRUK 205.0.0 and Meta XR Platform SDK 205.0.0 are direct manifest dependencies; no pre-existing package was upgraded. Resolution and Unity compilation succeeded.
