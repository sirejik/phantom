using System;
using System.Collections.Generic;
using Phantom.Kinematics;

namespace Phantom.RobotLocalization
{
    public enum RobotMarkerId { ShoulderLeft,ShoulderRight,TurretLeft,TurretRight,ElbowLeft,ElbowRight,GripperLeft,GripperRight,JawLeft,JawRight }
    public struct MarkerRotation
    {
        public double X,Y,Z,W;
        public bool IsValid
        {
            get
            {
                if(double.IsNaN(X)||double.IsNaN(Y)||double.IsNaN(Z)||double.IsNaN(W)||double.IsInfinity(X)||double.IsInfinity(Y)||double.IsInfinity(Z)||double.IsInfinity(W))return false;
                var norm=X*X+Y*Y+Z*Z+W*W;return norm>.98&&norm<1.02;
            }
        }
        public static MarkerRotation Identity=>new MarkerRotation{W=1};
    }
    public struct MarkerObservation { public RobotMarkerId Id; public Vec3 PositionRoom; public MarkerRotation RotationRoom; public bool Valid; }
    public struct RobotBaseFrame
    {
        public Vec3 OriginRoom,ForwardRoom,LeftRoom,UpRoom;
        public bool IsValid=>OriginRoom.IsFinite&&ForwardRoom.IsFinite&&LeftRoom.IsFinite&&UpRoom.IsFinite&&ForwardRoom.Magnitude>.9&&LeftRoom.Magnitude>.9&&UpRoom.Magnitude>.9;
        public Vec3 RoomVectorToRobot(Vec3 value)=>new Vec3(Vec3.Dot(value,ForwardRoom),Vec3.Dot(value,LeftRoom),Vec3.Dot(value,UpRoom));
        public Vec3 RobotPointToRoom(Vec3 value)=>OriginRoom+ForwardRoom*value.X+LeftRoom*value.Y+UpRoom*value.Z;
    }
    public sealed class RobotMarkerSnapshot
    {
        public readonly Dictionary<RobotMarkerId,Vec3> Positions=new Dictionary<RobotMarkerId,Vec3>();
        public readonly Dictionary<RobotMarkerId,MarkerRotation> Rotations=new Dictionary<RobotMarkerId,MarkerRotation>();
        public RobotBaseFrame BaseFrame;
        public bool HasAllTenPoses
        {
            get
            {
                foreach(RobotMarkerId id in Enum.GetValues(typeof(RobotMarkerId)))
                    if(!Positions.TryGetValue(id,out var position)||!position.IsFinite||!Rotations.TryGetValue(id,out var rotation)||!rotation.IsValid)return false;
                return true;
            }
        }
    }
    [Serializable]
    public struct QrMarkerObservation
    {
        public string Payload;
        public Vec3 PositionRoom;
        public double RotationX,RotationY,RotationZ,RotationW;
        public bool Valid;
    }
    public interface IRobotMarkerTracker
    {
        bool IsAvailable{get;}
        string StatusReason{get;}
        void SetQrTrackingEnabled(bool enabled);
        bool TryGetSnapshot(out RobotMarkerSnapshot snapshot);
        bool TryGetQrSnapshot(string requiredPayload,out QrMarkerObservation observation);
    }
    public static class RobotMarkerTrackerRegistry { public static IRobotMarkerTracker Current{get;set;} }
    public struct RobotGeometry { public RobotBaseFrame BaseFrame; public Vec3 BaseOriginRoom; public Vec3 ShoulderRoom; public Vec3 ElbowRoom; public Vec3 GripperRoom; public double L1; public double L2; public double TurretYawRad; public bool Valid; public string Reason; }

    public sealed class RobotGeometryEstimator
    {
        public RobotGeometry Estimate(IReadOnlyDictionary<RobotMarkerId,Vec3> markers)
            =>Estimate(markers,default);
        public RobotGeometry Estimate(IReadOnlyDictionary<RobotMarkerId,Vec3> markers,RobotBaseFrame baseFrame)
        {
            foreach(RobotMarkerId id in Enum.GetValues(typeof(RobotMarkerId))) if(markers==null||!markers.ContainsKey(id)||!markers[id].IsFinite)return new RobotGeometry{Reason="missing_"+id};
            var shoulder=(markers[RobotMarkerId.ShoulderLeft]+markers[RobotMarkerId.ShoulderRight])*.5;var elbow=(markers[RobotMarkerId.ElbowLeft]+markers[RobotMarkerId.ElbowRight])*.5;var gripper=(markers[RobotMarkerId.GripperLeft]+markers[RobotMarkerId.GripperRight])*.5;
            var l1=(elbow-shoulder).Magnitude;var l2=(gripper-elbow).Magnitude;
            var plausible=l1>=0.08&&l1<=0.40&&l2>=0.08&&l2<=0.40;
            if(!baseFrame.IsValid){var b=Tracking.XrSpaceBridge.FromShoulderPair(markers[RobotMarkerId.ShoulderLeft],markers[RobotMarkerId.ShoulderRight]);baseFrame=new RobotBaseFrame{OriginRoom=b.OriginFloor,ForwardRoom=b.XFloor,LeftRoom=b.YFloor,UpRoom=b.ZFloor};}
            var turretRoom=markers[RobotMarkerId.TurretLeft]-markers[RobotMarkerId.TurretRight];var turret=baseFrame.RoomVectorToRobot(turretRoom);var horizontal=Math.Sqrt(turret.X*turret.X+turret.Y*turret.Y);var turretValid=horizontal>=.02;var yaw=turretValid?Math.Atan2(-turret.X,turret.Y):0;
            return new RobotGeometry{BaseFrame=baseFrame,BaseOriginRoom=baseFrame.OriginRoom,ShoulderRoom=shoulder,ElbowRoom=elbow,GripperRoom=gripper,L1=l1,L2=l2,TurretYawRad=yaw,Valid=plausible&&baseFrame.IsValid&&turretValid,Reason=!plausible?"implausible_geometry_provisional":!turretValid?"turret_pair_degenerate":""};
        }
    }

    public sealed class RobotMarkerTracker : IRobotMarkerTracker
    {
        public bool IsAvailable => false;
        public string StatusReason => "No QR/marker trackable API exists in the installed package source";
        public void SetQrTrackingEnabled(bool enabled){}
        public bool TryGetSnapshot(out RobotMarkerSnapshot snapshot){snapshot=null;return false;}
        public bool TryGetQrSnapshot(string requiredPayload,out QrMarkerObservation observation){observation=default;return false;}
    }
}
