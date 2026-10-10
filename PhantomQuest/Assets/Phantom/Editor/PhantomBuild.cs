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
            var protocolSchemaHash=RequiredEnvironmentVariable("PHANTOM_PROTOCOL_SCHEMA_HASH");
            var protocolSemanticsHash=RequiredEnvironmentVariable("PHANTOM_PROTOCOL_SEMANTICS_HASH");
            var protocolContractHash=RequiredEnvironmentVariable("PHANTOM_PROTOCOL_CONTRACT_HASH");
            var configHash=RequiredEnvironmentVariable("PHANTOM_CONFIG_HASH");
            var bundleHash=RequiredEnvironmentVariable("PHANTOM_BUNDLE_HASH");
            var sourceTreeHash=RequiredEnvironmentVariable("PHANTOM_SOURCE_TREE_HASH");
            var packageLockHash=RequiredEnvironmentVariable("PHANTOM_PACKAGE_LOCK_SHA256");
            var buildId=RequiredEnvironmentVariable("PHANTOM_BUILD_ID");
            var worktreeDirty=RequiredEnvironmentVariable("PHANTOM_WORKTREE_DIRTY");
            if(worktreeDirty!="true"&&worktreeDirty!="false")throw new Exception("Invalid PHANTOM_WORKTREE_DIRTY value");
            if(profile!="Release"&&profile!="Diagnostic")throw new Exception("Invalid build profile: "+profile);
            if(!File.Exists(keystore))throw new FileNotFoundException("Release keystore not found",keystore);
            if(!File.Exists(passwordFile))throw new FileNotFoundException("Release keystore password file not found",passwordFile);
            var password=File.ReadAllText(passwordFile).Trim();
            if(string.IsNullOrEmpty(password))throw new Exception("Release keystore password is empty");
            Directory.CreateDirectory(Path.GetDirectoryName(output));
            PlatformSettings.AppID=configuredAppId;
            PlatformSettings.MobileAppID=configuredAppId;
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
            var oldExceptionStack=UnityEngine.Application.GetStackTraceLogType(UnityEngine.LogType.Exception);
            var oldErrorStack=UnityEngine.Application.GetStackTraceLogType(UnityEngine.LogType.Error);
            BuildReport report;
            try
            {
                EditorUserBuildSettings.development=profile=="Diagnostic";
                if(profile=="Diagnostic")
                {
                    PlayerSettings.SetStackTraceLogType(UnityEngine.LogType.Exception,UnityEngine.StackTraceLogType.Full);
                    PlayerSettings.SetStackTraceLogType(UnityEngine.LogType.Error,UnityEngine.StackTraceLogType.Full);
                }
                PlayerSettings.Android.useCustomKeystore=true;
                PlayerSettings.Android.keystoreName=keystore;
                PlayerSettings.Android.keystorePass=password;
                PlayerSettings.Android.keyaliasName=alias;
                PlayerSettings.Android.keyaliasPass=password;
                WriteEmbeddedInputs(profile,buildId,gitCommit,sourceTreeHash,worktreeDirty,protocolSchemaHash,protocolSemanticsHash,protocolContractHash,configHash,bundleHash,packageLockHash);
                var options=BuildOptions.None;
                if(profile=="Diagnostic")options=BuildOptions.Development|BuildOptions.AllowDebugging;
                report=BuildPipeline.BuildPlayer(paths,output,BuildTarget.Android,options);
            }
            finally
            {
                DeleteEmbeddedInputs();
                EditorUserBuildSettings.development=oldDevelopment;
                PlayerSettings.SetStackTraceLogType(UnityEngine.LogType.Exception,oldExceptionStack);
                PlayerSettings.SetStackTraceLogType(UnityEngine.LogType.Error,oldErrorStack);
                PlayerSettings.Android.useCustomKeystore=oldUseCustomKeystore;
                PlayerSettings.Android.keystoreName=oldKeystoreName;
                PlayerSettings.Android.keystorePass=oldKeystorePass;
                PlayerSettings.Android.keyaliasName=oldKeyaliasName;
                PlayerSettings.Android.keyaliasPass=oldKeyaliasPass;
                AssetDatabase.SaveAssets();
            }
            if(report.summary.result!=BuildResult.Succeeded)throw new Exception($"Android build failed: {report.summary.result}, errors={report.summary.totalErrors}");
            var apkHash=Sha256(File.ReadAllBytes(output));
            var identity=BuildIdentityJson(profile,buildId,gitCommit,sourceTreeHash,worktreeDirty,protocolSchemaHash,protocolSemanticsHash,protocolContractHash,configHash,bundleHash,packageLockHash);
            var embeddedBytes=new UTF8Encoding(false).GetBytes(identity+Environment.NewLine);
            var manifest=ExternalManifestJson(identity,apkHash,Sha256(embeddedBytes),DateTime.UtcNow.ToString("o"));
            File.WriteAllText(output+".build-manifest.json",manifest+Environment.NewLine);
        }

        static void WriteEmbeddedInputs(string profile,string buildId,string gitCommit,string sourceTreeHash,string worktreeDirty,string protocolSchemaHash,string protocolSemanticsHash,string protocolContractHash,string configHash,string bundleHash,string packageLockHash)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(EmbeddedBuildPath));
            var manifest=BuildIdentityJson(profile,buildId,gitCommit,sourceTreeHash,worktreeDirty,protocolSchemaHash,protocolSemanticsHash,protocolContractHash,configHash,bundleHash,packageLockHash);
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

        static string BuildIdentityJson(string profile,string buildId,string gitCommit,string sourceTreeHash,string worktreeDirty,string protocolSchemaHash,string protocolSemanticsHash,string protocolContractHash,string configHash,string bundleHash,string packageLockHash)
        {
            var core=PackageVersion("com.meta.xr.sdk.core");
            var mruk=PackageVersion("com.meta.xr.mrutilitykit");
            var openxr=PackageVersion("com.unity.xr.openxr");
            var metaOpenxr=PackageVersion("com.unity.xr.meta-openxr");
            var hands=PackageVersion("com.unity.xr.hands");
            var bodyCompatibility=BodyMultimodalCompatibility();
            var multimodal=profile=="Release"?"true":"false";var qualificationEligible="true";
            return $"{{\"schema_version\":8,\"build_identity_schema\":\"PHANTOM-BUILD-V4\",\"component\":\"QUEST\",\"build_id\":\"{buildId}\",\"git_commit\":\"{gitCommit}\",\"source_tree_hash\":\"{sourceTreeHash}\",\"worktree_dirty\":{worktreeDirty},\"build_profile\":\"{profile}\",\"qualification_eligible\":{qualificationEligible},\"protocol_version\":1,\"protocol_schema_hash\":\"{protocolSchemaHash}\",\"protocol_semantics_hash\":\"{protocolSemanticsHash}\",\"protocol_contract_hash\":\"{protocolContractHash}\",\"config_hash\":\"{configHash}\",\"commissioning_bundle_hash\":\"{bundleHash}\",\"unity_version\":\"{UnityEngine.Application.unityVersion}\",\"app_version\":\"{PlayerSettings.bundleVersion}\",\"package_lock_sha256\":\"{packageLockHash}\",\"toolchain_or_package_lock_hash\":\"{packageLockHash}\",\"meta_xr_core_version\":\"{core}\",\"movement_sdk_version\":\"{core}\",\"body_tracking_provider\":\"OVRBody/com.meta.xr.sdk.core\",\"multimodal_required\":{multimodal},\"body_provider_joint_set\":\"UpperBody\",\"body_right_shoulder_api\":\"OVRPlugin.BoneId.Body_RightShoulder\",\"body_multimodal_compatibility\":\"{bodyCompatibility}\",\"mruk_version\":\"{mruk}\",\"openxr_plugin_version\":\"{openxr}\",\"meta_openxr_version\":\"{metaOpenxr}\",\"xr_hands_version\":\"{hands}\"}}";
        }

        static string ExternalManifestJson(string identity,string apkHash,string embeddedIdentityHash,string createdAt)
        {
            var closing=identity.LastIndexOf('}');
            if(closing<0)throw new Exception("Invalid embedded identity JSON");
            return identity.Substring(0,closing)+$",\"apk_sha256\":\"{apkHash}\",\"embedded_identity_sha256\":\"{embeddedIdentityHash}\",\"signing_key_id\":\"phantom-quest-release\",\"created_at\":\"{createdAt}\"}}";
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
