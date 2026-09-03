using System;
using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Diagnostics;
using Phantom.Kinematics;
using Phantom.Networking.Generated;

namespace Phantom.Networking
{
    [Flags] public enum CommandFlags { Hello=1,Tracking=2,Hold=4,SafeHold=8 }
    public interface IRobotTransport:IDisposable { bool HandshakeComplete{get;}bool NetworkReady{get;}void Poll();ulong Send(JointAngles target,float grip,CommandFlags intent,ulong clientTimeUs); }
    public sealed class PhantomUdpClient:IRobotTransport
    {
        readonly UdpClient _udp;readonly IPEndPoint _remote;readonly byte[] _key,_bootId,_nonce=new byte[16];byte[] _session=new byte[16];ulong _txSequence,_rxSequence;long _lastReceiveTimestamp;
        public byte[] SessionId=>_session;public bool HandshakeComplete{get;private set;}public AxisCapabilities Capabilities{get;private set;}public HelloAckPacket Handshake{get;private set;}public TelemetryPacket LastTelemetry{get;private set;}public DecodedDatagram LastDatagram{get;private set;}public bool NetworkReady=>HandshakeComplete&&_lastReceiveTimestamp!=0&&(Stopwatch.GetTimestamp()-_lastReceiveTimestamp)*1000.0/Stopwatch.Frequency<150;
        public PhantomUdpClient(string host,int port,byte[] key,byte[] controllerBootId){if(key==null||key.Length<32)throw new ArgumentException("PSK");if(controllerBootId==null||controllerBootId.Length!=16)throw new ArgumentException("boot id");_key=(byte[])key.Clone();_bootId=(byte[])controllerBootId.Clone();using(var rng=RandomNumberGenerator.Create())rng.GetBytes(_nonce);_remote=new IPEndPoint(IPAddress.Parse(host),port);_udp=new UdpClient(0);_udp.Client.Blocking=false;}
        public ulong Send(JointAngles target,float grip,CommandFlags intent,ulong clientTimeUs)
        {
            byte[] bytes;if(!HandshakeComplete){if(IsZero(_bootId))return 0;var payload=new byte[56];WriteId(payload,0,"phantom01");payload[34]=0;payload[35]=0;Buffer.BlockCopy(_nonce,0,payload,36,16);bytes=ProtocolCodec.Encode(WireV1.MessageType.Hello,payload,_key,new byte[16],_bootId,0,clientTimeUs);}
            else{var flags=intent==CommandFlags.Tracking?MotionFlags.MotionEnable|MotionFlags.TrackingValid|MotionFlags.GraspValid:MotionFlags.HoldRequest|MotionFlags.TrackingValid;var payload=ProtocolCodec.EncodeCommand(new CommandPayload{Flags=flags,Target=target,GripIntent=Math.Max(0,Math.Min(1,grip))});bytes=ProtocolCodec.Encode(WireV1.MessageType.Command,payload,_key,_session,_bootId,++_txSequence,clientTimeUs);}_udp.Send(bytes,bytes.Length,_remote);return _txSequence;
        }
        public ulong SendMessage(WireV1.MessageType type,byte[] payload,ulong clientTimeUs){if(!HandshakeComplete)throw new InvalidOperationException("handshake");var bytes=ProtocolCodec.Encode(type,payload,_key,_session,_bootId,++_txSequence,clientTimeUs);_udp.Send(bytes,bytes.Length,_remote);return _txSequence;}
        public void Poll(){while(_udp.Available>0){IPEndPoint from=null;var bytes=_udp.Receive(ref from);if(!from.Equals(_remote)||!ProtocolCodec.TryDecode(bytes,_key,out var decoded)||!Equal(decoded.Header.ControllerBootId,_bootId))continue;if(decoded.Header.MessageType==WireV1.MessageType.HelloAck&&!HandshakeComplete&&ServerProtocol.TryDecodeHelloAck(decoded,out var ack)&&Equal(ack.ClientNonce,_nonce)&&Equal(ack.ProtocolHash,ProtocolHash())){_session=(byte[])decoded.Header.SessionId.Clone();_rxSequence=0;Handshake=ack;Capabilities=ack.Capabilities;HandshakeComplete=true;LastDatagram=decoded;_lastReceiveTimestamp=Stopwatch.GetTimestamp();}else if(HandshakeComplete&&Equal(decoded.Header.SessionId,_session)&&decoded.Header.Sequence>_rxSequence){if(decoded.Header.MessageType==WireV1.MessageType.Telemetry){if(!ServerProtocol.TryDecodeTelemetry(decoded,out var telemetry))continue;LastTelemetry=telemetry;_lastReceiveTimestamp=Stopwatch.GetTimestamp();}_rxSequence=decoded.Header.Sequence;LastDatagram=decoded;}}}
        public void Dispose(){_udp.Dispose();Array.Clear(_key,0,_key.Length);}static void WriteId(byte[]b,int o,string s){var v=System.Text.Encoding.UTF8.GetBytes(s);Buffer.BlockCopy(v,0,b,o,v.Length);}static bool Equal(byte[]a,byte[]b){if(a==null||b==null||a.Length!=b.Length)return false;var d=0;for(var i=0;i<a.Length;i++)d|=a[i]^b[i];return d==0;}static bool IsZero(byte[]b){var d=0;foreach(var x in b)d|=x;return d==0;}static byte[] ProtocolHash(){var hex=WireV1.ProtocolSchemaSha256;var bytes=new byte[hex.Length/2];for(var i=0;i<bytes.Length;i++)bytes[i]=Convert.ToByte(hex.Substring(i*2,2),16);return bytes;}
    }
}
