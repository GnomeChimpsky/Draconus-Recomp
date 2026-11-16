# Build the frozen launcher that ships with a release.
#
#   .\tools\build-launcher.ps1
#   .\tools\build-launcher.ps1 -Dist D:\out -Clean
#
# It pins Python 3.11 and PyInstaller 6.22.3, keeps its virtual environment and intermediate files
# under work\launcher-build\, and writes an onedir build to work\launcher-dist\DraconusLauncher\.
# onedir, not onefile: onefile re-extracts ~50 MB to %TEMP% on every launch and is the variant
# antivirus dislikes most.
#
# The launcher finds the game beside itself or one folder up (launcher.py, _game_dir), so packaging
# may keep it beside DraconusRecomp.exe and draconus.toml or in a Launcher\ subfolder. PyInstaller's
# output is not bit-identical; the pinned versions and this command are what make it repeatable.
param(
    [string]$Dist = "",
    [switch]$Clean,
    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pyInstallerVersion = "6.22.3"
# hooks-contrib decides which DLLs and data files are collected, so a new release changes the build
# without touching the launcher. Pin it with PyInstaller or "reproducible" is only a wish.
$hooksVersion = "2026.10"

# Python 3.11: the version this build was made with. PyInstaller supports it without the lag and
# rough edges of the newest interpreter.
$python = $null
$pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.11 -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = "py"; $pyArgs = @("-3.11") }
}
if (-not $python) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python 3.11 is required (python.org, 64-bit, with Tcl/Tk)"
    }
    $python = "python"
}
$version = & $python @pyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ($version -ne "3.11") {
    throw "Python 3.11 is required; $python reports $version"
}

$venv = Join-Path $root "work\launcher-build\venv"
if ($Clean -and (Test-Path $venv)) { Remove-Item $venv -Recurse -Force }
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Write-Host "creating $venv"
    & $python @pyArgs -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "could not create the virtual environment" }
}
$vpy = Join-Path $venv "Scripts\python.exe"

if (-not $NoInstall) {
    & $vpy -m pip install --disable-pip-version-check --quiet `
        "pyinstaller==$pyInstallerVersion" "pyinstaller-hooks-contrib==$hooksVersion"
    if ($LASTEXITCODE -ne 0) { throw "could not install PyInstaller $pyInstallerVersion" }
}
$installed = & $vpy -m PyInstaller --version
Write-Host "PyInstaller $installed (pinned $pyInstallerVersion)"

$distDir = if ($Dist) { $Dist } else { Join-Path $root "work\launcher-dist" }
$workDir = Join-Path $root "work\launcher-build\pyinstaller"
$specDir = Join-Path $root "work\launcher-build"
$emblem = Join-Path $root "tools\launcher-emblem.png"
$discTool = Join-Path $root "tools\draconus-disc"
$launcher = Join-Path $root "tools\launcher.py"
foreach ($needed in @($emblem, $launcher, $discTool)) {
    if (-not (Test-Path $needed)) { throw "missing $needed" }
}
New-Item -ItemType Directory -Force $distDir, $workDir, $specDir | Out-Null

Write-Host "freezing $launcher"
& $vpy -m PyInstaller --noconfirm --clean --windowed --onedir --name DraconusLauncher `
    --distpath $distDir --workpath $workDir --specpath $specDir `
    --paths (Join-Path $root "tools") --paths $discTool `
    --collect-submodules dracdisc --hidden-import vmu --hidden-import dracdisc.cli `
    --add-data "$emblem;." $launcher
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$out = Join-Path $distDir "DraconusLauncher"
$sum = Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum
Write-Host ("built: {0} ({1:N1} MB, {2} files)" -f $out, ($sum.Sum / 1MB), $sum.Count)
Write-Host "run:   $(Join-Path $out 'DraconusLauncher.exe')"
