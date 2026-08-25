using System;
using Phantom.Kinematics;

namespace Phantom.Networking
{
    public enum ServerMessageType : ushort { HelloAck = 1, Telemetry = 2 }
    public enum RobotRuntimeState : uint { Initializing = 0, Hold = 1, Tracking = 2, Fault = 3 }

    public struct AxisCapabilities
    {
        public JointLimits Limits;
        public JointAngles MaxVelocity;
        public JointAngles MaxAcceleration;
        public bool Homed;
        public uint AxisConfigHash;
    }

    public struct HelloAckPacket { public ulong SessionId; public uint LastSequence; public AxisCapabilities Capabilities; }
    public struct TelemetryPacket
    {
        public ulong SessionId; public uint LastSequence; public RobotRuntimeState State; public uint Fault;
        public ulong ServerTimeUs; public JointAngles Actual; public JointAngles Speed; public JointAngles SimDuty;
        public float GripActual; public float WatchdogAgeMs;
    }

    public static class ServerProtocol
    {
        public const int HelloAckSize = 84;
        public const int TelemetrySize = 84;

        public static bool TryDecodeHelloAck(byte[] data, out HelloAckPacket packet)
        {
            packet = default; if (!HeaderValid(data, HelloAckSize, ServerMessageType.HelloAck)) return false; var o=8;
            packet.SessionId=U64(data,ref o);packet.LastSequence=U32(data,ref o);o+=4; // reserved
            packet.Capabilities.Limits=new JointLimits(Angles(data,ref o),Angles(data,ref o));
            packet.Capabilities.MaxVelocity=Angles(data,ref o);packet.Capabilities.MaxAcceleration=Angles(data,ref o);
            packet.Capabilities.Homed=data[o++]!=0;o+=3;packet.Capabilities.AxisConfigHash=U32(data,ref o);
            return packet.SessionId!=0 && packet.Capabilities.Limits.Min.IsFinite && packet.Capabilities.Limits.Max.IsFinite;
        }

        public static bool TryDecodeTelemetry(byte[] data, out TelemetryPacket packet)
        {
            packet=default;if(!HeaderValid(data,TelemetrySize,ServerMessageType.Telemetry))return false;var o=8;
            packet.SessionId=U64(data,ref o);packet.LastSequence=U32(data,ref o);packet.State=(RobotRuntimeState)U32(data,ref o);packet.Fault=U32(data,ref o);
            packet.ServerTimeUs=U64(data,ref o);packet.Actual=Angles(data,ref o);packet.Speed=Angles(data,ref o);packet.SimDuty=Angles(data,ref o);
            packet.GripActual=F32(data,ref o);packet.WatchdogAgeMs=F32(data,ref o);
            return packet.Actual.IsFinite && packet.Speed.IsFinite;
        }

        static bool HeaderValid(byte[] data,int size,ServerMessageType type)
        {
            if(data==null||data.Length!=size||Crc32.Compute(data,0,size-4)!=U32(data,size-4))return false;var o=0;
            return U32(data,ref o)==ProtocolCodec.Magic&&U16(data,ref o)==ProtocolCodec.Version&&U16(data,ref o)==(ushort)type;
        }
        static JointAngles Angles(byte[] d,ref int o)=>new JointAngles(F32(d,ref o),F32(d,ref o),F32(d,ref o));
        static ushort U16(byte[] d,ref int o){var v=(ushort)(d[o]|d[o+1]<<8);o+=2;return v;}
        static uint U32(byte[] d,ref int o){var v=U32(d,o);o+=4;return v;}
        static uint U32(byte[] d,int o)=>(uint)(d[o]|d[o+1]<<8|d[o+2]<<16|d[o+3]<<24);
        static ulong U64(byte[] d,ref int o){ulong v=0;for(var i=0;i<8;i++)v|=(ulong)d[o++]<<(8*i);return v;}
        static float F32(byte[] d,ref int o){var b=BitConverter.GetBytes(U32(d,ref o));return BitConverter.ToSingle(b,0);}
    }
}
