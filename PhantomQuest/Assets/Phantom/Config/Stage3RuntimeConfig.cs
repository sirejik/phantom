using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using Phantom.Networking;

namespace Phantom.Config
{
    [Serializable] public sealed class QuestQualificationConfig { public bool qualification_only;public int actuator_scope_mask,safety_observation_mask;public string required_user_inputs; }
    [Serializable] public sealed class QuestNetworkConfig
    {
        public string discovery_service_type,discovery_domain,ip_family,control_key_id,commissioning_key_id;public int default_port,protocol_version,telemetry_max_age_ms,hello_retry_ms=250,hello_max_attempts=5,ping_interval_ms=500,ping_timeout_ms=750,max_missed_pongs=3,reconnect_delay_ms=250;
    }
    [Serializable] public sealed class Stage3RuntimeConfig
    {
        public string robot_id,build_profile;public QuestQualificationConfig qualification;public QuestNetworkConfig network;
        public NetworkClientOptions ToOptions()
        {
            if(build_profile!="Diagnostic"||qualification==null||!qualification.qualification_only||qualification.actuator_scope_mask!=0||qualification.safety_observation_mask!=0||qualification.required_user_inputs!="NONE")throw new InvalidOperationException("Stage 3 требует Diagnostic qualification_only, scope/observation 0x00 и отсутствие пользовательских inputs");
            var incomplete=new List<string>();
            if(string.IsNullOrEmpty(robot_id))incomplete.Add("robot_id");
            if(network==null)incomplete.Add("network");
            else
            {
                if(network.protocol_version!=1)incomplete.Add("protocol_version");
                if(network.discovery_service_type!="_phantom-ev3._udp")incomplete.Add("discovery_service_type");
                if(network.discovery_domain!="local.")incomplete.Add("discovery_domain");
                if(network.ip_family!="IPV4")incomplete.Add("ip_family");
                if(string.IsNullOrEmpty(network.control_key_id))incomplete.Add("control_key_id");
                // JsonUtility materializes a JSON null string as String.Empty on
                // the Quest runtime. Both null and empty mean that commissioning
                // is intentionally unavailable in the network-only profile.
                if(!string.IsNullOrEmpty(network.commissioning_key_id))incomplete.Add("commissioning_key_id_must_be_unset");
                if(network.default_port<1||network.default_port>65535)incomplete.Add("default_port");
            }
            if(incomplete.Count!=0)throw new InvalidOperationException("Конфигурация сети Stage 3 неполна: "+string.Join(",",incomplete));
            return new NetworkClientOptions{RobotId=robot_id,ServiceType=network.discovery_service_type,ControlKeyId=network.control_key_id,ProtocolMajor=network.protocol_version,TelemetryMaxAgeMs=network.telemetry_max_age_ms,HelloRetryMs=network.hello_retry_ms,HelloMaxAttempts=network.hello_max_attempts,PingIntervalMs=network.ping_interval_ms,PingTimeoutMs=network.ping_timeout_ms,MaxMissedPongs=network.max_missed_pongs,ReconnectDelayMs=network.reconnect_delay_ms,ExpectedBuildProfile=1,ExpectedBundleHash=NetworkOnlyDescriptorHash()};
        }
        // Same canonical session descriptor as EV3; contains no physical data.
        public static byte[] NetworkOnlyDescriptorHash()
        {
            const string json=Phantom.Networking.Generated.NetworkOnlySessionV1.CanonicalJson;
            using(var sha=SHA256.Create())return sha.ComputeHash(Encoding.UTF8.GetBytes(json));
        }
        public static byte[] Hex32(string value)
        {
            if(value==null||value.Length!=64)throw new FormatException("SHA-256");var bytes=new byte[32];
            for(var i=0;i<32;i++)bytes[i]=Convert.ToByte(value.Substring(i*2,2),16);return bytes;
        }
    }
}
