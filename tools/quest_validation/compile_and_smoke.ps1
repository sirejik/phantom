$ErrorActionPreference="Stop"
. "$PSScriptRoot/../toolchain.ps1"
$editorData=Get-PhantomUnityEditorData
$dotnet=Join-Path $editorData "NetCoreRuntime\dotnet.exe"
$csc=Join-Path $editorData "DotNetSdkRoslyn\csc.dll"
$api=Join-Path $editorData "MonoBleedingEdge\lib\mono\4.7.1-api"
$outDir=[System.IO.Path]::GetFullPath("results/quest/smoke")
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
# The compile set is derived, not hand-maintained: every runtime source that does
# not need a Unity API must build here, otherwise a break in one of them is only
# visible to the Unity EditMode gate, which needs an installed editor and is
# therefore absent from CI. Files are included by default; exclusion is explicit,
# so a newly added Unity-free file joins this gate automatically and a newly added
# Unity-dependent one fails the build until it is listed here on purpose.
# A `#if UNITY_*` block does not make a file Unity-dependent: csc simply drops it.
$assetRoot=(Resolve-Path "PhantomQuest/Assets/Phantom").Path
$unityDependent=@(
  "Diagnostics\QuestDeviceAuto.cs",          # UnityEngine.Application/SystemInfo probes
  "Editor\PhantomBuild.cs",                  # UnityEditor build pipeline
  "Editor\PhantomMrSceneBuilder.cs",         # UnityEditor scene authoring
  "Experiments\QuestValidationRunner.cs",    # MonoBehaviour harness
  "Logging\QuestJsonlLogger.cs",             # UnityEngine.Application.persistentDataPath
  "Logging\QuestNetworkEventSink.cs",        # depends on QuestJsonlLogger
  "Meta\MetaMrukRobotMarkerTracker.cs",      # Meta MRUK SDK
  "Meta\MetaMrukRoomReference.cs",           # Meta MRUK SDK
  "Meta\MetaPassthroughController.cs",       # Meta passthrough SDK
  "PhantomRuntime.cs",                        # MonoBehaviour composition root
  "Tracking\MetaQuestTrackingSource.cs",     # OpenXR/XR input
  "UI\Stage3NetworkUi.cs",                   # depends on QuestJsonlLogger
  "Visualization\PhantomWristHud.cs"         # UnityEngine rendering
)
foreach($excluded in $unityDependent){
  if(-not (Test-Path (Join-Path $assetRoot $excluded))){throw "stale exclusion, file is gone: $excluded"}
}
$sources=@()
foreach($file in Get-ChildItem $assetRoot -Recurse -Filter "*.cs"|Sort-Object FullName){
  if($file.FullName -like "*\Tests\*"){continue}
  $relative=$file.FullName.Substring($assetRoot.Length+1)
  if($unityDependent -contains $relative){continue}
  $sources+=$file.FullName
}
# A broken filter that silently compiles nothing would turn this gate green while
# checking less than before, so assert the set is real before handing it to csc.
foreach($anchor in @("PhantomStateMachine.cs","Stage3NetworkClient.cs","StartupWizardModel.cs","GeneratedProtocol.g.cs")){
  if(-not ($sources|Where-Object {$_ -like "*\$anchor"})){throw "compile set lost $anchor"}
}
Write-Host ("compiling " + $sources.Count + " Unity-free runtime sources")
& $dotnet $csc -nologo -langversion:9 -noconfig -nostdlib -target:library -out:"$outDir/Phantom.Core.dll" -r:"$api/mscorlib.dll" -r:"$api/System.dll" -r:"$api/System.Core.dll" @sources
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $dotnet $csc -nologo -langversion:9 -noconfig -nostdlib -target:exe -out:"$outDir/CoreSmoke.exe" -r:"$api/mscorlib.dll" -r:"$api/System.dll" -r:"$api/System.Core.dll" -r:"$outDir/Phantom.Core.dll" "tools/quest_validation/CoreSmoke.cs"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& "$outDir/CoreSmoke.exe"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $dotnet $csc -nologo -langversion:9 -noconfig -nostdlib -target:exe -out:"$outDir/Stage3CoreTests.exe" -r:"$api/mscorlib.dll" -r:"$api/System.dll" -r:"$api/System.Core.dll" -r:"$outDir/Phantom.Core.dll" "tools/quest_validation/Stage3CoreTests.cs"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& "$outDir/Stage3CoreTests.exe"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $dotnet $csc -nologo -langversion:9 -noconfig -nostdlib -target:exe -out:"$outDir/GoldenVectorInterop.exe" -r:"$api/mscorlib.dll" -r:"$api/System.dll" -r:"$api/System.Core.dll" -r:"$outDir/Phantom.Core.dll" "tools/quest_validation/GoldenVectorInterop.cs"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& "$outDir/GoldenVectorInterop.exe" ([System.IO.Path]::GetFullPath("protocol/golden_vectors/v1.json"))
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
