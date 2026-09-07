# Single discovery point for the host tools PHANTOM builds and tests need.
#
# Absolute paths used to be repeated across five scripts, so a developer with a
# different Unity install location or WSL distribution had to edit each one and
# no script told them what was missing. Everything here honours an environment
# override first, then the declared defaults in toolchains/host-tools.json.

# Deliberately no Set-StrictMode here: this module is dot-sourced, so a strict
# mode set here would silently change the language semantics of every calling
# script rather than only this file.

function Get-PhantomRepositoryRoot
{
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-PhantomHostToolsManifest
{
    $path = Join-Path (Get-PhantomRepositoryRoot) "toolchains/host-tools.json"
    if (!(Test-Path -LiteralPath $path)) { throw "Host tool manifest is missing: $path" }
    return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}

function Get-PhantomPinnedUnityVersion
{
    $path = Join-Path (Get-PhantomRepositoryRoot) "PhantomQuest/ProjectSettings/ProjectVersion.txt"
    foreach ($line in Get-Content -LiteralPath $path)
    {
        if ($line -match '^m_EditorVersion:\s*(\S+)\s*$') { return $Matches[1] }
    }
    throw "Could not read the pinned Unity version from ProjectVersion.txt"
}

function Get-PhantomUnityRoot
{
    # The Unity editor version is pinned by the project, never by a script.
    $version = Get-PhantomPinnedUnityVersion
    $manifest = Get-PhantomHostToolsManifest
    $candidates = @()
    if ($env:PHANTOM_UNITY_ROOT) { $candidates += $env:PHANTOM_UNITY_ROOT }
    foreach ($template in $manifest.unity.search_paths)
    {
        $candidates += $template.Replace('{version}', $version)
    }
    foreach ($candidate in $candidates)
    {
        if (Test-Path -LiteralPath (Join-Path $candidate "Editor/Data")) { return $candidate }
    }
    throw ("Unity $version was not found. Set PHANTOM_UNITY_ROOT to the editor directory " +
           "(the one containing Editor\Data) or install it where toolchains/host-tools.json expects. " +
           "Searched: " + ($candidates -join "; "))
}

function Get-PhantomUnityEditorData
{
    return (Join-Path (Get-PhantomUnityRoot) "Editor\Data")
}

function Get-PhantomUnityExe
{
    $exe = Join-Path (Get-PhantomUnityRoot) "Editor\Unity.exe"
    if (!(Test-Path -LiteralPath $exe)) { throw "Unity executable not found: $exe" }
    return $exe
}

function Get-PhantomAdb
{
    if ($env:PHANTOM_ADB)
    {
        if (!(Test-Path -LiteralPath $env:PHANTOM_ADB)) { throw "PHANTOM_ADB does not exist: $($env:PHANTOM_ADB)" }
        return $env:PHANTOM_ADB
    }
    $manifest = Get-PhantomHostToolsManifest
    $candidates = @()
    foreach ($relative in $manifest.android.adb_relative_paths)
    {
        $candidates += (Join-Path (Get-PhantomUnityEditorData) $relative)
    }
    foreach ($absolute in $manifest.android.adb_search_paths) { $candidates += $absolute }
    foreach ($candidate in $candidates)
    {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    $onPath = Get-Command adb -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    throw ("adb was not found. Set PHANTOM_ADB, install the Android SDK platform-tools with Unity, " +
           "or put adb on PATH. Searched: " + ($candidates -join "; "))
}

function Get-PhantomWslDistro
{
    if ($env:PHANTOM_WSL_DISTRO) { return $env:PHANTOM_WSL_DISTRO }
    return (Get-PhantomHostToolsManifest).wsl.distribution
}

function Invoke-PhantomWsl([string]$Command)
{
    $distro = Get-PhantomWslDistro
    wsl.exe -d $distro -- bash -lc $Command
}

function Get-PhantomWslPath([string]$WindowsPath)
{
    $distro = Get-PhantomWslDistro
    $quoted = "'" + (Resolve-Path $WindowsPath).Path + "'"
    return (wsl.exe -d $distro -- wslpath -a $quoted).Trim()
}
