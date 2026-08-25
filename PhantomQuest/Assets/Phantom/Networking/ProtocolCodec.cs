using System;
using Phantom.Kinematics;

namespace Phantom.Networking
{
    [Flags]
    public enum CommandFlags : ushort { None = 0, Hello = 1, Tracking = 2, Hold = 4, SafeHold = 8, Fault = 16 }

    public struct TargetPacket
    {
        public CommandFlags Flags;
        public ulong SessionId;
        public uint Sequence;
        public ulong ClientTimeUs;
        public JointAngles Target;
        public float GripIntent;
    }

    public static class ProtocolCodec
    {
        public const uint Magic = 0x544E4850; // ASCII bytes "PHNT" on the wire
        public const ushort Version = 1;
        public const int TargetPacketSize = 48;

        public static byte[] EncodeTarget(TargetPacket packet)
        {
            if (!packet.Target.IsFinite || float.IsNaN(packet.GripIntent) || float.IsInfinity(packet.GripIntent)) throw new ArgumentException("Non-finite target");
            var data = new byte[TargetPacketSize]; var offset = 0;
            WriteU32(data, ref offset, Magic); WriteU16(data, ref offset, Version); WriteU16(data, ref offset, (ushort)packet.Flags);
            WriteU64(data, ref offset, packet.SessionId); WriteU32(data, ref offset, packet.Sequence); WriteU64(data, ref offset, packet.ClientTimeUs);
            WriteF32(data, ref offset, (float)packet.Target.Base); WriteF32(data, ref offset, (float)packet.Target.Shoulder); WriteF32(data, ref offset, (float)packet.Target.Elbow); WriteF32(data, ref offset, packet.GripIntent);
            WriteU32(data, ref offset, Crc32.Compute(data, 0, TargetPacketSize - 4));
            return data;
        }

        public static bool TryDecodeTarget(byte[] data, out TargetPacket packet)
        {
            packet = default;
            if (data == null || data.Length != TargetPacketSize || Crc32.Compute(data, 0, data.Length - 4) != ReadU32(data, data.Length - 4)) return false;
            var offset = 0; if (ReadU32(data, ref offset) != Magic || ReadU16(data, ref offset) != Version) return false;
            packet.Flags = (CommandFlags)ReadU16(data, ref offset); packet.SessionId = ReadU64(data, ref offset); packet.Sequence = ReadU32(data, ref offset); packet.ClientTimeUs = ReadU64(data, ref offset);
            packet.Target = new JointAngles(ReadF32(data, ref offset), ReadF32(data, ref offset), ReadF32(data, ref offset)); packet.GripIntent = ReadF32(data, ref offset);
            return packet.Target.IsFinite && !float.IsNaN(packet.GripIntent) && !float.IsInfinity(packet.GripIntent);
        }

        static void WriteU16(byte[] d, ref int o, ushort v) { d[o++] = (byte)v; d[o++] = (byte)(v >> 8); }
        static void WriteU32(byte[] d, ref int o, uint v) { for (var i=0;i<4;i++) d[o++] = (byte)(v >> (8*i)); }
        static void WriteU64(byte[] d, ref int o, ulong v) { for (var i=0;i<8;i++) d[o++] = (byte)(v >> (8*i)); }
        static void WriteF32(byte[] d, ref int o, float v) { WriteU32(d, ref o, FloatToUInt(v)); }
        static ushort ReadU16(byte[] d, ref int o) { var v=(ushort)(d[o]|(d[o+1]<<8));o+=2;return v; }
        static uint ReadU32(byte[] d, ref int o) { var v=ReadU32(d,o);o+=4;return v; }
        static uint ReadU32(byte[] d, int o) => (uint)(d[o]|(d[o+1]<<8)|(d[o+2]<<16)|(d[o+3]<<24));
        static ulong ReadU64(byte[] d, ref int o) { ulong v=0;for(var i=0;i<8;i++)v|=(ulong)d[o++]<<(8*i);return v; }
        static float ReadF32(byte[] d, ref int o) => UIntToFloat(ReadU32(d, ref o));
        static uint FloatToUInt(float value) { var bytes=BitConverter.GetBytes(value);return BitConverter.ToUInt32(bytes,0); }
        static float UIntToFloat(uint value) { var bytes=BitConverter.GetBytes(value);return BitConverter.ToSingle(bytes,0); }
    }

    public static class Crc32
    {
        static readonly uint[] Table = BuildTable();
        public static uint Compute(byte[] data, int offset, int count) { uint crc=0xffffffff;for(var i=offset;i<offset+count;i++)crc=Table[(crc^data[i])&0xff]^(crc>>8);return crc^0xffffffff; }
        static uint[] BuildTable() { var table=new uint[256];for(uint i=0;i<256;i++){var c=i;for(var j=0;j<8;j++)c=(c&1)!=0?0xedb88320^(c>>1):c>>1;table[i]=c;}return table; }
    }
}
