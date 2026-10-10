using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;
using NUnit.Framework;
using Phantom.Networking;
using Phantom.Networking.Generated;

// Existing console suites are retained intact; NUnit owns selection and reports.
[TestFixture, NonParallelizable]
public sealed class HostTests
{
    static string Root => Environment.GetEnvironmentVariable("PHANTOM_REPO_ROOT") ?? FindRoot();
    static string FindRoot(){for(var p=new DirectoryInfo(AppContext.BaseDirectory);p!=null;p=p.Parent)if(File.Exists(Path.Combine(p.FullName,"ev3","CMakeLists.txt")))return p.FullName;throw new Exception("Repository root not found");}
    [Test, Category("Unit")] public void Core(){Assert.That(CoreSmoke.Run(),Is.Zero);}
    [Test, Category("Unit")] public void NetworkCore(){Assert.That(Stage3CoreTests.Run(),Is.Zero);}
    [Test, Category("Unit")] public void GoldenVectors(){Assert.That(GoldenVectorInterop.Run(new[]{Path.Combine(Root,"protocol/golden_vectors/v1.json")}),Is.Zero);}

    [TestCase("normal"), TestCase("hello_ack_lost"), TestCase("bad_hmac"), TestCase("telemetry_stop_resume"),
     TestCase("busy"), TestCase("wrong_robot"), TestCase("wrong_protocol"), TestCase("wrong_schema_hash"), TestCase("wrong_bundle_hash"), Category("Functional")]
    public void UdpFailures(string scenario)
    {
        using(var stub=new Ev3UdpFixture(scenario,BundleHash()))
            Assert.That(UdpIntegration.Run(new[]{stub.Boot,stub.Port.ToString(),BundleHash(),scenario}),Is.Zero);
    }

    static string BundleHash(){using var doc=JsonDocument.Parse(File.ReadAllText(Path.Combine(Root,"config/shared/generated/manifest.json")));return doc.RootElement.GetProperty("artifact_hashes").GetProperty("commissioning_bundle-network-only").GetString();}
    static string Distro => Environment.GetEnvironmentVariable("PHANTOM_WSL_DISTRO") ?? JsonDocument.Parse(File.ReadAllText(Path.Combine(Root,"config/tooling/environment.json"))).RootElement.GetProperty("wsl").GetProperty("distribution").GetString();
    static Process Launch(params string[] args)
    {
        var info=new ProcessStartInfo{FileName=OperatingSystem.IsWindows()?"wsl.exe":args[0],UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,RedirectStandardInput=true,WorkingDirectory=Root};
        if(OperatingSystem.IsWindows()){info.ArgumentList.Add("-d");info.ArgumentList.Add(Distro);info.ArgumentList.Add("--");}
        foreach(var arg in args.Skip(OperatingSystem.IsWindows()?0:1))info.ArgumentList.Add(arg);
        return Process.Start(info);
    }
    static string Run(params string[] args)
    {
        using var p=Launch(args);var output=p.StandardOutput.ReadToEndAsync();var error=p.StandardError.ReadToEndAsync();
        if(!p.WaitForExit(120000)){p.Kill(true);throw new Exception("Native fixture command timeout");}
        if(p.ExitCode!=0)throw new Exception("Native fixture command failed: "+error.Result+output.Result);
        return output.Result.Trim();
    }
    [Test, Category("Functional")]
    public void NativeClientServerInterop()
    {
        var root=OperatingSystem.IsWindows()?Run("wslpath","-a",Root.Replace('\\','/')):Root;
        var identity=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(root))).Substring(0,16).ToLowerInvariant();
        var build="/tmp/phantom-quest-interop-"+identity;
        Run("cmake","-S",root+"/ev3","-B",build,"-G","Ninja","-DCMAKE_BUILD_TYPE=Debug","-DPHANTOM_DIAGNOSTIC=ON","-DPHANTOM_BUILD_TESTS=ON");
        Run("cmake","--build",build,"--target","phantom-quest-interop-fixture");
        var buildId=new string('a',64);
        var manifest=JsonSerializer.Serialize(new{schema_version=2,component="EV3",build_profile="Diagnostic",build_id=buildId,
            protocol_schema_hash=File.ReadAllText(Path.Combine(Root,"protocol/generated/schema.sha256")).Split()[0],
            protocol_semantics_hash=File.ReadAllText(Path.Combine(Root,"protocol/generated/semantics.sha256")).Split()[0],
            protocol_contract_hash=WireV1.ProtocolContractSha256,commissioning_bundle_hash=BundleHash()});
        using var process=Launch(build+"/phantom-quest-interop-fixture",build+"/phantom-network",root+"/config/ev3/generated/diagnostic.json",root+"/config/shared/generated/commissioning-bundle-diagnostic.json",manifest);
        var errors=process.StandardError.ReadToEndAsync();
        try{
            var deadline=DateTime.UtcNow.AddSeconds(15);string port=null;
            while(DateTime.UtcNow<deadline){var line=process.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(15)).GetAwaiter().GetResult();if(line==null)throw new Exception("Native fixture exited: "+errors.GetAwaiter().GetResult());
                using var record=JsonDocument.Parse(line);if(record.RootElement.GetProperty("event").GetString()=="NETWORK_READY"){port=record.RootElement.GetProperty("port").GetInt32().ToString();break;}}
            Assert.That(port,Is.Not.Null,"Native network readiness");
            var address=OperatingSystem.IsWindows()?Run("hostname","-I").Split(' ',StringSplitOptions.RemoveEmptyEntries)[0]:"127.0.0.1";
            Assert.That(UdpIntegration.Run(new[]{new string('4',32),port,BundleHash(),"normal",buildId,address}),Is.Zero);
        }finally{
            process.StandardInput.Close();
            if(!process.WaitForExit(5000)){process.Kill(true);process.WaitForExit();}
            TestContext.WriteLine(errors.GetAwaiter().GetResult());
        }
        Assert.That(process.ExitCode,Is.Zero,errors.GetAwaiter().GetResult());
    }
}

// Network fault injection belongs to the C# functional fixture, not a Python server.
sealed class Ev3UdpFixture : IDisposable
{
    readonly UdpClient socket=new UdpClient(new IPEndPoint(IPAddress.Loopback,0));
    readonly Thread thread;readonly string scenario;readonly byte[] bundle;
    readonly byte[] key=Enumerable.Range(0,32).Select(i=>(byte)i).ToArray();
    readonly byte[] boot=Enumerable.Repeat((byte)0x42,16).ToArray(),session=Enumerable.Repeat((byte)0x60,16).ToArray();
    IPEndPoint peer;byte[] nonce;ulong sequence;bool corrupt;volatile bool stop;Exception failure;
    const string BuildId="257fb3d9c32bbdac0b267b4b1ed15952f134cbd3f56a6cb68f7708ef8757c590";
    public int Port => ((IPEndPoint)socket.Client.LocalEndPoint).Port;
    public string Boot => Convert.ToHexString(boot).ToLowerInvariant();
    public Ev3UdpFixture(string scenario,string bundle){this.scenario=scenario;this.bundle=Convert.FromHexString(bundle);socket.Client.ReceiveTimeout=10;thread=new Thread(Serve){IsBackground=true};thread.Start();}
    static void Put16(byte[] b,int at,int value){b[at]=(byte)value;b[at+1]=(byte)(value>>8);}
    static void Put32(byte[] b,int at,uint value){for(int i=0;i<4;i++)b[at+i]=(byte)(value>>(8*i));}
    static void Id(byte[] b,int at,string value){var bytes=Encoding.UTF8.GetBytes(value);Buffer.BlockCopy(bytes,0,b,at,bytes.Length);}
    void Send(WireV1.MessageType type,byte[] payload,bool bad=false)
    {
        var data=ProtocolCodec.Encode(type,payload,key,type==WireV1.MessageType.HelloAck&&scenario=="busy"?new byte[16]:session,boot,type==WireV1.MessageType.HelloAck?0:++sequence,0);
        if(bad)data[data.Length-1]^=1;socket.Send(data,data.Length,peer);
    }
    void Serve()
    {
        try{
            var clock=Stopwatch.StartNew();long telemetry=0;bool dropped=false;
            while(!stop){
                try{
                    IPEndPoint address=null;var data=socket.Receive(ref address);
                    if(ProtocolCodec.TryDecode(data,key,out var packet)){
                        if(packet.Header.MessageType==WireV1.MessageType.Hello){
                            peer=address;nonce=packet.Payload.Skip(36).Take(16).ToArray();
                            if(scenario=="hello_ack_lost"&&!dropped){dropped=true;continue;}
                            var payload=new byte[364];Buffer.BlockCopy(nonce,0,payload,0,16);Id(payload,16,scenario=="wrong_robot"?"phantom99":"phantom01");Buffer.BlockCopy(Convert.FromHexString(BuildId),0,payload,48,32);
                            Put16(payload,80,scenario=="wrong_protocol"?1:0);Buffer.BlockCopy(scenario=="wrong_schema_hash"?Enumerable.Repeat((byte)0xee,32).ToArray():Convert.FromHexString(WireV1.ProtocolContractSha256),0,payload,116,32);
                            Buffer.BlockCopy(scenario=="wrong_bundle_hash"?Enumerable.Repeat((byte)0xdd,32).ToArray():bundle,0,payload,148,32);Put16(payload,308,3);payload[312]=1;Put16(payload,314,scenario=="busy"?12:0);Send(WireV1.MessageType.HelloAck,payload);
                        }else if(packet.Header.MessageType==WireV1.MessageType.Ping)Send(WireV1.MessageType.Pong,packet.Payload);
                    }
                }catch(SocketException e)when(e.SocketErrorCode==SocketError.TimedOut||e.SocketErrorCode==SocketError.ConnectionReset){}
                var elapsed=clock.ElapsedMilliseconds;var paused=scenario=="telemetry_stop_resume"&&elapsed>1000&&elapsed<3000;
                if(peer!=null&&scenario!="busy"&&elapsed>=telemetry&&!paused){
                    var payload=new byte[236];Id(payload,0,"phantom01");Buffer.BlockCopy(Convert.FromHexString(BuildId),0,payload,32,32);Buffer.BlockCopy(bundle,0,payload,64,32);Put16(payload,128,3);Put32(payload,132,4);Put32(payload,160,uint.MaxValue);Put16(payload,194,7600);Id(payload,200,"UNSELECTED");payload[232]=2;payload[233]=1;
                    var bad=scenario=="bad_hmac"&&!corrupt;Send(WireV1.MessageType.Telemetry,payload,bad);corrupt|=bad;telemetry=elapsed+50;
                }
            }
        }catch(Exception e){if(!stop)failure=e;}
    }
    public void Dispose(){stop=true;socket.Dispose();if(!thread.Join(2000))throw new Exception("UDP fixture worker did not stop");if(failure!=null)throw new Exception("UDP fixture failed",failure);}
}
