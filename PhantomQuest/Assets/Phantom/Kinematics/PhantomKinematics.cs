using System;

namespace Phantom.Kinematics
{
    public enum IkStatus { Success, Projected, Unreachable, NearAxis, Invalid }

    public struct IkResult
    {
        public IkStatus Status;
        public JointAngles Angles;
        public Vec3 SolvedTarget;
        public bool Success => Status == IkStatus.Success || Status == IkStatus.Projected;
    }

    public sealed class PhantomForwardKinematics
    {
        public Vec3 Solve(JointAngles q, double l1, double l2)
        {
            if (!q.IsFinite || !Vec3.IsFiniteNumber(l1) || !Vec3.IsFiniteNumber(l2) || l1 <= 0 || l2 <= 0)
                return new Vec3(double.NaN, double.NaN, double.NaN);
            var radial = l1 * Math.Cos(q.Shoulder) + l2 * Math.Cos(q.Shoulder + q.Elbow);
            var z = l1 * Math.Sin(q.Shoulder) + l2 * Math.Sin(q.Shoulder + q.Elbow);
            return new Vec3(radial * Math.Cos(q.Base), radial * Math.Sin(q.Base), z);
        }
    }

    public sealed class PhantomInverseKinematics
    {
        readonly int _elbowBranch;
        readonly double _yawSingularityHoldRadiusM;

        /// <param name="yawSingularityHoldRadiusM">
        /// RobotGeometry.yaw_singularity_hold_radius_m. It is a commissioned
        /// measurement, so there is deliberately no default: inside this radius the
        /// Base yaw is not conditioned and the target must be rejected rather than
        /// resolved from an arbitrary or historical yaw (SAFETY S27).
        /// </param>
        public PhantomInverseKinematics(double yawSingularityHoldRadiusM, int elbowBranch = 1)
        {
            if (elbowBranch != -1 && elbowBranch != 1) throw new ArgumentOutOfRangeException(nameof(elbowBranch));
            if (double.IsNaN(yawSingularityHoldRadiusM) || double.IsInfinity(yawSingularityHoldRadiusM) || yawSingularityHoldRadiusM <= 0)
                throw new ArgumentOutOfRangeException(nameof(yawSingularityHoldRadiusM));
            _elbowBranch = elbowBranch;
            _yawSingularityHoldRadiusM = yawSingularityHoldRadiusM;
        }

        public IkResult Solve(Vec3 target, double l1, double l2, bool allowBoundaryProjection = false)
        {
            if (!target.IsFinite || !Vec3.IsFiniteNumber(l1) || !Vec3.IsFiniteNumber(l2) || l1 <= 0 || l2 <= 0)
                return new IkResult { Status = IkStatus.Invalid };
            var r = Math.Sqrt(target.X * target.X + target.Y * target.Y);
            if (r < _yawSingularityHoldRadiusM) return new IkResult { Status = IkStatus.NearAxis, SolvedTarget = target };
            var d = (r * r + target.Z * target.Z - l1 * l1 - l2 * l2) / (2 * l1 * l2);
            var status = IkStatus.Success;
            const double numericTolerance = 1e-12;
            if (d < -1 - numericTolerance || d > 1 + numericTolerance)
            {
                if (!allowBoundaryProjection) return new IkResult { Status = IkStatus.Unreachable, SolvedTarget = target };
                status = IkStatus.Projected;
            }
            d = Math.Max(-1, Math.Min(1, d));
            var elbow = Math.Atan2(_elbowBranch * Math.Sqrt(Math.Max(0, 1 - d * d)), d);
            var shoulder = Math.Atan2(target.Z, r) - Math.Atan2(l2 * Math.Sin(elbow), l1 + l2 * Math.Cos(elbow));
            var angles = new JointAngles(Math.Atan2(target.Y, target.X), shoulder, elbow);
            return new IkResult { Status = status, Angles = angles, SolvedTarget = new PhantomForwardKinematics().Solve(angles, l1, l2) };
        }
    }
}
