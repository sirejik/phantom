using Phantom.Kinematics;

namespace Phantom.Room
{
    public interface IRoomReference { bool IsReady { get; } string StatusReason { get; } Vec3 FloorOrigin { get; } }

    public static class RoomReferenceRegistry
    {
        public static IRoomReference Current { get; set; }
    }

    // MRUK is not present in the pinned package lock. This adapter deliberately blocks
    // normal operation instead of silently treating Unity tracking space as a room.
    public sealed class MrukRoomReference : IRoomReference
    {
        public bool IsReady => false;
        public string StatusReason => "MRUK package/API is not installed; Scene Capture room cannot be authoritative";
        public Vec3 FloorOrigin => Vec3.Zero;
    }

    public sealed class PhantomRoomFrame
    {
        public Vec3 Origin { get; }
        public PhantomRoomFrame(Vec3 origin) { Origin=origin; }
        public Vec3 ToRoom(Vec3 world)=>world-Origin;
    }

    public struct CalibrationZone
    {
        public Vec3 Center; public double RadiusMeters;
        public bool Contains(Vec3 point)=> (point-Center).Magnitude<=RadiusMeters;
    }
}
