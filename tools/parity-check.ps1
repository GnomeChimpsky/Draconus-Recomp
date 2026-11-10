# Compare the translated path against the interpreter, frame for frame.
#
#   tools\parity-check.ps1                     # windowed run, screenshot at presented 900
#   tools\parity-check.ps1 -Frames 2400 -ShotAt 2300
#   tools\parity-check.ps1 -Headless           # no window, counters only
#   tools\parity-check.ps1 -Hashes             # also compare the per-frame write hashes (slow)
#
# Both runs use the same seed, the same scripted presses and the same stop frame. The check passes
# when the stop reason, the frame count, the PVR and Maple counters and the two screenshots match.
# Needs engine\build-render and the owner's disc configured.
param(
    [int]$Frames = 1100,
    [int]$ShotAt = 900,
    [string]$Press = "start@1000,a@1400,start@2000",
    [switch]$Headless,
    [switch]$Hashes,
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$exe = Join-Path $root "engine\build-render\games\draconus\draconus_boot.exe"
$cfg = Join-Path $root "engine\games\draconus\draconus.toml"
$work = Join-Path $root "work\parity-check"

if (-not (Test-Path $exe)) { throw "build not found: $exe (run .\setup.ps1)" }
if (-not (Test-Path $cfg)) { throw "title config not found: $cfg (run .\setup.ps1)" }

if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Force $work | Out-Null

function Invoke-Run {
    param([string]$Name, [switch]$Interpret, [switch]$Window, [string]$HashFile)
    $dir = Join-Path $work $Name
    New-Item -ItemType Directory -Force $dir | Out-Null
    $engineArgs = @("--config", $cfg, "--no-audio", "--max-frames", "$Frames", "--rtc-seed", "1000000")
    if ($Press) { $engineArgs += @("--press", $Press) }
    if ($Interpret) { $engineArgs += "--interpret" }
    if ($Window) {
        $engineArgs += @("--window", "--screenshot-at", "$ShotAt")
    }
    if ($HashFile) {
        $engineArgs += @("--write-hash", $HashFile, "--mask-segment")
    }
    Push-Location $dir
    try {
        & $exe @engineArgs *> (Join-Path $dir "run.log")
        if ($LASTEXITCODE -ne 0) { throw "$Name exited with $LASTEXITCODE (see $dir\run.log)" }
    } finally {
        Pop-Location
    }
    return $dir
}

function Get-Line {
    param([string]$LogPath, [string]$Pattern)
    $line = Select-String -Path $LogPath -Pattern $Pattern | Select-Object -First 1
    if ($line) { return $line.Line } else { return "" }
}

Write-Host "running the interpreter..."
$i = Invoke-Run -Name "interp" -Interpret -Window:(-not $Headless) `
                -HashFile $(if ($Hashes) { Join-Path $work "hash_interp.txt" })
Write-Host "running the translated path..."
$t = Invoke-Run -Name "trans" -Window:(-not $Headless) `
                -HashFile $(if ($Hashes) { Join-Path $work "hash_trans.txt" })

$li = Join-Path $i "run.log"
$lt = Join-Path $t "run.log"
$failures = New-Object System.Collections.Generic.List[string]

# Hard gates: the run must stop the same way, reach the same frame, and agree on the render and
# controller traffic. Interrupt count and cycles are reported but not gated: the two engines charge
# slightly different instruction costs, so a few interrupts land a frame differently.
$stopI = Get-Line $li "^stop:"; $stopT = Get-Line $lt "^stop:"
$pvrI = Get-Line $li "^PVR:";  $pvrT = Get-Line $lt "^PVR:"
$mapleI = Get-Line $li "^maple:"; $mapleT = Get-Line $lt "^maple:"
$gui = Get-Line $li "^guest:"; $guT = Get-Line $lt "^guest:"
$irqI = Get-Line $li "^interrupts delivered:"; $irqT = Get-Line $lt "^interrupts delivered:"

function Get-FrameCount([string]$guest) {
    if ($guest -match "(\d+) frames") { return [int]$Matches[1] } else { return -1 }
}
$framesI = Get-FrameCount $gui
$framesT = Get-FrameCount $guT

$checks = @(
    @{ Name = "stop";     Ok = ($stopI -eq $stopT -and $stopI -ne ""); Show = $stopI },
    @{ Name = "frames";   Ok = ($framesI -eq $framesT -and $framesI -gt 0); Show = "$framesI vs $framesT" },
    @{ Name = "PVR";      Ok = ($pvrI -eq $pvrT -and $pvrI -ne ""); Show = $pvrI },
    @{ Name = "Maple";    Ok = ($mapleI -eq $mapleT -and $mapleI -ne ""); Show = $mapleI }
)
foreach ($c in $checks) {
    if (-not $c.Ok) { $failures.Add($c.Name) }
    Write-Host ("{0,-8} {1}  {2}" -f $c.Name, $(if ($c.Ok) { "ok  " } else { "FAIL" }), $c.Show)
}
Write-Host ("cycles   info  {0}" -f $gui)
Write-Host ("         info  {0}" -f $guT)
Write-Host ("irqs     info  {0}" -f $irqI)
Write-Host ("         info  {0}" -f $irqT)

if (-not $Headless) {
    $sa = Join-Path $i "screenshot-000.ppm"
    $sb = Join-Path $t "screenshot-000.ppm"
    if ((Test-Path $sa) -and (Test-Path $sb)) {
        $ba = [IO.File]::ReadAllBytes($sa)
        $bb = [IO.File]::ReadAllBytes($sb)
        $diff = -1
        if ($ba.Length -eq $bb.Length) {
            $diff = 0
            for ($k = 15; $k -lt $ba.Length; ++$k) { if ($ba[$k] -ne $bb[$k]) { ++$diff } }
        }
        if ($diff -eq 0) {
            Write-Host ("shot     ok    byte-identical, presented frame {0}" -f $ShotAt)
        } else {
            Write-Host ("shot     FAIL  {0} bytes differ" -f $diff)
            $failures.Add("screenshot")
        }
    } else {
        Write-Host "shot     FAIL  missing (run with -Headless to skip)"
        $failures.Add("screenshot")
    }
}

if ($Hashes) {
    # The write hash is per frame, and a write that lands either side of a frame tick because of the
    # two engines' slightly different instruction costs makes single frames differ even when the
    # write sequence is identical. Context, not a gate.
    function Read-Hash([string]$path) {
        $map = @{}
        foreach ($line in [IO.File]::ReadLines($path)) {
            if ($line.StartsWith("#")) { continue }
            $f = $line.Split(' ')
            if (-not $map.ContainsKey([int]$f[0])) { $map[[int]$f[0]] = $f[2] }
        }
        return $map
    }
    $ha = Read-Hash (Join-Path $work "hash_interp.txt")
    $hb = Read-Hash (Join-Path $work "hash_trans.txt")
    $same = 0; $diff = 0; $first = $null
    foreach ($frame in $ha.Keys) {
        if (-not $hb.ContainsKey($frame)) { continue }
        if ($ha[$frame] -eq $hb[$frame]) { ++$same } else {
            ++$diff
            if ($null -eq $first -or $frame -lt $first) { $first = $frame }
        }
    }
    Write-Host ""
    Write-Host "hashes   info  $same frames identical, $diff differ (first at frame $first)"
    Write-Host "         info  per-frame differences are frame-tick shifts unless the gates above fail"
}

Write-Host ""
if ($failures.Count -eq 0) {
    Write-Host "PARITY OK"
    if (-not $KeepArtifacts) { Remove-Item $work -Recurse -Force }
    exit 0
} else {
    Write-Host ("PARITY FAILED: " + ($failures -join ", "))
    Write-Host "artifacts kept in $work"
    exit 1
}
