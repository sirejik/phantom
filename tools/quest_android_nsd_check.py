#!/usr/bin/env python3
import pathlib,sys
root=pathlib.Path(__file__).resolve().parents[1]
java=(root/"PhantomQuest/Assets/Plugins/Android/PhantomScenePermissions.androidlib/src/main/java/dev/phantom/nsd/PhantomNsdBridge.java").read_text(encoding="utf-8")
csharp=(root/"PhantomQuest/Assets/Phantom/Networking/AndroidNsdDiscoveryBackend.cs").read_text(encoding="utf-8")
manifest=(root/"PhantomQuest/Assets/Plugins/Android/PhantomScenePermissions.androidlib/AndroidManifest.xml").read_text(encoding="utf-8")
required_java=("NsdManager.DiscoveryListener","NsdManager.ResolveListener","void onResolved(String instance, String serviceType, String host, int port","void onLost(String instance, String serviceType)","getAttributes()","stopServiceDiscovery")
required_csharp=("AndroidJavaProxy","PhantomNsdBridge$Listener","public void onResolved(string instance,string serviceType,string host,int port","public void onLost(string instance,string serviceType)","_bridge?.Call(\"stop\")","AndroidServiceType(serviceType)")
required_permissions=("android.permission.INTERNET","android.permission.ACCESS_NETWORK_STATE","android.permission.CHANGE_WIFI_MULTICAST_STATE")
missing=[value for value in required_java if value not in java]+[value for value in required_csharp if value not in csharp]+[value for value in required_permissions if value not in manifest]
if missing:print("Android NSD bridge audit missing: "+", ".join(missing));sys.exit(1)
print("Android NSD compile contract PASS: Java/C# callbacks, stop lifecycle and permissions present")
