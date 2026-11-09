# Launch Draconus from the recompiled build.
#
#   .\play-draconus.ps1                    # window, interpreter path (faster today)
#   .\play-draconus.ps1 -Scale 2           # 1280x960 window
#   .\play-draconus.ps1 -Translated        # machine-translated path (correct, slower today)
#   .\play-draconus.ps1 --max-frames 600   # extra args pass straight through
#
# Both paths run the game (docs/ENGINE-CHANGES.md, patch 007). The interpreter is the default
# because it is about 0.25x real time against the translated path's 0.15x: most calls still fall
# through to it, and the translated build pays an interpreter entry per call. Closing that gap is
# a translation-coverage task.
param(
    [switch]$Translated,
    [ValidateRange(1, 4)][int]$Scale = 1,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Extra
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $root "engine\build-render\games\draconus\draconus_boot.exe"
$cfg = Join-Path $root "engine\games\draconus\draconus.toml"

if (-not (Test-Path $exe)) {
    throw "recompiled build not found: $exe`nBuild it with:`n  cmake --build engine\build-render --target draconus_boot"
}
if (-not (Test-Path $cfg)) {
    throw "title config not found: $cfg`nSet it up with:`n  .\setup.ps1"
}

# Fail early and clearly if the disc is missing or the dump was never imported.
$imageLine = Select-String -LiteralPath $cfg -Pattern '^\s*image\s*=\s*"(.*)"' | Select-Object -First 1
if (-not $imageLine) { throw "no image line in $cfg" }
$image = $imageLine.Matches[0].Groups[1].Value
if ($image -like "CHANGE-ME*") {
    throw "no disc configured`nImport one with:`n  tools\import-disc.bat `"D:\path\to\draconus.gdi`""
}
if (-not (Test-Path -LiteralPath $image)) {
    throw "the configured dump is missing:`n  $image`nRe-import it with:`n  tools\import-disc.bat `"D:\path\to\draconus.gdi`""
}

# SDL3 ships beside the executable; copy it in from the local build if missing.
$sdl = Join-Path $root "work\sdl3\bin\SDL3.dll"
$dll = Join-Path (Split-Path $exe) "SDL3.dll"
if ((Test-Path $sdl) -and -not (Test-Path $dll)) {
    Copy-Item $sdl $dll
    Write-Host "copied SDL3.dll next to the executable"
}

$arguments = @("--config", $cfg, "--window")
if ($Scale -ne 1) { $arguments += @("--scale", "$Scale") }
if (-not $Translated) { $arguments += "--interpret" }
if ($Extra) { $arguments += $Extra }

Write-Host ("launching " + $exe)
if (-not $Translated) {
    Write-Host "path: interpreter (faster today)"
} else {
    Write-Host "path: translated (correct; still slower until more code is translated)"
}

& $exe @arguments
$code = $LASTEXITCODE

# Any non-zero exit is a real failure now: the translated path no longer stops at frame 54.
if ($code -ne 0) {
    Write-Host ""
    Write-Host "the build exited with code $code"
    Write-Host "diagnostics and history: docs\ENGINE-CHANGES.md"
}
exit $code
