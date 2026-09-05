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
        PhantomWristHud _hud;QuestJsonlLogger _logger;Stage3NetworkClient _network;BoundedNetworkFlightRecorder _flight;double _nextHud;string _startupError;
        public NetworkSnapshot NetworkSnapshot=>_network?.Snapshot;
        public int FlightRecorderCount=>_flight?.Count??0;
        void Awake()
        {
            _hud=GetComponent<PhantomWristHud>()??gameObject.AddComponent<PhantomWristHud>();_logger=new QuestJsonlLogger();_flight=new BoundedNetworkFlightRecorder(256);
            try
            {
                var config=LoadStage3Config();var options=config.ToOptions();var build=Resources.Load<TextAsset>("phantom-build");if(build){var identity=JsonUtility.FromJson<QuestBuildIdentity>(build.text);if(identity!=null&&!string.IsNullOrEmpty(identity.specification_sha256))options.ExpectedSpecificationHash=Stage3RuntimeConfig.Hex32(identity.specification_sha256);}
                var discovery=new AndroidNsdDiscoveryBackend();var transport=new UdpRobotTransport();var credentials=new AndroidPrivateControlCredentialStore(Application.persistentDataPath);
                _network=new Stage3NetworkClient(discovery,transport,credentials,options,null,new QuestNetworkEventSink(_logger,_flight));_network.Start();
                _logger.Log("runtime","stage3_network_only_start","Discovering","","{\"actuator_scope_mask\":0,\"motor_authority\":false}");
            }
            catch(Exception error){_startupError=error.Message;_logger.Log("runtime","configuration_mismatch","ConfigurationMismatch","","{\"category\":\"stage3_startup\"}");}
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
                qualification=new QuestQualificationConfig{qualification_only=true,actuator_scope_mask=0,required_user_inputs="NONE"},
                commissioning_bundle=new QuestBundleConfig{expected_hash="0f629d9260309e592798fa202dcab14f1f414bd43a54cbe55442af4af9231cfb"},
                network=new QuestNetworkConfig{discovery_service="_phantom-ev3._udp.local",default_port=30470,protocol_version=1,control_key_id="phantom01-control",telemetry_max_age_ms=100,hello_retry_ms=250,hello_max_attempts=5,ping_interval_ms=500,ping_timeout_ms=750,max_missed_pongs=3,reconnect_delay_ms=250}
            };
        }
    }

    public static class PhantomBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]static void Install()
        {
            if(UnityEngine.Object.FindFirstObjectByType<PhantomRuntime>()!=null)return;var go=new GameObject("PhantomRuntime");UnityEngine.Object.DontDestroyOnLoad(go);go.AddComponent<PhantomRuntime>();go.AddComponent<QuestDeviceAuto>();
#if DEVELOPMENT_BUILD
            go.AddComponent<Phantom.Experiments.QuestValidationRunner>();
#endif
        }
    }
}
