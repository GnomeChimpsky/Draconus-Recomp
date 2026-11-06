# M3/M6 reference: Flycast side by side

Flycast was at `C:\Users\Lawe\Desktop\New folder (4)\flycast.exe` (standalone, 20 MB). It boots
the retail disc correctly, so the project now has a visual oracle on this machine.

## How to drive it here

```powershell
$fc  = "C:\Users\Lawe\Desktop\New folder (4)\flycast.exe"
$gdi = "G:\...\Draconus - Cult of the Wyrm v1.000 (2000)(Crave)(US)[!].gdi"
Start-Process $fc -ArgumentList "`"$gdi`""
```

Flycast opens a normal window; `SetForegroundWindow` is blocked by Windows' anti-stealing
rule, but making it topmost works:

```powershell
Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;
public class W{[DllImport("user32.dll")]public static extern bool SetWindowPos(
IntPtr h,IntPtr a,int x,int y,int cx,int cy,uint f);}'
[W]::SetWindowPos($hwnd, [IntPtr](-1), 0,0,0,0, 0x0003)   # HWND_TOPMOST, NOSIZE|NOMOVE
```

then `PIL.ImageGrab.grab()` and restore with `[IntPtr](-2)`.

`flycast.exe` has no audio-recording option and its config exposes only texture dumps
(`rend.DumpTextures`), so **visual** reference is available here but audio reference is not.

## Title screen, ours vs Flycast

| | ours (`work/title-screen.png`) | Flycast (`work/flycast_top.png`) |
|---|---|---|
| Resolution | 640x480, native 4:3 | 2560x1440, content stretched to 16:9 |
| Logo, subtitle | present, correct | present, correct |
| "PRESS START BUTTON" | present | present |
| "COPYRIGHT(C)2000 TREYARCH LLC" | present | present |
| Overlay | **"No VMU Found / A VMU WITH AT LEAST 20 BLOCKS FREE IS NEEDED TO SAVE"** | none |

So the render itself matches: same layout, same fonts, same colours. The two differences are
**state**, not rendering:

1. **VMU presence.** We had none, so the game draws its warning over the title.
2. **Aspect.** Flycast filled a 16:9 window, so its capture is stretched; ours is 4:3 native.

A pixel diff is only meaningful after fixing both: run Flycast in a 4:3 window (or crop), and
attach a VMU on our side (`--vmu FILE`).

## Screenshots need a presented frame

`--screenshot-at N` fires on the *Nth presented frame*, so it does nothing in a headless run
(`presented` stays 0). With `--window` it works:

```
draconus_boot --config ... --interpret --window --max-frames 1500 --rtc-seed 1000000 \
    --vmu work/test.vmu --screenshot-at 1200
-> wrote screenshot-000.ppm: presented frame 1200, guest frame 1302
```

Note the two counters differ: presented frames lag guest frames, so a frame index from one run
does not transfer to the other.

## More content captured with a VMU attached

| frame (presented) | screen |
|---|---|
| 1200 | character screen: "CYNBIС THE WARRIOR / AEOWYN THE SORCERESS", portraits, dragon crest |
| 900 (earlier run, no window) | intro cinematic: red sky, terrain, creatures, siege engine |

So beyond the title, the character-select/attract screen renders correctly too (see
`work/vmu_title2.png`). Lining these up against Flycast needs Start pressed in Flycast, which
this harness does not automate yet — its window is a normal one, so `SendKeys`/`PostMessage` to
it is the next step for a frame-accurate M3 comparison.

## The VMU changes the flow, not just an overlay

With `--vmu work/test.vmu` the engine reports `memory card ...: created, formatted and
empty`, the warning disappears, and the game **skips the prompt and advances**:

* without a VMU, frame 900 is the title screen with the warning;
* with a VMU, frame 900 is already the **intro cinematic** (red sky, terrain, creatures,
  siege engine).

That is a 10+ second shift in the sequence, and it matters for any frame-indexed comparison:
two runs only line up if they agree on VMU presence.

## What this does for M6

Attaching a VMU did **not** change the title's silence (the capture is the same burst from
5-12 s then quiet), so the warning was not muting anything. Audio still appears only when the
game reaches menus/gameplay, which the 100 s capture shows as continuous from 25 s.

From here:

1. Capture Flycast audio by loopback (WASAPI) while it plays, or on a machine with a recording
   device, and compare 10 s of spectra — the only missing piece for the M6 gate.
2. Fix the like-for-like state (VMU on both sides, 4:3 in Flycast) before any pixel diff for
   M3, and use `--screenshot-at N` on our side against the same point in Flycast's timeline.
