using System;
using Phantom.Kinematics;

namespace Phantom.Workspace
{
    [Serializable]
    public struct WorkspaceConfig
    {
        public double InnerReach;
        public double OuterReach;
        public double NearYawRadius;
        public double FloorZ;
        public double BaseForbiddenRadius;
        /// <summary>
        /// Synthetic, deliberately unqualified geometry for pure-logic tests only.
        /// The real values are MEASURED parameters carried by RobotGeometry in the
        /// CommissioningBundle; the actuator path must never take them from here.
        /// </summary>
        public static WorkspaceConfig UnqualifiedTestFixture => new WorkspaceConfig { InnerReach = 0.10, OuterReach = 0.43, NearYawRadius = 0.05, FloorZ = 0.02, BaseForbiddenRadius = 0.05 };
    }

    public struct WorkspaceProjection
    {
        public Vec3 Requested;
        public Vec3 Projected;
        public bool WasProjected;
        public string Reason;
    }

    public sealed class WorkspaceProjector
    {
        readonly WorkspaceConfig _config;
        public WorkspaceProjector(WorkspaceConfig config) { _config = config; }

        public WorkspaceProjection Project(Vec3 input)
        {
            var result = new WorkspaceProjection { Requested = input, Projected = input, Reason = "none" };
            if (!input.IsFinite) { result.Projected = Vec3.Zero; result.WasProjected = true; result.Reason = "invalid"; return result; }
            var p = input;
            if (p.Z < _config.FloorZ) { p.Z = _config.FloorZ; result.Reason = "floor"; }
            var yawRadius = Math.Sqrt(p.X * p.X + p.Y * p.Y);
            if (yawRadius < Math.Max(_config.NearYawRadius, _config.BaseForbiddenRadius))
            {
                var minimum = Math.Max(_config.NearYawRadius, _config.BaseForbiddenRadius);
                if (yawRadius < 1e-9) { p.X = minimum; p.Y = 0; }
                else { p.X *= minimum / yawRadius; p.Y *= minimum / yawRadius; }
                result.Reason = "near_yaw";
            }
            var distance = p.Magnitude;
            if (distance > _config.OuterReach) { p *= _config.OuterReach / distance; result.Reason = "outer_reach"; }
            else if (distance < _config.InnerReach && distance > 1e-9) { p *= _config.InnerReach / distance; result.Reason = "inner_reach"; }
            result.Projected = p;
            result.WasProjected = (p - input).Magnitude > 1e-9;
            return result;
        }
    }

    public sealed class JointLimitProjector
    {
        readonly JointLimits _limits;
        public JointLimitProjector(JointLimits limits) { _limits = limits; }
        public JointAngles Project(JointAngles angles, out bool changed)
        {
            var projected = _limits.Clamp(angles);
            changed = Math.Abs(projected.Base - angles.Base) > 1e-12 || Math.Abs(projected.Shoulder - angles.Shoulder) > 1e-12 || Math.Abs(projected.Elbow - angles.Elbow) > 1e-12;
            return projected;
        }
    }
}
