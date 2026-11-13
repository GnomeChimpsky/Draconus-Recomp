# M3 reference: when Flycast first shows the game, and a picture of it.
#
#   tools\flycast-first-frame.ps1
#
# Flycast shows its own loading dialog first, which is not the emulated screen. The script waits for
# that dialog to go (its Cancel button has a distinctive blue), then reports the time from process
# start to the first non-black frame of the emulated picture, and saves that frame.
param(
    [string]$Flycast = "C:\Users\Lawe\Desktop\New folder (4)\flycast.exe",
    [int]$TimeoutSeconds = 45,
    [string]$Out = "work\flycast-first.png",
    # After the first frame, keep saving shots here every half second so the later screens (the
    # title, the first level) can be matched up too.
    [string]$SeriesDir = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$cfg = Join-Path $root "engine\games\draconus\draconus.toml"
$gdi = (Select-String -LiteralPath $cfg -Pattern '^\s*image\s*=\s*"(.*)"').Matches[0].Groups[1].Value
if (-not (Test-Path -LiteralPath $gdi)) { throw "disc image missing: $gdi" }

Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a,
        int x, int y, int cx, int cy, uint f);
}
"@

$sw = [Diagnostics.Stopwatch]::StartNew()
$proc = Start-Process -FilePath $Flycast -ArgumentList "`"$gdi`"" -PassThru
$hwnd = [IntPtr]::Zero
while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds -and $hwnd -eq [IntPtr]::Zero) {
    Start-Sleep -Milliseconds 100
    $proc.Refresh()
    if ($proc.HasExited) { throw "Flycast exited before showing a window" }
    $hwnd = $proc.MainWindowHandle
}
if ($hwnd -eq [IntPtr]::Zero) { throw "no Flycast window after $TimeoutSeconds s" }

# Above other windows: the grab reads the screen, and a covered window reads as black.
[void][Win32]::SetWindowPos($hwnd, [IntPtr](-1), 0, 0, 0, 0, 0x0003)  # HWND_TOPMOST

$first = $null
$loaded_at = $null
$saved = $false
$series_at = 0
$series_done = 0
while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
    Start-Sleep -Milliseconds 100
    # The client area only: the window chrome (title bar, borders) is never black and would be
    # reported as the first frame.
    $rc = New-Object Win32+RECT
    if (-not [Win32]::GetClientRect($hwnd, [ref]$rc)) { continue }
    $pt = New-Object Win32+POINT
    if (-not [Win32]::ClientToScreen($hwnd, [ref]$pt)) { continue }
    $r = New-Object Win32+RECT
    $r.L = $pt.X
    $r.T = $pt.Y
    $r.R = $pt.X + ($rc.R - $rc.L)
    $r.B = $pt.Y + ($rc.B - $rc.T)
    $w = $r.R - $r.L
    $h = $r.B - $r.T
    if ($w -le 0 -or $h -le 0) { continue }
    $bmp = New-Object System.Drawing.Bitmap($w, $h)
    try {
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        try { $g.CopyFromScreen($r.L, $r.T, 0, 0, $bmp.Size) } finally { $g.Dispose() }
        # Flycast's loading dialog has a blue Cancel button in the middle. While it is there the
        # emulated screen has not started, so it is not the M3 first frame.
        $btn = $bmp.GetPixel([int]($w * 0.5), [int]($h * 0.59))
        $loading = ($btn.B -gt 110 -and $btn.R -lt 90 -and $btn.G -lt 110)
        if ($loading) { continue }
        if ($null -eq $loaded_at) { $loaded_at = $sw.Elapsed.TotalSeconds }
        # A coarse grid is enough: any logo or title has bright pixels somewhere.
        $nonblack = $false
        for ($y = 0; $y -lt $h -and -not $nonblack; $y += 16) {
            for ($x = 0; $x -lt $w -and -not $nonblack; $x += 16) {
                $p = $bmp.GetPixel($x, $y)
                if ($p.R -gt 12 -or $p.G -gt 12 -or $p.B -gt 12) { $nonblack = $true }
            }
        }
        if ($nonblack -and $null -eq $first) {
            $first = $sw.Elapsed.TotalSeconds
            New-Item -ItemType Directory -Force (Split-Path -Parent (Join-Path $root $Out)) | Out-Null
            $bmp.Save((Join-Path $root $Out), [System.Drawing.Imaging.ImageFormat]::Png)
            $saved = $true
        }
        if ($saved) {
            if ($SeriesDir -and $series_done -lt 12 -and
                ($sw.Elapsed.TotalSeconds - $series_at) -ge 0.5) {
                $series_at = $sw.Elapsed.TotalSeconds
                $dir = Join-Path $root $SeriesDir
                New-Item -ItemType Directory -Force $dir | Out-Null
                $file = Join-Path $dir ("shot-{0:D2}.png" -f $series_done)
                $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
                $series_done++
            }
            if (-not $SeriesDir -or $series_done -ge 12) { break }
        }
    } finally {
        $bmp.Dispose()
    }
}

[void][Win32]::SetWindowPos($hwnd, [IntPtr](-2), 0, 0, 0, 0, 0x0003)  # HWND_NOTOPMOST
if (-not $proc.HasExited) {
    $proc.CloseMainWindow() | Out-Null
    Start-Sleep -Milliseconds 500
    if (-not $proc.HasExited) { $proc.Kill() }
}

if ($null -eq $first) {
    Write-Host "flycast: no non-black frame within $TimeoutSeconds s"
    exit 1
}
Write-Host ("flycast: loading dialog gone at {0:N2} s; first non-black after it at {1:N2} s; saved {2}" -f $loaded_at, $first, $Out)
