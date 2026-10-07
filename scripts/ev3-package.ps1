param(
  [ValidateSet("Release","Diagnostic","DeepDebug")][string[]]$Profile=@("Diagnostic"),
  [string]$InputRoot="build/ev3-armel",
  [string]$OutputRoot="build/ev3-packages"
)
$ErrorActionPreference="Stop"
$image="ev3dev/debian-stretch-cross@sha256:819ea7442bbe109d2b39c6c7766e7d1fe635bb98b86c4f6c3b636c0ce176a29f"
$repo=(Resolve-Path .).Path
$input=[System.IO.Path]::GetFullPath($(if([System.IO.Path]::IsPathRooted($InputRoot)){$InputRoot}else{Join-Path $repo $InputRoot}))
$output=[System.IO.Path]::GetFullPath($(if([System.IO.Path]::IsPathRooted($OutputRoot)){$OutputRoot}else{Join-Path $repo $OutputRoot}))
New-Item -ItemType Directory -Force -Path $output|Out-Null
foreach($name in $Profile){
  $lower=$name.ToLowerInvariant()
  $source=Join-Path $input $lower
  if(!(Test-Path -LiteralPath (Join-Path $source "build-manifest.json"))){throw "Missing EV3 $name artifact: $source"}
  $manifest=Get-Content -LiteralPath (Join-Path $source "build-manifest.json") -Raw|ConvertFrom-Json
  if($manifest.build_profile-ne $name){throw "EV3 $name manifest profile mismatch"}
  if($manifest.build_id-notmatch '^[0-9a-f]{64}$'){throw "Invalid EV3 build_id: $($manifest.build_id)"}
  $runtimeConfig=Get-Content -LiteralPath (Join-Path $source "config.generated.json") -Raw|ConvertFrom-Json
  if($name -eq "Release" -and $runtimeConfig.qualification_evidence_manifest_hash -match '^0{64}$'){throw "Release package is blocked: qualification evidence is absent"}
  if($name -in @("Diagnostic","DeepDebug") -and ($runtimeConfig.qualification_only-ne $true -or $runtimeConfig.actuator_scope_mask-ne 0 -or $runtimeConfig.safety_observation_mask-ne 0)){throw "$name package is not Stage-3 network-only"}
  if($name -eq "DeepDebug" -and $manifest.qualification_eligible-ne $false){throw "DeepDebug package must be qualification-ineligible"}
  $archiveName="phantom-$($manifest.build_id).tar.gz"
  $sourceMount=(Resolve-Path -LiteralPath $source).Path
  $command=@'
set -eu
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cp -a /artifact/. "$stage/"
find "$stage" -type d -exec chmod 0755 {} +
find "$stage" -type f -exec chmod 0644 {} +
chmod 0755 "$stage/bin/phantom-controller" "$stage/bin/phantom-safety" "$stage/bin/phantom-network" "$stage/bin/phantom-mdns" "$stage/bin/phantom-device-integration-test"
cd "$stage"
sha256sum -c SHA256SUMS
# List every payload member explicitly. Archiving `.` adds a standalone root
# member, which the fail-closed on-device installer intentionally rejects.
find "$stage" -mindepth 1 -printf '%P\0' | sort -z |
  tar --null --no-recursion --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C "$stage" -T - -cf - |
  gzip -n > /packages/__ARCHIVE__
tar -tzf /packages/__ARCHIVE__ >/dev/null
'@
  $command=$command.Replace('__ARCHIVE__',$archiveName)
  docker run --rm --entrypoint sh --mount "type=bind,src=$sourceMount,dst=/artifact,readonly" --mount "type=bind,src=$output,dst=/packages" $image -lc $command
  if($LASTEXITCODE-ne 0){throw "EV3 $name package failed"}
  $archivePath=Join-Path $output $archiveName
  $artifactHash=(Get-FileHash $archivePath -Algorithm SHA256).Hash.ToLower()
  $provenance=[ordered]@{schema_version=2;component="EV3";build_id=$manifest.build_id;build_profile=$name;source_tree_hash=$manifest.source_tree_hash;artifact_sha256=$artifactHash;embedded_identity_sha256=(Get-FileHash (Join-Path $source "build-manifest.json") -Algorithm SHA256).Hash.ToLower();created_at=(Get-Date).ToUniversalTime().ToString('o')}
  $provenance|ConvertTo-Json|Set-Content "$archivePath.build-manifest.json" -Encoding UTF8
  $buildResult=[ordered]@{schema_version=1;phase='BUILD';status='PASS';component='EV3';profile=$name;qualification_eligible=($name-ne'DeepDebug');build_id=$manifest.build_id;artifact_path=$archivePath;artifact_sha256=$artifactHash;config_hash=$manifest.config_hash;protocol_schema_hash=$manifest.protocol_schema_hash;protocol_semantics_hash=$manifest.protocol_semantics_hash;protocol_contract_hash=$manifest.protocol_contract_hash}
  [System.IO.File]::WriteAllText("$archivePath.build-result.json",($buildResult|ConvertTo-Json -Depth 5)+"`n",[System.Text.UTF8Encoding]::new($false))
  Write-Output "$archiveName $artifactHash"
}
