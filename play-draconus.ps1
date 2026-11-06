# Launch Draconus from the recompiled build.
#
#   .\play-draconus.ps1                       # window, interpreter path
#   .\play-draconus.ps1 --max-frames 600 ...  # extra args pass straight through
#
# The interpreter path is used because the machine-translated path still faults at
# 0x8C001006 (docs/ENGINE-CHANGES.md, "Bug report for upstream"). Remove --interpret
# once that is fixed.
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Extra)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $root "engine\build-render\games\draconus\draconus_boot.exe"
$cfg = Join-Path $root "engine\games\draconus\draconus.toml"

if (-not (Test-Path $exe)) {
    throw "recompiled build not found: $exe`nBuild it with:`n  cmake --build engine\build-render --target draconus_boot"
}
if (-not (Test-Path $cfg)) {
    throw "title config not found: $cfg"
}

# SDL3 ships beside the executable; copy it in from the local build if missing.
$sdl = Join-Path $root "work\sdl3\bin\SDL3.dll"
$dll = Join-Path (Split-Path $exe) "SDL3.dll"
if ((Test-Path $sdl) -and -not (Test-Path $dll)) {
    Copy-Item $sdl $dll
    Write-Host "copied SDL3.dll next to the executable"
}

# The game's own default: interpreter for logic, renderer for pixels.
$arguments = @("--config", $cfg, "--interpret", "--window")
if ($Extra) { $arguments += $Extra }

Write-Host ("launching " + $exe)
& $exe @arguments
exit $LASTEXITCODE
