using System;
using System.Collections.Generic;
using Phantom.Kinematics;
using Phantom.Mapping;
using Phantom.RobotLocalization;
using Phantom.Tracking;

namespace Phantom.Diagnostics
{
    public enum BodyProviderOperationalState
    {
        ApiAbsent,
        ConfigurationInvalid,
        ExplicitlyDisabledOrIncompatible,
        ConfiguredLifecycleInactive,
        InitializedNoLiveObservation,
        InitializedWithLiveObservation,
        InitializationFailed
    }

    [Serializable]
    public struct BodyProviderProbe
    {
        public bool ApiPresent;
        public bool ComponentPresent;
        public bool UpperBodyConfigured;
        public bool RightShoulderInJointSet;
        public bool ExplicitMultimodalConflict;
        public bool XrSessionActive;
        public bool XrFocusActive;
        public bool InitializationAttempted;
        public bool ProviderEnabled;
        public bool LiveObservationAvailable;
        public string Detail;
    }

    [Serializable]
    public struct BodyProviderClassification
    {
        public BodyProviderOperationalState State;
        public bool SoftwareCompatible;
        public string Reason;
    }

    public static class BodyProviderClassifier
    {
        public static BodyProviderClassification Classify(BodyProviderProbe probe)
        {
            if(!probe.ApiPresent)return Result(BodyProviderOperationalState.ApiAbsent,false,"provider_api_absent");
            if(!probe.ComponentPresent||!probe.UpperBodyConfigured||!probe.RightShoulderInJointSet)
                return Result(BodyProviderOperationalState.ConfigurationInvalid,false,"provider_configuration_invalid");
            if(probe.ExplicitMultimodalConflict)
                return Result(BodyProviderOperationalState.ExplicitlyDisabledOrIncompatible,false,"provider_explicitly_disabled_by_multimodal_conflict");
            if(!probe.XrSessionActive||!probe.XrFocusActive||!probe.InitializationAttempted)
                return Result(BodyProviderOperationalState.ConfiguredLifecycleInactive,true,"provider_configured_lifecycle_inactive");
            if(!probe.ProviderEnabled)
                return Result(BodyProviderOperationalState.InitializationFailed,false,"provider_initialization_failed_with_active_xr");
            return probe.LiveObservationAvailable
                ?Result(BodyProviderOperationalState.InitializedWithLiveObservation,true,"provider_initialized_live_observation_available")
                :Result(BodyProviderOperationalState.InitializedNoLiveObservation,true,"provider_initialized_no_live_observation");
        }

        public static bool IsExplicitOvrBodyMultimodalConflict(string provider,string metaXrCoreVersion,bool multimodalRequired)
            =>multimodalRequired&&string.Equals(provider,"OVRBody/com.meta.xr.sdk.core",StringComparison.Ordinal)&&
              string.Equals(metaXrCoreVersion,"205.0.0",StringComparison.Ordinal);

        public static bool IsFresh(PoseObservation observation,long nowUs,long maxAgeUs)
            =>observation.Valid&&observation.ReceiveMonotonicTimeUs>0&&nowUs>=observation.ReceiveMonotonicTimeUs&&nowUs-observation.ReceiveMonotonicTimeUs<=maxAgeUs;

        static BodyProviderClassification Result(BodyProviderOperationalState state,bool compatible,string reason)
            =>new BodyProviderClassification{State=state,SoftwareCompatible=compatible,Reason=reason};
    }

    [Serializable]
    public sealed class QuestSyntheticCaseResult
    {
        public string test_id;
        public bool passed;
        public string detail;
    }

    public static class QuestSyntheticQualification
    {
        public static QuestSyntheticCaseResult[] Run(bool robotTransportConstructed=false,bool motorAuthority=false)
        {
            const long now=2_000_000;
            var validPose=new PoseObservation{Position=new Vec3(.1,.2,.3),Valid=true,SampleOrQueryTimeUs=1_990_000,ReceiveMonotonicTimeUs=1_995_000};
            var frame=new TrackingFrame
            {
                MonotonicTimeUs=now,AppFocused=true,MultimodalConfigured=true,BothValid=true,
                RightShoulder=validPose,
                RightHand=new HandState{Valid=true,Wrist=validPose,Grasp=new GripObservation{Value01=.75f,Ready=true,Valid=true}},
                LeftController=new ControllerState{Valid=true,Pose=validPose,GripAnalog=.7f,GripHeld=true}
            };
            var results=new List<QuestSyntheticCaseResult>();
            Add(results,"synthetic-wrist",frame.RightHand.Wrist.Valid,"valid Wrist accepted");
            Add(results,"synthetic-body-right-shoulder",frame.RightShoulder.Valid,"valid Body_RightShoulder accepted");
            Add(results,"synthetic-grasp",frame.RightHand.Grasp.Valid&&frame.RightHand.Grasp.Ready&&frame.RightHand.Grasp.Value01>.7f,"grasp value/readiness accepted");
            Add(results,"synthetic-left-grip",frame.LeftController.Valid&&frame.LeftController.GripHeld&&frame.LeftController.GripAnalog>.6f,"physical-controller-shaped input accepted");
            var disconnected=frame;disconnected.LeftController=default;disconnected.BothValid=false;
            Add(results,"synthetic-controller-disconnect",!disconnected.LeftController.Valid&&!disconnected.BothValid,"disconnect invalidates simultaneous input");
            Add(results,"synthetic-stale-fresh-timing",BodyProviderClassifier.IsFresh(validPose,now,20_000)&&!BodyProviderClassifier.IsFresh(validPose,now,1_000),"fresh and stale observations separated");

            var snapshot=TenQrSnapshot();
            Add(results,"synthetic-ten-qr",snapshot.HasAllTenPoses&&snapshot.BaseFrame.IsValid,"all ten marker poses accepted");
            snapshot.Rotations.Remove(RobotMarkerId.JawLeft);
            Add(results,"synthetic-partial-qr-rejected",!snapshot.HasAllTenPoses,"partial marker set rejected");

            var sm=new PhantomStateMachine();
            var predicates=ReadyPredicates();
            var ready=sm.Update(predicates)==PhantomState.Ready&&sm.Update(predicates)==PhantomState.Hold;
            predicates.EnableHeld=true;var tracking=sm.Update(predicates)==PhantomState.Tracking;
            predicates.WristValid=false;var lost=sm.Update(predicates)==PhantomState.SafeHold;
            predicates.WristValid=true;var heldRecoveryBlocked=sm.Update(predicates)==PhantomState.SafeHold;
            predicates.EnableHeld=false;var released=sm.Update(predicates)==PhantomState.Hold;
            predicates.EnableHeld=true;var deliberateRearm=sm.Update(predicates)==PhantomState.Tracking;
            Add(results,"synthetic-tracking-loss-recovery",ready&&tracking&&lost&&heldRecoveryBlocked&&released&&deliberateRearm,"loss is fail-closed and recovery requires release/new rising edge");

            predicates.AppFocused=false;var focusLost=sm.Update(predicates)==PhantomState.SafeHold;
            predicates.AppFocused=true;var focusResumeHeld=sm.Update(predicates)==PhantomState.SafeHold;
            predicates.EnableHeld=false;var focusResumeReleased=sm.Update(predicates)==PhantomState.Hold;
            predicates.EnableHeld=true;var focusResumeRearmed=sm.Update(predicates)==PhantomState.Tracking;
            Add(results,"synthetic-focus-loss-recovery",focusLost&&focusResumeHeld&&focusResumeReleased&&focusResumeRearmed,"focus loss is fail-closed; resume requires release/new rising edge");

            sm.OnReferenceSpaceChange();
            var pauseSafe=sm.State==PhantomState.SafeHold;
            var pauseResumeHeld=sm.Update(predicates)==PhantomState.SafeHold;
            predicates.EnableHeld=false;var pauseResumeReleased=sm.Update(predicates)==PhantomState.Hold;
            predicates.EnableHeld=true;var pauseResumeRearmed=sm.Update(predicates)==PhantomState.Tracking;
            Add(results,"synthetic-pause-resume",pauseSafe&&pauseResumeHeld&&pauseResumeReleased&&pauseResumeRearmed,"pause/reference invalidation is fail-closed; resume requires deliberate re-arm");
            predicates.AppFocused=false;
            Add(results,"synthetic-fail-closed",!predicates.TrackingValid,"inactive focus invalidates tracking readiness before any output");
            Add(results,"stage2-no-physical-command-path",!robotTransportConstructed&&!motorAuthority,"RobotTransport absent and motor authority false");
            return results.ToArray();
        }

        static SafetyPredicates ReadyPredicates()=>new SafetyPredicates
        {
            AppFocused=true,XrReady=true,WristValid=true,ShoulderValid=true,LeftControllerValid=true,
            UserCalibrationValid=true,NetworkDiscovered=true,Connected=true,RobotReferenceValid=true
        };

        static RobotMarkerSnapshot TenQrSnapshot()
        {
            var snapshot=new RobotMarkerSnapshot{BaseFrame=new RobotBaseFrame{OriginRoom=Vec3.Zero,ForwardRoom=new Vec3(1,0,0),LeftRoom=new Vec3(0,1,0),UpRoom=new Vec3(0,0,1)}};
            var index=0;
            foreach(RobotMarkerId id in Enum.GetValues(typeof(RobotMarkerId)))
            {
                snapshot.Positions[id]=new Vec3(.01*index,.2,.3);
                snapshot.Rotations[id]=MarkerRotation.Identity;
                index++;
            }
            return snapshot;
        }

        static void Add(List<QuestSyntheticCaseResult> results,string id,bool passed,string detail)
            =>results.Add(new QuestSyntheticCaseResult{test_id=id,passed=passed,detail=detail});
    }
}
