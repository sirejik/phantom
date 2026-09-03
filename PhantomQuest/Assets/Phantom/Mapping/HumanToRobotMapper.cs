using System;
using Phantom.Kinematics;
namespace Phantom.Mapping
{
    public sealed class HumanToRobotMapper
    {
        readonly double _robotReach,_humanVectorMin;
        public HumanToRobotMapper(double robotNominalReach,double humanVectorMin=.05){if(robotNominalReach<=0||humanVectorMin<=0)throw new ArgumentOutOfRangeException();_robotReach=robotNominalReach;_humanVectorMin=humanVectorMin;}
        public bool TryMapVector(Vec3 shoulderToWristRobot,double humanArmReach,out Vec3 requested)
        {
            requested=Vec3.Zero;if(!shoulderToWristRobot.IsFinite||!Vec3.IsFiniteNumber(humanArmReach)||humanArmReach<=0)return false;var d=shoulderToWristRobot.Magnitude;if(d<_humanVectorMin)return false;var ratio=Math.Max(0,Math.Min(1,d/humanArmReach));requested=shoulderToWristRobot/d*(_robotReach*ratio);return requested.IsFinite;
        }
    }
    public sealed class GripMapper { public bool TryMap(float value,bool ready,bool valid,out float mapped){mapped=0;if(!valid||!ready||float.IsNaN(value)||float.IsInfinity(value))return false;mapped=Math.Max(0,Math.Min(1,value));return true;} }
}
