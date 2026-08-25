using System;
using Phantom.Kinematics;

namespace Phantom.Mapping
{
    [Serializable]
    public struct EngageAnchorState
    {
        public bool Valid;
        public Vec3 HumanAnchor;
        public Vec3 RobotAnchor;
    }

    public sealed class HumanToRobotMapper
    {
        readonly double _mappingRadius;
        EngageAnchorState _anchor;
        Vec3 _heldTarget;

        public HumanToRobotMapper(double mappingRadius) { if (mappingRadius <= 0) throw new ArgumentOutOfRangeException(nameof(mappingRadius)); _mappingRadius = mappingRadius; }
        public EngageAnchorState Anchor => _anchor;
        public Vec3 HeldTarget => _heldTarget;

        public bool Engage(Vec3 wristRoom, Vec3 shoulderRoom, double armLength, Vec3 currentRobotTcp)
        {
            if (!TryNormalize(wristRoom, shoulderRoom, armLength, out var human) || !currentRobotTcp.IsFinite) return false;
            _anchor = new EngageAnchorState { Valid = true, HumanAnchor = human, RobotAnchor = currentRobotTcp };
            _heldTarget = currentRobotTcp;
            return true;
        }

        public bool TryMap(Vec3 wristRoom, Vec3 shoulderRoom, double armLength, out Vec3 target)
        {
            target = _heldTarget;
            if (!_anchor.Valid || !TryNormalize(wristRoom, shoulderRoom, armLength, out var human)) return false;
            target = _anchor.RobotAnchor + _mappingRadius * (human - _anchor.HumanAnchor);
            _heldTarget = target;
            return target.IsFinite;
        }

        public void Release() { _anchor.Valid = false; }

        public static bool TryNormalize(Vec3 wristRoom, Vec3 shoulderRoom, double armLength, out Vec3 normalized)
        {
            normalized = Vec3.Zero;
            if (!wristRoom.IsFinite || !shoulderRoom.IsFinite || !Vec3.IsFiniteNumber(armLength) || armLength <= 1e-6) return false;
            normalized = (wristRoom - shoulderRoom) / armLength;
            return normalized.IsFinite;
        }
    }

    public sealed class GripMapper
    {
        public float Map(float value01, bool ready, bool valid, float heldValue)
        {
            if (!valid || !ready || float.IsNaN(value01) || float.IsInfinity(value01)) return heldValue;
            return Math.Max(0f, Math.Min(1f, value01));
        }
    }
}
