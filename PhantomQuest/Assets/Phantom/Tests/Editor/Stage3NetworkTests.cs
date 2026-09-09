using System;
using System.Linq;
using System.Net;
using NUnit.Framework;
using Phantom.Config;
using Phantom.Networking;
using Phantom.Networking.Generated;
using Phantom.UI;
using UnityEngine;

namespace Phantom.Tests
{
    public sealed class Stage3NetworkTests
    {
        static readonly byte[] Key=Enumerable.Range(0,32).Select(x=>(byte)x).ToArray();
        static readonly byte[] Bundle=Enumerable.Repeat((byte)0x42,32).ToArray();
        const string BuildId="257fb3d9c32bbdac0b267b4b1ed15952f134cbd3f56a6cb68f7708ef8757c590";

        [Test] public void NetworkOnlyConfigurationHasZeroScopeAndNoUserInputs()
        {
            var config=new Stage3RuntimeConfig{schema_version=1,robot_id="phantom01",build_profile="Diagnostic",qualification=new QuestQualificationConfig{qualification_only=true,qualification_evidence_manifest_hash=new string('0',64),actuator_scope_mask=0,safety_observation_mask=0,required_user_inputs="NONE"},commissioning_bundle=new QuestBundleConfig{expected_hash=new string('4',64)},network=new QuestNetworkConfig{discovery_service_type="_phantom-ev3._udp",discovery_domain="local.",ip_family="IPV4",default_port=30470,protocol_version=1,control_key_id="control",telemetry_max_age_ms=100}};
            var options=config.ToOptions();Assert.That(options.ExpectedBuildProfile,Is.EqualTo(1));Assert.That(config.qualification.actuator_scope_mask,Is.Zero);
        }

        [Test] public void GeneratedJsonNullCommissioningKeyIsAcceptedAsAbsent()
        {
            const string json="{\"schema_version\":1,\"robot_id\":\"phantom01\",\"build_profile\":\"Diagnostic\",\"qualification\":{\"qualification_only\":true,\"qualification_evidence_manifest_hash\":\"0000000000000000000000000000000000000000000000000000000000000000\",\"actuator_scope_mask\":0,\"safety_observation_mask\":0,\"required_user_inputs\":\"NONE\"},\"commissioning_bundle\":{\"expected_hash\":\"4444444444444444444444444444444444444444444444444444444444444444\"},\"network\":{\"discovery_service_type\":\"_phantom-ev3._udp\",\"discovery_domain\":\"local.\",\"ip_family\":\"IPV4\",\"default_port\":30470,\"protocol_version\":1,\"control_key_id\":\"phantom01-control\",\"commissioning_key_id\":null,\"telemetry_max_age_ms\":100}}";
            var config=JsonUtility.FromJson<Stage3RuntimeConfig>(json);
            Assert.That(config.network.commissioning_key_id,Is.EqualTo(string.Empty));
            Assert.DoesNotThrow(()=>config.ToOptions());
        }

        [Test] public void NetworkOnlyConfigurationRejectsCommissioningKeySlot()
        {
            var config=new Stage3RuntimeConfig{schema_version=1,robot_id="phantom01",build_profile="Diagnostic",qualification=new QuestQualificationConfig{qualification_only=true,qualification_evidence_manifest_hash=new string('0',64),actuator_scope_mask=0,safety_observation_mask=0,required_user_inputs="NONE"},commissioning_bundle=new QuestBundleConfig{expected_hash=new string('4',64)},network=new QuestNetworkConfig{discovery_service_type="_phantom-ev3._udp",discovery_domain="local.",ip_family="IPV4",default_port=30470,protocol_version=1,control_key_id="control",commissioning_key_id="commissioning",telemetry_max_age_ms=100}};
            var error=Assert.Throws<InvalidOperationException>(()=>config.ToOptions());
            Assert.That(error.Message,Does.Contain("commissioning_key_id_must_be_unset"));
        }

        [Test] public void FakeDiscoveryCreatesAuthenticatedFreshSessionAndInvalidatesOnLoss()
        {
            var discovery=new FakeDiscoveryBackend();var transport=new FakeDatagramTransport();var clock=new ManualMonotonicClock();var recorder=new BoundedNetworkFlightRecorder();var boot=Id(0x20);var session=Id(0x60);var endpoint=new IPEndPoint(IPAddress.Loopback,31339);
            using(var client=new Stage3NetworkClient(discovery,transport,new EphemeralControlCredentialStore("control",Key),Options(),clock,recorder))
            {
                client.Start();discovery.Add(new DiscoveredRobot{ServiceKey="svc",InstanceName="PHANTOM-phantom01",ServiceType="_phantom-ev3._udp",RobotId="phantom01",ProtocolMajor=1,ControllerBootId=boot,BuildId=BuildId,Endpoint=endpoint});byte[] hello;Assert.True(transport.TryTakeSent(out hello));transport.Inject(Ack(hello,session,boot));client.Tick();Assert.True(client.Snapshot.SessionActive);byte[] ping;Assert.True(transport.TryTakeSent(out ping));transport.Inject(Telemetry(session,boot,1));client.Tick();Assert.That(client.Snapshot.Freshness,Is.EqualTo(TelemetryFreshness.Fresh));clock.Advance(101);client.Tick();Assert.That(client.Snapshot.Freshness,Is.EqualTo(TelemetryFreshness.Stale));discovery.Remove("svc");Assert.False(client.Snapshot.SessionActive);Assert.That(client.Snapshot.State,Is.EqualTo(NetworkState.Discovering));
            }
        }

        [Test] public void RussianUiCoversConnectedAndFailureStates()
        {
            var snapshot=new NetworkSnapshot{State=NetworkState.TelemetryFresh,SessionActive=true,RobotId="phantom01",Freshness=TelemetryFreshness.Fresh,RemoteState=RobotRuntimeState.ConnectedUnreferenced,BatteryMv=7600};Assert.That(Stage3NetworkUi.Format(snapshot),Does.Contain("СОЕДИНЕНО").And.Contain("ТЕЛЕМЕТРИЯ   АКТУАЛЬНА"));snapshot.SessionActive=false;snapshot.State=NetworkState.AuthenticationFailure;Assert.That(Stage3NetworkUi.Format(snapshot),Does.Contain("ОШИБКА АУТЕНТИФИКАЦИИ"));
        }

        static NetworkClientOptions Options()=>new NetworkClientOptions{RobotId="phantom01",ServiceType="_phantom-ev3._udp",ControlKeyId="control",ExpectedBundleHash=Bundle,ExpectedBuildProfile=1,TelemetryMaxAgeMs=100,HelloRetryMs=50,HelloMaxAttempts=3,PingIntervalMs=100,PingTimeoutMs=50,MaxMissedPongs=2,ReconnectDelayMs=25};
        static byte[] Ack(byte[] hello,byte[] session,byte[] boot){DecodedDatagram request;Assert.True(ProtocolCodec.TryDecode(hello,Key,out request));var p=new byte[364];Buffer.BlockCopy(request.Payload,36,p,0,16);PutId(p,16,"phantom01");Buffer.BlockCopy(Hex(BuildId),0,p,48,32);Buffer.BlockCopy(Hex(WireV1.ProtocolContractSha256),0,p,116,32);Buffer.BlockCopy(Bundle,0,p,148,32);PutU16(p,308,3);p[312]=1;return ProtocolCodec.Encode(WireV1.MessageType.HelloAck,p,Key,session,boot,0,0);}
        static byte[] Telemetry(byte[] session,byte[] boot,ulong sequence){var p=new byte[236];PutId(p,0,"phantom01");Buffer.BlockCopy(Hex(BuildId),0,p,32,32);Buffer.BlockCopy(Bundle,0,p,64,32);PutU16(p,128,3);PutU32(p,132,4);PutU32(p,160,0xffffffff);PutU16(p,194,7600);PutId(p,200,"UNSELECTED");p[232]=2;p[233]=1;return ProtocolCodec.Encode(WireV1.MessageType.Telemetry,p,Key,session,boot,sequence,0);}
        static byte[] Id(byte start){var result=new byte[16];for(var i=0;i<16;i++)result[i]=(byte)(start+i);return result;}
        static byte[] Hex(string value){var result=new byte[value.Length/2];for(var i=0;i<result.Length;i++)result[i]=Convert.ToByte(value.Substring(i*2,2),16);return result;}
        static void PutId(byte[] b,int o,string value){var bytes=System.Text.Encoding.UTF8.GetBytes(value);Buffer.BlockCopy(bytes,0,b,o,bytes.Length);}
        static void PutU16(byte[] b,int o,ushort v){b[o]=(byte)v;b[o+1]=(byte)(v>>8);}
        static void PutU32(byte[] b,int o,uint v){for(var i=0;i<4;i++)b[o+i]=(byte)(v>>(8*i));}
    }
}
