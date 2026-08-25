using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using Oculus.Platform;

namespace Phantom.Editor
{
    public static class PhantomBuild
    {
        const string PackageName="dev.phantom.questprototype";
        const string MetaAppId="1405011949353501";

        public static void BuildAndroid()
        {
            var output=Environment.GetEnvironmentVariable("PHANTOM_APK_PATH");
            if(string.IsNullOrEmpty(output))output=Path.GetFullPath(Path.Combine("..","build","quest","PhantomQuest-release.apk"));
            var keystore=RequiredEnvironmentVariable("PHANTOM_KEYSTORE_PATH");
            var passwordFile=RequiredEnvironmentVariable("PHANTOM_KEYSTORE_PASSWORD_FILE");
            var alias=RequiredEnvironmentVariable("PHANTOM_KEY_ALIAS");
            var configuredAppId=RequiredEnvironmentVariable("PHANTOM_META_APP_ID");
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
            BuildReport report;
            try
            {
                EditorUserBuildSettings.development=false;
                PlayerSettings.Android.useCustomKeystore=true;
                PlayerSettings.Android.keystoreName=keystore;
                PlayerSettings.Android.keystorePass=password;
                PlayerSettings.Android.keyaliasName=alias;
                PlayerSettings.Android.keyaliasPass=password;
                report=BuildPipeline.BuildPlayer(paths,output,BuildTarget.Android,BuildOptions.None);
            }
            finally
            {
                PlayerSettings.Android.useCustomKeystore=oldUseCustomKeystore;
                PlayerSettings.Android.keystoreName=oldKeystoreName;
                PlayerSettings.Android.keystorePass=oldKeystorePass;
                PlayerSettings.Android.keyaliasName=oldKeyaliasName;
                PlayerSettings.Android.keyaliasPass=oldKeyaliasPass;
            }
            if(report.summary.result!=BuildResult.Succeeded)throw new Exception($"Android build failed: {report.summary.result}, errors={report.summary.totalErrors}");
        }

        static string RequiredEnvironmentVariable(string name)
        {
            var value=Environment.GetEnvironmentVariable(name);
            if(string.IsNullOrEmpty(value))throw new Exception("Required environment variable is missing: "+name);
            return value;
        }
    }
}
