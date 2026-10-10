using System;
using System.Linq;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Threading;
using Phantom.Networking;
using Phantom.Networking.Generated;

internal static class Stage3CoreTests
{
    static readonly byte[] Key=Enumerable.Range(0,32).Select(x=>(byte)x).ToArray();
    static readonly byte[] Bundle=Enumerable.Repeat((byte)0x42,32).ToArray();
    const string BuildId="257fb3d9c32bbdac0b267b4b1ed15952f134cbd3f56a6cb68f7708ef8757c590";
    static int _checks;

    sealed class Rig:IDisposable
    {
        public readonly FakeDiscoveryBackend Discovery=new FakeDiscoveryBackend();
        public readonly FakeDatagramTransport Transport=new FakeDatagramTransport();
        public readonly ManualMonotonicClock Clock=new ManualMonotonicClock();
        public readonly BoundedNetworkFlightRecorder Recorder=new BoundedNetworkFlightRecorder(32);
        public readonly Stage3NetworkClient Client;
        public DiscoveredRobot Service;
        public byte[] Session;
        public Rig()
        {
            Client=new Stage3NetworkClient(Discovery,Transport,new EphemeralControlCredentialStore("control",Key),new NetworkClientOptions{RobotId="phantom01",ServiceType="_phantom-ev3._udp",ControlKeyId="control",ExpectedBundleHash=Bundle,ExpectedBuildProfile=1,HelloRetryMs=50,HelloMaxAttempts=3,PingIntervalMs=100,PingTimeoutMs=50,MaxMissedPongs=2,ReconnectDelayMs=25,TelemetryMaxAgeMs=100},Clock,Recorder);
            Service=Robot("svc","127.0.0.1",31339,Id(0x20));
        }
        public byte[] Begin()
        {Client.Start();Discovery.Add(Robot("other","127.0.0.1",31340,Id(0x40),"phantom02"));Discovery.Add(Service);return TakeSent("HELLO");}
        public byte[] Connect()
        {
            var hello=Begin();Session=Id(0x60);Transport.Inject(Ack(hello,Session,Service.ControllerBootId));Client.Tick();Check(Client.Snapshot.SessionActive,"session not active");return hello;
        }
        public byte[] TakeSent(string label){byte[] value;Check(Transport.TryTakeSent(out value),label+" missing");return value;}
        public void Dispose(){Client.Dispose();}
    }

    public static int Run()
    {
        CredentialStateClassification();DiscoveryHandshakeRetryAndIdentity();RejectedHelloAckSemantics();PingTelemetryAndFreshness();PingTimeoutIsBounded();EndpointBootAndServiceRecovery();ParserAndBindingRejections();LifecycleAndBounds();TransportRestartConcurrencyIsBounded();
        Console.WriteLine("PASS: Quest Stage-3 core "+_checks+" checks (discovery, HELLO retry, HMAC, session, PING/PONG, telemetry, recovery, lifecycle)");return 0;
    }

    static void CredentialStateClassification()
    {
        var root=Path.Combine(Path.GetTempPath(),"phantom-credential-test-"+Guid.NewGuid().ToString("N"));
        var secrets=Path.Combine(root,"phantom-secrets");Directory.CreateDirectory(secrets);
        try
        {
            using(var store=new AndroidPrivateControlCredentialStore(root))
            {
                Check(store.GetStatus("control")==CredentialStoreStatus.Absent,"missing credential not classified absent");
                File.WriteAllBytes(Path.Combine(secrets,"control.psk"),new byte[]{1,2,3});
                Check(store.GetStatus("control")==CredentialStoreStatus.Corrupt,"unreadable credential collapsed to absent");
                File.WriteAllBytes(Path.Combine(secrets,"control.psk"),Key);
                byte[] loaded=null;Check(store.GetStatus("control")==CredentialStoreStatus.Ready&&store.TryLoad("control",out loaded),"valid credential not ready");
                if(loaded!=null)Array.Clear(loaded,0,loaded.Length);
            }
        }
        finally{if(Directory.Exists(root))Directory.Delete(root,true);}
    }

    static void DiscoveryHandshakeRetryAndIdentity()
    {
        using(var rig=new Rig())
        {
            var first=rig.Begin();Check(rig.Client.VisibleServiceCount==2,"multiple service visibility");Check(rig.Client.Snapshot.RobotId=="phantom01","wrong selected identity");
            rig.Clock.Advance(50);rig.Client.Tick();var retry=rig.TakeSent("HELLO retry");
            DecodedDatagram a,b;Check(ProtocolCodec.TryDecode(first,Key,out a),"first hello decode");Check(ProtocolCodec.TryDecode(retry,Key,out b),"retry hello decode");Collection(a.Payload.Skip(36).Take(16).ToArray(),b.Payload.Skip(36).Take(16).ToArray(),"retry nonce changed");
            rig.Session=Id(0x60);rig.Transport.Inject(Ack(retry,rig.Session,rig.Service.ControllerBootId));rig.Client.Tick();Check(rig.Client.Snapshot.SessionActive,"valid ACK rejected");Check(rig.Client.Snapshot.SentSequence==1,"post-handshake sequence did not start at one");
        }
        using(var rig=new Rig())
        {
            var hello=rig.Begin();rig.Transport.Inject(Ack(hello,Id(0x60),rig.Service.ControllerBootId,Bundle,"wrong"));rig.Client.Tick();Check(rig.Client.Snapshot.State==NetworkState.ProtocolMismatch&&!rig.Client.Snapshot.SessionActive,"wrong robot ACK accepted");
        }
        using(var rig=new Rig())
        {
            var hello=rig.Begin();rig.Transport.Inject(Ack(hello,Id(0x60),rig.Service.ControllerBootId,Enumerable.Repeat((byte)7,32).ToArray()));rig.Client.Tick();Check(rig.Client.Snapshot.State==NetworkState.ConfigurationMismatch,"wrong bundle not classified");
        }
    }

    static void PingTelemetryAndFreshness()
    {
        using(var rig=new Rig())
        {
            rig.Connect();var ping=rig.TakeSent("PING");DecodedDatagram decoded;Check(ProtocolCodec.TryDecode(ping,Key,out decoded)&&decoded.Header.MessageType==WireV1.MessageType.Ping&&decoded.Header.Sequence==1,"invalid PING");
            rig.Clock.Advance(7);rig.Transport.Inject(ProtocolCodec.Encode(WireV1.MessageType.Pong,decoded.Payload,Key,rig.Session,rig.Service.ControllerBootId,1,rig.Clock.NowMicroseconds));rig.Client.Tick();Check(Math.Abs(rig.Client.Snapshot.RttMilliseconds-7)<.01,"RTT");
            rig.Transport.Inject(Telemetry(rig.Session,rig.Service.ControllerBootId,2));rig.Client.Tick();Check(rig.Client.Snapshot.Freshness==TelemetryFreshness.Fresh&&rig.Client.Snapshot.BatteryMv==7600,"telemetry decode");
            rig.Clock.Advance(101);rig.Client.Tick();Check(rig.Client.Snapshot.Freshness==TelemetryFreshness.Stale&&rig.Client.Snapshot.State==NetworkState.TelemetryStale,"stale telemetry");
            rig.Transport.Inject(Telemetry(rig.Session,rig.Service.ControllerBootId,3));rig.Client.Tick();Check(rig.Client.Snapshot.Freshness==TelemetryFreshness.Fresh,"telemetry recovery");
            Check(rig.Recorder.Snapshot().Any(x=>x.Name=="telemetry_stale")&&rig.Recorder.Snapshot().Any(x=>x.Name=="telemetry_recovered"),"freshness events");
        }
    }

    static void RejectedHelloAckSemantics()
    {
        using(var rig=new Rig())
        {
            var hello=rig.Begin();rig.Session=Id(0x60);var valid=Ack(hello,rig.Session,rig.Service.ControllerBootId);
            DecodedDatagram decoded;Check(ProtocolCodec.TryDecode(valid,Key,out decoded),"ACK decode");
            decoded.Payload[WireV1.HelloAckOffsetReserved0]=1;
            var bad=ProtocolCodec.Encode(WireV1.MessageType.HelloAck,decoded.Payload,Key,rig.Session,rig.Service.ControllerBootId,0,0);
            rig.Transport.Inject(bad);rig.Client.Tick();
            Check(!rig.Client.Snapshot.SessionActive&&rig.Client.Snapshot.State==NetworkState.ProtocolMismatch,"reserved ACK created session");
        }
        using(var rig=new Rig())
        {
            var hello=rig.Begin();rig.Transport.Inject(Ack(hello,new byte[16],rig.Service.ControllerBootId,null,"phantom01",12));rig.Client.Tick();
            Check(!rig.Client.Snapshot.SessionActive&&rig.Client.Snapshot.State==NetworkState.Reconnecting,"busy rejected ACK created authority");
        }
        using(var rig=new Rig())
        {
            var hello=rig.Begin();rig.Transport.Inject(Ack(hello,new byte[16],rig.Service.ControllerBootId,null,"phantom01",2));rig.Client.Tick();
            Check(!rig.Client.Snapshot.SessionActive&&rig.Client.Snapshot.State==NetworkState.AuthenticationFailure,"auth rejected ACK classification");
        }
        var payload=new byte[364];PutU16(payload,314,12);var threw=false;try{ProtocolCodec.Encode(WireV1.MessageType.HelloAck,payload,Key,Id(1),Id(2),0,0);}catch(ArgumentException){threw=true;}Check(threw,"rejected ACK accepted nonzero session");
    }

    static void EndpointBootAndServiceRecovery()
    {
        using(var rig=new Rig())
        {
            rig.Connect();rig.TakeSent("PING");var oldSession=rig.Session;var moved=Robot("svc","127.0.0.1",31341,rig.Service.ControllerBootId);rig.Service=moved;rig.Discovery.Update(moved);var hello=rig.TakeSent("endpoint HELLO");Check(!rig.Client.Snapshot.SessionActive&&rig.Client.Snapshot.SentSequence==0,"endpoint retained session state");rig.Session=Id(0x70);rig.Transport.Inject(Ack(hello,rig.Session,moved.ControllerBootId));rig.Client.Tick();Check(rig.Client.Snapshot.SessionActive&&!oldSession.SequenceEqual(rig.Session),"endpoint new session");
            rig.TakeSent("endpoint PING");var restarted=Robot("svc","127.0.0.1",31341,Id(0x30));rig.Service=restarted;rig.Discovery.Update(restarted);hello=rig.TakeSent("boot HELLO");Check(!rig.Client.Snapshot.SessionActive,"boot retained session");rig.Session=Id(0x71);rig.Transport.Inject(Ack(hello,rig.Session,restarted.ControllerBootId));rig.Client.Tick();Check(rig.Client.Snapshot.SessionActive,"boot reconnect");
            rig.Discovery.Remove("svc");Check(rig.Client.Snapshot.State==NetworkState.Discovering&&!rig.Client.Snapshot.SessionActive,"service loss");rig.Discovery.Add(restarted);hello=rig.TakeSent("restore HELLO");rig.Session=Id(0x72);rig.Transport.Inject(Ack(hello,rig.Session,restarted.ControllerBootId));rig.Client.Tick();Check(rig.Client.Snapshot.SessionActive,"service restore");
        }
    }

    static void PingTimeoutIsBounded()
    {
        using(var rig=new Rig())
        {
            rig.Connect();rig.TakeSent("first PING");rig.Clock.Advance(50);rig.Client.Tick();Check(rig.Client.Snapshot.SessionActive,"one lost PONG caused reconnect");rig.Clock.Advance(100);rig.Client.Tick();rig.TakeSent("second PING");rig.Clock.Advance(50);rig.Client.Tick();Check(!rig.Client.Snapshot.SessionActive&&rig.Client.Snapshot.State==NetworkState.Reconnecting,"bounded PONG failures did not reconnect");rig.Clock.Advance(25);rig.Client.Tick();rig.TakeSent("reconnect HELLO");
        }
    }

    static void ParserAndBindingRejections()
    {
        using(var rig=new Rig())
        {
            rig.Connect();rig.TakeSent("PING");var good=Telemetry(rig.Session,rig.Service.ControllerBootId,2);var bad=(byte[])good.Clone();bad[0]=(byte)'X';rig.Transport.Inject(bad);var auth=(byte[])good.Clone();auth[auth.Length-1]^=1;rig.Transport.Inject(auth);rig.Transport.Inject(good,new IPEndPoint(IPAddress.Loopback,39999));rig.Client.Tick();Check(rig.Client.Snapshot.RejectedPackets>=2&&rig.Client.Snapshot.AuthenticationFailures==1&&rig.Client.Snapshot.UnexpectedEndpointDrops==1,"parser counters");
            rig.Transport.Inject(good);rig.Client.Tick();var accepted=rig.Client.Snapshot.AcceptedPackets;rig.Transport.Inject(good);rig.Client.Tick();Check(rig.Client.Snapshot.AcceptedPackets==accepted&&rig.Client.Snapshot.ReplayDrops==1,"duplicate accepted");
            var nan=Telemetry(rig.Session,rig.Service.ControllerBootId,3);Buffer.BlockCopy(BitConverter.GetBytes(float.NaN),0,nan,64+164,4);Retag(nan);rig.Transport.Inject(nan);rig.Client.Tick();Check(rig.Client.Snapshot.Freshness==TelemetryFreshness.Invalid,"NaN telemetry accepted");
        }
    }

    static void LifecycleAndBounds()
    {
        using(var rig=new Rig())
        {
            var first=rig.Connect();rig.Client.Pause();Check(!rig.Transport.IsRunning&&!rig.Discovery.IsRunning&&rig.Client.Snapshot.State==NetworkState.Idle,"pause cleanup");rig.Client.Resume();var second=rig.TakeSent("resume HELLO");DecodedDatagram a,b;ProtocolCodec.TryDecode(first,Key,out a);ProtocolCodec.TryDecode(second,Key,out b);Check(!a.Payload.Skip(36).Take(16).SequenceEqual(b.Payload.Skip(36).Take(16)),"nonce reused after resume");rig.Client.Stop();rig.Client.Start();Check(rig.Discovery.StartCount==3,"start again");
            for(var i=0;i<100;i++)rig.Transport.TrySend(new byte[1]);Check(rig.Transport.SendDropCount>0,"send queue unbounded");
        }
        var recorder=new BoundedNetworkFlightRecorder(3);for(var i=0;i<10;i++)recorder.Record(new NetworkEvent{Name=i.ToString()});Check(recorder.Count==3&&recorder.Snapshot()[0].Name=="7","flight recorder not bounded");
        var sequence=new SessionState(Id(1),Id(2),new IPEndPoint(IPAddress.Loopback,1));Check(sequence.AllocateSequence()==1&&sequence.AllocateSequence()==2,"session send sequence");Check(sequence.TryAccept(1)&&!sequence.TryAccept(1)&&!sequence.TryAccept(0)&&sequence.TryAccept(3),"session receive sequence");
        var outOfRange=false;try{ProtocolCodec.EncodeCommand(new CommandPayload{Flags=MotionFlags.HoldRequest,Target=new Phantom.Kinematics.JointAngles(6.5,0,0),GripIntent=.5f});}catch(ArgumentOutOfRangeException){outOfRange=true;}Check(outOfRange,"Quest COMMAND absolute parser range differs from EV3");
        var invalidType=false;try{new NetworkClientOptions{ServiceType="_phantom-ev3._udp.local.",ControlKeyId="control",ExpectedBundleHash=Bundle}.Validate();}catch(ArgumentException){invalidType=true;}Check(invalidType,"non-canonical DNS-SD type accepted");
        var invalidSlot=false;try{new NetworkClientOptions{ServiceType="_phantom-ev3._udp",ControlKeyId="control",ControlKeySlot=1,ExpectedBundleHash=Bundle}.Validate();}catch(ArgumentException){invalidSlot=true;}Check(invalidSlot,"commissioning slot accepted by Stage-3 client");
    }

    static void TransportRestartConcurrencyIsBounded()
    {
        var transport=new UdpRobotTransport();var maximum=0;
        try
        {
            for(var i=0;i<100;i++){transport.Start(new IPEndPoint(IPAddress.Loopback,30000+i));maximum=Math.Max(maximum,UdpRobotTransport.ActiveWorkerCount);}
        }
        finally{transport.Dispose();}
        var deadline=DateTime.UtcNow.AddSeconds(1);while(DateTime.UtcNow<deadline&&UdpRobotTransport.ActiveWorkerCount!=0)Thread.Sleep(2);
        Check(maximum<=1,"UDP restart created concurrent workers");Check(UdpRobotTransport.ActiveWorkerCount==0,"UDP worker leaked after restart storm");
    }

    static DiscoveredRobot Robot(string key,string host,int port,byte[] boot,string robot="phantom01")=>new DiscoveredRobot{ServiceKey=key,InstanceName="PHANTOM-"+robot,ServiceType="_phantom-ev3._udp",RobotId=robot,ProtocolMajor=1,ControllerBootId=boot,BuildId=BuildId,Endpoint=new IPEndPoint(IPAddress.Parse(host),port)};
    static byte[] Ack(byte[] hello,byte[] session,byte[] boot,byte[] bundle=null,string robot="phantom01",ushort result=0)
    {
        DecodedDatagram request;Check(ProtocolCodec.TryDecode(hello,Key,out request),"HELLO parse for ACK");var p=new byte[364];Buffer.BlockCopy(request.Payload,36,p,0,16);PutId(p,16,robot);Buffer.BlockCopy(Hex(BuildId),0,p,48,32);PutU16(p,80,0);p[82]=0;p[83]=0;Buffer.BlockCopy(Hex(WireV1.ProtocolContractSha256),0,p,116,32);Buffer.BlockCopy(bundle??Bundle,0,p,148,32);PutU16(p,308,3);p[312]=1;PutU16(p,314,result);return ProtocolCodec.Encode(WireV1.MessageType.HelloAck,p,Key,session,boot,0,0);
    }
    static byte[] Telemetry(byte[] session,byte[] boot,ulong sequence)
    {
        var p=new byte[236];PutId(p,0,"phantom01");Buffer.BlockCopy(Hex(BuildId),0,p,32,32);Buffer.BlockCopy(Bundle,0,p,64,32);PutU16(p,128,3);PutU16(p,130,0);PutU32(p,132,4);PutU64(p,152,0);PutU32(p,160,0xffffffff);PutU16(p,192,0);PutU16(p,194,7600);PutU32(p,196,0);PutId(p,200,"UNSELECTED");p[232]=2;p[233]=1;return ProtocolCodec.Encode(WireV1.MessageType.Telemetry,p,Key,session,boot,sequence,0);
    }
    static void Retag(byte[] packet){using(var mac=new HMACSHA256(Key)){var tag=mac.ComputeHash(packet,0,packet.Length-32);Buffer.BlockCopy(tag,0,packet,packet.Length-32,32);}}
    static byte[] Id(byte start){var result=new byte[16];for(var i=0;i<16;i++)result[i]=(byte)(start+i);return result;}
    static byte[] Hex(string value){var result=new byte[value.Length/2];for(var i=0;i<result.Length;i++)result[i]=Convert.ToByte(value.Substring(i*2,2),16);return result;}
    static void PutId(byte[] b,int o,string value){var bytes=System.Text.Encoding.UTF8.GetBytes(value);Buffer.BlockCopy(bytes,0,b,o,bytes.Length);}
    static void PutU16(byte[] b,int o,ushort v){b[o]=(byte)v;b[o+1]=(byte)(v>>8);}
    static void PutU32(byte[] b,int o,uint v){for(var i=0;i<4;i++)b[o+i]=(byte)(v>>(8*i));}
    static void PutU64(byte[] b,int o,ulong v){for(var i=0;i<8;i++)b[o+i]=(byte)(v>>(8*i));}
    static void Collection(byte[] a,byte[] b,string message){Check(a.SequenceEqual(b),message);}
    static void Check(bool value,string message){_checks++;if(!value)throw new Exception(message);}
}
