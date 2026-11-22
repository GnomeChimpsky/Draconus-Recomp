# Rebuild the bundled renhdrum.dll from its pinned upstream tag, or verify the one in the tree.
#
#   tools\build-renhdrum.ps1           build from source and install into third_party\renhdrum
#   tools\build-renhdrum.ps1 -Check    verify the checked-in file against the pinned SHA-256
#
# Why this exists: the game loads renhdrum.dll at run time, and a release has to carry it. Building it
# needs a Rust toolchain that nothing else here uses, so the binary is checked in (see
# third_party\renhdrum\SOURCE.md) and this script is how to reproduce or refresh it.
param(
    [switch]$Check,
    # Where the result goes. Defaults to third_party\renhdrum beside this repository.
    [string]$Out = "",
    # Install even when the rebuild's hash differs from the pinned one. A different Rust or MSVC
    # version usually produces a different (still working) binary.
    [switch]$Force
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pinTag = "v0.5.0"
$pinCommit = "e778da6e169640e225a7f898b77cbb40af97c60f"
$pinnedHash = "827B5DB99B13339F63B7BDA08D59C3244A82D2FFCC42DCE669B49FFFE637A8C5"
$dest = if ($Out) { $Out } else { Join-Path $root "third_party\renhdrum" }
$dll = Join-Path $dest "renhdrum.dll"

function Get-Sha256([string]$path) {
    (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
}

if ($Check) {
    if (-not (Test-Path -LiteralPath $dll)) { throw "missing $dll" }
    $hash = Get-Sha256 $dll
    if ($hash -ne $pinnedHash) {
        Write-Host "renhdrum.dll does not match the pinned build"
        Write-Host ("  expected {0}" -f $pinnedHash)
        Write-Host ("  actual   {0}" -f $hash)
        exit 1
    }
    Write-Host ("renhdrum.dll matches the pinned build ({0})" -f $pinnedHash)
    exit 0
}

$cargo = Get-Command cargo -ErrorAction SilentlyContinue
if (-not $cargo) {
    throw ("cargo not found. Install Rust with the MSVC toolchain (https://rustup.rs), or keep the " +
           "bundled third_party\renhdrum\renhdrum.dll, which is what releases use.")
}

$src = Join-Path $root "work\renhdrum-src"
if (-not (Test-Path -LiteralPath (Join-Path $src "Cargo.toml"))) {
    Write-Host ("cloning RenHDrum {0}" -f $pinTag)
    New-Item -ItemType Directory -Force (Split-Path -Parent $src) | Out-Null
    & git clone --depth 1 --branch $pinTag https://github.com/trzz1214/RenHDrum $src
    if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
}
$head = (& git -C $src rev-parse HEAD).Trim()
if ($head -ne $pinCommit) {
    throw ("{0} is at {1}, expected the pinned {2}. Delete it and re-run." -f $src, $head, $pinCommit)
}

Push-Location $src
try {
    & cargo build --release --locked
    if ($LASTEXITCODE -ne 0) { throw "cargo build failed" }
} finally {
    Pop-Location
}

$built = Join-Path $src "target\release\renhdrum.dll"
if (-not (Test-Path -LiteralPath $built)) { throw "no $built after the build" }

# The published binary is statically linked against the C runtime on purpose: a machine without the
# Visual C++ redistributable would otherwise fail to load it, silently and only for haptics.
$bytes = [IO.File]::ReadAllBytes($built)
$ascii = [Text.Encoding]::ASCII.GetString($bytes)
if ($ascii.Contains("VCRUNTIME140.dll")) {
    throw ("the build depends on VCRUNTIME140.dll; build from the repository root so .cargo\config.toml " +
           "applies its +crt-static flag")
}

$hash = Get-Sha256 $built
Write-Host ("built {0}  sha256 {1}" -f $built, $hash)
if ($hash -ne $pinnedHash -and -not $Force) {
    throw ("the rebuild does not match the pinned hash `n  expected {0}`n  actual   {1}`n" +
           "A different Rust or MSVC version usually explains it. Re-run with -Force to install it, " +
           "then update SOURCE.md and the hash in this script.") -f $pinnedHash, $hash
}

New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item -LiteralPath $built -Destination $dll -Force
foreach ($file in @("LICENSE-MIT", "NOTICE")) {
    Copy-Item -LiteralPath (Join-Path $src $file) -Destination (Join-Path $dest $file) -Force
}
Write-Host ("installed {0}" -f $dll)
