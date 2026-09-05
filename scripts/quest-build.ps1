param(
    [string]$Output="build/quest/PhantomQuest-release.apk",
    [string]$SigningDirectory=".secrets/quest-release",
    [ValidateSet("Release","Diagnostic")][string]$Profile="Release"
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
$env:PHANTOM_BUILD_PROFILE=$Profile
$env:PHANTOM_GIT_COMMIT=(git rev-parse HEAD).Trim()
$env:PHANTOM_WORKTREE_DIRTY=if((git status --porcelain).Count -gt 0){"true"}else{"false"}
$env:PHANTOM_SPECIFICATION_SHA256=(Get-FileHash docs\PHANTOM_SPECIFICATION.md -Algorithm SHA256).Hash.ToLower()
$env:PHANTOM_PROTOCOL_SCHEMA_HASH=(Get-Content protocol\generated\schema.sha256).Split()[0]
$questConfig=if($Profile -eq "Diagnostic"){"config\generated\quest-network-only.generated.json"}else{"config\generated\quest.generated.json"}
$env:PHANTOM_QUEST_CONFIG_PATH=[System.IO.Path]::GetFullPath($questConfig)
$env:PHANTOM_CONFIG_HASH=(Get-FileHash $questConfig -Algorithm SHA256).Hash.ToLower()
$configManifest=Get-Content config\generated\config-manifest.json -Raw|ConvertFrom-Json
$env:PHANTOM_BUNDLE_HASH=if($Profile -eq "Diagnostic"){$configManifest.artifact_hashes.'commissioning_bundle-network-only'}else{$configManifest.artifact_hashes.commissioning_bundle}
$env:PHANTOM_PACKAGE_LOCK_SHA256=(Get-FileHash PhantomQuest\Packages\packages-lock.json -Algorithm SHA256).Hash.ToLower()
$env:PHANTOM_SOURCE_TREE_HASH=(python tools\source_hash.py PhantomQuest\Assets\Phantom PhantomQuest\Assets\Plugins PhantomQuest\Packages PhantomQuest\ProjectSettings).Trim()
$env:PHANTOM_BUILD_ID=(python tools\build_identity.py --component QUEST --profile $Profile --git-commit $env:PHANTOM_GIT_COMMIT --source-tree-hash $env:PHANTOM_SOURCE_TREE_HASH --specification-sha256 $env:PHANTOM_SPECIFICATION_SHA256 --protocol-schema-hash $env:PHANTOM_PROTOCOL_SCHEMA_HASH --component-config-hash $env:PHANTOM_CONFIG_HASH --toolchain-or-package-lock-hash $env:PHANTOM_PACKAGE_LOCK_SHA256).Trim()
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
$process=Start-Process -FilePath $unity -ArgumentList $arguments -WindowStyle Hidden -PassThru
# Start-Process -Wait waits for the complete descendant process tree on Windows.
# Unity may leave Gradle helpers alive after the editor has already returned, so
# wait for the editor process itself and use its real exit code.
$process.WaitForExit()
$unityExitCode=$process.ExitCode
# A surviving Gradle daemon can retain a Windows file handle in the generated
# launcher and make the immediately following profile build nondeterministic.
$gradleWrapper=[System.IO.Path]::GetFullPath("PhantomQuest/Library/Bee/Android/Prj/IL2CPP/Gradle/gradlew.bat")
if(Test-Path -LiteralPath $gradleWrapper)
{
    $previousLocation=Get-Location
    try
    {
        Set-Location ([System.IO.Path]::GetDirectoryName($gradleWrapper))
        & $gradleWrapper --stop | Out-Null
    }
    finally { Set-Location $previousLocation }
}
if($unityExitCode -ne 0){throw "Unity Android build failed with exit code $unityExitCode; see results/quest/android-build.log"}
