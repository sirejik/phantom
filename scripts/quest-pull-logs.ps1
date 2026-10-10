param(
    [string]$Destination='results/quest/runs',
    [string]$Package='dev.phantom.questprototype',
    [string]$StateRoot='',
    [ValidateRange(1,300)][int]$TimeoutSeconds=60
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/../tools/toolchain.ps1"
. "$PSScriptRoot/pair-state.ps1"
$adb=Get-PhantomAdb
$serial=Get-PhantomQuestDevice $adb $StateRoot
$destinationPath=[IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $destinationPath|Out-Null
$remote="/sdcard/Android/data/$Package/files/phantom-runs/."
Invoke-PhantomAdb $adb $serial @('pull',$remote,$destinationPath) $TimeoutSeconds|Out-Host
& python "$PSScriptRoot/../tools/quest_validation/analyze.py" $destinationPath
if($LASTEXITCODE-ne 0){throw 'Quest log analysis failed'}
