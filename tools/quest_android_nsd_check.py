#!/usr/bin/env python3
"""Static contract audit for the Android boundary the Quest client depends on.

Nothing here replaces a device run; it only proves the pieces the device gate
needs are actually compiled in. Two of them were previously documented but
absent: the bounded MulticastLock, and any implemented way to get the CONTROL
PSK into the Keystore-wrapped store.
"""
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parents[1]
androidlib = root / "PhantomQuest/Assets/Plugins/Android/PhantomScenePermissions.androidlib"
java = (androidlib / "src/main/java/dev/phantom/nsd/PhantomNsdBridge.java").read_text(encoding="utf-8")
csharp = (root / "PhantomQuest/Assets/Phantom/Networking/AndroidNsdDiscoveryBackend.cs").read_text(encoding="utf-8")
manifest = (androidlib / "AndroidManifest.xml").read_text(encoding="utf-8")
credential_java = (androidlib / "src/main/java/dev/phantom/security/PhantomCredentialStore.java").read_text(encoding="utf-8")
credential_csharp = (root / "PhantomQuest/Assets/Phantom/Networking/ControlCredentials.cs").read_text(encoding="utf-8")
runtime_csharp = (root / "PhantomQuest/Assets/Phantom/PhantomRuntime.cs").read_text(encoding="utf-8")
device_auto_csharp = (root / "PhantomQuest/Assets/Phantom/Diagnostics/QuestDeviceAuto.cs").read_text(encoding="utf-8")
provisioning_script = (root / "scripts/quest-provision-credential.ps1").read_text(encoding="utf-8")

REQUIRED = [
    ("NSD bridge", java, (
        "NsdManager.DiscoveryListener", "NsdManager.ResolveListener",
        "void onResolved(String instance, String serviceType, String host, int port",
        "void onLost(String instance, String serviceType)", "getAttributes()", "stopServiceDiscovery",
        # Bounded MulticastLock, acquired for discovery and released on every exit.
        "WifiManager.MulticastLock", "createMulticastLock", "acquireMulticastLock()",
        "releaseMulticastLock()", "isMulticastLockHeld",
        # Service type normalization down to `_service._proto`.
        "static String normalize(String value)", '"._udp"', '"._tcp"',
    )),
    ("NSD C# adapter", csharp, (
        "AndroidJavaProxy", "PhantomNsdBridge$Listener",
        "public void onResolved(string instance,string serviceType,string host,int port",
        "public void onLost(string instance,string serviceType)",
        '_bridge?.Call("stop")', "AndroidServiceType(serviceType)",
        "NormalizeServiceType", "MulticastLockHeld",
    )),
    ("Android manifest", manifest, (
        "android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE",
        "android.permission.CHANGE_WIFI_MULTICAST_STATE",
        # Required to obtain WifiManager at all.
        "android.permission.ACCESS_WIFI_STATE",
    )),
    ("credential store (Java)", credential_java, (
        '"AndroidKeyStore"', '"AES/GCM/NoPadding"', "GCMParameterSpec(128",
        "updateAAD(keyId.getBytes(StandardCharsets.US_ASCII))", "Context.MODE_PRIVATE",
        # One-shot out-of-band import plus shredding of the plaintext drop.
        "importProvisioningDrop", "isProvisioned", "PROVISIONING_DIRECTORY",
        "getExternalFilesDir", "shred(", "decodeKeyMaterial",
    )),
    ("credential store (C#)", credential_csharp, (
        "UNITY_ANDROID && !UNITY_EDITOR", "dev.phantom.security.PhantomCredentialStore",
        'GetStatic<AndroidJavaObject>("currentActivity")', 'CallStatic<byte[]>("load",activity,keyId)',
        "catch(AndroidJavaException)",
        'CallStatic<int>("importProvisioningDrop",activity,keyId)', "TryImportProvisioningDrop",
        "IsProvisioned", "DecodeKeyMaterial",
    )),
    ("runtime wiring", runtime_csharp, (
        "TryImportProvisioningDrop", "ControlCredentialProvisioned", "control_credential",
    )),
    ("device evidence", device_auto_csharp, (
        "quest-control-credential-present", "quest-log-storage-healthy",
    )),
    ("host provisioning path", provisioning_script, (
        "phantom-provisioning", "adb", "Diagnostic",
    )),
]

# The provisioning path must never echo, embed or persist the key itself.
FORBIDDEN = [
    ("host provisioning path", provisioning_script, ("Write-Output $keyBytes", "Write-Host $key")),
    ("runtime wiring", runtime_csharp, ("Convert.ToBase64String(key", "_key.ToString()")),
]

missing = []
for label, text, required in REQUIRED:
    for value in required:
        if value not in text:
            missing.append("%s: %s" % (label, value))
for label, text, forbidden in FORBIDDEN:
    for value in forbidden:
        if value in text:
            missing.append("%s: forbidden credential echo %s" % (label, value))

if missing:
    print("Android boundary contract audit missing:")
    for value in missing:
        print("  - " + value)
    sys.exit(1)
print("Android boundary contract PASS: NSD callbacks/lifecycle/permissions, bounded MulticastLock, "
      "service-type normalization, Keystore-wrapped credentials and an implemented out-of-band "
      "provisioning path with device evidence")
