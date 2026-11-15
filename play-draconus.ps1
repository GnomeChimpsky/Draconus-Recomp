# Launch Draconus from the recompiled build.
#
#   .\play-draconus.ps1                    # window, translated path (fastest)
#   .\play-draconus.ps1 -Scale 2           # 1280x960 window
#   .\play-draconus.ps1 -Scale 4 -Widescreen -Fullscreen   # 2560x1440 full screen
#   .\play-draconus.ps1 -Interpret         # the development interpreter, for comparison
#   .\play-draconus.ps1 -ModernControls    # left stick strafe, right stick turn, LT block, RT attack
#   .\play-draconus.ps1 -Vmu .\card.vmu    # attach a particular memory card
#   .\play-draconus.ps1 --max-frames 600   # extra args pass straight through
#
# Both paths run the game (docs/ENGINE-CHANGES.md). The translated path is the default because it
# is the faster one (1.2x real time headless, about 0.8x windowed at 1,800 frames, against the
# interpreter's 0.25x) and the two agree frame for frame (tools\parity-check.ps1).
#
# A windowed run always has a memory card: the per-user card for this title, created blank and
# formatted on the first run, so the game's save and load screens work with no setup. The
# launcher's Saves tab manages cards and can boot straight into a chosen save.
#
# PositionalBinding=$false is what makes the last line above true. Without it PowerShell binds an
# argument it does not recognise to the first declared parameter that takes one, so
# `--max-frames 600` became `-Scale` and failed to convert, and `-Scale 2 --fps` would have been
# quietly swallowed by `-Aspect`. Every setting below is therefore named only, and everything the
# script does not recognise goes to the engine as written.
[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Interpret,
    [switch]$Translated,
    [ValidateRange(1, 4)][int]$Scale = 1,
    # -Widescreen: hor+ at 16:9. The title's projection is widened and 3D scenes are presented
    # stretched, so more world is visible horizontally and nothing is distorted. Menus, the title
    # and loading cards are flat 2D screens, keep their 4:3 shape, and are pillarboxed.
    # -Aspect takes any ratio, for example 21:9.
    [switch]$Widescreen,
    [string]$Aspect = "",
    # -DisplayMode: windowed (default), borderless (desktop fullscreen at the display's own size)
    # or exclusive (a fullscreen display mode, which can change the panel's refresh timing). A
    # system that refuses exclusive falls back to borderless.
    [ValidateSet("windowed", "borderless", "exclusive")][string]$DisplayMode = "windowed",
    # -Fullscreen: fill the display at its own size instead of opening the window the scale names.
    [switch]$Fullscreen,
    # -PresentRate 120: present the display at that rate while the game logic keeps running at
    # 60 Hz. The extra presents repeat the current image unless -Interpolate asks for the geometry
    # between the two frames to be drawn instead.
    [int]$PresentRate = 0,
    # -Interpolate: with a present rate above 60, draw the frame between the two guest frames
    # instead of repeating one. The guest and the game speed are untouched; 2D screens and frames
    # whose strips changed keep the current picture.
    [switch]$Interpolate,
    # -ModernControls: left stick strafes and still moves forward/back, right stick turns, the left
    # trigger blocks and the right trigger attacks. A and X keep their own buttons too; menus use
    # the right stick or the d-pad. The launcher exposes the same option as Controls > Modern.
    [switch]$ModernControls,
    # -Vmu FILE: attach this 128 KB card image. Without it the default per-user card is used
    # (%APPDATA%\dream-recomp\saves\draconus\vmu_a1.bin), created on the first run.
    [string]$Vmu = "",
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
$ratio = if ($Aspect) { $Aspect } elseif ($Widescreen) { "16:9" } else { "" }
if ($ratio) { $arguments += @("--aspect", $ratio) }
if ($Fullscreen) { $arguments += "--fullscreen" }
if ($PresentRate -gt 0) { $arguments += @("--present-rate", "$PresentRate") }
if ($Interpolate) { $arguments += "--frame-interpolation" }
if ($DisplayMode -ne "windowed") { $arguments += @("--display", $DisplayMode) }
if ($ModernControls) { $arguments += @("--controls", "modern") }
if ($Vmu) { $arguments += @("--vmu", $Vmu) }
if ($Interpret -and -not $Translated) { $arguments += "--interpret" }
if ($Extra) { $arguments += $Extra }

Write-Host ("launching " + $exe)
if ($Interpret -and -not $Translated) {
    Write-Host "path: interpreter (the reference; the translated path is faster)"
} else {
    Write-Host "path: translated (the fast configuration)"
}
if ($ModernControls) {
    Write-Host "controls: modern (left stick strafe, right stick turn, LT block, RT attack)"
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
