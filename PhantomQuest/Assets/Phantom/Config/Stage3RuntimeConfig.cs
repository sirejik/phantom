using System;
using Phantom.Networking;

namespace Phantom.Config
{
    [Serializable] public sealed class QuestQualificationConfig { public bool qualification_only;public int actuator_scope_mask;public string required_user_inputs; }
    [Serializable] public sealed class QuestBundleConfig { public string expected_hash; }
    [Serializable] public sealed class QuestNetworkConfig
    {
        public string discovery_service,control_key_id;public int default_port,protocol_version,telemetry_max_age_ms,hello_retry_ms=250,hello_max_attempts=5,ping_interval_ms=500,ping_timeout_ms=750,max_missed_pongs=3,reconnect_delay_ms=250;
    }
    [Serializable] public sealed class Stage3RuntimeConfig
    {
        public int schema_version;public string robot_id,build_profile;public QuestQualificationConfig qualification;public QuestBundleConfig commissioning_bundle;public QuestNetworkConfig network;
        public NetworkClientOptions ToOptions()
        {
            if(schema_version!=1||build_profile!="Diagnostic"||qualification==null||!qualification.qualification_only||qualification.actuator_scope_mask!=0||qualification.required_user_inputs!="NONE")throw new InvalidOperationException("Stage 3 requires Diagnostic qualification_only scope 0x00 and no user inputs");
            if(network==null||network.protocol_version!=1||commissioning_bundle==null)throw new InvalidOperationException("Stage 3 network configuration is incomplete");
            return new NetworkClientOptions{RobotId=robot_id,ServiceType=network.discovery_service,ControlKeyId=network.control_key_id,ProtocolMajor=network.protocol_version,TelemetryMaxAgeMs=network.telemetry_max_age_ms,HelloRetryMs=network.hello_retry_ms,HelloMaxAttempts=network.hello_max_attempts,PingIntervalMs=network.ping_interval_ms,PingTimeoutMs=network.ping_timeout_ms,MaxMissedPongs=network.max_missed_pongs,ReconnectDelayMs=network.reconnect_delay_ms,ExpectedBuildProfile=1,ExpectedBundleHash=Hex32(commissioning_bundle.expected_hash)};
        }
        public static byte[] Hex32(string value)
        {
            if(value==null||value.Length!=64)throw new FormatException("SHA-256");var bytes=new byte[32];
            for(var i=0;i<32;i++)bytes[i]=Convert.ToByte(value.Substring(i*2,2),16);return bytes;
        }
    }
}
