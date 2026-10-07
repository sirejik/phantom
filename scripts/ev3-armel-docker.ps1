param([string]$Output="build/ev3-armel",[ValidateSet("Release","Diagnostic","DeepDebug")][string]$Profile="Diagnostic")
$ErrorActionPreference="Stop"
$image="ev3dev/debian-stretch-cross@sha256:819ea7442bbe109d2b39c6c7766e7d1fe635bb98b86c4f6c3b636c0ce176a29f"
$workspace=(Resolve-Path .).Path
$out=[System.IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Force -Path $out | Out-Null
docker image inspect $image --format '{{.Id}}' | Out-Null
if($LASTEXITCODE -ne 0){throw "Pinned EV3 cross image unavailable: $image"}
$facts=docker run --rm --entrypoint sh $image -lc 'arm-linux-gnueabi-g++ --version | head -1; sha256sum /usr/bin/arm-linux-gnueabi-g++'
$commit=(git rev-parse HEAD).Trim()
    $protocolHash=(Get-Content protocol/generated/schema.sha256).Split()[0]
    $protocolSemanticsHash=(Get-Content protocol/generated/semantics.sha256).Split()[0]
    $protocolContractHash=(Get-Content protocol/generated/contract.sha256).Split()[0]
$sourceHash=(python tools/source_hash.py ev3 protocol deploy).Trim()
$toolchainLockHash=(Get-FileHash toolchains/ev3dev-stretch.lock.json -Algorithm SHA256).Hash.ToLower()
$dirty=((git status --porcelain).Count -gt 0)
$profile=$Profile
  $profileOut=[System.IO.Path]::GetFullPath((Join-Path $out $profile.ToLower()))
  if(!$profileOut.StartsWith($out.TrimEnd('\')+'\',[System.StringComparison]::OrdinalIgnoreCase)){throw "Unsafe armel output path: $profileOut"}
  if(Test-Path -LiteralPath $profileOut){Remove-Item -LiteralPath $profileOut -Recurse -Force}
  $binOut=Join-Path $profileOut bin
  New-Item -ItemType Directory -Force -Path $binOut | Out-Null
  docker run --rm --entrypoint sh --mount "type=bind,src=$workspace,dst=/workspace,readonly" --mount "type=bind,src=$binOut,dst=/out" $image /workspace/scripts/ev3-armel-build /out $profile
  if($LASTEXITCODE -ne 0){throw "EV3 armel Docker build failed: $profile"}
  $configSource=if($profile -in @("Diagnostic","DeepDebug")){"config/generated/ev3-network-only.generated.json"}else{"config/generated/ev3.generated.json"}
  $bundleSource=if($profile -in @("Diagnostic","DeepDebug")){"config/generated/commissioning_bundle-network-only.generated.json"}else{"config/generated/commissioning_bundle.generated.json"}
  Copy-Item $configSource "$profileOut/config.generated.json" -Force
  Copy-Item $bundleSource "$profileOut/commissioning-bundle.generated.json" -Force
  Copy-Item ev3/network/phantom_network.py "$binOut/phantom-network" -Force
  Copy-Item ev3/network/phantom_mdns.py "$binOut/phantom-mdns" -Force
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
    schema_version=5;build_identity_schema="PHANTOM-BUILD-V4";component="EV3";build_id=$buildId;git_commit=$commit;source_tree_hash=$sourceHash;worktree_dirty=$dirty;target="ARMv5TEJ-armel-gnueabi";build_profile=$profile
    protocol_version=1;protocol_schema_hash=$protocolHash;protocol_semantics_hash=$protocolSemanticsHash;protocol_contract_hash=$protocolContractHash;config_hash=$profileConfigHash;commissioning_bundle_hash=if($profile -in @("Diagnostic","DeepDebug")){(Get-Content config/generated/config-manifest.json -Raw|ConvertFrom-Json).artifact_hashes.'commissioning_bundle-network-only'}else{(Get-Content config/generated/config-manifest.json -Raw|ConvertFrom-Json).artifact_hashes.commissioning_bundle};qualification_eligible=($profile-ne"DeepDebug")
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
