using System;
using Phantom.Calibration;
using Phantom.Config;
using Phantom.Experiments;
using Phantom.Kinematics;
using Phantom.Logging;
using Phantom.Mapping;
using Phantom.Networking;
using Phantom.RobotLocalization;
using Phantom.Room;
using Phantom.Tracking;
using Phantom.UI;
using Phantom.Visualization;
using Phantom.Workspace;
using UnityEngine;
using UnityEngine.Profiling;

namespace Phantom
{
    public sealed class PhantomRuntime : MonoBehaviour
    {
        public string simulatorHost="192.168.0.112"; public int simulatorPort=31337;
        MetaQuestTrackingSource _tracking; PhantomWristHud _hud; QuestValidationRunner _validation; PhantomUdpClient _network; QuestJsonlLogger _logger;
        readonly PhantomStateMachine _stateMachine=new PhantomStateMachine(); readonly IRoomReference _fallbackRoom=new MrukRoomReference(); IRoomReference _room;
        PhantomConfig _config; EnableHysteresis _enable; HumanToRobotMapper _mapper; WorkspaceProjector _workspace; PhantomInverseKinematics _ik; GripMapper _gripMapper;
        JointAngles _targetAngles; Vec3 _targetTcp=new Vec3(0.30,0,0.08); float _gripIntent; PhantomState _previousState=PhantomState.Initializing; SafetyPredicates _previousPredicates;
        readonly RobotCalibrationSession _robotSession=new RobotCalibrationSession(1.0); RobotGeometry _robotGeometry;
        UserCalibrationWizard _userWizard; UserCalibration _userCalibration; bool _calibrating; bool _lastY;
        double _nextSend; bool _wasEnableHeld; int _logDivider;
        bool _previousBothValid; bool _previousMultimodalConfigured; string _previousInteractionMode=""; string _previousInteractionSource="";
        float _smoothedDeltaTime; double _nextHudUpdate; double _nextPerformanceLog; string _performanceStatus="КАДР/С —";
        int _baselineCompositorDroppedFrames=-1;

        void Awake()
        {
            QualitySettings.vSyncCount=0;Application.targetFrameRate=72;
            _config=new PhantomConfig{SimulatorHost=simulatorHost,SimulatorPort=simulatorPort};_enable=new EnableHysteresis(_config.GripEngageThreshold,_config.GripReleaseThreshold);
            _mapper=new HumanToRobotMapper(_config.MappingRadiusMeters);_workspace=new WorkspaceProjector(_config.Workspace);_ik=new PhantomInverseKinematics();_gripMapper=new GripMapper();_room=_fallbackRoom;
            _tracking=GetComponent<MetaQuestTrackingSource>()??gameObject.AddComponent<MetaQuestTrackingSource>();_hud=GetComponent<PhantomWristHud>()??gameObject.AddComponent<PhantomWristHud>();
            _validation=GetComponent<QuestValidationRunner>()??gameObject.AddComponent<QuestValidationRunner>();
            _logger=new QuestJsonlLogger();
            try{_network=new PhantomUdpClient(_config.SimulatorHost,_config.SimulatorPort);}catch(Exception e){Debug.LogError("PHANTOM UDP init: "+e.Message);}
            _logger.Log("runtime","app_launch",_stateMachine.State.ToString(),_network?.SessionId.ToString()??"",$"{{\"room_adapter\":\"{_room.StatusReason}\"}}");
        }

        void Update()
        {
            if(_network!=null){try{_network.Poll();}catch(Exception e){Debug.LogWarning("PHANTOM UDP poll: "+e.Message);}}
            _room=RoomReferenceRegistry.Current??_fallbackRoom;_tracking.TryGetFrame(out var frame);var held=_enable.Update(frame.LeftController.GripAnalog);
            UpdateRobotCalibration();UpdateUserCalibration(frame);
            var networkReady=_network!=null&&_network.NetworkReady&&_network.Capabilities.Homed;var fault=_network!=null&&(_network.LastTelemetry.Fault!=0||_network.LastTelemetry.State==RobotRuntimeState.Fault);
            var predicates=new SafetyPredicates{AppFocused=frame.AppFocused,RightHandValid=frame.RightHand.Valid&&frame.RightHand.Wrist.Valid,LeftControllerValid=frame.LeftController.Valid,EnableHeld=held,RoomValid=_room.IsReady,RobotGeometryValid=_robotGeometry.Valid,UserCalibrationValid=_userCalibration.Quality.Valid,NetworkReady=networkReady,Fault=fault};
            LogPredicateTransitions(predicates,frame);
            var state=_stateMachine.Update(predicates);
            if(state!=_previousState){_logger.Log("runtime","state_transition",state.ToString(),SessionId,$"{{\"from\":\"{_previousState}\"}}");if(state==PhantomState.SafeHold)_tracking.Haptic(0.8f,0.35f);_previousState=state;}
            var humanVector=CurrentHumanVectorRobot(frame);var l1=_robotGeometry.Valid?_robotGeometry.L1:_config.L1Meters;var l2=_robotGeometry.Valid?_robotGeometry.L2:_config.L2Meters;
            if(held&&!_wasEnableHeld&&state==PhantomState.Tracking)
            {
                var currentTcp=_network!=null&&_network.NetworkReady?new PhantomForwardKinematics().Solve(_network.LastTelemetry.Actual,l1,l2):_targetTcp;
                if(_mapper.Engage(humanVector,Vec3.Zero,_userCalibration.ArmLengthWristMeters,currentTcp))_tracking.Haptic(0.5f,0.06f);
            }
            if(!held&&_wasEnableHeld)_mapper.Release();_wasEnableHeld=held;
            if(state==PhantomState.Tracking&&_mapper.TryMap(humanVector,Vec3.Zero,_userCalibration.ArmLengthWristMeters,out var requested))
            {
                var projection=_workspace.Project(requested);var ik=_ik.Solve(projection.Projected,l1,l2);
                if(ik.Success){var limits=_network!=null&&_network.HandshakeComplete?_network.Capabilities.Limits:_config.FallbackJointLimits;_targetAngles=new JointLimitProjector(limits).Project(ik.Angles,out _);_targetTcp=new PhantomForwardKinematics().Solve(_targetAngles,l1,l2);}_gripIntent=_gripMapper.Map(frame.RightHand.Grasp.Value01,frame.RightHand.Grasp.Ready,frame.RightHand.Grasp.Valid,_gripIntent);
            }
            SendLatest(state,frame.MonotonicTimeUs);if((++_logDivider%10)==0)_logger.Log("runtime","runtime_sample",state.ToString(),SessionId,JsonUtility.ToJson(new RuntimeSample{tracking=frame,q_target=_targetAngles,target_tcp=_targetTcp,grip_intent=_gripIntent,network_ready=predicates.NetworkReady,q_actual=_network!=null?_network.LastTelemetry.Actual:default,room_ready=_room.IsReady,room_status=_room.StatusReason,floor_origin=_room.FloorOrigin}));
            UpdatePerformance();UpdateHud(state,frame,predicates,held);
            _previousPredicates=predicates;
        }

        void UpdatePerformance()
        {
            var delta=Mathf.Max(.0001f,Time.unscaledDeltaTime);
            _smoothedDeltaTime=_smoothedDeltaTime<=0?delta:Mathf.Lerp(_smoothedDeltaTime,delta,.05f);
            var now=Time.realtimeSinceStartupAsDouble;if(now<_nextPerformanceLog)return;_nextPerformanceLog=now+5.0;
            var monoMb=Profiler.GetMonoUsedSizeLong()/(1024f*1024f);var allocatedMb=Profiler.GetTotalAllocatedMemoryLong()/(1024f*1024f);
            var sample=new PerformanceSample{fps=1f/_smoothedDeltaTime,mono_used_mb=monoMb,allocated_mb=allocatedMb};
            sample.app_cpu_time=OVRPlugin.GetPerfMetricsFloat(OVRPlugin.PerfMetrics.App_CpuTime_Float).GetValueOrDefault(-1f);
            sample.app_gpu_time=OVRPlugin.GetPerfMetricsFloat(OVRPlugin.PerfMetrics.App_GpuTime_Float).GetValueOrDefault(-1f);
            sample.compositor_dropped_frames=OVRPlugin.GetPerfMetricsInt(OVRPlugin.PerfMetrics.Compositor_DroppedFrameCount_Int).GetValueOrDefault(-1);
            sample.spacewarp_mode=OVRPlugin.GetPerfMetricsInt(OVRPlugin.PerfMetrics.Compositor_SpaceWarp_Mode_Int).GetValueOrDefault(-1);
            if(sample.compositor_dropped_frames>=0)
            {
                if(_baselineCompositorDroppedFrames<0)_baselineCompositorDroppedFrames=sample.compositor_dropped_frames;
                sample.compositor_dropped_frames_since_launch=Math.Max(0,sample.compositor_dropped_frames-_baselineCompositorDroppedFrames);
            }
            _performanceStatus=$"КАДР/С {sample.fps:F0}  ПАМЯТЬ {allocatedMb:F0} МБ  ПРОПУСКИ {(sample.compositor_dropped_frames_since_launch>=0?sample.compositor_dropped_frames_since_launch.ToString():"Н/Д")}";
            _logger.Log("runtime","performance_sample",_stateMachine.State.ToString(),SessionId,JsonUtility.ToJson(sample));
        }

        void UpdateHud(PhantomState state,TrackingFrame frame,SafetyPredicates predicates,bool held)
        {
            var now=Time.realtimeSinceStartupAsDouble;if(now<_nextHudUpdate)return;_nextHudUpdate=now+.10;
            _hud.SetTracking(frame);var validationText=_validation!=null?"\n\n"+_validation.HudText:"";
            var roomText=state==PhantomState.RoomRequired?"\nКОМНАТА: "+_room.StatusReason:"";
            _hud.Content=$"PHANTOM — {StateName(state)}  {_performanceStatus}\nСИМУЛЯТОР {ReadyName(_network?.NetworkReady==true)}  РУКА {TrackingName(predicates.RightHandValid)}  КОНТРОЛЛЕР {TrackingName(predicates.LeftControllerValid)}\nОБА {YesNo(frame.BothValid)}  СОВМЕСТНЫЙ РЕЖИМ {OnWait(frame.MultimodalConfigured)}\nИСТОЧНИК {InteractionName(frame.InteractionMode)}\nУПРАВЛЕНИЕ {(held?"УДЕРЖИВАЕТСЯ":"ОТПУЩЕНО")}  СЖАТИЕ {(frame.RightHand.Grasp.Ready?frame.RightHand.Grasp.Value01.ToString("F2"):"Н/Д")}\n{StartupWizardModel.Instruction(state)}{roomText}{validationText}";
        }

        static string StateName(PhantomState state)
        {
            switch(state)
            {
                case PhantomState.Disconnected:return "НЕТ СВЯЗИ";
                case PhantomState.Initializing:return "ИНИЦИАЛИЗАЦИЯ";
                case PhantomState.RoomRequired:return "НУЖНА КОМНАТА";
                case PhantomState.RobotCalibration:return "КАЛИБРОВКА РОБОТА";
                case PhantomState.UserCalibration:return "КАЛИБРОВКА ПОЛЬЗОВАТЕЛЯ";
                case PhantomState.Ready:return "ГОТОВО";
                case PhantomState.ArmedHold:return "ОЖИДАНИЕ ВКЛЮЧЕНИЯ";
                case PhantomState.Tracking:return "СЛЕЖЕНИЕ";
                case PhantomState.SafeHold:return "БЕЗОПАСНАЯ ОСТАНОВКА";
                case PhantomState.Fault:return "ОШИБКА";
                default:return state.ToString();
            }
        }

        static string InteractionName(string mode)
        {
            switch(mode)
            {
                case "simultaneous":return "РУКА + КОНТРОЛЛЕР";
                case "hand_only":return "ТОЛЬКО РУКА";
                case "controller_only":return "ТОЛЬКО КОНТРОЛЛЕР";
                case "none":return "НЕТ";
                default:return "ОЖИДАНИЕ";
            }
        }

        static string ReadyName(bool value)=>value?"ГОТОВ":"ОЖИДАНИЕ";
        static string TrackingName(bool value)=>value?"ВИДНА":"ПОТЕРЯНА";
        static string YesNo(bool value)=>value?"ДА":"НЕТ";
        static string OnWait(bool value)=>value?"ВКЛ":"ОЖИДАНИЕ";

        void UpdateRobotCalibration()
        {
            if(_robotGeometry.Valid)return;var tracker=RobotMarkerTrackerRegistry.Current;if(tracker==null||!tracker.IsAvailable||!tracker.TryGetSnapshot(out var snapshot))return;
            var now=Time.realtimeSinceStartupAsDouble;_robotSession.Add(now,snapshot);
            if(_robotSession.TryFinish(now,out var geometry)){_robotGeometry=geometry;_logger.Log("Q7_MarkerRig","robot_geometry_locked",_stateMachine.State.ToString(),SessionId,JsonUtility.ToJson(new RobotGeometryLog{l1=geometry.L1,l2=geometry.L2,samples=_robotSession.Quality.SampleCount,max_position_std_m=_robotSession.Quality.MaxPositionStdMeters}));}
            else if(_robotSession.Quality.WindowSeconds>=1.0&&_robotSession.Quality.Reason!="collecting"){_logger.Log("Q7_MarkerRig","robot_geometry_rejected",_stateMachine.State.ToString(),SessionId,JsonUtility.ToJson(_robotSession.Quality));_robotSession.Reset();}
        }

        void UpdateUserCalibration(TrackingFrame frame)
        {
            var yRising=frame.LeftController.Y&&!_lastY;_lastY=frame.LeftController.Y;
            if(!_room.IsReady||!_robotGeometry.Valid||!frame.Head.Valid)return;
            if(!_calibrating&&yRising)
            {
                _userWizard=new UserCalibrationWizard(new CalibrationZone{Center=frame.Head.Position,RadiusMeters=.15});_userWizard.Start(frame);_calibrating=true;_logger.Log("Q8_UserShoulderFit","calibration_start",_stateMachine.State.ToString(),SessionId);return;
            }
            if(!_calibrating)return;_userWizard.Add(frame);
            if(yRising&&_userWizard.SampleCount>=100)
            {
                _userCalibration=_userWizard.Finish(frame);_calibrating=false;_logger.Log("Q8_UserShoulderFit","calibration_result",_stateMachine.State.ToString(),SessionId,JsonUtility.ToJson(_userCalibration));
            }
        }

        Vec3 CurrentHumanVectorRobot(TrackingFrame frame)
        {
            if(!_userCalibration.Quality.Valid||!frame.Head.Valid||!frame.RightHand.Wrist.Valid||!_robotGeometry.Valid)return Vec3.Zero;
            var shoulder=_userCalibration.RuntimeShoulder(frame.Head.Position);return _robotGeometry.BaseFrame.RoomVectorToRobot(frame.RightHand.Wrist.Position-shoulder);
        }

        void SendLatest(PhantomState state,long timeUs)
        {
            if(_network==null||Time.realtimeSinceStartupAsDouble<_nextSend)return;_nextSend=Time.realtimeSinceStartupAsDouble+0.02;
            var flags=!_network.HandshakeComplete?CommandFlags.Hello:state==PhantomState.Tracking?CommandFlags.Tracking:state==PhantomState.SafeHold?CommandFlags.SafeHold:CommandFlags.Hold;
            try{_network.Send(_targetAngles,_gripIntent,flags,(ulong)Math.Max(0,timeUs));}catch(Exception e){Debug.LogWarning("PHANTOM UDP send: "+e.Message);}
        }
        string SessionId=>_network?.SessionId.ToString()??"";
        void LogPredicateTransitions(SafetyPredicates p,TrackingFrame frame)
        {
            Transition("app_focused",_previousPredicates.AppFocused,p.AppFocused);Transition("right_hand_valid",_previousPredicates.RightHandValid,p.RightHandValid);Transition("left_controller_valid",_previousPredicates.LeftControllerValid,p.LeftControllerValid);Transition("enable_held",_previousPredicates.EnableHeld,p.EnableHeld);Transition("room_valid",_previousPredicates.RoomValid,p.RoomValid);Transition("robot_geometry_valid",_previousPredicates.RobotGeometryValid,p.RobotGeometryValid);Transition("user_calibration_valid",_previousPredicates.UserCalibrationValid,p.UserCalibrationValid);Transition("network_ready",_previousPredicates.NetworkReady,p.NetworkReady);
            Transition("both_valid",_previousBothValid,frame.BothValid);Transition("multimodal_configured",_previousMultimodalConfigured,frame.MultimodalConfigured);
            if(_previousInteractionMode!=frame.InteractionMode||_previousInteractionSource!=frame.InteractionSource)_logger.Log("runtime","interaction_source",_stateMachine.State.ToString(),SessionId,JsonUtility.ToJson(new InteractionLog{mode=frame.InteractionMode,source=frame.InteractionSource,multimodal_status=_tracking.MultimodalStatus}));
            _previousBothValid=frame.BothValid;_previousMultimodalConfigured=frame.MultimodalConfigured;_previousInteractionMode=frame.InteractionMode;_previousInteractionSource=frame.InteractionSource;
        }
        void Transition(string name,bool before,bool after){if(before!=after)_logger.Log("runtime",name,_stateMachine.State.ToString(),SessionId,$"{{\"value\":{after.ToString().ToLowerInvariant()}}}");}
        void OnApplicationFocus(bool focused){_logger?.Log("runtime",focused?"focus_gained":"focus_lost",_stateMachine.State.ToString(),SessionId);}
        void OnApplicationPause(bool paused){_logger?.Log("runtime",paused?"pause":"resume",_stateMachine.State.ToString(),SessionId);}
        void OnDestroy(){_network?.Dispose();_logger?.Dispose();}
        [Serializable] sealed class RuntimeSample{public TrackingFrame tracking;public JointAngles q_target;public Vec3 target_tcp;public float grip_intent;public bool network_ready;public JointAngles q_actual;public bool room_ready;public string room_status;public Vec3 floor_origin;}
        [Serializable] sealed class PerformanceSample
        {
            public float fps,mono_used_mb,allocated_mb;
            public float app_cpu_time=-1,app_gpu_time=-1;
            public int compositor_dropped_frames=-1,compositor_dropped_frames_since_launch=-1,spacewarp_mode=-1;
        }
        [Serializable] sealed class RobotGeometryLog{public double l1,l2;public int samples;public double max_position_std_m;}
        [Serializable] sealed class InteractionLog{public string mode,source,multimodal_status;}
    }

    public static class PhantomBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Install(){if(UnityEngine.Object.FindFirstObjectByType<PhantomRuntime>()!=null)return;var go=new GameObject("PhantomRuntime");UnityEngine.Object.DontDestroyOnLoad(go);go.AddComponent<PhantomRuntime>();}
    }
}
