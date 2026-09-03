using System;
using Phantom.Kinematics;

namespace Phantom.Tracking
{
    [Serializable]
    public struct PoseObservation
    {
        public Vec3 Position;
        public bool Valid;
        public long SampleOrQueryTimeUs;
        public long ReceiveMonotonicTimeUs;
        public float TimeUncertaintyMs;
        public string Quality;
        public string RuntimeQuality;
    }

    [Serializable]
    public struct GripObservation
    {
        public float Value01;
        public bool Ready;
        public bool Valid;
    }

    [Serializable]
    public struct HandState
    {
        public PoseObservation Wrist;
        public PoseObservation Palm;
        public GripObservation Grasp;
        public bool Valid;
    }

    [Serializable]
    public struct ControllerState
    {
        public PoseObservation Pose;
        public float GripAnalog;
        public bool GripHeld;
        public float Trigger;
        public bool X;
        public bool Y;
        public bool Valid;
    }

    [Serializable]
    public struct TrackingFrame
    {
        public long MonotonicTimeUs;
        public PoseObservation Head;
        public PoseObservation RightShoulder;
        public HandState RightHand;
        public ControllerState LeftController;
        public bool AppFocused;
        public bool BothValid;
        public bool MultimodalConfigured;
        public string InteractionMode;
        public string InteractionSource;
    }

    public interface IPhantomTrackingSource
    {
        bool TryGetFrame(out TrackingFrame frame);
    }

    public interface IGripSignalProvider { GripObservation Current { get; } }

    public sealed class SyntheticTrackingSource : IPhantomTrackingSource
    {
        public TrackingFrame Frame;
        public bool TryGetFrame(out TrackingFrame frame){frame=Frame;return true;}
    }
}
