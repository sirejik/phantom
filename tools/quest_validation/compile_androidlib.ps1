# Compiles the PhantomScenePermissions androidlib against the pinned Android SDK.
# Without this the Java plugin is only ever compiled inside a full Unity Android
# build, so a syntax or type error there costs a ~10 minute Gradle run to find
# and never fails a deterministic gate.
$ErrorActionPreference="Stop"
. "$PSScriptRoot/../toolchain.ps1"
$editorData=Get-PhantomUnityEditorData
$javac=Join-Path $editorData "PlaybackEngines\AndroidPlayer\OpenJDK\bin\javac.exe"
if(!(Test-Path -LiteralPath $javac)){throw "bundled javac not found: $javac"}
$platforms=Join-Path $editorData "PlaybackEngines\AndroidPlayer\SDK\platforms"
# The compile target follows the project's own compileSdk rather than whatever
# happens to sort last, so this gate cannot drift away from what Gradle uses.
$compileSdk=(Select-String -Path "PhantomQuest/ProjectSettings/ProjectSettings.asset" -Pattern "AndroidTargetSdkVersion: (\d+)").Matches.Groups[1].Value
$androidJar=Join-Path $platforms "android-$compileSdk\android.jar"
if(!(Test-Path -LiteralPath $androidJar)){
  $newest=Get-ChildItem $platforms -Directory|Where-Object {$_.Name -match '^android-(\d+)$'}|Sort-Object {[int]($_.Name -replace 'android-','')}|Select-Object -Last 1
  if(-not $newest){throw "no Android platform jar under $platforms"}
  Write-Host ("target SDK " + $compileSdk + " not installed, compiling against " + $newest.Name)
  $androidJar=Join-Path $newest.FullName "android.jar"
}
$sources=Get-ChildItem "PhantomQuest/Assets/Plugins/Android/PhantomScenePermissions.androidlib/src" -Recurse -Filter "*.java"|Select-Object -ExpandProperty FullName
if($sources.Count -eq 0){throw "no androidlib sources found"}
# Class files are build output, not evidence: results/** holds machine-readable
# reports of executed gates, and build/ is the ignored artifact tree.
$out=[System.IO.Path]::GetFullPath("build/quest/androidlib-classes")
New-Item -ItemType Directory -Force -Path $out|Out-Null
& $javac -nowarn -Xlint:none -bootclasspath $androidJar -source 8 -target 8 -d $out @sources
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
Write-Host ("androidlib PASS: " + $sources.Count + " Java sources compiled against " + (Split-Path (Split-Path $androidJar) -Leaf))
