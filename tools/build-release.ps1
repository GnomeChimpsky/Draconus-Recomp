# Build the public release layout that players download.
#
#   tools\build-release.ps1                    # work\release
#   tools\build-release.ps1 -Out D:\out        # elsewhere
#   tools\build-release.ps1 -SkipLauncher      # assemble everything but the frozen launcher
#
# The release is deliberately a small, explicit set of files: the game executable, the frozen
# launcher, the title TOML, SDL3, the Visual C++ runtime DLLs, and the legal/notice files. The
# launcher and the _internal folder it needs sit at the root, so the player double-clicks
# DraconusLauncher.exe rather than looking inside a folder. It
# never copies engine/, extracted game files, dumps, saves, screenshots or captures: the runtime
# reads the boot program from the player's own disc (patches/0005), so a release must not contain
# an extracted 1ST_READ.BIN.
#
# The Visual C++ runtime is copied from the installed Visual Studio redistributable because the
# game is linked against the dynamic CRT and a clean Windows install does not necessarily have it.
param(
    [string]$Out = "",
    [string]$BuildDir = "",
    [switch]$SkipLauncher,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $BuildDir) { $BuildDir = Join-Path $root "engine\build-render" }
if (-not $Out) { $Out = Join-Path $root "work\release" }
$Out = [IO.Path]::GetFullPath($Out)

function Find-VisualStudio {
    $programFilesX86 = ${env:ProgramFiles(x86)}
    if (-not $programFilesX86) { $programFilesX86 = "C:\Program Files (x86)" }
    $vswhere = Join-Path $programFilesX86 "Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path -LiteralPath $vswhere) {
        $found = (& $vswhere -latest -products * `
                  -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
                  -property installationPath 2>$null | Select-Object -First 1)
        if ($found) { return $found.Trim() }
    }
    foreach ($candidate in @(
        "C:\Program Files\Microsoft Visual Studio\2022\Community",
        "C:\Program Files\Microsoft Visual Studio\2022\Professional",
        "C:\Program Files\Microsoft Visual Studio\2022\Enterprise",
        "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools")) {
        if (Test-Path -LiteralPath (Join-Path $candidate "VC\Auxiliary\Build\vcvars64.bat")) {
            return $candidate
        }
    }
    throw "Visual Studio 2022 C++ build tools not found; the Visual C++ runtime cannot be collected."
}

function Find-CrtDir {
    $vs = Find-VisualStudio
    $redist = Join-Path $vs "VC\Redist\MSVC"
    if (-not (Test-Path -LiteralPath $redist)) {
        throw "Visual C++ redistributable not found under $redist"
    }
    foreach ($version in (Get-ChildItem -LiteralPath $redist -Directory | Sort-Object Name -Descending)) {
        $crt = Join-Path $version.FullName "x64\Microsoft.VC143.CRT"
        if (Test-Path -LiteralPath $crt) { return $crt }
        $crt = Get-ChildItem -LiteralPath $version.FullName -Recurse -Directory `
                   -Filter "Microsoft.VC*.CRT" -ErrorAction SilentlyContinue |
               Where-Object { $_.FullName -match '\\x64\\' } |
               Select-Object -First 1
        if ($crt) { return $crt.FullName }
    }
    throw "No x64 Microsoft.VC*.CRT folder under $redist; install the Visual C++ redistributable."
}

$gameExe = Join-Path $BuildDir "games\draconus\draconus_boot.exe"
$sdl = Join-Path $BuildDir "games\draconus\SDL3.dll"
$toml = Join-Path $root "game\draconus\draconus.toml"
foreach ($needed in @($gameExe, $sdl, $toml)) {
    if (-not (Test-Path -LiteralPath $needed)) {
        throw "missing $needed (build the engine first, and make sure SDL3.dll is beside it)"
    }
}

if (Test-Path -LiteralPath $Out) {
    if (-not $Force) {
        throw "output already exists: $Out (pass -Force to replace it)"
    }
    Remove-Item -LiteralPath $Out -Recurse -Force
}
New-Item -ItemType Directory -Force $Out | Out-Null

Copy-Item -LiteralPath $gameExe -Destination (Join-Path $Out "DraconusRecomp.exe")
Copy-Item -LiteralPath $sdl -Destination (Join-Path $Out "SDL3.dll")

# The shipped TOML is a template: a release must not carry the builder's own disc path.
$text = Get-Content -LiteralPath $toml -Raw
$text = [regex]::Replace($text, '(?m)^[ \t]*image[ \t]*=.*$',
                         'image = "CHANGE-ME: path to your own .gdi (or .chd) dump"')
if ($text -notmatch '(?m)^[ \t]*boot_lba[ \t]*=' -or
    $text -notmatch '(?m)^[ \t]*boot_size[ \t]*=') {
    throw "$toml has no boot_lba/boot_size; the release needs the boot-from-disc fields"
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Join-Path $Out "draconus.toml"), $text, $utf8)

# Dynamic CRT: a clean Windows install may not have these, and the launcher's _internal folder is
# not on the game's DLL search path.
$crt = Find-CrtDir
foreach ($dll in @("MSVCP140.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll")) {
    $source = Join-Path $crt $dll
    if (-not (Test-Path -LiteralPath $source)) { throw "missing $dll in $crt" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $Out $dll)
}

foreach ($file in @("LICENSE", "README.md", "RELEASE-NOTES.md", "THIRD-PARTY-NOTICES.md",
                    "Draconus Recomped Emblem light.png")) {
    $source = Join-Path $root $file
    if (-not (Test-Path -LiteralPath $source)) { throw "missing release file: $source" }
    Copy-Item -LiteralPath $source -Destination (Join-Path $Out $file)
}
Copy-Item -LiteralPath (Join-Path $root "docs\LEGAL.md") -Destination (Join-Path $Out "LEGAL.md")
# The README links docs/LEGAL.md; keep that path valid inside the bundle too.
$docs = Join-Path $Out "docs"
New-Item -ItemType Directory -Force $docs | Out-Null
Copy-Item -LiteralPath (Join-Path $root "docs\LEGAL.md") -Destination (Join-Path $docs "LEGAL.md")

if (-not $SkipLauncher) {
    $stage = Join-Path $Out ".launcher-stage"
    & (Join-Path $root "tools\build-launcher.ps1") -Dist $stage
    $built = Join-Path $stage "DraconusLauncher"
    $launcher = Join-Path $built "DraconusLauncher.exe"
    if (-not (Test-Path -LiteralPath $launcher)) {
        throw "the frozen launcher was not produced at $launcher"
    }
    # Flatten the onedir build: the player should not have to enter a folder, and the launcher
    # finds everything it needs in the _internal folder beside it.
    Move-Item -LiteralPath $launcher -Destination (Join-Path $Out "DraconusLauncher.exe")
    Move-Item -LiteralPath (Join-Path $built "_internal") -Destination (Join-Path $Out "_internal")
    Remove-Item -LiteralPath $stage -Recurse -Force
}

# A small, reproducible record of what was assembled.
$commit = "unknown"
if (Get-Command git -ErrorAction SilentlyContinue) {
    $line = (& git -C $root rev-parse --short HEAD 2>$null | Select-Object -First 1)
    if ($line) { $commit = $line.Trim() }
    $dirty = (& git -C $root status --porcelain 2>$null | Select-Object -First 1)
    if ($dirty) { $commit += "-dirty" }
}
$info = @(
    "Draconus-Recomp release",
    "commit: $commit",
    "built:  $(Get-Date -Format o)",
    "repo:   https://github.com/GnomeChimpsky/Draconus-Recomp",
    "disc:   user supplies their own GDI or CHD",
    "",
    "Run DraconusLauncher.exe, pick your disc, press Check disc, then Play.",
    "No disc image, extracted game file, save or screenshot is included."
) -join "`r`n"
[System.IO.File]::WriteAllText((Join-Path $Out "BUILD-INFO.txt"), $info + "`r`n", $utf8)

# Refuse the mistake this script exists to prevent: a game-data file in the release tree.
$forbidden = @(Get-ChildItem -LiteralPath $Out -Recurse -File | Where-Object {
    $_.Extension -in @(".gdi", ".chd", ".bin", ".raw", ".iso", ".cdi", ".ppm", ".vmu", ".sav") -or
    $_.Name -eq "1ST_READ.BIN"
})
if ($forbidden.Count -gt 0) {
    $list = ($forbidden | ForEach-Object { "  " + $_.FullName }) -join "`n"
    throw "the release tree contains game data or an extracted file:`n$list"
}
if (Test-Path -LiteralPath (Join-Path $Out "extracted")) {
    throw "the release tree contains an extracted/ folder; the runtime must read the player's disc"
}

$sum = Get-ChildItem -LiteralPath $Out -Recurse -File | Measure-Object Length -Sum
Write-Host ("release: {0}" -f $Out)
Write-Host ("         {0:N1} MB, {1} files, commit {2}" -f ($sum.Sum / 1MB), $sum.Count, $commit)
if ($SkipLauncher) {
    Write-Host ("run:     {0}" -f (Join-Path $Out "DraconusRecomp.exe"))
} else {
    Write-Host ("run:     {0}" -f (Join-Path $Out "DraconusLauncher.exe"))
}
