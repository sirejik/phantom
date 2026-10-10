<# Stable ExecutionPolicy-independent entry point. Dispatches exactly one requested phase. #>
param(
    [Parameter(Mandatory=$true)][ValidateSet('TEST','BUILD','PROVISION','TRANSFER','INSTALL','START','DEBUG','DEVICE')][string]$Phase,
    [Parameter(Mandatory=$true)][ValidateSet('EV3','QUEST','PAIR')][string]$Component,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$PhaseArguments
)
$ErrorActionPreference='Stop'
$key="$($Phase.ToUpperInvariant()):$($Component.ToUpperInvariant())"
$script=switch($key)
{
    'TEST:EV3' {'ev3-test.ps1'}
    'TEST:QUEST' {'quest-test.ps1'}
    'BUILD:EV3' {'ev3-build.ps1'}
    'BUILD:QUEST' {'quest-build.ps1'}
    'PROVISION:PAIR' {'provision-fixed-pair.ps1'}
    'TRANSFER:EV3' {'ev3-transfer.ps1'}
    'INSTALL:EV3' {'ev3-install.ps1'}
    'INSTALL:QUEST' {'quest-install.ps1'}
    'START:EV3' {'ev3-start.ps1'}
    'START:QUEST' {'quest-start.ps1'}
    'DEBUG:EV3' {'ev3-start.ps1';$PhaseArguments=@('-CaptureDebug')+$PhaseArguments}
    'DEBUG:QUEST' {'quest-start.ps1';$PhaseArguments=@('-CaptureDebug')+$PhaseArguments}
    'DEVICE:EV3' {'ev3-device-integration-test.ps1'}
    'DEVICE:QUEST' {'quest-device-integration-test.ps1'}
    default {throw "Lifecycle phase is not implemented for component: $key"}
}
$powershell=Join-Path $PSHOME 'powershell.exe'
& $powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot $script) @PhaseArguments
exit $LASTEXITCODE
