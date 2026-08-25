#if PHANTOM_MRUK
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Phantom.Meta
{
    /// <summary>
    /// Configures the single Meta XR camera rig used by PHANTOM mixed reality.
    /// The scene contains the official OVRCameraRig prefab; runtime creation is
    /// only a defensive fallback for an incorrectly loaded scene.
    /// </summary>
    public sealed class MetaPassthroughController : MonoBehaviour
    {
        static readonly HashSet<string> LegacyTemplateRoots=new HashSet<string>
        {
            "Environment", "Lighting", "Interactables", "Teleport Area Setup", "UI"
        };

        bool _lastInitialized;
        bool _reportedInitialState;

        void Awake()
        {
            var rig=EnsureRuntimeRig();
            DisableLegacyTemplateContent();
            ConfigureExclusiveCamera(rig);
            LogRuntimeAudit(rig);
            Debug.Log("PHANTOM MR passthrough requested manager="+(OVRManager.instance!=null)+
                      " layer="+(rig&&rig.GetComponent<OVRPassthroughLayer>()!=null));
        }

        public static OVRCameraRig EnsureRuntimeRig()
        {
            var rigs=UnityEngine.Object.FindObjectsByType<OVRCameraRig>(FindObjectsInactive.Include,FindObjectsSortMode.None);
            OVRCameraRig rig=null;
            foreach(var candidate in rigs)
            {
                if(rig==null&&candidate.gameObject.activeInHierarchy){rig=candidate;continue;}
                candidate.enabled=false;
                foreach(var camera in candidate.GetComponentsInChildren<Camera>(true))camera.enabled=false;
                Debug.LogError("PHANTOM MR disabled duplicate OVRCameraRig="+candidate.name);
            }

            if(!rig)
            {
                var rigObject=new GameObject("PHANTOM Meta XR Camera Rig (Fallback)");
                rig=rigObject.AddComponent<OVRCameraRig>();
                Debug.LogError("PHANTOM MR scene rig missing; created runtime fallback");
            }

            rig.transform.localPosition=Vector3.zero;
            rig.transform.localRotation=Quaternion.identity;
            rig.transform.localScale=Vector3.one;
            rig.usePerEyeCameras=false;
            rig.useFixedUpdateForTracking=false;
            rig.disableEyeAnchorCameras=false;
            rig.enabled=true;
            foreach(var behaviour in rig.GetComponents<MonoBehaviour>())
                if(behaviour&&behaviour.GetType().Name=="OVRHeadsetEmulator")behaviour.enabled=false;
            rig.EnsureGameObjectIntegrity();

            var manager=rig.GetComponent<OVRManager>();
            if(!manager)manager=rig.gameObject.AddComponent<OVRManager>();
            manager.trackingOriginType=OVRManager.TrackingOrigin.FloorLevel;
            manager.usePositionTracking=true;
            manager.useRotationTracking=true;
            manager.useIPDInPositionTracking=true;
            manager.LateControllerUpdate=true;
            manager.isInsightPassthroughEnabled=true;
            ConfigureRendering(manager);

            var layer=rig.GetComponent<OVRPassthroughLayer>();
            if(!layer)layer=rig.gameObject.AddComponent<OVRPassthroughLayer>();
            layer.hidden=false;
            layer.textureOpacity=1f;
            return rig;
        }

        static void ConfigureRendering(OVRManager manager)
        {
            // Conservative baseline: no optional second pose path, resolution
            // changes, foveation, or app-spacewarp reprojection.
            manager.LateLatching=false;
            manager.enableDynamicResolution=false;
            OVRManager.foveatedRenderingLevel=OVRManager.FoveatedRenderingLevel.Off;
            OVRManager.useDynamicFoveatedRendering=false;
        }

        static void ConfigureExclusiveCamera(OVRCameraRig rig)
        {
            if(!rig)return;
            var central=rig.centerEyeAnchor.GetComponent<Camera>();
            if(!central)central=rig.centerEyeAnchor.gameObject.AddComponent<Camera>();
            central.enabled=true;
            central.tag="MainCamera";
            central.clearFlags=CameraClearFlags.SolidColor;
            central.backgroundColor=Color.clear;
            central.nearClipPlane=.05f;

            foreach(var camera in UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsInactive.Include,FindObjectsSortMode.None))
            {
                if(camera==central)continue;
                camera.enabled=false;
                if(camera.CompareTag("MainCamera"))camera.tag="Untagged";
            }

            var centralListener=central.GetComponent<AudioListener>();
            if(!centralListener)centralListener=central.gameObject.AddComponent<AudioListener>();
            centralListener.enabled=true;
            foreach(var listener in UnityEngine.Object.FindObjectsByType<AudioListener>(FindObjectsInactive.Include,FindObjectsSortMode.None))
                if(listener!=centralListener)listener.enabled=false;
        }

        static void DisableLegacyTemplateContent()
        {
            var scene=SceneManager.GetActiveScene();
            foreach(var root in scene.GetRootGameObjects())
            {
                if(!LegacyTemplateRoots.Contains(root.name)&&!root.name.StartsWith("XR Origin"))continue;
                root.SetActive(false);
                Debug.LogWarning("PHANTOM MR disabled legacy template root="+root.name);
            }
        }

        static void LogRuntimeAudit(OVRCameraRig rig)
        {
            var activeCameras=0;var activeListeners=0;var activeRigs=0;var activeManagers=0;var activePassthrough=0;
            foreach(var camera in UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsInactive.Include,FindObjectsSortMode.None))if(camera.enabled&&camera.gameObject.activeInHierarchy)activeCameras++;
            foreach(var listener in UnityEngine.Object.FindObjectsByType<AudioListener>(FindObjectsInactive.Include,FindObjectsSortMode.None))if(listener.enabled&&listener.gameObject.activeInHierarchy)activeListeners++;
            foreach(var candidate in UnityEngine.Object.FindObjectsByType<OVRCameraRig>(FindObjectsInactive.Include,FindObjectsSortMode.None))if(candidate.enabled&&candidate.gameObject.activeInHierarchy)activeRigs++;
            foreach(var manager in UnityEngine.Object.FindObjectsByType<OVRManager>(FindObjectsInactive.Include,FindObjectsSortMode.None))if(manager.enabled&&manager.gameObject.activeInHierarchy)activeManagers++;
            foreach(var layer in UnityEngine.Object.FindObjectsByType<OVRPassthroughLayer>(FindObjectsInactive.Include,FindObjectsSortMode.None))if(layer.enabled&&layer.gameObject.activeInHierarchy)activePassthrough++;
            Debug.Log($"PHANTOM MR AUDIT rig={rig?.name??"<null>"} active_rigs={activeRigs} managers={activeManagers} cameras={activeCameras} listeners={activeListeners} passthrough_layers={activePassthrough} fixed_update={rig?.useFixedUpdateForTracking} eye_cameras_disabled={rig?.disableEyeAnchorCameras}");
        }

        void Update()
        {
            var initialized=OVRManager.IsInsightPassthroughInitialized();
            if(_reportedInitialState&&initialized==_lastInitialized)return;
            _reportedInitialState=true;
            _lastInitialized=initialized;
            Debug.Log("PHANTOM MR passthrough initialized="+initialized);
        }
    }
}
#endif
