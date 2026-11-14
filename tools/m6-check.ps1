# M6 audio gate.
#
#   1. ten seconds of music spectra matched against Flycast;
#   2. ten minutes without dropouts, compared against the same ten minutes of Flycast;
#   3. a WAV capture diff (the two captures above).
#
#   tools\m6-check.ps1                 # run every clause, capturing what is missing
#   tools\m6-check.ps1 -Skip10min      # only the ten-second spectral clause
#   tools\m6-check.ps1 -SkipCapture    # reuse work\m6\*.wav, fail if they are missing
#
# Flycast is used only to make the reference capture (tools\flycast-m6.ps1). The engine side is
# the normal translated build, headless, with the same scripted presses the audio baseline used.
# The captures live in work\m6 and are not committed.
param(
    [string]$Ref90 = "",
    [string]$Ours90 = "",
    [string]$Ref600 = "",
    [string]$Ours600 = "",
    [switch]$Skip10min,
    [switch]$SkipCapture,
    [string]$Flycast = "",
    [string]$Disc = "",
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$exe = Join-Path $root "engine\build-render\games\draconus\draconus_boot.exe"
$cfg = Join-Path $root "engine\games\draconus\draconus.toml"
$work = Join-Path $root "work\m6"
$tool = Join-Path $root "tools\audio-check.py"
if (-not $Ref90) { $Ref90 = Join-Path $work "flycast_90s.wav" }
if (-not $Ours90) { $Ours90 = Join-Path $work "ours_90s.wav" }
if (-not $Ref600) { $Ref600 = Join-Path $work "flycast_10min.wav" }
if (-not $Ours600) { $Ours600 = Join-Path $work "ours_10min.wav" }
New-Item -ItemType Directory -Force $work | Out-Null

if (-not (Test-Path $exe)) { throw "build not found: $exe (run .\setup.ps1)" }
if (-not (Test-Path $cfg)) { throw "title config not found: $cfg (run .\setup.ps1)" }

$failed = 0
function Report([string]$name, [bool]$ok, [string]$detail) {
    $tag = if ($ok) { "ok  " } else { "FAIL" }
    Write-Host ("{0,-16} {1}   {2}" -f $name, $tag, $detail)
    if (-not $ok) { $script:failed++ }
}

function Capture-Reference([string]$out, [int]$seconds) {
    if ($SkipCapture) { throw "missing reference $out and -SkipCapture was given" }
    & (Join-Path $root "tools\flycast-m6.ps1") -Seconds $seconds -Out $out -Flycast $Flycast -Disc $Disc
    # A .ps1 script does not set $LASTEXITCODE. It throws on failure; reaching here means the file
    # should exist, so that is the check.
    if (-not (Test-Path $out)) { throw "Flycast reference capture failed: $out was not written" }
}

function Capture-Ours([string]$out, [int]$frames) {
    Write-Host ("running ours: {0} frames -> {1}" -f $frames, $out)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & $exe --config $cfg --max-frames $frames --rtc-seed 1000000 `
           --press "start@1150,a@1400" --wav $out --report ([IO.Path]::ChangeExtension($out, ".log")) 2>&1 |
        Tee-Object -FilePath ([IO.Path]::ChangeExtension($out, ".stdout.log")) | Out-Null
    $sw.Stop()
    if ($LASTEXITCODE -ne 0) { throw "our capture exited with $LASTEXITCODE" }
    if (-not (Test-Path $out)) { throw "our capture wrote no WAV" }
    Write-Host ("ours finished in {0:n1} s of host time" -f $sw.Elapsed.TotalSeconds)
}

# --- ten seconds of spectra -------------------------------------------------------------------
if (-not (Test-Path $Ref90)) { Capture-Reference $Ref90 90 }
Capture-Ours $Ours90 5400
Write-Host ""
Write-Host "=== M6.1  ten seconds of music spectra ==="
& python $tool compare $Ref90 $Ours90 --reference-start 34 --gate
if ($LASTEXITCODE -ne 0) { $failed++ }

# --- ten minutes without dropouts -------------------------------------------------------------
if (-not $Skip10min) {
    if (-not (Test-Path $Ref600)) { Capture-Reference $Ref600 600 }
    Capture-Ours $Ours600 36000
    Write-Host ""
    Write-Host "=== M6.2  ten minutes without dropouts ==="
    & python $tool gaps $Ours600 --reference $Ref600 --gate
    if ($LASTEXITCODE -ne 0) { $failed++ }
}

Write-Host ""
if ($failed -eq 0) {
    Write-Host "M6 AUDIO OK"
    if (-not $KeepArtifacts) {
        # Keep the WAVs: they are the evidence, and re-capturing them costs minutes.
        Write-Host "captures kept in $work"
    }
    exit 0
}
Write-Host "M6 AUDIO FAILED: $failed check(s)"
exit 1
