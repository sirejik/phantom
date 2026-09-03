$ErrorActionPreference="Stop"
$editorData="C:\Program Files\Unity\Hub\Editor\6000.3.22f1\Editor\Data"
$dotnet=Join-Path $editorData "NetCoreRuntime\dotnet.exe"
$csc=Join-Path $editorData "DotNetSdkRoslyn\csc.dll"
$api=Join-Path $editorData "MonoBleedingEdge\lib\mono\4.7.1-api"
$outDir=[System.IO.Path]::GetFullPath("results/quest/smoke")
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$sourceDirs=@("Kinematics","Workspace","Calibration","Config","Networking","Replay","Room","RobotLocalization")
$sources=@()
foreach($dir in $sourceDirs){$sources+=Get-ChildItem "PhantomQuest/Assets/Phantom/$dir" -Filter "*.cs"|Select-Object -ExpandProperty FullName}
$sources+=(Resolve-Path "PhantomQuest/Assets/Phantom/Tracking/TrackingState.cs").Path
$sources+=(Resolve-Path "PhantomQuest/Assets/Phantom/Tracking/XrSpaceBridge.cs").Path
$sources+=(Resolve-Path "PhantomQuest/Assets/Phantom/Mapping/HumanToRobotMapper.cs").Path
$sources+=(Resolve-Path "PhantomQuest/Assets/Phantom/Mapping/PhantomStateMachine.cs").Path
$sources+=(Resolve-Path "PhantomQuest/Assets/Phantom/Diagnostics/QuestAutoQualification.cs").Path
& $dotnet $csc -nologo -langversion:9 -noconfig -nostdlib -target:library -out:"$outDir/Phantom.Core.dll" -r:"$api/mscorlib.dll" -r:"$api/System.dll" -r:"$api/System.Core.dll" @sources
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $dotnet $csc -nologo -langversion:9 -noconfig -nostdlib -target:exe -out:"$outDir/CoreSmoke.exe" -r:"$api/mscorlib.dll" -r:"$api/System.dll" -r:"$api/System.Core.dll" -r:"$outDir/Phantom.Core.dll" "tools/quest_validation/CoreSmoke.cs"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& "$outDir/CoreSmoke.exe"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
