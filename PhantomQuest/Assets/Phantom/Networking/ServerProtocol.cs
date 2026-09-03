using System;
using Phantom.Kinematics;
using Phantom.Networking.Generated;

namespace Phantom.Networking
{
    public enum RobotRuntimeState:ushort { Boot=0,UserCalibration=1,Discovery=2,ConnectedUnreferenced=3,RobotCalibration=4,Ready=5,Hold=6,Tracking=7,SafeHold=8,Stopped=9,Commissioning=10 }
    public struct AxisCapabilities { public JointLimits Limits;public JointAngles MaxVelocity,MaxAcceleration;public bool JointReferenceValid,GripperReferenceValid; }
    public struct HelloAckPacket { public byte[] ClientNonce;public string RobotId,BuildId;public byte[] ProtocolHash,BundleHash;public RobotRuntimeState State;public ushort ReferenceFlags;public AxisCapabilities Capabilities; }
    public struct TelemetryPacket { public string RobotId,BuildId;public RobotRuntimeState State;public ushort Fault;public uint StatusFlags;public ulong LastSequence;public uint CommandAgeMs;public JointAngles Actual,Speed;public float GripActual;public ushort GripState,BatteryMv; }
    public static class ServerProtocol
    {
        public static bool TryDecodeHelloAck(DecodedDatagram datagram,out HelloAckPacket packet)
        {
            packet=default;if(datagram.Header.MessageType!=WireV1.MessageType.HelloAck||datagram.Payload==null||datagram.Payload.Length!=364)return false;var b=datagram.Payload;var o=0;packet.ClientNonce=Bytes(b,ref o,16);packet.RobotId=Id32(b,ref o);packet.BuildId=Id32(b,ref o);o+=2+1+1+32;packet.ProtocolHash=Bytes(b,ref o,32);packet.BundleHash=Bytes(b,ref o,32);o+=32*4;packet.State=(RobotRuntimeState)U16(b,ref o);packet.ReferenceFlags=U16(b,ref o);o+=1+1+2;var min=new JointAngles(F32(b,ref o),F32(b,ref o),F32(b,ref o));var max=new JointAngles(F32(b,ref o),F32(b,ref o),F32(b,ref o));var vel=new JointAngles(F32(b,ref o),F32(b,ref o),F32(b,ref o));var accel=new JointAngles(F32(b,ref o),F32(b,ref o),F32(b,ref o));packet.Capabilities=new AxisCapabilities{Limits=new JointLimits(min,max),MaxVelocity=vel,MaxAcceleration=accel,JointReferenceValid=(packet.ReferenceFlags&1)!=0,GripperReferenceValid=(packet.ReferenceFlags&2)!=0};return packet.Capabilities.Limits.Min.IsFinite&&packet.Capabilities.Limits.Max.IsFinite;
        }
        public static bool TryDecodeTelemetry(DecodedDatagram datagram,out TelemetryPacket packet)
        {
            packet=default;if(datagram.Header.MessageType!=WireV1.MessageType.Telemetry||datagram.Payload==null||datagram.Payload.Length!=236)return false;var b=datagram.Payload;var o=0;packet.RobotId=Id32(b,ref o);packet.BuildId=Id32(b,ref o);o+=64;packet.State=(RobotRuntimeState)U16(b,ref o);packet.Fault=U16(b,ref o);packet.StatusFlags=U32(b,ref o);o+=16;packet.LastSequence=U64(b,ref o);packet.CommandAgeMs=U32(b,ref o);packet.Actual=new JointAngles(F32(b,ref o),F32(b,ref o),F32(b,ref o));packet.Speed=new JointAngles(F32(b,ref o),F32(b,ref o),F32(b,ref o));packet.GripActual=F32(b,ref o);packet.GripState=U16(b,ref o);packet.BatteryMv=U16(b,ref o);return packet.Actual.IsFinite&&packet.Speed.IsFinite&&!float.IsNaN(packet.GripActual)&&!float.IsInfinity(packet.GripActual);
        }
        static byte[] Bytes(byte[]b,ref int o,int n){var v=new byte[n];Buffer.BlockCopy(b,o,v,0,n);o+=n;return v;}static string Id32(byte[]b,ref int o){var end=o;while(end<o+32&&b[end]!=0)end++;var s=System.Text.Encoding.UTF8.GetString(b,o,end-o);o+=32;return s;}static ushort U16(byte[]b,ref int o)=>ProtocolCodec.ReadU16(b,ref o);static uint U32(byte[]b,ref int o)=>ProtocolCodec.ReadU32(b,ref o);static ulong U64(byte[]b,ref int o)=>ProtocolCodec.ReadU64(b,ref o);static float F32(byte[]b,ref int o)=>ProtocolCodec.ReadF32(b,ref o);
    }
}
