using System;
using System.Net;
using System.Net.Sockets;
using Phantom.Kinematics;

namespace Phantom.Networking
{
    public sealed class PhantomUdpClient : IDisposable
    {
        readonly UdpClient _udp;
        readonly IPEndPoint _remote;
        readonly SessionState _session = new SessionState();
        DateTime _lastReceiveUtc;
        public bool HandshakeComplete { get; private set; }
        public AxisCapabilities Capabilities { get; private set; }
        public TelemetryPacket LastTelemetry { get; private set; }
        public ulong SessionId => _session.SessionId;
        public bool NetworkReady => HandshakeComplete && (DateTime.UtcNow - _lastReceiveUtc).TotalSeconds < 0.5;

        public PhantomUdpClient(string host, int port)
        {
            _remote = new IPEndPoint(IPAddress.Parse(host), port); _udp = new UdpClient(0); _udp.Client.Blocking = false;
        }

        public uint Send(JointAngles target, float grip, CommandFlags flags, ulong clientTimeUs)
        {
            var sequence = _session.AllocateSequence();
            var bytes = ProtocolCodec.EncodeTarget(new TargetPacket { Flags=flags,SessionId=SessionId,Sequence=sequence,ClientTimeUs=clientTimeUs,Target=target,GripIntent=grip });
            _udp.Send(bytes,bytes.Length,_remote); return sequence;
        }

        public void Poll()
        {
            while (_udp.Available > 0)
            {
                IPEndPoint from=null;var bytes=_udp.Receive(ref from);
                if(ServerProtocol.TryDecodeHelloAck(bytes,out var ack)&&ack.SessionId==SessionId){Capabilities=ack.Capabilities;HandshakeComplete=true;_lastReceiveUtc=DateTime.UtcNow;}
                else if(ServerProtocol.TryDecodeTelemetry(bytes,out var telemetry)&&telemetry.SessionId==SessionId)
                {
                    var previous=LastTelemetry;
                    var stale=previous.SessionId!=0&&telemetry.LastSequence!=previous.LastSequence&&!SequenceMath.IsNewer(telemetry.LastSequence,previous.LastSequence);
                    var duplicateOld=previous.SessionId!=0&&telemetry.LastSequence==previous.LastSequence&&telemetry.ServerTimeUs<=previous.ServerTimeUs;
                    if(stale||duplicateOld)continue;
                    LastTelemetry=telemetry;_lastReceiveUtc=DateTime.UtcNow;
                }
            }
        }
        public void Dispose()=>_udp.Dispose();
    }
}
