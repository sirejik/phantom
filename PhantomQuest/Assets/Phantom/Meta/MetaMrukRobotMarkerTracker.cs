#if PHANTOM_MRUK
using System;
using System.Collections.Generic;
using Meta.XR.MRUtilityKit;
using Phantom.Kinematics;
using Phantom.RobotLocalization;
using Phantom.Room;
using Phantom.Tracking;
using UnityEngine;

namespace Phantom.Meta
{
    public sealed class MetaMrukRobotMarkerTracker : MonoBehaviour, IRobotMarkerTracker
    {
        [SerializeField] Vector3 baseOriginFromMarkerMeters=Vector3.zero;
        [SerializeField] Vector3 baseFrameEulerInMarkerDegrees=Vector3.zero;
        readonly Dictionary<RobotMarkerId,MRUKTrackable> _trackables=new Dictionary<RobotMarkerId,MRUKTrackable>();
        readonly List<MRUKTrackable> _qrTrackables=new List<MRUKTrackable>();
        readonly List<MRUKTrackable> _initialTrackables=new List<MRUKTrackable>();
        string _reason="MRUK QR tracker initializing";
        bool _subscribed;
        bool _capabilityChecked;
        bool _trackingRequested;
        float _nextInitializationAttempt;
        public bool IsAvailable=>_subscribed;
        public string StatusReason=>_reason;

        void Start()
        {
            RobotMarkerTrackerRegistry.Current=this;
            TryInitialize();
        }
        void Update(){if(!_subscribed&&!_capabilityChecked&&Time.unscaledTime>=_nextInitializationAttempt)TryInitialize();}
        void TryInitialize()
        {
            _nextInitializationAttempt=Time.unscaledTime+1f;
            if(!OVRPlugin.initialized){_reason="OpenXR runtime initializing";return;}
            if(!MRUK.Instance){_reason="MRUK instance unavailable";return;}
            var roomReference=RoomReferenceRegistry.Current;
            if(roomReference==null||!roomReference.IsReady){_reason=roomReference?.StatusReason??"room reference unavailable";return;}
            try
            {
                if(!MRUK.Instance.QRCodeTrackingSupported){_capabilityChecked=true;_reason="QR tracking unavailable on this device/runtime";return;}
            }
            catch(Exception exception)
            {
                _capabilityChecked=true;_reason="QR capability check failed: "+exception.GetType().Name;return;
            }
            MRUK.Instance.SceneSettings.TrackableAdded.AddListener(OnTrackableAdded);MRUK.Instance.SceneSettings.TrackableRemoved.AddListener(OnTrackableRemoved);_subscribed=true;_reason="QR tracker idle until a QR test starts";
            MRUK.Instance.GetTrackables(_initialTrackables);foreach(var trackable in _initialTrackables)OnTrackableAdded(trackable);
            ApplyTrackingRequest();
        }
        public void SetQrTrackingEnabled(bool enabled){_trackingRequested=enabled;ApplyTrackingRequest();}
        void ApplyTrackingRequest()
        {
            if(!_subscribed||!MRUK.Instance||MRUK.Instance.SceneSettings==null)return;
            var config=MRUK.Instance.SceneSettings.TrackerConfiguration;
            if(config.QRCodeTrackingEnabled==_trackingRequested)return;
            config.QRCodeTrackingEnabled=_trackingRequested;MRUK.Instance.SceneSettings.TrackerConfiguration=config;
            _reason=_trackingRequested?"QR tracker starting; point headset at marker":"QR tracker idle until a QR test starts";
        }
        void OnTrackableAdded(MRUKTrackable trackable)
        {
            if(!trackable||trackable.TrackableType!=OVRAnchor.TrackableType.QRCode)return;
            if(!_qrTrackables.Contains(trackable))_qrTrackables.Add(trackable);
            if(TryParse(trackable.MarkerPayloadString,out var id))_trackables[id]=trackable;
            _reason="QR detected: "+DisplayPayload(trackable.MarkerPayloadString)+"; robot markers "+_trackables.Count+"/6";
        }
        void OnTrackableRemoved(MRUKTrackable trackable){_qrTrackables.Remove(trackable);if(TryParse(trackable.MarkerPayloadString,out var id))_trackables.Remove(id);_reason="QR removed: "+DisplayPayload(trackable.MarkerPayloadString);}
        public bool TryGetSnapshot(out RobotMarkerSnapshot snapshot)
        {
            snapshot=null;if(_trackables.Count!=6)return false;var baseMarker=_trackables[RobotMarkerId.BaseBack];var rotation=baseMarker.transform.rotation*Quaternion.Euler(baseFrameEulerInMarkerDegrees);var origin=baseMarker.transform.TransformPoint(baseOriginFromMarkerMeters);
            var frame=new RobotBaseFrame{OriginRoom=MetaQuestTrackingSource.UnityToCanonical(origin),ForwardRoom=MetaQuestTrackingSource.UnityToCanonical(rotation*Vector3.forward).Normalized,LeftRoom=MetaQuestTrackingSource.UnityToCanonical(rotation*Vector3.left).Normalized,UpRoom=MetaQuestTrackingSource.UnityToCanonical(rotation*Vector3.up).Normalized};
            if(!frame.IsValid)return false;snapshot=new RobotMarkerSnapshot{BaseFrame=frame};foreach(var pair in _trackables){if(!pair.Value||!pair.Value.IsTracked)return false;snapshot.Positions[pair.Key]=MetaQuestTrackingSource.UnityToCanonical(pair.Value.transform.position);}return true;
        }
        public bool TryGetQrSnapshot(string requiredPayload,out QrMarkerObservation observation)
        {
            observation=default;MRUKTrackable selected=null;
            foreach(var trackable in _qrTrackables)
            {
                if(!trackable||!trackable.IsTracked)continue;
                if(!string.IsNullOrEmpty(requiredPayload)&&!string.Equals(trackable.MarkerPayloadString,requiredPayload,StringComparison.Ordinal))continue;
                if(selected==null||string.Equals(trackable.MarkerPayloadString,"QR_TEST",StringComparison.OrdinalIgnoreCase))selected=trackable;
            }
            if(!selected)return false;
            var rotation=selected.transform.rotation;
            observation=new QrMarkerObservation{Payload=string.IsNullOrEmpty(selected.MarkerPayloadString)?"<binary>":selected.MarkerPayloadString,PositionRoom=MetaQuestTrackingSource.UnityToCanonical(selected.transform.position),RotationX=rotation.x,RotationY=rotation.y,RotationZ=rotation.z,RotationW=rotation.w,Valid=true};
            return true;
        }
        static string DisplayPayload(string payload)=>string.IsNullOrEmpty(payload)?"<binary>":payload.Length<=80?payload:payload.Substring(0,80);
        static bool TryParse(string payload,out RobotMarkerId id)
        {
            var normalized=payload?.Trim().ToUpperInvariant();
            if(!string.IsNullOrEmpty(normalized))
            {
                var separator=normalized.LastIndexOf(':');
                if(separator>=0&&separator+1<normalized.Length)normalized=normalized.Substring(separator+1);
            }
            switch(normalized){case "BASE_BACK":id=RobotMarkerId.BaseBack;return true;case "SHOULDER_L":id=RobotMarkerId.ShoulderL;return true;case "SHOULDER_R":id=RobotMarkerId.ShoulderR;return true;case "ELBOW_L":id=RobotMarkerId.ElbowL;return true;case "ELBOW_R":id=RobotMarkerId.ElbowR;return true;case "TCP_CAL":id=RobotMarkerId.TcpCal;return true;default:id=default;return false;}
        }
        void OnDestroy(){if(_subscribed&&MRUK.Instance){MRUK.Instance.SceneSettings.TrackableAdded.RemoveListener(OnTrackableAdded);MRUK.Instance.SceneSettings.TrackableRemoved.RemoveListener(OnTrackableRemoved);}if(ReferenceEquals(RobotMarkerTrackerRegistry.Current,this))RobotMarkerTrackerRegistry.Current=null;}
    }

    public static class MetaAdapterBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Install()
        {
            if(UnityEngine.Object.FindFirstObjectByType<MetaMrukRoomReference>()!=null)return;
            var go=new GameObject("PhantomMetaAdapters");UnityEngine.Object.DontDestroyOnLoad(go);go.AddComponent<MetaPassthroughController>();go.AddComponent<MetaMrukRoomReference>();go.AddComponent<MetaMrukRobotMarkerTracker>();
        }
    }
}
#endif
