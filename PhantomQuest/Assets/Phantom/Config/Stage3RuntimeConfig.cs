using System;
using Phantom.Networking;

namespace Phantom.Config
{
    [Serializable] public sealed class QuestQualificationConfig { public bool qualification_only;public string qualification_evidence_manifest_hash;public int actuator_scope_mask,safety_observation_mask;public string required_user_inputs; }
    [Serializable] public sealed class QuestBundleConfig { public string expected_hash; }
    [Serializable] public sealed class QuestNetworkConfig
    {
        public string discovery_service_type,discovery_domain,ip_family,control_key_id,commissioning_key_id;public int default_port,protocol_version,telemetry_max_age_ms,hello_retry_ms=250,hello_max_attempts=5,ping_interval_ms=500,ping_timeout_ms=750,max_missed_pongs=3,reconnect_delay_ms=250;
    }
    [Serializable] public sealed class Stage3RuntimeConfig
    {
        public int schema_version;public string robot_id,build_profile;public QuestQualificationConfig qualification;public QuestBundleConfig commissioning_bundle;public QuestNetworkConfig network;
        public NetworkClientOptions ToOptions()
        {
            if(schema_version!=1||build_profile!="Diagnostic"||qualification==null||!qualification.qualification_only||qualification.actuator_scope_mask!=0||qualification.safety_observation_mask!=0||qualification.required_user_inputs!="NONE"||qualification.qualification_evidence_manifest_hash!=new string('0',64))throw new InvalidOperationException("Stage 3 requires Diagnostic qualification_only scope/observation 0x00, zero evidence hash and no user inputs");
            if(network==null||network.protocol_version!=1||network.discovery_service_type!="_phantom-ev3._udp"||network.discovery_domain!="local."||network.ip_family!="IPV4"||network.commissioning_key_id!=null||commissioning_bundle==null)throw new InvalidOperationException("Stage 3 network configuration is incomplete");
            return new NetworkClientOptions{RobotId=robot_id,ServiceType=network.discovery_service_type,ControlKeyId=network.control_key_id,ProtocolMajor=network.protocol_version,TelemetryMaxAgeMs=network.telemetry_max_age_ms,HelloRetryMs=network.hello_retry_ms,HelloMaxAttempts=network.hello_max_attempts,PingIntervalMs=network.ping_interval_ms,PingTimeoutMs=network.ping_timeout_ms,MaxMissedPongs=network.max_missed_pongs,ReconnectDelayMs=network.reconnect_delay_ms,ExpectedBuildProfile=1,ExpectedBundleHash=Hex32(commissioning_bundle.expected_hash)};
        }
        public static byte[] Hex32(string value)
        {
            if(value==null||value.Length!=64)throw new FormatException("SHA-256");var bytes=new byte[32];
            for(var i=0;i<32;i++)bytes[i]=Convert.ToByte(value.Substring(i*2,2),16);return bytes;
        }
    }
}
