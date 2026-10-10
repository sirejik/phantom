param(
    [ValidateSet('Release','Diagnostic')][string]$Profile='Diagnostic',
    [string]$OutputRoot='build/ev3-armel',
    [string]$PackageRoot='build/ev3-packages',
    [switch]$VerifyReproducibility,
    [string]$ReproducibilityWorkspace='build/reproducibility'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/build-environment.ps1"
if($VerifyReproducibility){Invoke-PhantomBuildReproducibility EV3 $Profile $ReproducibilityWorkspace;return}
$ErrorActionPreference='Stop'
$image=Assert-PhantomEv3BuildEnvironment
foreach($check in @(@('tools/protocolgen.py','--check'),@('tools/configgen.py','--check'))){
    & python $check[0] $check[1]
    if($LASTEXITCODE-ne 0){throw "EV3 BUILD prerequisite check failed: $($check[0])"}
}
$Output=$OutputRoot
$workspace=(Resolve-Path .).Path
$out=[System.IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path $out | Out-Null
$lock=Get-PhantomEv3ToolchainLock
$commit=(git rev-parse HEAD).Trim()
    $protocolHash=(Get-Content protocol/generated/schema.sha256).Split()[0]
    $protocolSemanticsHash=(Get-Content protocol/generated/semantics.sha256).Split()[0]
    $protocolContractHash=(Get-Content protocol/generated/contract.sha256).Split()[0]
$sourceHash=(python tools/source_hash.py --component EV3).Trim()
$toolchainLockHash=(Get-FileHash (Get-PhantomEv3ToolchainLockPath) -Algorithm SHA256).Hash.ToLower()
$dirty=((git status --porcelain).Count -gt 0)
$profile=$Profile
  $profileOut=[System.IO.Path]::GetFullPath((Join-Path $out $profile.ToLower()))
  if(!$profileOut.StartsWith($out.TrimEnd('\')+'\',[System.StringComparison]::OrdinalIgnoreCase)){throw "Unsafe armel output path: $profileOut"}
  if(Test-Path -LiteralPath $profileOut){Remove-Item -LiteralPath $profileOut -Recurse -Force}
  $binOut=Join-Path $profileOut bin
  New-Item -ItemType Directory -Force -Path $binOut | Out-Null
  $command=Get-PhantomEv3BuildCommand $profile
  docker run --rm --entrypoint sh --mount "type=bind,src=$workspace,dst=/workspace,readonly" --mount "type=bind,src=$profileOut,dst=/out" $image -lc $command
  if($LASTEXITCODE -ne 0){throw "EV3 armel Docker build failed: $profile"}
  $facts=Get-Content -LiteralPath (Join-Path $profileOut 'toolchain-facts.txt')
  Remove-Item -LiteralPath (Join-Path $profileOut 'toolchain-facts.txt')
  $configSource=if($profile -in @("Diagnostic")){"config/generated/ev3-network-only.generated.json"}else{"config/generated/ev3.generated.json"}
  $bundleSource=if($profile -in @("Diagnostic")){"config/generated/commissioning_bundle-network-only.generated.json"}else{"config/generated/commissioning_bundle.generated.json"}
  Copy-Item $configSource "$profileOut/config.generated.json" -Force
  Copy-Item $bundleSource "$profileOut/commissioning-bundle.generated.json" -Force
  Copy-Item protocol/phantom_protocol.py "$binOut/phantom_protocol.py" -Force
  Copy-Item protocol/jcs.py "$binOut/jcs.py" -Force
  Copy-Item protocol/generated/ipc_layout.py "$binOut/ipc_layout.py" -Force
  Copy-Item protocol/wire_schema.yaml "$binOut/wire_schema.yaml" -Force
  Copy-Item protocol/semantics.yaml "$binOut/semantics.yaml" -Force
  Copy-Item deploy/scripts/device-integration-test.py "$binOut/phantom-device-integration-test" -Force
  Copy-Item deploy/systemd "$profileOut/systemd" -Recurse -Force
  Copy-Item deploy/tmpfiles "$profileOut/tmpfiles" -Recurse -Force
  $profileConfigHash=(Get-FileHash $configSource -Algorithm SHA256).Hash.ToLower()
  $buildId=(python tools/build_identity.py --component EV3 --profile $profile --source-tree-hash $sourceHash --protocol-contract-hash $protocolContractHash --component-config-hash $profileConfigHash --toolchain-or-package-lock-hash $toolchainLockHash).Trim()
  $manifest=[ordered]@{
    schema_version=5;build_identity_schema="PHANTOM-BUILD-V4";component="EV3";build_id=$buildId;git_commit=$commit;source_tree_hash=$sourceHash;worktree_dirty=$dirty;target=$lock.target;build_profile=$profile
    protocol_version=1;protocol_schema_hash=$protocolHash;protocol_semantics_hash=$protocolSemanticsHash;protocol_contract_hash=$protocolContractHash;config_hash=$profileConfigHash;commissioning_bundle_hash=if($profile -in @("Diagnostic")){(Get-Content config/generated/config-manifest.json -Raw|ConvertFrom-Json).artifact_hashes.'commissioning_bundle-network-only'}else{(Get-Content config/generated/config-manifest.json -Raw|ConvertFrom-Json).artifact_hashes.commissioning_bundle};qualification_eligible=$true
    cross_image=$image;toolchain_facts=($facts -join " | ")
    toolchain_or_package_lock_hash=$toolchainLockHash;source_date_epoch_or_reproducible_epoch=0
    controller_sha256=(Get-FileHash "$binOut/phantom-controller" -Algorithm SHA256).Hash.ToLower()
    safety_sha256=(Get-FileHash "$binOut/phantom-safety" -Algorithm SHA256).Hash.ToLower()
  }
  $manifest|ConvertTo-Json -Depth 4|Set-Content "$profileOut/build-manifest.json" -Encoding UTF8
  $checksumLines=Get-ChildItem $profileOut -Recurse -File|Where-Object Name -ne SHA256SUMS|ForEach-Object{"$((Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.FullName.Substring($profileOut.Length+1).Replace('\','/'))"}
  # The manifest is consumed by GNU sha256sum on ev3dev. PowerShell 5's
  # Set-Content emits CRLF, which makes the trailing CR part of each filename.
  [System.IO.File]::WriteAllText((Join-Path $profileOut "SHA256SUMS"),(($checksumLines -join "`n")+"`n"),[System.Text.Encoding]::ASCII)
Write-Output "EV3 armel artifacts: $out"

$InputRoot=$OutputRoot
$OutputRoot=$PackageRoot
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
  if($name -in @("Diagnostic") -and ($runtimeConfig.qualification_only-ne $true -or $runtimeConfig.actuator_scope_mask-ne 0 -or $runtimeConfig.safety_observation_mask-ne 0)){throw "$name package is not Stage-3 network-only"}
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
  $buildResult=[ordered]@{schema_version=1;phase='BUILD';status='PASS';component='EV3';profile=$name;qualification_eligible=$true;build_id=$manifest.build_id;artifact_path=$archivePath;artifact_sha256=$artifactHash;config_hash=$manifest.config_hash;protocol_schema_hash=$manifest.protocol_schema_hash;protocol_semantics_hash=$manifest.protocol_semantics_hash;protocol_contract_hash=$manifest.protocol_contract_hash}
  [System.IO.File]::WriteAllText("$archivePath.build-result.json",($buildResult|ConvertTo-Json -Depth 5)+"`n",[System.Text.UTF8Encoding]::new($false))
  Write-Output "$archiveName $artifactHash"
}

$manifest=Get-Content -LiteralPath (Join-Path $profileOut 'build-manifest.json') -Raw -Encoding UTF8|ConvertFrom-Json
$package=Join-Path $output "phantom-$($manifest.build_id).tar.gz"
python tools/artifact_check.py --component EV3 --profile $Profile --artifact $package --ev3-directory $profileOut
if($LASTEXITCODE-ne 0){throw "EV3 BUILD artifact validation failed: $Profile"}
