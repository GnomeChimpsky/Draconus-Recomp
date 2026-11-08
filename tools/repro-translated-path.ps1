# Reproduce the translated-path fault and print the evidence in one command.
#
#   tools\repro-translated-path.ps1
#
# Runs the machine-translated path (which stops at guest frame 54) under the diagnostics added
# during this investigation and prints the lines that matter. Needs engine\build-render to exist
# and the disc configured (tools\import-disc.bat). Nothing is modified.
#
# Expected on this title (Draconus: Cult of the Wyrm, USA V1.000):
#   * stop: fault, pc 0x60000040, 54 frames
#   * task-switching RTEs: 1
#   * a nested exception (nesting 2) immediately before the switch
#   * ldc.l @r15+,spc loading 0x60000040 (an SR value) from the handler's stack
param(
    [int]$Frames = 60
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$exe = Join-Path $root "engine\build-render\games\draconus\draconus_boot.exe"
$cfg = Join-Path $root "engine\games\draconus\draconus.toml"

if (-not (Test-Path $exe)) { throw "build not found: $exe (see docs/09-TOOLING.md)" }
if (-not (Test-Path $cfg)) { throw "config not found: $cfg (run setup.ps1 and tools\import-disc.bat)" }

$env:DREAM_TRACE_SWITCH = "1"
$env:DREAM_TRACE_SPC = "1"
$env:DREAM_WATCH_WRITE = "0x8C483938:0x0C"

Write-Host "=== run (translated path, $Frames frames) ==="
$work = Join-Path $root "work"
New-Item -ItemType Directory -Force $work | Out-Null
$log = Join-Path $work "repro-translated.log"
# The engine writes the diagnostics to stderr; Windows PowerShell turns native stderr into
# ErrorRecords, so relax the preference for the call and restore it afterwards.
$was = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $exe --config $cfg --max-frames $Frames --rtc-seed 1000000 *> $log
$ErrorActionPreference = $was
$out = Get-Content $log

Remove-Item Env:DREAM_TRACE_SWITCH, Env:DREAM_TRACE_SPC, Env:DREAM_WATCH_WRITE -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== exception entry and switch decision ==="
$out | Select-String -Pattern "^exc:" | Select-Object -Last 3 | ForEach-Object { $_.Line }
$out | Select-String -Pattern "^switch:" | ForEach-Object { $_.Line }

Write-Host ""
Write-Host "=== SPC writes (the bad one is ldc.l loading 0x60000040) ==="
$out | Select-String -Pattern "^spc-write" | Select-Object -Last 4 | ForEach-Object { $_.Line }

Write-Host ""
Write-Host "=== writes into the handler's saved pr/spc/ssr slots ==="
$out | Select-String -Pattern "^watch:" | Select-Object -Last 6 | ForEach-Object { $_.Line }

Write-Host ""
Write-Host "=== outcome ==="
$out | Select-String -Pattern "^stop:|^guest:|^task-switching|^fault" | ForEach-Object { $_.Line }

Write-Host ""
Write-Host "full trace: run the same command and keep stderr, or see docs/ENGINE-CHANGES.md"
