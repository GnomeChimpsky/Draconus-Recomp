# M3 gate checks that can run without Flycast:
#
#   1. determinism   two 600-frame headless runs produce byte-identical write-hash files
#   2. capture replay an F11 capture bundle draws again through dream_render_view
#
# The Flycast first-frame comparison is the third M3 clause and is still manual:
# docs/14-M3-M6-FLYCAST-REFERENCE.md.
#
#   tools\m3-check.ps1            # both checks
#   tools\m3-check.ps1 -SkipCapture
param(
    [switch]$SkipCapture
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$exe = Join-Path $root "engine\build-render\games\draconus\draconus_boot.exe"
$view = Join-Path $root "engine\build-render\render\dream_render_view.exe"
$cfg = Join-Path $root "engine\games\draconus\draconus.toml"
$work = Join-Path $root "work\m3"
New-Item -ItemType Directory -Force $work | Out-Null

$failed = 0
function Report([string]$name, [bool]$ok, [string]$detail) {
    $tag = if ($ok) { "ok  " } else { "FAIL" }
    Write-Host ("{0,-10} {1}   {2}" -f $name, $tag, $detail)
    if (-not $ok) { $script:failed++ }
}

# --- determinism -----------------------------------------------------------------------------
Push-Location $work
try {
    foreach ($i in 1, 2) {
        & $exe --config $cfg --max-frames 600 --rtc-seed 1000000 --no-audio `
               --write-hash (Join-Path $work "det_$i.txt") *> (Join-Path $work "det_$i.log")
    }
} finally {
    Pop-Location
}
$h1 = (Get-FileHash (Join-Path $work "det_1.txt") -Algorithm SHA256).Hash
$h2 = (Get-FileHash (Join-Path $work "det_2.txt") -Algorithm SHA256).Hash
$lines = (Get-Content (Join-Path $work "det_1.txt") | Measure-Object -Line).Lines
Report "determinism" ($h1 -eq $h2 -and $lines -ge 600) "$lines frames, $($h1.Substring(0,16))..."

# --- capture replay --------------------------------------------------------------------------
if (-not $SkipCapture) {
    $cap = Join-Path $work "capture"
    New-Item -ItemType Directory -Force $cap | Out-Null
    Get-ChildItem $cap -Filter 'capture-*' -ErrorAction SilentlyContinue | Remove-Item -Force
    Push-Location $cap
    try {
        & $exe --config $cfg --window --max-frames 420 --rtc-seed 1000000 --capture-at 320 `
               *> (Join-Path $cap "run.log")
    } finally {
        Pop-Location
    }
    $ta = Get-ChildItem $cap -Filter 'capture-*.ta' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $ta) {
        Report "capture" $false "no capture bundle was written (was the frame reached?)"
    } else {
        $base = [IO.Path]::GetFileNameWithoutExtension($ta.Name)
        Push-Location $cap
        try {
            & $view $ta.Name --vram "$base.vram" --screenshot replay.ppm `
                   *> (Join-Path $cap "replay.log")
        } finally {
            Pop-Location
        }
        $shot = Join-Path $cap "replay.ppm"
        $drew = Select-String -Path (Join-Path $cap "replay.log") -Pattern 'drew \d+ polygons' -Quiet
        $ok = (Test-Path $shot) -and $drew -and ((Get-Item $shot).Length -gt 10000)
        Report "capture" $ok "replayed $(Split-Path -Leaf $ta.Name) -> replay.ppm"
    }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "M3 CHECKS OK (Flycast first-frame comparison is still manual)"
    exit 0
}
Write-Host "M3 CHECKS FAILED: $failed"
exit 1
