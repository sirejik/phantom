param([string]$Destination="results/quest/runs",[string]$Package="dev.phantom.questprototype")
$ErrorActionPreference="Stop"
$adb="C:\Program Files\Unity\Hub\Editor\6000.3.22f1\Editor\Data\PlaybackEngines\AndroidPlayer\SDK\platform-tools\adb.exe"
if(!(Test-Path -LiteralPath $adb)){throw "Bundled adb not found: $adb"}
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$remote="/sdcard/Android/data/$Package/files/phantom-runs/."
& $adb pull $remote $Destination
if($LASTEXITCODE -ne 0){throw "adb pull failed"}
python tools/quest_validation/analyze.py $Destination
