#if PHANTOM_MRUK
using System;
using System.Collections.Generic;
using Meta.XR.MRUtilityKit;
using Phantom.Kinematics;
using Phantom.Room;
using Phantom.Tracking;
using UnityEngine;
using UnityEngine.XR;

namespace Phantom.Meta
{
    public sealed class MetaMrukRoomReference : MonoBehaviour, IRoomReference
    {
        const float QueryTimeoutSeconds=5f;
        const float RetrySeconds=8f;
        const float FloorBoundsMarginMeters=.20f;
        const float MinRoomScaleSpanMeters=1.50f;
        readonly List<XRInputSubsystem> _inputSubsystems=new List<XRInputSubsystem>();
        readonly List<Vector3> _boundaryPoints=new List<Vector3>();
        bool _ready; bool _queryInProgress; string _reason="MRUK initializing"; Vec3 _floor; MRUK _mruk;
        bool _roomLocalized; string _localizedRoomDescription="";
        float _roomWidth; float _roomDepth;
        bool _spaceSetupRequested;
        float _queryStartedAt; float _nextPoll; float _nextRetry; int _queryAttempts;
        Guid _selectedRoomUuid; Guid _selectedFloorUuid; OVRLocatable _floorLocatable;
        public bool IsReady=>_ready; public string StatusReason=>_reason; public Vec3 FloorOrigin=>_floor;

        sealed class RoomCandidate
        {
            public Guid RoomUuid;
            public Guid FloorUuid;
            public OVRLocatable FloorLocatable;
            public Vector3 FloorPosition;
            public Quaternion FloorRotation;
            public bool ContainsHead;
            public float PlaneDistance;
            public float FloorArea;
            public float FloorWidth;
            public float FloorDepth;
        }

        void Start()
        {
            EnsureMrukCameraRig();
            var mruk=MRUK.Instance;
            if(!mruk)
            {
                // Keep MRUK alive for QR trackables, but do not use its global scene
                // discovery here. It scans every historical room and can stall on
                // stale component-enable callbacks.
                var mrukObject=new GameObject("MRUK");
                mrukObject.SetActive(false);
                mruk=mrukObject.AddComponent<MRUK>();
                mruk.SceneSettings=new MRUK.MRUKSettings{LoadSceneOnStartup=false};
                mrukObject.SetActive(true);
            }
            else if(mruk.SceneSettings==null)
            {
                mruk.SceneSettings=new MRUK.MRUKSettings{LoadSceneOnStartup=false};
            }
            mruk.EnableWorldLock=false;
            _mruk=mruk;
            RoomReferenceRegistry.Current=this;
            BeginTargetedRoomQuery();
        }

        static void EnsureMrukCameraRig()
        {
            MetaPassthroughController.EnsureRuntimeRig();
        }

        async void BeginTargetedRoomQuery()
        {
            if(_queryInProgress)return;
#if UNITY_ANDROID && !UNITY_EDITOR
            var permission=OVRPermissionsRequester.ScenePermission;
            if(!UnityEngine.Android.Permission.HasUserAuthorizedPermission(permission))
            {
                _ready=false;_reason="waiting for Spatial Data permission";
                var callbacks=new UnityEngine.Android.PermissionCallbacks();
                callbacks.PermissionGranted+=_=>BeginTargetedRoomQuery();
                callbacks.PermissionDenied+=_=>{_ready=false;_reason="Spatial Data permission denied";};
                UnityEngine.Android.Permission.RequestUserPermission(permission,callbacks);
                return;
            }
#endif
            _queryInProgress=true;_queryStartedAt=Time.unscaledTime;_queryAttempts++;
            _ready=false;_reason=$"querying localized room layouts (attempt {_queryAttempts})";
            try
            {
                var rooms=new List<OVRAnchor>();
                var roomResult=await OVRAnchor.FetchAnchorsAsync(rooms,new OVRAnchor.FetchOptions
                {
                    SingleComponentType=typeof(OVRRoomLayout)
                });
                if(!roomResult.Success)
                {
                    RejectQuery("room-layout discovery failed: "+roomResult.Status);
                    return;
                }
                if(rooms.Count==0&&!_spaceSetupRequested)
                {
                    _spaceSetupRequested=true;
                    _reason="opening Meta Space Setup: no saved room layout is available to this app";
                    Debug.LogWarning("PHANTOM ROOM "+_reason);
                    var setupCompleted=await OVRScene.RequestSpaceSetup();
                    if(!setupCompleted)
                    {
                        RejectQuery("Meta Space Setup request failed");
                        return;
                    }
                    _reason="Space Setup closed; checking room layouts";
                    roomResult=await OVRAnchor.FetchAnchorsAsync(rooms,new OVRAnchor.FetchOptions
                    {
                        SingleComponentType=typeof(OVRRoomLayout)
                    });
                    if(!roomResult.Success)
                    {
                        RejectQuery("post-setup room-layout discovery failed: "+roomResult.Status);
                        return;
                    }
                }

                var candidates=new List<RoomCandidate>();
                var headDevice=InputDevices.GetDeviceAtXRNode(XRNode.Head);
                var headPosition=Vector3.zero;
                var haveHead=headDevice.isValid&&headDevice.TryGetFeatureValue(CommonUsages.devicePosition,out headPosition);
                foreach(var roomAnchor in rooms)
                {
                    if(!roomAnchor.TryGetComponent<OVRRoomLayout>(out var layout)||
                       !layout.TryGetRoomLayout(out _,out var floorUuid,out _))continue;
                    var floors=new List<OVRAnchor>();
                    var floorResult=await OVRAnchor.FetchAnchorsAsync(floors,new OVRAnchor.FetchOptions
                    {
                        SingleUuid=floorUuid
                    });
                    if(!floorResult.Success||floors.Count!=1)continue;
                    var floorAnchor=floors[0];
                    if(!floorAnchor.TryGetComponent<OVRLocatable>(out var locatable))continue;
                    if(!locatable.IsEnabled&&!await locatable.SetEnabledAsync(true,QueryTimeoutSeconds))continue;
                    if(!locatable.TryGetSceneAnchorPose(out var pose)||!pose.Position.HasValue||!pose.Rotation.HasValue||
                       !pose.IsPositionTracked||!pose.IsRotationTracked)continue;

                    var candidate=new RoomCandidate
                    {
                        RoomUuid=roomAnchor.Uuid,
                        FloorUuid=floorUuid,
                        FloorLocatable=locatable,
                        FloorPosition=pose.Position.Value,
                        FloorRotation=pose.Rotation.Value,
                        PlaneDistance=float.MaxValue
                    };
                    if(haveHead)
                    {
                        var localHead=Quaternion.Inverse(candidate.FloorRotation)*(headPosition-candidate.FloorPosition);
                        candidate.PlaneDistance=Mathf.Abs(localHead.z);
                        if(floorAnchor.TryGetComponent<OVRBounded2D>(out var bounds)&&bounds.IsEnabled)
                        {
                            var rect=bounds.BoundingBox;
                            candidate.FloorArea=rect.width*rect.height;
                            candidate.FloorWidth=Mathf.Abs(rect.width);
                            candidate.FloorDepth=Mathf.Abs(rect.height);
                            rect.xMin-=FloorBoundsMarginMeters;rect.xMax+=FloorBoundsMarginMeters;
                            rect.yMin-=FloorBoundsMarginMeters;rect.yMax+=FloorBoundsMarginMeters;
                            candidate.ContainsHead=rect.Contains(new Vector2(localHead.x,localHead.y));
                        }
                    }
                    candidates.Add(candidate);
                }

                var selected=SelectCurrentCandidate(candidates,haveHead);
                if(selected==null)
                {
                    if(!_spaceSetupRequested)
                    {
                        _spaceSetupRequested=true;
                        _reason="Открывается Meta Space Setup: текущая комната не распознана";
                        Debug.LogWarning("PHANTOM ROOM "+_reason);
                        var setupCompleted=await OVRScene.RequestSpaceSetup();
                        _queryInProgress=false;
                        if(!setupCompleted)
                        {
                            RejectQuery("Meta Space Setup не завершён");
                            return;
                        }
                        _reason="Space Setup закрыт; повторное распознавание комнаты";
                        _nextRetry=Time.unscaledTime+.5f;
                        return;
                    }
                    RejectQuery(candidates.Count==0
                        ?$"no localized floor among {rooms.Count} room layout(s)"
                        :$"no room floor contains the current head position ({candidates.Count} localized candidate(s))");
                    return;
                }
                AcceptCandidate(selected,candidates.Count);
            }
            catch(Exception exception)
            {
                RejectQuery("targeted room query failed: "+exception.GetType().Name);
            }
        }

        static RoomCandidate SelectCurrentCandidate(List<RoomCandidate> candidates,bool haveHead)
        {
            RoomCandidate selected=null;
            foreach(var candidate in candidates)
            {
                if(haveHead&&!candidate.ContainsHead)continue;
                if(selected==null||candidate.PlaneDistance<selected.PlaneDistance-.005f||
                   (Mathf.Abs(candidate.PlaneDistance-selected.PlaneDistance)<=.005f&&candidate.FloorArea>selected.FloorArea))
                    selected=candidate;
            }
            // With no valid head pose, accepting is safe only when there is exactly
            // one localized room. Otherwise wait for a later query instead of guessing.
            return !haveHead&&candidates.Count!=1?null:selected;
        }

        void AcceptCandidate(RoomCandidate candidate,int localizedCount)
        {
            _selectedRoomUuid=candidate.RoomUuid;_selectedFloorUuid=candidate.FloorUuid;
            _floorLocatable=candidate.FloorLocatable;
            _floor=MetaQuestTrackingSource.UnityToCanonical(candidate.FloorPosition);
            _roomWidth=candidate.FloorWidth;_roomDepth=candidate.FloorDepth;
            _queryInProgress=false;_roomLocalized=true;
            _localizedRoomDescription=$"комната {_selectedRoomUuid} распознана (floor {_selectedFloorUuid}, candidates={localizedCount}, head_inside={candidate.ContainsHead})";
            RefreshRoomScaleBoundaryGate();
            Debug.Log("PHANTOM ROOM targeted_selection "+_reason);
        }

        void RefreshRoomScaleBoundaryGate()
        {
            if(_roomWidth<MinRoomScaleSpanMeters||_roomDepth<MinRoomScaleSpanMeters)
            {
                _ready=false;
                _reason=$"КОМНАТА СЛИШКОМ МАЛА ИЛИ НЕТ ГРАНИЦ ПОЛА ({_roomWidth:F1}×{_roomDepth:F1} м): выполните Space Setup";
                return;
            }

            // Query only the running OpenXR input subsystem. OVRBoundary's
            // OuterBoundary API is deprecated and unsupported by OpenXR.
            // The SDK-set polygon is the active Meta safety boundary; its size
            // lets us reject the small stationary safe zone explicitly.
            _inputSubsystems.Clear();
            SubsystemManager.GetSubsystems(_inputSubsystems);
            XRInputSubsystem boundarySource=null;
            foreach(var subsystem in _inputSubsystems)
            {
                if(!subsystem.running)continue;
                if(boundarySource!=null)
                {
                    _ready=false;
                    _reason="ОШИБКА XR: несколько активных подсистем сообщили границы";
                    return;
                }
                boundarySource=subsystem;
            }
            if(boundarySource==null)
            {
                _ready=false;
                _reason="НУЖНЫ ГРАНИЦЫ КОМНАТЫ: откройте Meta → Быстрые настройки → Граница и создайте комнатную границу";
                return;
            }
            _boundaryPoints.Clear();
            if(!boundarySource.TryGetBoundaryPoints(_boundaryPoints)||_boundaryPoints.Count<3)
            {
                _ready=false;
                _reason="НУЖНЫ ГРАНИЦЫ КОМНАТЫ: OpenXR не получил многоугольник активной границы";
                return;
            }

            var minX=float.PositiveInfinity;var maxX=float.NegativeInfinity;
            var minZ=float.PositiveInfinity;var maxZ=float.NegativeInfinity;
            foreach(var point in _boundaryPoints)
            {
                minX=Mathf.Min(minX,point.x);maxX=Mathf.Max(maxX,point.x);
                minZ=Mathf.Min(minZ,point.z);maxZ=Mathf.Max(maxZ,point.z);
            }
            var width=maxX-minX;var depth=maxZ-minZ;
            if(width<MinRoomScaleSpanMeters||depth<MinRoomScaleSpanMeters)
            {
                _ready=false;
                _reason=$"СТАЦИОНАРНАЯ ГРАНИЦА НЕ ПОДХОДИТ ({width:F1}×{depth:F1} м): выберите комнатную границу";
                return;
            }
            _ready=true;
            _reason=$"ГОТОВО: {_localizedRoomDescription}; пол {_roomWidth:F1}×{_roomDepth:F1} м; активная граница {width:F1}×{depth:F1} м";
        }

        void RejectQuery(string reason)
        {
            _queryInProgress=false;_ready=false;_nextRetry=Time.unscaledTime+RetrySeconds;
            _reason="WAITING_FOR_ROOM_LOCALIZATION: "+reason;
            Debug.LogWarning("PHANTOM ROOM "+_reason);
        }

        void Update()
        {
            if(Time.unscaledTime<_nextPoll)return;
            _nextPoll=Time.unscaledTime+.5f;
            if(_roomLocalized)
            {
                if(_floorLocatable.IsEnabled&&_floorLocatable.TryGetSceneAnchorPose(out var pose)&&
                   pose.Position.HasValue&&pose.Rotation.HasValue&&pose.IsPositionTracked&&pose.IsRotationTracked)
                {
                    _floor=MetaQuestTrackingSource.UnityToCanonical(pose.Position.Value);
                    RefreshRoomScaleBoundaryGate();
                    return;
                }
                _roomLocalized=false;_ready=false;_reason="ПОТЕРЯНО РАСПОЗНАВАНИЕ ПОЛА ТЕКУЩЕЙ КОМНАТЫ";_nextRetry=Time.unscaledTime+1f;
                Debug.LogWarning("PHANTOM ROOM "+_reason);
            }
            if(_queryInProgress)
            {
                var elapsed=Time.unscaledTime-_queryStartedAt;
                _reason=$"querying localized room layouts ({elapsed:F0}s, attempt {_queryAttempts})";
                return;
            }
            if(Time.unscaledTime>=_nextRetry)BeginTargetedRoomQuery();
        }

        void OnDestroy()
        {
            if(ReferenceEquals(RoomReferenceRegistry.Current,this))RoomReferenceRegistry.Current=null;
        }
    }
}
#endif
