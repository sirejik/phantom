using System;
using System.Linq;
using System.Net;
using System.Threading;
using Phantom.Networking;

internal static class UdpIntegration
{
    static byte[] Hex(string value){var bytes=new byte[value.Length/2];for(var i=0;i<bytes.Length;i++)bytes[i]=Convert.ToByte(value.Substring(i*2,2),16);return bytes;}
    public static int Main(string[] args)
    {
        if(args.Length<3)throw new ArgumentException("boot id, port and bundle hash required");var scenario=args.Length>3?args[3]:"normal";var buildId=args.Length>4?args[4]:"257fb3d9c32bbdac0b267b4b1ed15952f134cbd3f56a6cb68f7708ef8757c590";var key=Enumerable.Range(0,32).Select(x=>(byte)x).ToArray();var discovery=new FakeDiscoveryBackend();var transport=new UdpRobotTransport();var recorder=new BoundedNetworkFlightRecorder();
        using(var client=new Stage3NetworkClient(discovery,transport,new EphemeralControlCredentialStore("control",key),new NetworkClientOptions{RobotId="phantom01",ServiceType="_phantom-ev3._udp",ControlKeyId="control",ExpectedBundleHash=Hex(args[2]),ExpectedBuildProfile=1,TelemetryMaxAgeMs=150,HelloRetryMs=100,HelloMaxAttempts=10,PingIntervalMs=100,PingTimeoutMs=300,MaxMissedPongs=3,ReconnectDelayMs=100},null,recorder))
        {
            client.Start();discovery.Add(new DiscoveredRobot{ServiceKey="udp-simulator",InstanceName="PHANTOM-phantom01",ServiceType="_phantom-ev3._udp",RobotId="phantom01",ProtocolMajor=1,ControllerBootId=Hex(args[0]),BuildId=buildId,Endpoint=new IPEndPoint(IPAddress.Loopback,int.Parse(args[1]))});
            var rejection=scenario=="wrong_bundle_hash"?"configuration_mismatch":scenario=="busy"?"handshake_rejected":scenario=="wrong_robot"||scenario=="wrong_protocol"||scenario=="wrong_schema_hash"?"protocol_mismatch":null;
            var deadline=DateTime.UtcNow.AddSeconds(4);
            if(rejection!=null)
            {
                while(DateTime.UtcNow<deadline&&!recorder.Snapshot().Any(x=>x.Name==rejection)){client.Tick();Thread.Sleep(5);}
                if(!recorder.Snapshot().Any(x=>x.Name==rejection)||client.Snapshot.SessionActive)throw new Exception("expected handshake rejection was not fail-closed: "+scenario);
                Console.WriteLine("PASS: real UDP Stage-3 negative scenario="+scenario+" classified="+rejection+"; no session/COMMAND");
            }
            else
            {
                while(DateTime.UtcNow<deadline&&(!client.Snapshot.SessionActive||client.Snapshot.Freshness!=TelemetryFreshness.Fresh||client.Snapshot.RttMilliseconds<0)){client.Tick();Thread.Sleep(5);}
                if(!client.Snapshot.SessionActive)throw new Exception("HELLO_ACK timeout");if(client.Snapshot.Freshness!=TelemetryFreshness.Fresh)throw new Exception("TELEMETRY timeout");if(client.Snapshot.RttMilliseconds<0)throw new Exception("PONG timeout");if(client.Snapshot.RemoteState==RobotRuntimeState.Ready||client.Snapshot.RemoteState==RobotRuntimeState.Tracking)throw new Exception("network-only simulator entered actuator state");if(client.Snapshot.SentSequence<1||client.Snapshot.AcceptedPackets<2)throw new Exception("sequence/packet path incomplete");
                if(scenario=="hello_ack_lost"&&!recorder.Snapshot().Any(x=>x.Name=="handshake_retry"))throw new Exception("lost HELLO_ACK did not retry");
                if(scenario=="bad_hmac")
                {deadline=DateTime.UtcNow.AddSeconds(2);while(DateTime.UtcNow<deadline&&client.Snapshot.AuthenticationFailures==0){client.Tick();Thread.Sleep(5);}if(client.Snapshot.AuthenticationFailures==0)throw new Exception("bad HMAC was not observed");}
                if(scenario=="telemetry_stop_resume")
                {deadline=DateTime.UtcNow.AddSeconds(5);var stale=false;var recovered=false;while(DateTime.UtcNow<deadline&&!recovered){client.Tick();if(client.Snapshot.Freshness==TelemetryFreshness.Stale)stale=true;if(stale&&client.Snapshot.Freshness==TelemetryFreshness.Fresh)recovered=true;Thread.Sleep(5);}if(!stale||!recovered)throw new Exception("telemetry stale/recovery not observed");}
                Console.WriteLine("PASS: real UDP Stage-3 scenario="+scenario+" HELLO/HMAC session, PING/PONG RTT, TELEMETRY; no COMMAND sent");
            }
        }
        var workerDeadline=DateTime.UtcNow.AddSeconds(1);while(DateTime.UtcNow<workerDeadline&&UdpRobotTransport.ActiveWorkerCount!=0)Thread.Sleep(5);if(UdpRobotTransport.ActiveWorkerCount!=0)throw new Exception("UDP worker leaked after dispose");return 0;
    }
}
