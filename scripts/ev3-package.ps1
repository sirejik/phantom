param(
  [ValidateSet("Release","Diagnostic")][string[]]$Profile=@("Release","Diagnostic"),
  [string]$InputRoot="build/ev3-armel",
  [string]$OutputRoot="build/ev3-packages"
)
$ErrorActionPreference="Stop"
$image="ev3dev/debian-stretch-cross@sha256:819ea7442bbe109d2b39c6c7766e7d1fe635bb98b86c4f6c3b636c0ce176a29f"
$repo=(Resolve-Path .).Path
$commit=(git rev-parse HEAD).Trim()
if((git status --porcelain).Count -ne 0){throw "EV3 packages require a clean committed worktree"}
$input=[System.IO.Path]::GetFullPath((Join-Path $repo $InputRoot))
$output=[System.IO.Path]::GetFullPath((Join-Path $repo $OutputRoot))
New-Item -ItemType Directory -Force -Path $output|Out-Null
foreach($name in $Profile){
  $lower=$name.ToLowerInvariant()
  $source=Join-Path $input $lower
  if(!(Test-Path -LiteralPath (Join-Path $source "build-manifest.json"))){throw "Missing EV3 $name artifact: $source"}
  $manifest=Get-Content -LiteralPath (Join-Path $source "build-manifest.json") -Raw|ConvertFrom-Json
  if($manifest.git_commit-ne $commit -or $manifest.worktree_dirty-ne $false -or $manifest.build_profile-ne $name){throw "EV3 $name manifest is not a clean artifact for $commit"}
  if($manifest.build_id-notmatch '^[A-Za-z0-9._-]+$'){throw "Unsafe EV3 build_id: $($manifest.build_id)"}
  $archiveName="phantom-$($manifest.build_id).tar.gz"
  $sourceMount=(Resolve-Path -LiteralPath $source).Path
  $command=@'
set -eu
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cp -a /artifact/. "$stage/"
find "$stage" -type d -exec chmod 0755 {} +
find "$stage" -type f -exec chmod 0644 {} +
chmod 0755 "$stage/bin/phantom-controller" "$stage/bin/phantom-safety" "$stage/bin/phantom-network" "$stage/bin/phantom-mdns" "$stage/bin/phantom-device-auto" "$stage/bin/phantom-wifi-autoconnect"
cd "$stage"
sha256sum -c SHA256SUMS
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -cf - . | gzip -n > /packages/__ARCHIVE__
tar -tzf /packages/__ARCHIVE__ >/dev/null
'@
  $command=$command.Replace('__ARCHIVE__',$archiveName)
  docker run --rm --entrypoint sh --mount "type=bind,src=$sourceMount,dst=/artifact,readonly" --mount "type=bind,src=$output,dst=/packages" $image -lc $command
  if($LASTEXITCODE-ne 0){throw "EV3 $name package failed"}
  Write-Output "$archiveName $((Get-FileHash (Join-Path $output $archiveName) -Algorithm SHA256).Hash.ToLower())"
}
