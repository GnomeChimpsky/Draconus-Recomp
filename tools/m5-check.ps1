# M5 gate: 60 s of scripted play with zero untranslated calls, and per-checkpoint frame
# diffs against Flycast under threshold.
#
#   tools\m5-check.ps1                     # zero-call run + 10 checkpoints against Flycast
#   tools\m5-check.ps1 -SkipFlycast        # the zero-call run only
#   tools\m5-check.ps1 -Threshold 12       # tighter frame diff
#   tools\m5-check.ps1 -Flycast D:\flycast\flycast.exe -Disc D:\game.gdi
#
# The run enters gameplay at about frame 4,600 and stops at 8,200, so the last 60 s
# (3,600 frames) are in-game. Both engines get the same controller schedule; Flycast's
# Lua callback presses the same buttons on the same guest frames, then holds each
# checkpoint still while its window is grabbed.
#
# The frame-diff threshold is the mean absolute RGB difference (0-255). A correct pair
# measures 1.5-14.6 here; a pair from two different screens measures 27-38. 16 separates
# them while allowing the two renderers' different texture filtering, and the known
# additive glow effect whose phase depends on boot-time state.
#
# Requires: engine\build-render built, the owner's disc configured, Python with Pillow and
# numpy. Flycast is only needed when -SkipFlycast is absent. Everything is written under
# work\m5-check.
param(
    [string]$Flycast = "",
    [string]$Disc = "",
    [switch]$SkipFlycast,
    [int]$Frames = 8200,
    [double]$Threshold = 16.0
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$exe = Join-Path $root "engine\build-render\games\draconus\draconus_boot.exe"
$cfg = Join-Path $root "engine\games\draconus\draconus.toml"
$view = Join-Path $root "engine\build-render\render\dream_render_view.exe"
$work = Join-Path $root "work\m5-check"
$our = Join-Path $work "our"
$fly = Join-Path $work "flycast"
$markers = Join-Path $work "markers"

foreach ($p in @($exe, $cfg, $view)) {
    if (-not (Test-Path $p)) {
        throw "missing: $p (run .\setup.ps1, which builds draconus_boot and dream_render_view)"
    }
}

# 900 title, 2400 character select, 3000 loading card, 3600 story, then gameplay.
$checkpoints = @(900, 2400, 3000, 3600, 5400, 5600, 6000, 6200, 6600, 6800)
$press = "start@1000,start@1800,a@2300,a@2800,a@3100,start@4500," +
         "up@4800,up@5200,up@5600,up@6000,up@6400"

if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Force $work, $our, $fly, $markers | Out-Null

$python = "python"
$blank = Join-Path $work "blank.vmu"
& $python (Join-Path $root "tools\vmu.py") --new $blank | Out-Null
if (-not (Test-Path $blank)) { throw "could not create a blank VMU" }

function Invoke-Engine {
    param([string]$Card, [int]$MaxFrames, [string]$Report, [string[]]$Extra = @())
    $a = @("--config", $cfg, "--max-frames", "$MaxFrames", "--rtc-seed", "1000000",
           "--vmu", $Card, "--report", $Report)
    if ($press) { $a += @("--press", $press) }
    if ($Extra.Count -gt 0) { $a += $Extra }
    & $exe @a > $null 2>&1
    if ($LASTEXITCODE -ne 0) { throw "engine exited with $LASTEXITCODE (see $Report)" }
}

# --- zero untranslated calls over the whole 60 s run -----------------------------------------
$uCard = Join-Path $work "untranslated.vmu"
Copy-Item $blank $uCard -Force
$uLog = Join-Path $work "untranslated.log"
$env:DREAM_TRACE_UNTRANSLATED = "1"
try {
    Invoke-Engine -Card $uCard -MaxFrames $Frames -Report $uLog
} finally {
    Remove-Item Env:DREAM_TRACE_UNTRANSLATED -ErrorAction SilentlyContinue
}
$uText = Get-Content $uLog -Raw
if ($uText -notmatch "untranslated call targets:\s*(\d+)") {
    throw "the run report has no untranslated count"
}
$untranslated = [int]$Matches[1]
if ($uText -notmatch "guest:.*?(\d+) frames") { throw "the run report has no frame count" }
$ranFrames = [int]$Matches[1]
if ($ranFrames -lt $Frames) { throw "the run stopped at $ranFrames frames, expected $Frames" }
if ($untranslated -ne 0) {
    Write-Host "untranslated  FAIL  $untranslated call(s) over $ranFrames frames"
    Select-String -Path $uLog -Pattern "^  0x|^[0-9a-f]{8} r" | Select-Object -First 20 |
        ForEach-Object { Write-Host ("              " + $_.Line) }
    throw "M5 zero-untranslated clause failed"
}
Write-Host ("untranslated  ok    0 calls over {0} frames ({1:N1} s guest)" -f `
            $ranFrames, ($ranFrames / 60.0))

# --- our frames --------------------------------------------------------------------------------
function Render-OurFrame([int]$Frame) {
    $tag = "f{0:D4}" -f $Frame
    $card = Join-Path $our ("card-{0}.vmu" -f $tag)
    Copy-Item $blank $card -Force
    $ta = Join-Path $our ("{0}.ta" -f $tag)
    $log = Join-Path $our ("{0}.log" -f $tag)
    $ppm = Join-Path $our ("{0}.ppm" -f $tag)
    $png = Join-Path $our ("{0}.png" -f $tag)
    Remove-Item $ta, "$ta.vram", "$ta.vram.regs", $ppm, $png -Force -ErrorAction SilentlyContinue
    Invoke-Engine -Card $card -MaxFrames ($Frame + 240) -Report $log `
        -Extra @("--dump-ta", $ta, "--dump-ta-at-frame", "$Frame", "--dump-vram", (Join-Path $our "$tag.stop.vram"))
    if (-not (Test-Path $ta)) { throw "no render at or after frame $Frame (see $log)" }
    & $view $ta --vram "$ta.vram" --width 640 --height 480 --screenshot $ppm *> ($log + ".view")
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ppm)) { throw "render view failed for frame $Frame" }
    & $python -c "from PIL import Image; Image.open(r'$ppm').save(r'$png')"
    if ($LASTEXITCODE -ne 0) { throw "could not convert $ppm" }
}
foreach ($f in $checkpoints) { Render-OurFrame $f }
Write-Host ("our frames    ok    {0} checkpoint(s) rendered at 960x720" -f $checkpoints.Count)

# --- Flycast frames ----------------------------------------------------------------------------
if (-not $SkipFlycast) {
    if (-not $Flycast) {
        $candidates = @($env:FLYCAST_EXE,
                        (Join-Path $root "tools\flycast\flycast.exe"),
                        (Get-Command flycast.exe -ErrorAction SilentlyContinue).Source) |
                      Where-Object { $_ -and (Test-Path -LiteralPath $_) }
        if (@($candidates).Count -eq 0) {
            throw "Flycast not found; pass -Flycast PATH or -SkipFlycast"
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

    # Flycast bit values: A=4, START=8, UP=16. A press is released eight frames later,
    # matching the engine's --press ("hold for 8 frames from frame F").
    $holds = @(@(1000, 8), @(1800, 8), @(2300, 4), @(2800, 4), @(3100, 4), @(4500, 8),
               @(4800, 16), @(5200, 16), @(5600, 16), @(6000, 16), @(6400, 16))
    $holdLua = ($holds | ForEach-Object { "{" + $_[0] + ", " + $_[1] + "}" }) -join ", "
    $cpLua = ($checkpoints -join ", ")
    $stop = ($checkpoints | Measure-Object -Maximum).Maximum + 5
    $markerLua = $markers.Replace('\', '/')
    $luaPath = Join-Path $work "m5_flycast.lua"
    @"
-- Generated by tools\m5-check.ps1. Freeze at each checkpoint until the host grabs it.
local dir = "$markerLua/"
local stop_frame = $stop
local frames = 0
local checkpoints = {}
for _, f in ipairs({$cpLua}) do checkpoints[f] = "f" .. string.format("%04d", f) end
local holds = {$holdLua}
local press_at, release_at = {}, {}
for _, h in ipairs(holds) do
    press_at[h[1]] = h[2]
    release_at[h[1] + 8] = h[2]
end
local function exists(p)
    local f = io.open(p, "r")
    if f then f:close() return true end
    return false
end
local function freeze(name)
    local r = io.open(dir .. "ready-" .. name .. ".txt", "w")
    r:write(tostring(frames))
    r:close()
    local go = dir .. "go-" .. name .. ".txt"
    local deadline = os.time() + 60
    while not exists(go) do
        if os.time() > deadline then break end
    end
    os.remove(go)
end
flycast_callbacks = {
    vblank = function()
        frames = frames + 1
        if release_at[frames] then flycast.input.releaseButtons(1, release_at[frames]) end
        if press_at[frames] then flycast.input.pressButtons(1, press_at[frames]) end
        local name = checkpoints[frames]
        if name then freeze(name) end
        if frames >= stop_frame then flycast.emulator.exit() end
    end
}
"@ | Set-Content -LiteralPath $luaPath -Encoding utf8

    & $python (Join-Path $root "tools\m5_flycast_capture.py") `
        --flycast $Flycast --disc $Disc --lua $luaPath `
        --outdir $fly --markerdir $markers --width 960 --height 720 --timeout 300
    if ($LASTEXITCODE -ne 0) { throw "Flycast capture failed" }
    $missing = $checkpoints | Where-Object { -not (Test-Path (Join-Path $fly ("f{0:D4}.png" -f $_))) }
    if ($missing) { throw ("Flycast did not capture checkpoint(s): " + ($missing -join ", ")) }
    Write-Host ("flycast       ok    {0} checkpoint(s) captured at 960x720" -f $checkpoints.Count)

    & $python (Join-Path $root "tools\m5_frame_diff.py") `
        --our $our --flycast $fly --frames ($checkpoints -join ",") --threshold $Threshold `
        --sbs (Join-Path $work "review")
    if ($LASTEXITCODE -ne 0) { throw "M5 frame diff failed" }
}

Write-Host ""
Write-Host "M5 CHECK OK"
Write-Host ("  untranslated: 0 calls over {0} frames" -f $ranFrames)
if (-not $SkipFlycast) {
    Write-Host ("  frame diff:   {0} checkpoints, all at or below MAE {1:g}" -f $checkpoints.Count, $Threshold)
    Write-Host ("  artifacts:    {0}" -f $work)
}
exit 0
