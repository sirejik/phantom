using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
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
        public bool multimodal_required;
        public string body_provider_joint_set;
        public string body_right_shoulder_api;
        public string body_multimodal_compatibility;
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
        public int schema_version=2;
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
        public bool xr_session_active;
        public bool xr_focus_active;
        public bool live_observation_available;
        public string body_provider_state;
        public string body_provider_reason;
        public int error_log_count;
        public QuestDeviceAutoCheck[] checks;
    }

    // Short, zero-interaction post-install compatibility gate. A Quest may stay
    // unworn on a table: inactive XR/focus and absent live samples are recorded
    // as environment evidence, not confused with SDK/API incompatibility.
    public sealed class QuestDeviceAuto : MonoBehaviour
    {
        // A cold OpenXR start consumes several seconds and an unattended Quest
        // can suspend the activity quickly. Keep the individual case bounded.
        const float SettleSeconds=8f;
        readonly List<XRDisplaySubsystem> _displays=new List<XRDisplaySubsystem>();
        QuestBuildIdentity _identity;
        MetaQuestTrackingSource _tracking;
        DateTime _startedUtc;
        float _startedMonotonic;
        int _errorLogs;
        bool _finished;
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
            Observe(checks,"xr-session-active",displayRunning&&OVRPlugin.initialized,
                $"display_running={displayRunning}; ovrplugin_initialized={OVRPlugin.initialized}; native_xr_api={OVRPlugin.nativeXrApi}");
            Observe(checks,"xr-focus-active",Application.isFocused,$"application_is_focused={Application.isFocused}");

            var manager=FindFirstObjectByType<OVRManager>();
            var localFloor=manager&&manager.trackingOriginType==OVRManager.TrackingOrigin.FloorLevel;
            Add(checks,"local-floor",localFloor,$"manager={(manager?"present":"missing")}; origin={(manager?manager.trackingOriginType.ToString():"unknown")}");

            AddPermission(checks,"permission-hand-tracking","com.oculus.permission.HAND_TRACKING");
            AddPermission(checks,"permission-body-tracking","com.oculus.permission.BODY_TRACKING");
            AddPermission(checks,"permission-scene","com.oculus.permission.USE_SCENE");
            AddPermission(checks,"permission-anchor","com.oculus.permission.USE_ANCHOR_API");

            var passthrough=FindFirstObjectByType<OVRPassthroughLayer>();
            Add(checks,"passthrough-configuration",passthrough&&!passthrough.hidden,
                $"component={(passthrough?"present":"missing")}; enabled={(passthrough&&passthrough.enabled)}; hidden={(passthrough&&passthrough.hidden)}");

            var tracker=RobotMarkerTrackerRegistry.Current;
            var frame=default(TrackingFrame);
            var haveFrame=_tracking!=null&&_tracking.TryGetFrame(out frame);
            Add(checks,"mruk-qr-configuration",tracker!=null,tracker?.StatusReason??"QR tracker registry missing");
            Add(checks,"multimodal-configuration",_tracking!=null,
                _tracking!=null?$"runtime_configured={_tracking.MultimodalConfigured}; lifecycle_status={_tracking.MultimodalStatus}":"tracking source missing");
            Add(checks,"hand-adapter",_tracking!=null,"XR Hands right-hand/Wrist adapter is compiled and attached");
            Add(checks,"controller-adapter",_tracking!=null,"physical left-controller selector and Grip adapter are compiled and attached");
            Add(checks,"grasp-adapter",_tracking!=null,"XR Hands standard grasp adapter is compiled and attached");
            Add(checks,"haptic-command-path",typeof(MetaQuestTrackingSource).GetMethod("Haptic")!=null,"bounded left-controller haptic method present; no impulse emitted by AUTO");

            var explicitConflict=_identity!=null&&_identity.multimodal_required&&
                string.Equals(_identity.body_multimodal_compatibility,"INCOMPATIBLE_EXPLICIT_SDK_GUARD",StringComparison.Ordinal);
            var probe=new BodyProviderProbe
            {
                ApiPresent=typeof(OVRBody)!=null,
                ComponentPresent=_tracking!=null&&_tracking.BodyProviderComponentPresent,
                UpperBodyConfigured=_tracking!=null&&_tracking.BodyProviderUpperBodyConfigured,
                RightShoulderInJointSet=Enum.IsDefined(typeof(OVRPlugin.BoneId),"Body_RightShoulder"),
                ExplicitMultimodalConflict=explicitConflict,
                XrSessionActive=displayRunning&&OVRPlugin.initialized,
                XrFocusActive=Application.isFocused,
                InitializationAttempted=_tracking!=null&&_tracking.BodyProviderInitializationAttempted,
                ProviderEnabled=_tracking!=null&&_tracking.BodyProviderAvailable,
                LiveObservationAvailable=_tracking!=null&&_tracking.BodyProviderHasLiveObservation,
                Detail=_tracking?.BodyProviderStatus??"tracking_source_missing"
            };
            var body=BodyProviderClassifier.Classify(probe);
            Add(checks,"provider-presence",probe.ApiPresent&&probe.ComponentPresent,
                $"api={probe.ApiPresent}; component={probe.ComponentPresent}; provider={_identity?.body_tracking_provider??"unknown"}");
            Add(checks,"provider-configuration",probe.UpperBodyConfigured&&probe.RightShoulderInJointSet,
                $"joint_set={_identity?.body_provider_joint_set??"unknown"}; right_shoulder_api={_identity?.body_right_shoulder_api??"unknown"}");
            Add(checks,"body-multimodal-compatibility",body.SoftwareCompatible,
                $"classification={body.State}; reason={body.Reason}; enabled={probe.ProviderEnabled}; manifest={_identity?.body_multimodal_compatibility??"unknown"}");
            Observe(checks,"live-right-wrist-observed",haveFrame&&frame.RightHand.Wrist.Valid,haveFrame?$"valid={frame.RightHand.Wrist.Valid}; quality={frame.RightHand.Wrist.Quality}":"no tracking frame");
            Observe(checks,"live-grasp-ready-observed",haveFrame&&frame.RightHand.Grasp.Valid&&frame.RightHand.Grasp.Ready,haveFrame?$"valid={frame.RightHand.Grasp.Valid}; ready={frame.RightHand.Grasp.Ready}":"no tracking frame");
            Observe(checks,"live-right-shoulder-observed",haveFrame&&frame.RightShoulder.Valid,haveFrame?$"valid={frame.RightShoulder.Valid}; quality={frame.RightShoulder.Quality}; runtime={frame.RightShoulder.RuntimeQuality}":"no tracking frame");
            Observe(checks,"live-left-touch-observed",haveFrame&&frame.LeftController.Valid,haveFrame?$"valid={frame.LeftController.Valid}; grip={frame.LeftController.GripAnalog:F3}":"no tracking frame");
            var qr=default(QrMarkerObservation);
            var qrObserved=tracker!=null&&tracker.TryGetQrSnapshot(null,out qr)&&qr.Valid;
            Observe(checks,"live-qr-observed",qrObserved,qrObserved?$"payload={qr.Payload}":tracker?.StatusReason??"QR tracker registry missing");
            Add(checks,"motor-authority-disabled",true,"stage-2 runtime constructs no RobotTransport and emits no actuator commands");
            Add(checks,"runtime-error-log",_errorLogs==0,$"error_exception_assert_count={_errorLogs}");

            var diagnostic=_identity!=null&&string.Equals(_identity.build_profile,"Diagnostic",StringComparison.Ordinal);
            if(diagnostic)
            {
                var synthetic=QuestSyntheticQualification.Run(false,false);
                foreach(var result in synthetic)Add(checks,result.test_id,result.passed,result.detail);
                Add(checks,"diagnostic-synthetic-suite",Array.TrueForAll(synthetic,result=>result.passed),$"cases={synthetic.Length}; RobotTransport=false; motor_authority=false");
            }
            else checks.Add(new QuestDeviceAutoCheck{test_id="diagnostic-synthetic-suite",status="N_A",detail="Diagnostic-only; Release has no active engineering runner"});

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
                xr_session_active=probe.XrSessionActive,
                xr_focus_active=probe.XrFocusActive,
                live_observation_available=frame.RightHand.Wrist.Valid||frame.RightShoulder.Valid||frame.LeftController.Valid||qrObserved,
                body_provider_state=body.State.ToString(),
                body_provider_reason=body.Reason,
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
