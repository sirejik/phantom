# Quest Environment Inventory

- Unity: `6000.3.22f1` (`1c726e1fb402`).
- Meta XR OpenXR: `2.5.1`; OpenXR Plugin: `1.17.1`; XR Hands: `1.8.1`; XR Interaction Toolkit: `3.5.1`; AR Foundation: `6.5.0`.
- MRUK before implementation: absent. `com.meta.xr.mrutilitykit` `205.0.0` was added and resolved with `com.meta.xr.sdk.core` `205.0.0`.
- Meta XR Platform SDK `205.0.0` is installed. `OculusPlatformSettings.asset` sets both desktop and mobile App ID to `1405011949353501`; Android package remains `dev.phantom.questprototype`.
- Meta Interaction SDK: not present. XRI is present, but it is not Meta Interaction SDK.
- Android: min/target API 34, ARM64 setting, IL2CPP, bundled Build Tools 36.0.0, NDK r27c, OpenJDK 17.0.18.
- Android OpenXR config enables Meta Quest, Oculus Touch, Touch Plus, Hand Tracking, and Meta Hand Tracking Aim. Meta plane/anchor/bounding-box/raycast features are disabled.

Verified from installed source, not recalled API names:

- Wrist/Palm: `XRHand.GetJoint(...).TryGetPose`.
- Grasp: `XRHandSubsystem.rightHandCommonGestures.TryGetGraspValue`; its boolean is preserved as `ready`, so unavailable data is not interpreted as open.
- Left controller: `UnityEngine.XR.InputDevices` with `CommonUsages.grip`, `gripButton`, `trigger`, `primaryButton`, and `secondaryButton`.

No existing package version was changed. The Meta assembly compiled against the resolved official MRUK room and QR APIs. The originally installed Meta OpenXR package exposes AR Foundation scene planes/anchors but no QR/marker trackable API; those APIs are not treated as equivalent.

Verification on 2026-08-24:

- Unity EditMode tests: 13/13 passed.
- Android ARM64 IL2CPP development build: succeeded; `build/quest/PhantomQuest.apk`, 132,080,463 bytes, SHA-256 `9696636fb1a69b2bbce6772499a5d5d6082a2bcdf20c27ad6d5a488d5afd93af`. APK inspection confirmed API 34, ARM64, `UnityPlayerGameActivity`, OpenXR, `HAND_TRACKING`, and `com.oculus.permission.USE_SCENE`.
- A Quest 3 was connected; a development APK was installed and Scene permission granted. The run did not qualify any Q0-Q12 result because Horizon OS rejected Scene/QR discovery as an untrusted sideloaded package.

Release preparation on 2026-08-25:

- A permanent RSA-4096 release key was created at `.secrets/quest-release/phantom-quest-release.keystore`; its password file is beside it. The whole directory and common keystore extensions are git-ignored, and an exact-value scan found no password outside `.secrets`.
- `build/quest/PhantomQuest-release.apk`: versionCode 3, 117,138,694 bytes, SHA-256 `c908dcdb11a2a3b93ee147d13f351259fdab3e0c8cea7301f0ae9ad98fd6472d`.
- Verified non-debuggable, zip-aligned, APK Signature Scheme v2, RSA-4096 certificate SHA-256 `2374d7eeeaa983ae4b8bf7d24721b4f410d9eb83264b03ca7a6271099c3c1dd7`, package `dev.phantom.questprototype`, App ID present in packaged Unity data.
- The release APK was installed on the connected Quest 3 after the package/user was registered in Meta Alpha. Horizon OS accepted Meta trust (`PackageUntrusted=0`), both Scene permission aliases remained granted, and the runtime log had no fatal, `OVRCameraRig`, or `NullReferenceException` error. With the headset active, UDP handshake to the PC simulator at `192.168.0.112:31337` succeeded and the device log reported `network_ready=true`; room/QR physical validation remains separate.
