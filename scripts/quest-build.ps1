param(
    [string]$Output="build/quest/PhantomQuest-release.apk",
    [string]$SigningDirectory=".secrets/quest-release"
)
$ErrorActionPreference="Stop"
$unity="C:\Program Files\Unity\Hub\Editor\6000.3.22f1\Editor\Unity.exe"
$signingRoot=[System.IO.Path]::GetFullPath($SigningDirectory)
$keystore=Join-Path $signingRoot "phantom-quest-release.keystore"
$passwordFile=Join-Path $signingRoot "keystore.pass"
if(!(Test-Path -LiteralPath $keystore)){throw "Release keystore not found: $keystore"}
if(!(Test-Path -LiteralPath $passwordFile)){throw "Release keystore password file not found: $passwordFile"}
$env:PHANTOM_APK_PATH=[System.IO.Path]::GetFullPath($Output)
$env:PHANTOM_KEYSTORE_PATH=$keystore
$env:PHANTOM_KEYSTORE_PASSWORD_FILE=$passwordFile
$env:PHANTOM_KEY_ALIAS="phantom-quest-release"
$env:PHANTOM_META_APP_ID="1405011949353501"
# Android Gradle Prefab corrupts non-ASCII Windows profile paths in generated
# batch files. Keep its cache in the ASCII-only workspace path.
$env:GRADLE_USER_HOME=[System.IO.Path]::GetFullPath(".gradle-quest")
$arguments=@(
    "-batchmode","-nographics",
    "-projectPath",[System.IO.Path]::GetFullPath("PhantomQuest"),
    "-executeMethod","Phantom.Editor.PhantomBuild.BuildAndroid",
    "-logFile",[System.IO.Path]::GetFullPath("results/quest/android-build.log"),
    "-quit"
)
$process=Start-Process -FilePath $unity -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
if($process.ExitCode -ne 0){throw "Unity Android build failed with exit code $($process.ExitCode); see results/quest/android-build.log"}
