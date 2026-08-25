using System;
using System.Collections.Generic;
using Phantom.Kinematics;

namespace Phantom.RobotLocalization
{
    public enum RobotMarkerId { BaseBack, ShoulderL, ShoulderR, ElbowL, ElbowR, TcpCal }
    public struct MarkerObservation { public RobotMarkerId Id; public Vec3 PositionRoom; public bool Valid; }
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
        public RobotBaseFrame BaseFrame;
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
    public struct RobotGeometry { public RobotBaseFrame BaseFrame; public Vec3 BaseOriginRoom; public Vec3 ShoulderRoom; public double L1; public double L2; public bool Valid; public string Reason; }

    public sealed class RobotGeometryEstimator
    {
        public RobotGeometry Estimate(IReadOnlyDictionary<RobotMarkerId,Vec3> markers)
            =>Estimate(markers,default);
        public RobotGeometry Estimate(IReadOnlyDictionary<RobotMarkerId,Vec3> markers,RobotBaseFrame baseFrame)
        {
            foreach(RobotMarkerId id in Enum.GetValues(typeof(RobotMarkerId))) if(markers==null||!markers.ContainsKey(id)||!markers[id].IsFinite)return new RobotGeometry{Reason="missing_"+id};
            var shoulder=(markers[RobotMarkerId.ShoulderL]+markers[RobotMarkerId.ShoulderR])*0.5;
            var elbow=(markers[RobotMarkerId.ElbowL]+markers[RobotMarkerId.ElbowR])*0.5;
            var l1=(elbow-shoulder).Magnitude;var l2=(markers[RobotMarkerId.TcpCal]-elbow).Magnitude;
            var plausible=l1>=0.08&&l1<=0.40&&l2>=0.08&&l2<=0.40;
            if(!baseFrame.IsValid)baseFrame=new RobotBaseFrame{OriginRoom=markers[RobotMarkerId.BaseBack],ForwardRoom=new Vec3(1,0,0),LeftRoom=new Vec3(0,1,0),UpRoom=new Vec3(0,0,1)};
            return new RobotGeometry{BaseFrame=baseFrame,BaseOriginRoom=baseFrame.OriginRoom,ShoulderRoom=shoulder,L1=l1,L2=l2,Valid=plausible&&baseFrame.IsValid,Reason=plausible?"":"implausible_geometry_provisional"};
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
