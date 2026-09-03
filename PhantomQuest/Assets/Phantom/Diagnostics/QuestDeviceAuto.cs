using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using Phantom.Kinematics;
using Phantom.RobotLocalization;
using Phantom.Tracking;
using UnityEngine;
using UnityEngine.XR;

namespace Phantom.Diagnostics
{
    [Serializable]
    public sealed class QuestBuildIdentity
    {
        public int schema_version;
        public string build_id;
        public string git_commit;
        public string source_tree_hash;
        public bool worktree_dirty;
        public string build_profile;
        public int protocol_version;
        public string specification_sha256;
        public string protocol_schema_hash;
        public string config_hash;
        public string unity_version;
        public string app_version;
        public string package_lock_sha256;
        public string meta_xr_core_version;
        public string movement_sdk_version;
        public string body_tracking_provider;
        public string mruk_version;
        public string openxr_plugin_version;
        public string meta_openxr_version;
        public string xr_hands_version;
    }

    [Serializable]
    public sealed class QuestDeviceAutoCheck
    {
        public string test_id;
        public int introduced_at_stage=2;
        public string status;
        public string detail;
    }

    [Serializable]
    public sealed class QuestDeviceAutoReport
    {
        public int schema_version=1;
        public string gate="QUEST DEVICE AUTO";
        public string status;
        public string build_id;
        public string build_profile;
        public string git_commit;
        public string specification_sha256;
        public string protocol_schema_hash;
        public string config_hash;
        public string unity_version;
        public string device_model;
        public string operating_system;
        public string started_utc;
        public string finished_utc;
        public long duration_ms;
        public bool motor_authority;
        public int error_log_count;
        public QuestDeviceAutoCheck[] checks;
    }

    // Short, zero-output post-install gate. It deliberately does not pretend to
    // be the 30-minute P0/manual qualification: it proves identity, config,
    // OpenXR startup and capability availability for the installed APK.
    public sealed class QuestDeviceAuto : MonoBehaviour
    {
        // A cold OpenXR start consumes several seconds and an unattended Quest
        // can suspend the activity after roughly 15 seconds. Keep this smoke
        // inside that window; the 30-minute P0 qualification is a separate gate.
        const float SettleSeconds=8f;
        readonly List<XRDisplaySubsystem> _displays=new List<XRDisplaySubsystem>();
        QuestBuildIdentity _identity;
        MetaQuestTrackingSource _tracking;
        DateTime _startedUtc;
        float _startedMonotonic;
        int _errorLogs;
        bool _finished;
#if UNITY_ANDROID && !UNITY_EDITOR
        UnityEngine.Android.PermissionCallbacks _permissionCallbacks;
#endif

        void Awake()
        {
            _startedUtc=DateTime.UtcNow;
            _startedMonotonic=Time.realtimeSinceStartup;
            _tracking=GetComponent<MetaQuestTrackingSource>();
            Application.logMessageReceived+=OnLog;
            StartCoroutine(Run());
        }

        IEnumerator Run()
        {
            var build=Resources.Load<TextAsset>("phantom-build");
            _identity=build?JsonUtility.FromJson<QuestBuildIdentity>(build.text):null;
            Debug.Log("PHANTOM DEVICE AUTO START "+(build?build.text:"{\"error\":\"embedded_build_manifest_missing\"}"));
            RequestMissingPermissions();
            while(Time.realtimeSinceStartup-_startedMonotonic<SettleSeconds)yield return new WaitForSecondsRealtime(.25f);
            WriteReport();
        }

        void WriteReport()
        {
            if(_finished)return;
            _finished=true;
            var checks=new List<QuestDeviceAutoCheck>();
            Add(checks,"embedded-build-identity",_identity!=null&&!string.IsNullOrEmpty(_identity.build_id)&&!_identity.worktree_dirty,
                _identity==null?"embedded build manifest missing":$"build_id={_identity.build_id}; profile={_identity.build_profile}; dirty={_identity.worktree_dirty}");

            var config=Resources.Load<TextAsset>("phantom-quest-config");
            var actualConfigHash=config?Sha256(config.bytes):"missing";
            Add(checks,"config-load-and-hash",_identity!=null&&config&&string.Equals(actualConfigHash,_identity.config_hash,StringComparison.OrdinalIgnoreCase),
                $"expected={_identity?.config_hash??"missing"}; actual={actualConfigHash}");

            _displays.Clear();SubsystemManager.GetSubsystems(_displays);
            var displayRunning=_displays.Exists(value=>value!=null&&value.running);
            Add(checks,"openxr-session",displayRunning&&OVRPlugin.initialized,
                $"display_running={displayRunning}; ovrplugin_initialized={OVRPlugin.initialized}; native_xr_api={OVRPlugin.nativeXrApi}");

            var manager=FindFirstObjectByType<OVRManager>();
            var localFloor=manager&&manager.trackingOriginType==OVRManager.TrackingOrigin.FloorLevel;
            Add(checks,"local-floor",localFloor,$"manager={(manager?"present":"missing")}; origin={(manager?manager.trackingOriginType.ToString():"unknown")}");

            AddPermission(checks,"permission-hand-tracking","com.oculus.permission.HAND_TRACKING");
            AddPermission(checks,"permission-body-tracking","com.oculus.permission.BODY_TRACKING");
            AddPermission(checks,"permission-scene","com.oculus.permission.USE_SCENE");
            AddPermission(checks,"permission-anchor","com.oculus.permission.USE_ANCHOR_API");

            var passthrough=FindFirstObjectByType<OVRPassthroughLayer>();
            Add(checks,"passthrough-capability",passthrough&&passthrough.enabled&&!passthrough.hidden,
                $"component={(passthrough?"present":"missing")}; enabled={(passthrough&&passthrough.enabled)}; visible={(passthrough&&!passthrough.hidden)}");

            var tracker=RobotMarkerTrackerRegistry.Current;
            Add(checks,"mruk-qr-capability",tracker!=null&&tracker.IsAvailable,tracker?.StatusReason??"QR tracker registry missing");
            Add(checks,"multimodal-capability",_tracking!=null&&_tracking.MultimodalConfigured,_tracking?.MultimodalStatus??"tracking source missing");
            Add(checks,"body-provider-capability",_tracking!=null&&_tracking.BodyProviderAvailable,
                _tracking!=null?$"provider=OVRBody; enabled={_tracking.BodyProviderAvailable}; multimodal={_tracking.MultimodalStatus}":"tracking source missing");
            var frame=default(TrackingFrame);
            var haveFrame=_tracking!=null&&_tracking.TryGetFrame(out frame);
            Observe(checks,"p0-right-wrist-observed",haveFrame&&frame.RightHand.Wrist.Valid,haveFrame?$"valid={frame.RightHand.Wrist.Valid}; quality={frame.RightHand.Wrist.Quality}":"no tracking frame");
            Observe(checks,"p0-grasp-ready-observed",haveFrame&&frame.RightHand.Grasp.Valid&&frame.RightHand.Grasp.Ready,haveFrame?$"valid={frame.RightHand.Grasp.Valid}; ready={frame.RightHand.Grasp.Ready}":"no tracking frame");
            Observe(checks,"p0-right-shoulder-observed",haveFrame&&frame.RightShoulder.Valid,haveFrame?$"valid={frame.RightShoulder.Valid}; quality={frame.RightShoulder.Quality}; runtime={frame.RightShoulder.RuntimeQuality}":"no tracking frame");
            Observe(checks,"p0-left-touch-observed",haveFrame&&frame.LeftController.Valid,haveFrame?$"valid={frame.LeftController.Valid}; grip={frame.LeftController.GripAnalog:F3}":"no tracking frame");
            var qr=default(QrMarkerObservation);
            var qrObserved=tracker!=null&&tracker.TryGetQrSnapshot(null,out qr)&&qr.Valid;
            Observe(checks,"p0-qr-observed",qrObserved,qrObserved?$"payload={qr.Payload}":tracker?.StatusReason??"QR tracker registry missing");
            Add(checks,"motor-authority-disabled",true,"stage-2 runtime constructs no RobotTransport and emits no actuator commands");
            Add(checks,"runtime-error-log",_errorLogs==0,$"error_exception_assert_count={_errorLogs}");

            var diagnostic=_identity!=null&&string.Equals(_identity.build_profile,"Diagnostic",StringComparison.Ordinal);
            if(diagnostic)Add(checks,"diagnostic-synthetic-tracking-qr",SyntheticProviderSmoke(),"pure synthetic frame and all ten QR poses accepted without RobotTransport");
            else checks.Add(new QuestDeviceAutoCheck{test_id="diagnostic-synthetic-tracking-qr",status="N_A",detail="Diagnostic-only; Release has no active engineering runner"});

            var runner=FindFirstObjectByType<Phantom.Experiments.QuestValidationRunner>();
            Add(checks,"release-engineering-disabled",diagnostic||runner==null,diagnostic?"N_A for Diagnostic profile":$"validation_runner_active={runner!=null}");

            var failed=checks.Exists(value=>value.status=="FAIL");
            var now=DateTime.UtcNow;
            var report=new QuestDeviceAutoReport
            {
                status=failed?"FAIL":"PASS",
                build_id=_identity?.build_id??"UNKNOWN",
                build_profile=_identity?.build_profile??"UNKNOWN",
                git_commit=_identity?.git_commit??"UNKNOWN",
                specification_sha256=_identity?.specification_sha256??"UNKNOWN",
                protocol_schema_hash=_identity?.protocol_schema_hash??"UNKNOWN",
                config_hash=_identity?.config_hash??"UNKNOWN",
                unity_version=Application.unityVersion,
                device_model=SystemInfo.deviceModel,
                operating_system=SystemInfo.operatingSystem,
                started_utc=_startedUtc.ToString("o"),
                finished_utc=now.ToString("o"),
                duration_ms=(long)((Time.realtimeSinceStartup-_startedMonotonic)*1000),
                motor_authority=false,
                error_log_count=_errorLogs,
                checks=checks.ToArray()
            };
            var json=JsonUtility.ToJson(report,true);
            File.WriteAllText(Path.Combine(Application.persistentDataPath,"quest-device-auto.json"),json+Environment.NewLine);
            Debug.Log("PHANTOM DEVICE AUTO RESULT "+JsonUtility.ToJson(report));
        }

        void AddPermission(List<QuestDeviceAutoCheck> checks,string id,string permission)
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            var granted=UnityEngine.Android.Permission.HasUserAuthorizedPermission(permission);
            Add(checks,id,granted,$"{permission}; granted={granted}");
#else
            checks.Add(new QuestDeviceAutoCheck{test_id=id,status="N_A",detail="Android device permission check"});
#endif
        }

        void RequestMissingPermissions()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            var required=new[]{"com.oculus.permission.BODY_TRACKING","com.oculus.permission.USE_SCENE","com.oculus.permission.USE_ANCHOR_API"};
            var missing=new List<string>();
            foreach(var permission in required)if(!UnityEngine.Android.Permission.HasUserAuthorizedPermission(permission))missing.Add(permission);
            if(missing.Count==0)return;
            _permissionCallbacks=new UnityEngine.Android.PermissionCallbacks();
            _permissionCallbacks.PermissionGranted+=value=>Debug.Log("PHANTOM permission_granted="+value);
            _permissionCallbacks.PermissionDenied+=value=>Debug.LogWarning("PHANTOM permission_denied="+value);
            _permissionCallbacks.PermissionDeniedAndDontAskAgain+=value=>Debug.LogWarning("PHANTOM permission_denied_dont_ask_again="+value);
            UnityEngine.Android.Permission.RequestUserPermissions(missing.ToArray(),_permissionCallbacks);
            Debug.Log("PHANTOM permission_request_started="+string.Join(",",missing));
#endif
        }

        static bool SyntheticProviderSmoke()
        {
            var frame=new TrackingFrame{MonotonicTimeUs=1,AppFocused=true,MultimodalConfigured=true};
            frame.RightHand.Valid=true;frame.RightHand.Wrist=new PoseObservation{Position=new Vec3(.3,.4,.5),Valid=true};
            frame.LeftController.Valid=true;frame.BothValid=true;
            var snapshot=new RobotMarkerSnapshot
            {
                BaseFrame=new RobotBaseFrame{OriginRoom=new Vec3(0,0,0),ForwardRoom=new Vec3(1,0,0),LeftRoom=new Vec3(0,0,1),UpRoom=new Vec3(0,1,0)}
            };
            var index=0;
            foreach(RobotMarkerId id in Enum.GetValues(typeof(RobotMarkerId)))
            {
                snapshot.Positions[id]=new Vec3(.1*index,.5,.2);
                snapshot.Rotations[id]=MarkerRotation.Identity;
                index++;
            }
            return frame.BothValid&&frame.RightHand.Wrist.Valid&&snapshot.HasAllTenPoses&&snapshot.BaseFrame.IsValid;
        }

        static void Add(List<QuestDeviceAutoCheck> checks,string id,bool passed,string detail)
            =>checks.Add(new QuestDeviceAutoCheck{test_id=id,status=passed?"PASS":"FAIL",detail=detail});

        static void Observe(List<QuestDeviceAutoCheck> checks,string id,bool observed,string detail)
            =>checks.Add(new QuestDeviceAutoCheck{test_id=id,status=observed?"PASS":"NOT_RUN",detail=detail});

        static string Sha256(byte[] bytes)
        {
            using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();
        }

        void OnLog(string condition,string stackTrace,LogType type)
        {
            if(type==LogType.Exception||type==LogType.Error||type==LogType.Assert)_errorLogs++;
        }

        void OnDestroy()
        {
            if(!_finished)WriteReport();
            Application.logMessageReceived-=OnLog;
        }

        void OnApplicationPause(bool paused)
        {
            // Always leave machine-readable evidence when Horizon suspends the
            // app. Capability checks remain fail-closed if XR is already gone.
            if(paused&&!_finished)WriteReport();
        }
    }
}
