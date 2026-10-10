param(
    [string]$Destination='results/ev3/logs',[string]$StateRoot='',
    [ValidateRange(1,10000)][int]$Lines=1000,
    [ValidateRange(1,60)][int]$TimeoutSeconds=15,[switch]$SkipAnalysis
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$directory=[IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Force -Path $directory|Out-Null
# Fixed units and bounded output; no credential files or motor commands.
$command="journalctl --no-pager -o json -n $Lines -u phantom-controller.service -u phantom-safety.service -u phantom-network.service -u phantom-mdns.service"
$result=Invoke-PhantomEv3Command $command $StateRoot $TimeoutSeconds
if($result.ExitCode-ne 0){throw 'EV3 journal collection failed'}
$path=Join-Path $directory 'journal.jsonl'
[IO.File]::WriteAllText($path,($result.Stdout-join"`n")+"`n",[Text.UTF8Encoding]::new($false))
if(!$SkipAnalysis)
{
    & python "$PSScriptRoot/../tools/analyze_logs.py" EV3 $path --out (Join-Path $directory 'analysis')
    if($LASTEXITCODE-ne 0){throw 'EV3 log analysis failed'}
}
Write-Output "EV3 logs: $path"
