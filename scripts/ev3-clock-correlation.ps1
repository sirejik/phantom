param(
  [string]$DeviceHost="ev3dev.local",
  [string]$DeviceUser="robot",
  [string]$KeyPath=".ev3-ssh/id_ed25519",
  [string]$OutputPath="results/ev3/clock-correlation.json",
  [ValidateRange(1,120)][int]$MaxDeltaSeconds=15,
  [ValidateRange(1,120)][int]$MaxRoundTripSeconds=30
)
$ErrorActionPreference="Stop"
$resolvedKey=(Resolve-Path -LiteralPath $KeyPath).Path
$before=[DateTimeOffset]::UtcNow
$destination="$DeviceUser@$DeviceHost"
$raw=& ssh -i $resolvedKey -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=8 $destination "date -u +%Y-%m-%dT%H:%M:%SZ"
$sshExit=$LASTEXITCODE
$after=[DateTimeOffset]::UtcNow
if($sshExit -ne 0){throw "EV3 clock query failed with exit $sshExit"}
$device=[DateTimeOffset]::ParseExact(($raw|Select-Object -Last 1).Trim(),"yyyy-MM-ddTHH:mm:ssZ",[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::AssumeUniversal)
$roundTrip=($after-$before).TotalSeconds
$midpoint=$before.AddTicks([long](($after-$before).Ticks/2))
$delta=($device-$midpoint).TotalSeconds
$pass=($roundTrip -le $MaxRoundTripSeconds -and [Math]::Abs($delta) -le $MaxDeltaSeconds)
$report=[ordered]@{
  schema_version=1
  gate="EV3 HOST CLOCK CORRELATION"
  status=if($pass){"PASS"}else{"FAIL"}
  device_host=$DeviceHost
  host_before_utc=$before.ToString("o")
  host_after_utc=$after.ToString("o")
  device_wall_clock_utc=$device.ToUniversalTime().ToString("o")
  round_trip_seconds=[Math]::Round($roundTrip,3)
  device_delta_from_host_midpoint_seconds=[Math]::Round($delta,3)
  max_delta_seconds=$MaxDeltaSeconds
  max_round_trip_seconds=$MaxRoundTripSeconds
}
$parent=Split-Path -Parent $OutputPath
if($parent){New-Item -ItemType Directory -Force -Path $parent|Out-Null}
$report|ConvertTo-Json -Depth 4|Set-Content -LiteralPath $OutputPath -Encoding UTF8
$report|ConvertTo-Json -Compress
if(!$pass){exit 2}
