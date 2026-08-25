using System;
using Phantom.Kinematics;
using Phantom.Networking;

namespace Phantom.Telemetry
{
    [Serializable]
    public struct TelemetrySnapshot
    {
        public ulong SessionId; public uint LastSequence; public JointAngles Target; public JointAngles Actual; public JointAngles Speed;
        public float GripIntent; public float GripActual; public float WatchdogAgeMs; public RobotRuntimeState State; public uint Fault;
    }
}
