using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.Rendering;
using UnityEngine.XR.Hands;
using UnityEngine.XR.OpenXR;

namespace Phantom.Editor
{
    public static class PhantomMrSceneBuilder
    {
        public const string ScenePath="Assets/Scenes/PhantomMR.unity";
        const string CameraRigPrefabPath="Packages/com.meta.xr.sdk.core/Prefabs/OVRCameraRig.prefab";
        const string RuntimeControllerPrefabPath="Packages/com.meta.xr.sdk.core/Prefabs/OVRRuntimeControllerPrefab.prefab";
        const string LeftHandPrefabPath="Assets/Samples/XR Hands/1.8.1/HandVisualizer/Prefabs/Left Hand Tracking.prefab";
        const string RightHandPrefabPath="Assets/Samples/XR Hands/1.8.1/HandVisualizer/Prefabs/Right Hand Tracking.prefab";

        [MenuItem("PHANTOM/Rebuild Minimal MR Scene")]
        public static void RebuildMinimalMrScene()
        {
            ConfigureQuestProject();
            var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
            SceneManager.SetActiveScene(scene);
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(CameraRigPrefabPath);
            if(!prefab)throw new InvalidOperationException("Official Meta OVRCameraRig prefab was not found: "+CameraRigPrefabPath);
            var root=(GameObject)PrefabUtility.InstantiatePrefab(prefab);
            if(!root)throw new InvalidOperationException("Could not instantiate official Meta OVRCameraRig prefab");
            root.name="PHANTOM Meta XR Camera Rig";
            root.transform.SetPositionAndRotation(Vector3.zero,Quaternion.identity);
            root.transform.localScale=Vector3.one;

            var rig=root.GetComponent<OVRCameraRig>();
            var manager=root.GetComponent<OVRManager>();
            if(!rig||!manager)throw new InvalidOperationException("Official Meta prefab is missing OVRCameraRig or OVRManager");
            foreach(var behaviour in root.GetComponents<MonoBehaviour>())
                if(behaviour&&behaviour.GetType().Name=="OVRHeadsetEmulator")behaviour.enabled=false;
            rig.usePerEyeCameras=false;
            rig.useFixedUpdateForTracking=false;
            rig.disableEyeAnchorCameras=false;
            manager.monoscopic=false;
            manager.trackingOriginType=OVRManager.TrackingOrigin.FloorLevel;
            manager.usePositionTracking=true;
            manager.useRotationTracking=true;
            manager.useIPDInPositionTracking=true;
            manager.LateControllerUpdate=true;
            manager.LateLatching=false;
            manager.enableDynamicResolution=false;
            manager.isInsightPassthroughEnabled=true;

            var passthrough=root.GetComponent<OVRPassthroughLayer>()??root.AddComponent<OVRPassthroughLayer>();
            passthrough.hidden=false;
            passthrough.textureOpacity=1f;

            rig.EnsureGameObjectIntegrity();
            var central=rig.centerEyeAnchor.GetComponent<Camera>();
            central.enabled=true;
            central.tag="MainCamera";
            central.clearFlags=CameraClearFlags.SolidColor;
            central.backgroundColor=Color.clear;
            central.nearClipPlane=.05f;
            foreach(var camera in root.GetComponentsInChildren<Camera>(true))
            {
                if(camera==central)continue;
                camera.enabled=false;
                camera.tag="Untagged";
            }

            var listener=central.GetComponent<AudioListener>()??central.gameObject.AddComponent<AudioListener>();
            listener.enabled=true;
            AddTrackedHand(rig.trackingSpace,LeftHandPrefabPath,"PHANTOM Left Hand Visual",Handedness.Left);
            AddTrackedHand(rig.trackingSpace,RightHandPrefabPath,"PHANTOM Right Hand Visual",Handedness.Right);
            AddRuntimeController(rig.leftControllerAnchor,"PHANTOM Left Touch Controller Visual",OVRInput.Controller.LTouch);
            AddRuntimeController(rig.rightControllerAnchor,"PHANTOM Right Touch Controller Visual",OVRInput.Controller.RTouch);
            RenderSettings.skybox=null;
            RenderSettings.fog=false;
            EditorSceneManager.SaveScene(scene,ScenePath);
            EditorBuildSettings.scenes=new[]{new EditorBuildSettingsScene(ScenePath,true)};
            ValidateCurrentSceneOrThrow();
            AssetDatabase.SaveAssets();
            Debug.Log("PHANTOM MR SCENE rebuilt from official Meta OVRCameraRig prefab: "+ScenePath);
        }

        public static void ValidateBuildSceneOrThrow()
        {
            var enabled=EditorBuildSettings.scenes.Where(candidate=>candidate.enabled).ToArray();
            Require(enabled.Length==1,"exactly one enabled build scene is required");
            Require(enabled[0].path==ScenePath,"the only build scene must be "+ScenePath);
            EditorSceneManager.OpenScene(ScenePath,OpenSceneMode.Single);
            ValidateCurrentSceneOrThrow();
        }

        public static void ValidateCurrentSceneOrThrow()
        {
            var rigs=ActiveComponents<OVRCameraRig>();
            var managers=ActiveComponents<OVRManager>();
            var cameras=ActiveComponents<Camera>();
            var listeners=ActiveComponents<AudioListener>();
            var passthroughLayers=ActiveComponents<OVRPassthroughLayer>();
            var handEvents=ActiveComponents<XRHandTrackingEvents>();
            var controllerVisuals=ActiveComponents<OVRRuntimeController>();
            Require(rigs.Count==1,"exactly one active OVRCameraRig is required");
            Require(managers.Count==1,"exactly one active OVRManager is required");
            Require(cameras.Count==1,"exactly one active Camera is required");
            Require(listeners.Count==1,"exactly one active AudioListener is required");
            Require(passthroughLayers.Count==1,"exactly one active OVRPassthroughLayer is required");
            Require(handEvents.Count==2,"exactly two XR Hands visual event sources are required");
            Require(controllerVisuals.Count==2,"exactly two Meta runtime controller visuals are required");

            var rig=rigs[0];var manager=managers[0];var camera=cameras[0];var passthrough=passthroughLayers[0];
            Require(manager.gameObject==rig.gameObject,"OVRManager must belong to the active OVRCameraRig");
            Require(camera.transform==rig.centerEyeAnchor,"the only active Camera must be CenterEyeAnchor");
            Require(camera.CompareTag("MainCamera"),"CenterEyeAnchor Camera must carry the MainCamera tag");
            Require(camera.clearFlags==CameraClearFlags.SolidColor&&camera.backgroundColor.a<=.001f,"MR camera must clear to a transparent solid color");
            Require(camera.stereoTargetEye==StereoTargetEyeMask.Both,"CenterEyeAnchor must render both eyes");
            Require(!rig.usePerEyeCameras&&!rig.useFixedUpdateForTracking&&!rig.disableEyeAnchorCameras,"OVRCameraRig must use one center camera and Update/onBeforeRender tracking");
            Require(manager.trackingOriginType==OVRManager.TrackingOrigin.FloorLevel,"MR tracking origin must be FloorLevel");
            Require(manager.usePositionTracking&&manager.useRotationTracking&&manager.useIPDInPositionTracking,"head position, rotation and IPD tracking must be enabled");
            Require(manager.LateControllerUpdate,"late controller update must be enabled");
            Require(!manager.LateLatching&&!manager.enableDynamicResolution,"late latching and dynamic resolution must be disabled for the diagnostic baseline");
            Require(manager.isInsightPassthroughEnabled,"OVRManager passthrough must be enabled");
            Require(!passthrough.hidden&&Mathf.Approximately(passthrough.textureOpacity,1f),"passthrough background must be visible at full opacity");
            Require(handEvents.Count(value=>value.handedness==Handedness.Left)==1&&handEvents.Count(value=>value.handedness==Handedness.Right)==1,"one left and one right hand visual are required");
            foreach(var handEvent in handEvents)
            {
                Require(handEvent.updateType==XRHandTrackingEvents.UpdateTypes.BeforeRender,"hand visuals must update only in BeforeRender");
                Require(handEvent.transform.IsChildOf(rig.trackingSpace),"hand visuals must be children of OVRCameraRig trackingSpace");
            }
            Require(controllerVisuals.Count(value=>value.m_controller==OVRInput.Controller.LTouch&&value.transform.parent==rig.leftControllerAnchor)==1,
                "the left runtime controller visual must be attached to LeftControllerAnchor");
            Require(controllerVisuals.Count(value=>value.m_controller==OVRInput.Controller.RTouch&&value.transform.parent==rig.rightControllerAnchor)==1,
                "the right runtime controller visual must be attached to RightControllerAnchor");

            ValidateQuestProjectSettings();

            foreach(var behaviour in UnityEngine.Object.FindObjectsByType<MonoBehaviour>(FindObjectsInactive.Include,FindObjectsSortMode.None))
            {
                if(!behaviour.gameObject.activeInHierarchy)continue;
                Require(behaviour.GetType().FullName!="Unity.XR.CoreUtils.XROrigin","Unity XROrigin must not coexist with OVRCameraRig");
                Require(behaviour.GetType().FullName!="Unity.XR.CompositionLayers.CompositionLayer","the HUD and diagnostics must render only in the eye buffer");
                Require(behaviour.GetType().Name!="OVRHeadsetEmulator"||!behaviour.enabled,"OVRHeadsetEmulator must be disabled in a device build scene");
            }
            foreach(var root in SceneManager.GetActiveScene().GetRootGameObjects())ValidateNoDemoContent(root.transform);
            Debug.Log($"PHANTOM MR EDITOR AUDIT PASS scene={SceneManager.GetActiveScene().path} rigs={rigs.Count} managers={managers.Count} cameras={cameras.Count} listeners={listeners.Count} passthrough={passthroughLayers.Count} hand_visuals={handEvents.Count} hand_update=BeforeRender controller_visuals={controllerVisuals.Count}");
        }

        public static void ConfigureQuestProject()
        {
            var config=OVRProjectConfig.CachedProjectConfig;
            if(!config)throw new InvalidOperationException("OculusProjectConfig is missing");
            config.handTrackingSupport=OVRProjectConfig.HandTrackingSupport.ControllersAndHands;
            // Fast Motion Mode is incompatible with simultaneous hands + controllers
            // and can add jitter, so the documented balanced default is intentional.
            config.handTrackingFrequency=OVRProjectConfig.HandTrackingFrequency.LOW;
            config.anchorSupport=OVRProjectConfig.AnchorSupport.Enabled;
            config.sceneSupport=OVRProjectConfig.FeatureSupport.Required;
            config.insightPassthroughSupport=OVRProjectConfig.FeatureSupport.Required;
            config.renderModelSupport=OVRProjectConfig.RenderModelSupport.Enabled;
            EditorUtility.SetDirty(config);
            AssetDatabase.SaveAssets();
        }

        static void ValidateQuestProjectSettings()
        {
            var config=OVRProjectConfig.CachedProjectConfig;
            Require(config,"OculusProjectConfig is required");
            Require(config.handTrackingSupport==OVRProjectConfig.HandTrackingSupport.ControllersAndHands,"Meta hand tracking must support controllers and hands");
            Require(config.handTrackingFrequency==OVRProjectConfig.HandTrackingFrequency.LOW,"Fast Motion hand tracking is incompatible with the required multimodal mode");
            Require(config.renderModelSupport==OVRProjectConfig.RenderModelSupport.Enabled,"Meta runtime controller render-model support must be enabled");
            Require(config.sceneSupport==OVRProjectConfig.FeatureSupport.Required,"Meta Scene API must be required");
            Require(config.insightPassthroughSupport==OVRProjectConfig.FeatureSupport.Required,"passthrough must be required");

            var settings=OpenXRSettings.GetSettingsForBuildTargetGroup(BuildTargetGroup.Android);
            Require(settings,"Android OpenXR settings are required");
            var enabled=settings.GetFeatures().Where(feature=>feature&&feature.enabled).ToArray();
            Require(enabled.Any(feature=>feature.GetType().Name=="MetaQuestFeature"),"Meta Quest OpenXR support must be enabled");
            Require(enabled.Any(feature=>feature.GetType().Name=="MetaXRFeature"),"Meta XR Core OpenXR feature must be enabled");
            Require(enabled.Any(feature=>feature.GetType().Name=="HandTracking"),"OpenXR hand-tracking subsystem must be enabled");
            Require(enabled.Any(feature=>feature.GetType().Name=="HandInteractionProfile"),"OpenXR hand interaction profile must be enabled");
            Require(enabled.Any(feature=>feature.GetType().Name=="MetaQuestTouchPlusControllerProfile"),"Quest Touch Plus controller profile must be enabled");
            foreach(var feature in enabled)
            {
                var assemblyName=feature.GetType().Assembly.GetName().Name??"";
                Require(!assemblyName.StartsWith("Unity.XR.AndroidOpenXR",StringComparison.Ordinal),"Android XR feature must not be enabled for a Meta Quest build: "+feature.name);
                Require(feature.GetType().Name.IndexOf("Foveation",StringComparison.OrdinalIgnoreCase)<0,"foveation must stay disabled for the diagnostic baseline: "+feature.name);
                Require(feature.GetType().Name.IndexOf("SpaceWarp",StringComparison.OrdinalIgnoreCase)<0,"space warp must stay disabled for the diagnostic baseline: "+feature.name);
                Require(feature.GetType().Name.IndexOf("Subsampled",StringComparison.OrdinalIgnoreCase)<0,"subsampled layout must stay disabled for the diagnostic baseline: "+feature.name);
            }
            var graphicsApis=PlayerSettings.GetGraphicsAPIs(BuildTarget.Android);
            Require(graphicsApis.Length==1&&graphicsApis[0]==GraphicsDeviceType.OpenGLES3,"Quest diagnostic baseline must use only OpenGLES3");
            Require(QualitySettings.antiAliasing==4,"Quest URP quality level must use 4x MSAA");
            var manifest=File.ReadAllText(Path.Combine("Packages","manifest.json"));
            Require(manifest.IndexOf("com.unity.xr.androidxr-openxr",StringComparison.Ordinal)<0,"Google Android XR package must not be installed in the Meta Quest project");
        }

        static void AddTrackedHand(Transform trackingSpace,string prefabPath,string objectName,Handedness handedness)
        {
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(prefabPath);
            if(!prefab)throw new InvalidOperationException("XR Hands visual prefab was not found: "+prefabPath);
            var hand=(GameObject)PrefabUtility.InstantiatePrefab(prefab);
            if(!hand)throw new InvalidOperationException("Could not instantiate XR Hands visual: "+prefabPath);
            hand.name=objectName;
            hand.transform.SetParent(trackingSpace,false);
            var events=hand.GetComponent<XRHandTrackingEvents>();
            if(!events)throw new InvalidOperationException("XR Hands visual has no XRHandTrackingEvents: "+prefabPath);
            events.handedness=handedness;
            events.updateType=XRHandTrackingEvents.UpdateTypes.BeforeRender;
        }

        static void AddRuntimeController(Transform controllerAnchor,string objectName,OVRInput.Controller controller)
        {
            var prefab=AssetDatabase.LoadAssetAtPath<GameObject>(RuntimeControllerPrefabPath);
            if(!prefab)throw new InvalidOperationException("Official Meta runtime controller prefab was not found: "+RuntimeControllerPrefabPath);
            var visual=(GameObject)PrefabUtility.InstantiatePrefab(prefab);
            if(!visual)throw new InvalidOperationException("Could not instantiate Meta runtime controller prefab");
            visual.name=objectName;
            visual.transform.SetParent(controllerAnchor,false);
            var runtimeController=visual.GetComponent<OVRRuntimeController>();
            if(!runtimeController)throw new InvalidOperationException("Meta runtime controller prefab has no OVRRuntimeController");
            runtimeController.m_controller=controller;
            runtimeController.m_supportAnimation=true;
        }

        static List<T> ActiveComponents<T>() where T:Behaviour
            =>UnityEngine.Object.FindObjectsByType<T>(FindObjectsInactive.Include,FindObjectsSortMode.None)
                .Where(component=>component.enabled&&component.gameObject.activeInHierarchy).ToList();

        static void ValidateNoDemoContent(Transform value)
        {
            if(!value.gameObject.activeInHierarchy)return;
            var name=value.name.ToLowerInvariant();
            Require(!name.Contains("joystick")&&!name.Contains("locomotion")&&!name.Contains("teleport"),"demo locomotion object is forbidden: "+value.name);
            foreach(Transform child in value)ValidateNoDemoContent(child);
        }

        static void Require(bool condition,string message)
        {
            if(!condition)throw new BuildFailedException("PHANTOM MR scene audit failed: "+message);
        }
    }
}
