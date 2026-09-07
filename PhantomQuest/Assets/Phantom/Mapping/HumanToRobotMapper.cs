using System;
using Phantom.Kinematics;

namespace Phantom.Mapping
{
    /// <summary>
    /// Commissioning-owned inputs to the absolute mapping (REFERENCE 11.1.1).
    /// Every field is a measured/commissioned parameter carried by RobotGeometry
    /// or the Quest human-mapping configuration; none of them may be a compiled-in
    /// default, because a wrong reach or scale ceiling directly changes how far
    /// the robot is commanded to move.
    /// </summary>
    [Serializable]
    public struct MappingProfile
    {
        /// <summary>RobotGeometry.robot_nominal_reach_m.</summary>
        public double RobotNominalReachM;
        /// <summary>Qualified linear mapping ceiling (quest human_mapping.max_mapping_scale).</summary>
        public double MaxMappingScale;
        /// <summary>Below this the shoulder-to-wrist vector carries no usable direction.</summary>
        public double HumanVectorMinM;

        public bool IsValid =>
            IsPositiveFinite(RobotNominalReachM) && IsPositiveFinite(MaxMappingScale) && IsPositiveFinite(HumanVectorMinM);

        static bool IsPositiveFinite(double value) => !double.IsNaN(value) && !double.IsInfinity(value) && value > 0;
    }

    public enum MappingStatus { Success, ProfileUnqualified, InvalidInput, VectorTooShort }

    public struct MappingResult
    {
        public MappingStatus Status;
        public Vec3 RequestedTargetB;
        /// <summary>min(robot_nominal_reach_m, human_arm_reach * max_mapping_scale).</summary>
        public double MappingReachM;
        public double ReachRatio;
        public bool Success => Status == MappingStatus.Success;
    }

    public sealed class HumanToRobotMapper
    {
        readonly MappingProfile _profile;

        /// <param name="profile">
        /// Commissioned mapping parameters. An invalid profile never produces a
        /// target: an unmeasured scale ceiling must block motion, not silently fall
        /// back to the robot's full reach.
        /// </param>
        public HumanToRobotMapper(MappingProfile profile) { _profile = profile; }

        public MappingResult Map(Vec3 shoulderToWristRobot, double humanArmReach)
        {
            var result = new MappingResult { Status = MappingStatus.InvalidInput };
            if (!_profile.IsValid) { result.Status = MappingStatus.ProfileUnqualified; return result; }
            if (!shoulderToWristRobot.IsFinite || !Vec3.IsFiniteNumber(humanArmReach) || humanArmReach <= 0) return result;

            var distance = shoulderToWristRobot.Magnitude;
            if (distance < _profile.HumanVectorMinM) { result.Status = MappingStatus.VectorTooShort; return result; }

            // REFERENCE 11.1.1 / FR-MAP-08. The scale ceiling is the reason this is a
            // `min`: without it a short calibrated arm would amplify tracking noise
            // by robot_nominal_reach / human_arm_reach, which is exactly what
            // max_mapping_scale is qualified to bound.
            var mappingReach = Math.Min(_profile.RobotNominalReachM, humanArmReach * _profile.MaxMappingScale);
            var reachRatio = Math.Max(0, Math.Min(1, distance / humanArmReach));
            var requested = shoulderToWristRobot / distance * (mappingReach * reachRatio);
            if (!requested.IsFinite) return result;

            result.Status = MappingStatus.Success;
            result.RequestedTargetB = requested;
            result.MappingReachM = mappingReach;
            result.ReachRatio = reachRatio;
            return result;
        }

        public bool TryMapVector(Vec3 shoulderToWristRobot, double humanArmReach, out Vec3 requested)
        {
            var result = Map(shoulderToWristRobot, humanArmReach);
            requested = result.Success ? result.RequestedTargetB : Vec3.Zero;
            return result.Success;
        }
    }

    public sealed class GripMapper
    {
        public bool TryMap(float value, bool ready, bool valid, out float mapped)
        {
            mapped = 0;
            if (!valid || !ready || float.IsNaN(value) || float.IsInfinity(value)) return false;
            mapped = Math.Max(0, Math.Min(1, value));
            return true;
        }
    }
}
