using System;
using System.Security.Cryptography;
using Phantom.Kinematics;
using Phantom.Networking.Generated;

namespace Phantom.Networking
{
    [Flags] public enum MotionFlags:uint { None=0,MotionEnable=1,HoldRequest=2,TrackingValid=4,GraspValid=8 }
    public struct WireHeader { public WireV1.MessageType MessageType;public byte[] SessionId,ControllerBootId;public ulong Sequence,SenderMonotonicUs; }
    public struct DecodedDatagram { public WireHeader Header;public byte[] Payload; }
    public struct CommandPayload { public MotionFlags Flags;public JointAngles Target;public float GripIntent; }
    public static class ProtocolCodec
    {
        public static byte[] Encode(WireV1.MessageType type,byte[] payload,byte[] key,byte[] sessionId,byte[] bootId,ulong sequence,ulong senderUs)
        {
            Require(payload!=null&&payload.Length==PayloadSize(type),"payload length");Require(key!=null&&key.Length>=32,"PSK must contain 256 bits");Require(sessionId!=null&&sessionId.Length==16&&bootId!=null&&bootId.Length==16,"id length");var hello=type==WireV1.MessageType.Hello;var ack=type==WireV1.MessageType.HelloAck;Require(!hello||IsZero(sessionId)&&sequence==0,"HELLO binding");Require(!ack||!IsZero(sessionId)&&sequence==0,"HELLO_ACK binding");Require(hello||ack||!IsZero(sessionId)&&sequence>0,"session binding");
            var result=new byte[64+payload.Length+32];var o=0;result[o++]=(byte)'P';result[o++]=(byte)'H';result[o++]=(byte)'N';result[o++]=(byte)'T';WriteU16(result,ref o,1);WriteU16(result,ref o,(ushort)type);WriteU16(result,ref o,64);WriteU16(result,ref o,(ushort)payload.Length);WriteU32(result,ref o,0);Buffer.BlockCopy(sessionId,0,result,o,16);o+=16;Buffer.BlockCopy(bootId,0,result,o,16);o+=16;WriteU64(result,ref o,sequence);WriteU64(result,ref o,senderUs);Buffer.BlockCopy(payload,0,result,o,payload.Length);using(var mac=new HMACSHA256(key)){var tag=mac.ComputeHash(result,0,64+payload.Length);Buffer.BlockCopy(tag,0,result,64+payload.Length,32);}return result;
        }
        public static bool TryDecode(byte[] data,byte[] key,out DecodedDatagram packet)
        {
            packet=default;if(data==null||key==null||key.Length<32||data.Length<96||data.Length>1024)return false;var o=0;if(data[o++]!='P'||data[o++]!='H'||data[o++]!='N'||data[o++]!='T'||ReadU16(data,ref o)!=1)return false;var type=(WireV1.MessageType)ReadU16(data,ref o);var header=ReadU16(data,ref o);var length=ReadU16(data,ref o);var flags=ReadU32(data,ref o);int expected;try{expected=PayloadSize(type);}catch{return false;}if(header!=64||flags!=0||length!=expected||data.Length!=64+length+32)return false;var session=new byte[16];var boot=new byte[16];Buffer.BlockCopy(data,o,session,0,16);o+=16;Buffer.BlockCopy(data,o,boot,0,16);o+=16;var sequence=ReadU64(data,ref o);var sender=ReadU64(data,ref o);var hello=type==WireV1.MessageType.Hello;var ack=type==WireV1.MessageType.HelloAck;if(hello&&(!IsZero(session)||sequence!=0)||ack&&(IsZero(session)||sequence!=0)||!hello&&!ack&&(IsZero(session)||sequence==0))return false;using(var mac=new HMACSHA256(key)){if(!FixedEquals(mac.ComputeHash(data,0,64+length),0,data,64+length,32))return false;}var payload=new byte[length];Buffer.BlockCopy(data,64,payload,0,length);if(type==WireV1.MessageType.Command&&!TryDecodeCommand(payload,out _))return false;packet=new DecodedDatagram{Header=new WireHeader{MessageType=type,SessionId=session,ControllerBootId=boot,Sequence=sequence,SenderMonotonicUs=sender},Payload=payload};return true;
        }
        public static byte[] EncodeCommand(CommandPayload command)
        {
            if((((uint)command.Flags)&~15u)!=0||!command.Target.IsFinite||!Finite(command.GripIntent)||command.GripIntent<0||command.GripIntent>1)throw new ArgumentOutOfRangeException(nameof(command));var b=new byte[24];var o=0;WriteU32(b,ref o,(uint)command.Flags);WriteF32(b,ref o,(float)command.Target.Base);WriteF32(b,ref o,(float)command.Target.Shoulder);WriteF32(b,ref o,(float)command.Target.Elbow);WriteF32(b,ref o,command.GripIntent);WriteU32(b,ref o,0);return b;
        }
        public static bool TryDecodeCommand(byte[] b,out CommandPayload command)
        {
            command=default;if(b==null||b.Length!=24)return false;var o=0;var flags=ReadU32(b,ref o);var q=new JointAngles(ReadF32(b,ref o),ReadF32(b,ref o),ReadF32(b,ref o));var grip=ReadF32(b,ref o);var reserved=ReadU32(b,ref o);if((flags&~15u)!=0||reserved!=0||!q.IsFinite||!Finite(grip)||grip<0||grip>1)return false;command=new CommandPayload{Flags=(MotionFlags)flags,Target=q,GripIntent=grip};return true;
        }
        public static int PayloadSize(WireV1.MessageType type){var size=WireV1.PayloadBytes(type);if(size<0)throw new ArgumentOutOfRangeException(nameof(type));return size;}
        static bool FixedEquals(byte[] a,int ao,byte[] b,int bo,int count){var diff=0;for(var i=0;i<count;i++)diff|=a[ao+i]^b[bo+i];return diff==0;}static bool IsZero(byte[] b){var v=0;for(var i=0;i<b.Length;i++)v|=b[i];return v==0;}static void Require(bool ok,string message){if(!ok)throw new ArgumentException(message);}
        static bool Finite(float v)=>!float.IsNaN(v)&&!float.IsInfinity(v);internal static void WriteU16(byte[] b,ref int o,ushort v){b[o++]=(byte)v;b[o++]=(byte)(v>>8);}internal static void WriteU32(byte[] b,ref int o,uint v){for(var i=0;i<4;i++)b[o++]=(byte)(v>>(8*i));}internal static void WriteU64(byte[] b,ref int o,ulong v){for(var i=0;i<8;i++)b[o++]=(byte)(v>>(8*i));}internal static void WriteF32(byte[] b,ref int o,float v){var x=BitConverter.GetBytes(v);Buffer.BlockCopy(x,0,b,o,4);o+=4;}internal static ushort ReadU16(byte[] b,ref int o){var v=(ushort)(b[o]|b[o+1]<<8);o+=2;return v;}internal static uint ReadU32(byte[] b,ref int o){uint v=0;for(var i=0;i<4;i++)v|=(uint)b[o++]<<(8*i);return v;}internal static ulong ReadU64(byte[] b,ref int o){ulong v=0;for(var i=0;i<8;i++)v|=(ulong)b[o++]<<(8*i);return v;}internal static float ReadF32(byte[] b,ref int o){var v=BitConverter.ToSingle(b,o);o+=4;return v;}
    }
}
