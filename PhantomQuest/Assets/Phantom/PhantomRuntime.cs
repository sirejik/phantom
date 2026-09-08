using System;
using Phantom.Config;
using Phantom.Diagnostics;
using Phantom.Logging;
using Phantom.Networking;
using Phantom.UI;
using Phantom.Visualization;
using UnityEngine;

namespace Phantom
{
    // Stage 3 is network-only: this runtime has no COMMAND API and creates no
    // actuator target, tracking, calibration, localization, QR or Grip dependency.
    public sealed class PhantomRuntime:MonoBehaviour
    {
        PhantomWristHud _hud;QuestJsonlLogger _logger;Stage3NetworkClient _network;BoundedNetworkFlightRecorder _flight;double _nextHud;string _startupError;string _startupBuildId;
        string _credentialState="unknown";bool _credentialProvisioned;
        public NetworkSnapshot NetworkSnapshot=>_network?.Snapshot;
        public int FlightRecorderCount=>_flight?.Count??0;
        /// <summary>DEVICE integration evidence: a usable credential exists, never its value.</summary>
        public bool ControlCredentialProvisioned=>_credentialProvisioned;
        public string ControlCredentialState=>_credentialState;
        public bool LoggingDegraded=>_logger!=null&&_logger.Degraded;
        void Awake()
        {
            _hud=GetComponent<PhantomWristHud>()??gameObject.AddComponent<PhantomWristHud>();_logger=new QuestJsonlLogger();_flight=new BoundedNetworkFlightRecorder(256);
            try
            {
                var config=LoadStage3Config();var options=config.ToOptions();var build=Resources.Load<TextAsset>("phantom-build");QuestBuildIdentity identity=null;if(build){identity=JsonUtility.FromJson<QuestBuildIdentity>(build.text);_startupBuildId=identity?.build_id;if(identity!=null&&!string.IsNullOrEmpty(identity.specification_sha256))options.ExpectedSpecificationHash=Stage3RuntimeConfig.Hex32(identity.specification_sha256);}
                var discovery=new AndroidNsdDiscoveryBackend();var transport=new UdpRobotTransport();var credentials=new AndroidPrivateControlCredentialStore(Application.persistentDataPath);
                // Engineering CONTROL PSK provisioning (ENGINEERING 8.11): the host
                // drops the key into the app-specific provisioning directory outside
                // the runtime protocol; it is imported once into the Keystore-wrapped
                // store and the plaintext drop is shredded. Diagnostic profile only,
                // and only the outcome is ever logged.
                _credentialState="absent";
                if(string.Equals(config.build_profile,"Diagnostic",StringComparison.Ordinal)||string.Equals(config.build_profile,"DeepDebug",StringComparison.Ordinal))
                {
                    var imported=credentials.TryImportProvisioningDrop(options.ControlKeyId);
                    if(imported==CredentialProvisioningResult.Imported)_logger.Log("runtime","control_credential_provisioned","Discovering","","{\"key_id_present\":true}");
                    else if(imported==CredentialProvisioningResult.Rejected)_logger.Log("runtime","control_credential_rejected","Discovering","","{\"key_id_present\":false}");
                }
                var credentialStatus=credentials.GetStatus(options.ControlKeyId);
                _credentialProvisioned=credentialStatus==CredentialStoreStatus.Ready;
                _credentialState=credentialStatus.ToString().ToLowerInvariant();
                _network=new Stage3NetworkClient(discovery,transport,credentials,options,null,new QuestNetworkEventSink(_logger,_flight));_network.Start();
                WriteStartupStatus(identity?.build_id,_credentialState,"ready");
                _logger.Log("runtime","stage3_network_only_start","Discovering","","{\"actuator_scope_mask\":0,\"motor_authority\":false,\"control_credential\":\""+_credentialState+"\"}");
            }
            catch(Exception error){_startupError=error.Message;WriteStartupStatus(_startupBuildId,_credentialState,"configuration_error");_logger.Log("runtime","configuration_mismatch","ConfigurationMismatch","","{\"category\":\"stage3_startup\"}");}
        }

        void Update()
        {
            _network?.Tick();if(Time.realtimeSinceStartupAsDouble<_nextHud)return;_nextHud=Time.realtimeSinceStartupAsDouble+.1;
            _hud.Content=_network==null?"PHANTOM\n\nОШИБКА КОНФИГУРАЦИИ\n"+(_startupError??""):Stage3NetworkUi.Format(_network.Snapshot,true);
        }

        void OnApplicationPause(bool paused){if(paused)_network?.Pause();else _network?.Resume();}
        void OnDestroy(){_network?.Dispose();_logger?.Dispose();}

        static Stage3RuntimeConfig LoadStage3Config()
        {
            var asset=Resources.Load<TextAsset>("phantom-quest-config");
            if(asset)return JsonUtility.FromJson<Stage3RuntimeConfig>(asset.text);
            return new Stage3RuntimeConfig
            {
                schema_version=1,robot_id="phantom01",build_profile="Diagnostic",
                qualification=new QuestQualificationConfig{qualification_only=true,qualification_evidence_manifest_hash=new string('0',64),actuator_scope_mask=0,safety_observation_mask=0,required_user_inputs="NONE"},
                commissioning_bundle=new QuestBundleConfig{expected_hash="17e18488df22ff736b3ede887b82397b9e06f9ac052beed011dc6c2a7eeaaeb9"},
                network=new QuestNetworkConfig{discovery_service_type="_phantom-ev3._udp",discovery_domain="local.",ip_family="IPV4",default_port=30470,protocol_version=1,control_key_id="phantom01-control",commissioning_key_id=null,telemetry_max_age_ms=100,hello_retry_ms=250,hello_max_attempts=5,ping_interval_ms=500,ping_timeout_ms=750,max_missed_pongs=3,reconnect_delay_ms=250}
            };
        }

        static void WriteStartupStatus(string buildId,string credentialStatus,string runtimeStatus)
        {
            try
            {
                var directory=System.IO.Path.Combine(Application.persistentDataPath,"phantom-status");
                System.IO.Directory.CreateDirectory(directory);
                var path=System.IO.Path.Combine(directory,"startup.json");var temporary=path+".tmp";
                var status=new QuestStartupStatus{schema_version=1,build_id=buildId??"",control_credential=credentialStatus??"unknown",runtime_status=runtimeStatus};
                System.IO.File.WriteAllText(temporary,JsonUtility.ToJson(status),new System.Text.UTF8Encoding(false));
                if(System.IO.File.Exists(path))System.IO.File.Delete(path);System.IO.File.Move(temporary,path);
            }
            catch(Exception){/* Readiness diagnostics must never crash runtime. */}
        }
    }

    [Serializable]public sealed class QuestStartupStatus
    {public int schema_version;public string build_id;public string control_credential;public string runtime_status;}

    public static class PhantomBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]static void Install()
        {
            if(UnityEngine.Object.FindFirstObjectByType<PhantomRuntime>()!=null)return;var go=new GameObject("PhantomRuntime");UnityEngine.Object.DontDestroyOnLoad(go);go.AddComponent<PhantomRuntime>();go.AddComponent<QuestDeviceIntegrationTest>();
#if DEVELOPMENT_BUILD
            go.AddComponent<Phantom.Experiments.QuestValidationRunner>();
#endif
        }
    }
}
