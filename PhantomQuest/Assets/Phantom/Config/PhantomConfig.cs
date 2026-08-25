using System;
using Phantom.Kinematics;
using Phantom.Workspace;

namespace Phantom.Config
{
    [Serializable]
    public sealed class PhantomConfig
    {
        public string SimulatorHost = "192.168.0.112";
        public int SimulatorPort = 31337;
        public double L1Meters = 0.215;
        public double L2Meters = 0.215;
        public double MappingRadiusMeters = 0.32;
        public float GripEngageThreshold = 0.75f;
        public float GripReleaseThreshold = 0.55f;
        public WorkspaceConfig Workspace = WorkspaceConfig.Default;
        public JointLimits FallbackJointLimits = new JointLimits(new JointAngles(-2.8, -1.2, 0.0), new JointAngles(2.8, 1.4, 2.8));
    }
}
