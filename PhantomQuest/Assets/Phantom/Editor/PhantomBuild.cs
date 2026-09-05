using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.PackageManager;
using Oculus.Platform;

namespace Phantom.Editor
{
    public static class PhantomBuild
    {
        const string PackageName="dev.phantom.questprototype";
        const string MetaAppId="1405011949353501";
        const string EmbeddedBuildPath="Assets/Resources/phantom-build.json";
        const string EmbeddedConfigPath="Assets/Resources/phantom-quest-config.json";

        public static void BuildAndroid()
        {
            var output=Environment.GetEnvironmentVariable("PHANTOM_APK_PATH");
            if(string.IsNullOrEmpty(output))output=Path.GetFullPath(Path.Combine("..","build","quest","PhantomQuest-release.apk"));
            var keystore=RequiredEnvironmentVariable("PHANTOM_KEYSTORE_PATH");
            var passwordFile=RequiredEnvironmentVariable("PHANTOM_KEYSTORE_PASSWORD_FILE");
            var alias=RequiredEnvironmentVariable("PHANTOM_KEY_ALIAS");
            var configuredAppId=RequiredEnvironmentVariable("PHANTOM_META_APP_ID");
            var profile=Environment.GetEnvironmentVariable("PHANTOM_BUILD_PROFILE")??"Release";
            var gitCommit=RequiredEnvironmentVariable("PHANTOM_GIT_COMMIT");
            var specificationHash=RequiredEnvironmentVariable("PHANTOM_SPECIFICATION_SHA256");
            var protocolHash=RequiredEnvironmentVariable("PHANTOM_PROTOCOL_SCHEMA_HASH");
            var configHash=RequiredEnvironmentVariable("PHANTOM_CONFIG_HASH");
            var sourceTreeHash=RequiredEnvironmentVariable("PHANTOM_SOURCE_TREE_HASH");
            var packageLockHash=RequiredEnvironmentVariable("PHANTOM_PACKAGE_LOCK_SHA256");
            var worktreeDirty=RequiredEnvironmentVariable("PHANTOM_WORKTREE_DIRTY");
            if(worktreeDirty!="true"&&worktreeDirty!="false")throw new Exception("Invalid PHANTOM_WORKTREE_DIRTY value");
            if(profile!="Release"&&profile!="Diagnostic")throw new Exception("Invalid build profile: "+profile);
            if(configuredAppId!=MetaAppId)throw new Exception("Unexpected Meta App ID: "+configuredAppId);
            if(!File.Exists(keystore))throw new FileNotFoundException("Release keystore not found",keystore);
            if(!File.Exists(passwordFile))throw new FileNotFoundException("Release keystore password file not found",passwordFile);
            var password=File.ReadAllText(passwordFile).Trim();
            if(string.IsNullOrEmpty(password))throw new Exception("Release keystore password is empty");
            Directory.CreateDirectory(Path.GetDirectoryName(output));
            PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.Android,PackageName);
            PlatformSettings.AppID=MetaAppId;
            PlatformSettings.MobileAppID=MetaAppId;
            EditorUtility.SetDirty(PlatformSettings.Instance);
            AssetDatabase.SaveAssets();
            EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.Android,BuildTarget.Android);
            PhantomMrSceneBuilder.ConfigureQuestProject();
            PhantomMrSceneBuilder.ValidateBuildSceneOrThrow();
            var scenes=Array.FindAll(EditorBuildSettings.scenes,s=>s.enabled);var paths=Array.ConvertAll(scenes,s=>s.path);
            var oldUseCustomKeystore=PlayerSettings.Android.useCustomKeystore;
            var oldKeystoreName=PlayerSettings.Android.keystoreName;
            var oldKeystorePass=PlayerSettings.Android.keystorePass;
            var oldKeyaliasName=PlayerSettings.Android.keyaliasName;
            var oldKeyaliasPass=PlayerSettings.Android.keyaliasPass;
            var oldDevelopment=EditorUserBuildSettings.development;
            BuildReport report;
            try
            {
                EditorUserBuildSettings.development=profile=="Diagnostic";
                PlayerSettings.Android.useCustomKeystore=true;
                PlayerSettings.Android.keystoreName=keystore;
                PlayerSettings.Android.keystorePass=password;
                PlayerSettings.Android.keyaliasName=alias;
                PlayerSettings.Android.keyaliasPass=password;
                WriteEmbeddedInputs(profile,gitCommit,sourceTreeHash,worktreeDirty,specificationHash,protocolHash,configHash,packageLockHash);
                report=BuildPipeline.BuildPlayer(paths,output,BuildTarget.Android,BuildOptions.None);
            }
            finally
            {
                DeleteEmbeddedInputs();
                EditorUserBuildSettings.development=oldDevelopment;
                PlayerSettings.Android.useCustomKeystore=oldUseCustomKeystore;
                PlayerSettings.Android.keystoreName=oldKeystoreName;
                PlayerSettings.Android.keystorePass=oldKeystorePass;
                PlayerSettings.Android.keyaliasName=oldKeyaliasName;
                PlayerSettings.Android.keyaliasPass=oldKeyaliasPass;
                AssetDatabase.SaveAssets();
            }
            if(report.summary.result!=BuildResult.Succeeded)throw new Exception($"Android build failed: {report.summary.result}, errors={report.summary.totalErrors}");
            var apkHash=Sha256(File.ReadAllBytes(output));
            var manifest=BuildManifestJson(profile,gitCommit,sourceTreeHash,worktreeDirty,specificationHash,protocolHash,configHash,packageLockHash,apkHash,DateTime.UtcNow.ToString("o"));
            File.WriteAllText(output+".build-manifest.json",manifest+Environment.NewLine);
        }

        static void WriteEmbeddedInputs(string profile,string gitCommit,string sourceTreeHash,string worktreeDirty,string specificationHash,string protocolHash,string configHash,string packageLockHash)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(EmbeddedBuildPath));
            var manifest=BuildManifestJson(profile,gitCommit,sourceTreeHash,worktreeDirty,specificationHash,protocolHash,configHash,packageLockHash,"","embedded-before-apk-hash");
            File.WriteAllText(EmbeddedBuildPath,manifest+Environment.NewLine,new UTF8Encoding(false));
            var configPath=RequiredEnvironmentVariable("PHANTOM_QUEST_CONFIG_PATH");
            File.Copy(configPath,EmbeddedConfigPath,true);
            AssetDatabase.ImportAsset(EmbeddedBuildPath,ImportAssetOptions.ForceSynchronousImport);
            AssetDatabase.ImportAsset(EmbeddedConfigPath,ImportAssetOptions.ForceSynchronousImport);
        }

        static void DeleteEmbeddedInputs()
        {
            AssetDatabase.DeleteAsset(EmbeddedBuildPath);
            AssetDatabase.DeleteAsset(EmbeddedConfigPath);
        }

        static string BuildManifestJson(string profile,string gitCommit,string sourceTreeHash,string worktreeDirty,string specificationHash,string protocolHash,string configHash,string packageLockHash,string apkHash,string buildTime)
        {
            var core=PackageVersion("com.meta.xr.sdk.core");
            var mruk=PackageVersion("com.meta.xr.mrutilitykit");
            var openxr=PackageVersion("com.unity.xr.openxr");
            var metaOpenxr=PackageVersion("com.unity.xr.meta-openxr");
            var hands=PackageVersion("com.unity.xr.hands");
            var bodyCompatibility=BodyMultimodalCompatibility();
            return $"{{\"schema_version\":3,\"build_id\":\"{gitCommit}-{profile.ToLowerInvariant()}-quest\",\"git_commit\":\"{gitCommit}\",\"source_tree_hash\":\"{sourceTreeHash}\",\"worktree_dirty\":{worktreeDirty},\"build_profile\":\"{profile}\",\"protocol_version\":1,\"specification_sha256\":\"{specificationHash}\",\"protocol_schema_hash\":\"{protocolHash}\",\"config_hash\":\"{configHash}\",\"unity_version\":\"{UnityEngine.Application.unityVersion}\",\"app_version\":\"{PlayerSettings.bundleVersion}\",\"package_lock_sha256\":\"{packageLockHash}\",\"meta_xr_core_version\":\"{core}\",\"movement_sdk_version\":\"{core}\",\"body_tracking_provider\":\"OVRBody/com.meta.xr.sdk.core\",\"multimodal_required\":true,\"body_provider_joint_set\":\"UpperBody\",\"body_right_shoulder_api\":\"OVRPlugin.BoneId.Body_RightShoulder\",\"body_multimodal_compatibility\":\"{bodyCompatibility}\",\"mruk_version\":\"{mruk}\",\"openxr_plugin_version\":\"{openxr}\",\"meta_openxr_version\":\"{metaOpenxr}\",\"xr_hands_version\":\"{hands}\",\"apk_sha256\":\"{apkHash}\",\"build_time\":\"{buildTime}\"}}";
        }

        static string BodyMultimodalCompatibility()
        {
            foreach(var package in UnityEditor.PackageManager.PackageInfo.GetAllRegisteredPackages())
            {
                if(package.name!="com.meta.xr.sdk.core")continue;
                var path=Path.Combine(package.resolvedPath,"Scripts","Movement","OVRBody.cs");
                if(!File.Exists(path))throw new Exception("Resolved OVRBody source is missing: "+path);
                var source=File.ReadAllText(path);
                return source.Contains("SimultaneousHandsAndControllersEnabled")&&
                       source.Contains("Body API and simultaneous hands and controllers cannot be enabled at the same time")
                    ?"INCOMPATIBLE_EXPLICIT_SDK_GUARD"
                    :"NO_EXPLICIT_SDK_GUARD_FOUND";
            }
            throw new Exception("Meta XR Core package is not registered");
        }

        static string PackageVersion(string name)
        {
            foreach(var package in UnityEditor.PackageManager.PackageInfo.GetAllRegisteredPackages())if(package.name==name)return package.version;
            throw new Exception("Required Unity package is not registered: "+name);
        }
        static string Sha256(byte[] data){using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(data)).Replace("-","").ToLowerInvariant();}

        static string RequiredEnvironmentVariable(string name)
        {
            var value=Environment.GetEnvironmentVariable(name);
            if(string.IsNullOrEmpty(value))throw new Exception("Required environment variable is missing: "+name);
            return value;
        }
    }
}
