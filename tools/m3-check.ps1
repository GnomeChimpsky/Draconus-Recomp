# M3 gate: the three clauses of "first frame".
#
#   1. determinism   two 600-frame headless runs produce byte-identical write-hash files
#   2. capture       an F11-style capture bundle draws again through dream_render_view
#   3. first frame   our first non-blank frame matches Flycast's first non-blank game
#                    frame at or below MAE 16, the metric the M5 check uses
#
# Clause 3 needs Flycast and a window. Our engine boots 1ST_READ.BIN directly, so its
# first picture is the game's first render; Flycast plays the boot ROM's Sega licence
# screen first, so tools\m3_first_frame.py finds the game's first picture after it and
# compares that. Put flycast.exe under tools\flycast\, set FLYCAST_EXE, or pass -Flycast.
#
#   tools\m3-check.ps1                  # all three clauses
#   tools\m3-check.ps1 -SkipCapture     # determinism + first frame
#   tools\m3-check.ps1 -SkipFlycast     # determinism + capture replay
#   tools\m3-check.ps1 -Threshold 12    # tighter first-frame MAE
#
# Requires: engine\build-render built, the owner's disc configured, Python with Pillow
# and numpy (for tools\vmu.py and the first-frame comparison), and Flycast unless
# -SkipFlycast. Everything is written under work\m3.
param(
    [string]$Flycast = "",
    [string]$Disc = "",
    [switch]$SkipCapture,
    [switch]$SkipFlycast,
    [int]$Frames = 600,
    [double]$Threshold = 16.0
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
# Native tools write progress to stderr (the display notice, for one), and a windowed
# run must not turn that into a terminating error: $ErrorActionPreference = "Stop"
# plus "*>" does exactly that in Windows PowerShell. Run them with the preference
# relaxed and decide on the exit code instead.
function Invoke-Native {
    param([string]$FilePath, [string[]]$Arguments, [string]$Log)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $FilePath @Arguments *> $Log
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

foreach ($p in @($exe, $view, $cfg)) {
    if (-not (Test-Path $p)) {
        throw "missing: $p (run .\setup.ps1, which builds draconus_boot and dream_render_view)"
    }
}

# A blank card on every windowed run, so the run's state does not depend on whatever
# is in the per-user memory card. Headless determinism runs stay card-less.
$blank = Join-Path $work "blank.vmu"
$code = Invoke-Native python @((Join-Path $root "tools\vmu.py"), "--new", $blank) `
                            (Join-Path $work "vmu.log")
if ($code -ne 0 -or -not (Test-Path $blank)) { throw "could not create a blank VMU" }

# --- determinism -----------------------------------------------------------------------------
Push-Location $work
try {
    foreach ($i in 1, 2) {
        $log = Join-Path $work "det_$i.log"
        $hash = Join-Path $work "det_$i.txt"
        $code = Invoke-Native $exe @("--config", $cfg, "--max-frames", "$Frames",
                                     "--rtc-seed", "1000000", "--no-audio",
                                     "--write-hash", $hash) $log
        if ($code -ne 0) { throw "determinism run $i exited with $code (see $log)" }
    }
} finally {
    Pop-Location
}
$det1 = Join-Path $work "det_1.txt"
$det2 = Join-Path $work "det_2.txt"
if (-not (Test-Path $det1) -or -not (Test-Path $det2)) {
    throw "the determinism runs wrote no write-hash file"
}
$h1 = (Get-FileHash $det1 -Algorithm SHA256).Hash
$h2 = (Get-FileHash $det2 -Algorithm SHA256).Hash
$lines = (Get-Content $det1 | Measure-Object -Line).Lines
Report "determinism" ($h1 -eq $h2 -and $lines -ge $Frames) "$lines frames, $($h1.Substring(0,16))..."

# --- capture replay --------------------------------------------------------------------------
if (-not $SkipCapture) {
    $cap = Join-Path $work "capture"
    New-Item -ItemType Directory -Force $cap | Out-Null
    # A failed run must not leave the previous run's replay looking current.
    Get-ChildItem $cap -Filter 'capture-*' -ErrorAction SilentlyContinue | Remove-Item -Force
    Remove-Item (Join-Path $cap "replay.ppm"), (Join-Path $cap "replay.log") `
        -Force -ErrorAction SilentlyContinue
    $card = Join-Path $cap "capture.vmu"
    Copy-Item $blank $card -Force
    Push-Location $cap
    try {
        # --capture-at counts *presented* pictures, and the title/intro renders fewer
        # pictures than guest frames; 600 frames leaves room for presented 320 (about
        # guest 420 here), so the checkpoint is reached on any display.
        $code = Invoke-Native $exe @("--config", $cfg, "--window", "--vmu", $card,
                                     "--max-frames", "600", "--rtc-seed", "1000000",
                                     "--capture-at", "320") (Join-Path $cap "run.log")
        if ($code -ne 0) { throw "capture run exited with $code (see run.log)" }
    } finally {
        Pop-Location
    }
    $ta = Get-ChildItem $cap -Filter 'capture-*.ta' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $ta) {
        Report "capture" $false "no capture bundle was written (was presented 320 reached?)"
    } else {
        $base = [IO.Path]::GetFileNameWithoutExtension($ta.Name)
        Push-Location $cap
        try {
            $code = Invoke-Native $view @($ta.Name, "--vram", "$base.vram",
                                          "--screenshot", "replay.ppm") `
                                       (Join-Path $cap "replay.log")
        } finally {
            Pop-Location
        }
        $shot = Join-Path $cap "replay.ppm"
        $drew = Select-String -Path (Join-Path $cap "replay.log") -Pattern 'drew \d+ polygons' -Quiet
        $ok = ($code -eq 0) -and (Test-Path $shot) -and $drew -and ((Get-Item $shot).Length -gt 10000)
        Report "capture" $ok "replayed $(Split-Path -Leaf $ta.Name) -> replay.ppm"
    }
}

# --- first non-blank frame vs Flycast --------------------------------------------------------
if (-not $SkipFlycast) {
    if (-not $Flycast) {
        $candidates = @($env:FLYCAST_EXE,
                        (Join-Path $root "tools\flycast\flycast.exe"),
                        (Get-Command flycast.exe -ErrorAction SilentlyContinue).Source) |
                      Where-Object { $_ -and (Test-Path -LiteralPath $_) }
        if (@($candidates).Count -eq 0) {
            throw "Flycast not found; pass -Flycast PATH, set FLYCAST_EXE, or use -SkipFlycast"
        }
        $Flycast = @($candidates)[0]
    }
    if (-not (Test-Path -LiteralPath $Flycast)) { throw "Flycast not found: $Flycast" }
    if (-not $Disc) {
        $line = Select-String -LiteralPath $cfg -Pattern '^\s*image\s*=\s*"(.*)"' | Select-Object -First 1
        if (-not $line) { throw "no disc configured in $cfg" }
        $Disc = $line.Matches[0].Groups[1].Value
    }
    if (-not (Test-Path -LiteralPath $Disc)) { throw "disc image missing: $Disc" }

    $first = Join-Path $work "first"
    New-Item -ItemType Directory -Force $first | Out-Null
    $measure = Join-Path $first "measure.vmu"
    $dump = Join-Path $first "dump.vmu"
    Copy-Item $blank $measure -Force
    Copy-Item $blank $dump -Force

    # What our engine's first non-blank frame is: the game's first render. The window
    # frame callback reports the presented and guest frames and the time since start.
    $measureLog = Join-Path $first "measure.log"
    $env:DREAM_FIRST_FRAME = "1"
    try {
        $code = Invoke-Native $exe @("--config", $cfg, "--window", "--vmu", $measure,
                                     "--max-frames", "300", "--rtc-seed", "1000000",
                                     "--no-audio") $measureLog
    } finally {
        Remove-Item Env:DREAM_FIRST_FRAME -ErrorAction SilentlyContinue
    }
    if ($code -ne 0) { throw "first-frame run exited with $code (see $measureLog)" }
    $match = Select-String -Path $measureLog -Pattern 'first non-blank: presented \d+ guest (\d+)'
    if (-not $match) {
        throw "no 'first non-blank' line (needs a window/GPU; see $measureLog, or -SkipFlycast)"
    }
    $guest = [int]$match.Matches[0].Groups[1].Value

    # Render that guest frame through the render library at 960x720, the size M5's
    # Flycast captures use, so the two pictures are directly comparable.
    $ta = Join-Path $first "first.ta"
    $vram = Join-Path $first "first.vram"
    $ppm = Join-Path $first "first.ppm"
    $png = Join-Path $first "our-first.png"
    Remove-Item $ta, $vram, $ppm, $png -Force -ErrorAction SilentlyContinue
    $dumpLog = Join-Path $first "dump.log"
    $code = Invoke-Native $exe @("--config", $cfg, "--vmu", $dump,
                                 "--max-frames", "$($guest + 60)", "--rtc-seed", "1000000",
                                 "--dump-ta", $ta, "--dump-ta-at-frame", "$guest",
                                 "--dump-vram", $vram) $dumpLog
    if ($code -ne 0 -or -not (Test-Path $ta)) {
        throw "could not dump the display list at guest frame $guest (see $dumpLog)"
    }
    $viewLog = Join-Path $first "view.log"
    $code = Invoke-Native $view @($ta, "--vram", $vram, "--screenshot", $ppm) $viewLog
    if ($code -ne 0 -or -not (Test-Path $ppm)) {
        throw "could not render the first frame (see $viewLog)"
    }
    $code = Invoke-Native python @("-c",
        "from PIL import Image; Image.open(r'$ppm').save(r'$png')") (Join-Path $first "png.log")
    if ($code -ne 0 -or -not (Test-Path $png)) { throw "could not convert $ppm" }

    $compareLog = Join-Path $first "compare.log"
    $code = Invoke-Native python @((Join-Path $root "tools\m3_first_frame.py"),
                                   "--flycast", $Flycast, "--disc", $Disc,
                                   "--our", $png, "--frame", "$guest",
                                   "--outdir", $first,
                                   "--markerdir", (Join-Path $first "markers"),
                                   "--threshold", "$Threshold") $compareLog
    Get-Content $compareLog -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    $text = Get-Content $compareLog -Raw -ErrorAction SilentlyContinue
    $flyFrame = if ($text -match 'first game picture at frame (\d+)') { $Matches[1] } else { "?" }
    $mae = if ($text -match 'MAE ([\d.]+)') { $Matches[1] } else { "?" }
    Report "first frame" ($code -eq 0) "ours guest $guest, Flycast $flyFrame, MAE $mae (limit $Threshold)"
} else {
    Write-Host ("{0,-10} {1}   {2}" -f "first frame", "skip", "-SkipFlycast")
}

Write-Host ""
if ($failed -eq 0) {
    $done = @("determinism")
    if (-not $SkipCapture) { $done += "capture replay" }
    if (-not $SkipFlycast) { $done += "first non-blank within Flycast tolerance" }
    Write-Host ("M3 CHECKS OK ({0})" -f ($done -join ", "))
    exit 0
}
Write-Host "M3 CHECKS FAILED: $failed"
exit 1
