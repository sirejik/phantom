using System;
using Phantom.Kinematics;

namespace Phantom.Tracking
{
    public struct RobotBasis
    {
        public Vec3 OriginFloor,XFloor,YFloor,ZFloor;
        public bool Valid=>OriginFloor.IsFinite&&XFloor.IsFinite&&YFloor.IsFinite&&ZFloor.IsFinite&&Math.Abs(Vec3.Dot(Vec3.Cross(XFloor,YFloor),ZFloor)-1)<1e-6;
    }
    public interface IXrSpaceBridge
    {
        bool LocalFloorValid{get;}
        Vec3 FloorVectorToRobot(Vec3 floorVector,RobotBasis basis);
        void InvalidateReferenceSpace();
    }
    public sealed class XrSpaceBridge : IXrSpaceBridge
    {
        public bool LocalFloorValid{get;private set;}=true;
        public Vec3 FloorVectorToRobot(Vec3 v,RobotBasis b){if(!LocalFloorValid||!b.Valid||!v.IsFinite)throw new InvalidOperationException("invalid LOCAL_FLOOR/basis");return new Vec3(Vec3.Dot(v,b.XFloor),Vec3.Dot(v,b.YFloor),Vec3.Dot(v,b.ZFloor));}
        public void InvalidateReferenceSpace(){LocalFloorValid=false;}
        public void AcceptNewLocalFloor(){LocalFloorValid=true;}
        public static RobotBasis FromShoulderPair(Vec3 left,Vec3 right)
        {
            var z=new Vec3(0,1,0);var lateral=left-right-z*Vec3.Dot(left-right,z);if(lateral.Magnitude<1e-6)return default;var y=lateral.Normalized;var x=Vec3.Cross(y,z).Normalized;return new RobotBasis{OriginFloor=(left+right)*.5,XFloor=x,YFloor=y,ZFloor=z};
        }
    }
}
