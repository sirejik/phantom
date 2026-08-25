using System;
using System.Threading;
using Phantom.Kinematics;
using Phantom.Networking;

internal static class UdpIntegration
{
    public static int Main()
    {
        using(var client=new PhantomUdpClient("127.0.0.1",31339))
        {
            var start=DateTime.UtcNow;while(!client.HandshakeComplete&&(DateTime.UtcNow-start).TotalSeconds<2){client.Send(new JointAngles(0,0,.5),0,CommandFlags.Hello,0);Thread.Sleep(20);client.Poll();}
            if(!client.HandshakeComplete||!client.Capabilities.Homed)throw new Exception("HELLO_ACK/capabilities timeout");
            var target=new JointAngles(.5,.4,1.0);start=DateTime.UtcNow;
            while((DateTime.UtcNow-start).TotalSeconds<1.5){client.Send(target,.7f,CommandFlags.Tracking,0);Thread.Sleep(20);client.Poll();}
            var actual=client.LastTelemetry.Actual;if(!client.NetworkReady||actual.Base<.25||actual.Shoulder<.2||client.LastTelemetry.GripActual<.3f)throw new Exception($"telemetry did not follow target: {actual.Base}, {actual.Shoulder}, grip={client.LastTelemetry.GripActual}");
            client.Send(target,.7f,CommandFlags.Hold,0);Console.WriteLine($"PASS: UDP handshake/capabilities/absolute target/telemetry q=({actual.Base:F3},{actual.Shoulder:F3},{actual.Elbow:F3}) grip={client.LastTelemetry.GripActual:F3}");return 0;
        }
    }
}
