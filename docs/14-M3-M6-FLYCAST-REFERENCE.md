# M3/M6 reference: Flycast side by side

Flycast is a standalone emulator used as the visual oracle. Put `flycast.exe` under
`tools\flycast\` or set `FLYCAST_EXE`; the scripts also accept `-Flycast PATH`. It boots the
retail disc correctly, so the project has a visual oracle on the development machine. The emulator
is GPL-2.0 and is not part of this repository, so a clean checkout needs the user to supply it.

## How to drive it here

```powershell
$fc  = "$env:FLYCAST_EXE"      # or the path to flycast.exe
$gdi = "D:\path\to\draconus.gdi"
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

then `PIL.ImageGrab.grab()` and restore with `[IntPtr](-2)`. A screen grab is fine for a quick
look, but it is not frame-exact: another window can cover it, and it samples the moment it runs.

**The frame-exact path.** `tools\m5_flycast_capture.py` launches Flycast with a Lua script
(`-config config:LuaFileName=...`) whose `vblank` callback freezes at chosen guest frames: it writes
`ready-<name>.txt` and busy-waits for the host's `go-<name>.txt`, so the frame is held still while
the host copies the client area with `PrintWindow(PW_CLIENTONLY | PW_RENDERFULLCONTENT)`. The window
is 960x720 (4:3) with `rend.WideScreen=no` and `rend.ScreenStretching=100`. `tools\m5-check.ps1`
uses this for ten checkpoints and `tools\m3-check.ps1` for the first frame. Lua's vblank counter is
the guest frame counter the checks use; the comparison is by content, not by wall time.

`flycast.exe` has no "record audio" menu item, but its SDL2 audio backend can be pointed at SDL's
disk driver, which writes the mixed output to a file. Set `SDL_AUDIODRIVER=disk` and
`SDL_DISKAUDIOFILE=<raw>`, and pass `-config audio:backend=sdl2`. The file is raw s16le stereo
44.1 kHz; `tools/audio-check.py raw2wav` converts it. `tools/flycast-m6.ps1` wraps the whole
procedure, including the Lua script that presses START and A on chosen guest frames. That gives a
digital audio oracle, not a loopback recording.

## Title screen, ours vs Flycast (initial comparison, 2026-11-06)

| | ours (`work/title-screen.png`) | Flycast (`work/flycast_top.png`) |
|---|---|---|
| Resolution | 640x480, native 4:3 | 2560x1440, content stretched to 16:9 |
| Logo, subtitle | present, correct | present, correct |
| "PRESS START BUTTON" | present | present |
| "COPYRIGHT(C)2000 TREYARCH LLC" | present | present |
| Overlay | **"No VMU Found / A VMU WITH AT LEAST 20 BLOCKS FREE IS NEEDED TO SAVE"** | none |

So the render itself matches: same layout, same fonts, same colours. The two differences in that
pair were **state**, not rendering: we had no VMU (so the warning was drawn) and Flycast's 16:9
window stretched its capture. The current checks fix both: our runs attach a blank VMU and Flycast
is captured in a 4:3 960x720 window.

One state difference remains and is accepted. The engine always attaches a jump pack (patch 029,
so the game's rumble reaches the pad), and the title draws **"JUMPPACK OPERATIONAL"** when it sees
one; Flycast's default configuration has no jump pack, so its title has no such line. M5's title
checkpoint contains the line and still stays inside the threshold; the M3 first-frame pair is the
logo before that line exists, so it is unaffected. A strict title-screen diff would need a jump
pack configured in Flycast; the project deliberately keeps the pack enabled instead.

## Screenshots and captures count presented frames

`--screenshot-at N` and `--capture-at N` fire on the *Nth presented frame*, not the Nth guest frame.
A headless run presents nothing (`presented` stays 0), so they do nothing there; with `--window`
they work:

```
draconus_boot --config ... --interpret --window --max-frames 1500 --rtc-seed 1000000 \
    --vmu work/test.vmu --screenshot-at 1200
-> wrote screenshot-000.ppm: presented frame 1200, guest frame 1302
```

Presented frames lag guest frames, and the ratio depends on how often the title asks for a render
and on the display, so a presented index does not transfer between runs or machines. The M3 capture
clause needs enough frame budget for this: a 420-frame run presented only 317 pictures, so the
check now runs 600 frames and captures at presented 320. For any *comparison*, target the guest
frame instead: `--dump-ta-at-frame N` plus `dream_render_view`, which is what the M3 first-frame and
M5 checkpoint checks do.

## More content captured with a VMU attached

| frame (presented) | screen |
|---|---|
| 1200 | character screen: "CYNBIС THE WARRIOR / AEOWYN THE SORCERESS", portraits, dragon crest |
| 900 (earlier run) | intro cinematic: red sky, terrain, creatures, siege engine |

So beyond the title, the character-select/attract screen renders correctly too (see
`work/vmu_title2.png`). These were captured by hand. The comparison is now automated:
`tools\m5-check.ps1` presses START/A/UP at chosen guest frames through Flycast's Lua API, freezes
each checkpoint and compares ten of them; `tools\m3-check.ps1` compares the first frame.

## The first frame, compared automatically

Our engine boots `1ST_READ.BIN` directly, so its first picture is the game's first render (the
Crave logo fading in). Flycast runs the boot ROM first: its first non-black picture is the Sega
licence screen, which is not game content. Comparing those two "firsts" would compare different
screens, so `tools\m3_first_frame.py` — run by `tools\m3-check.ps1` — finds Flycast's first
non-blank **game** picture and compares that with ours. It makes two frozen-frame passes: a coarse
sweep to find the bright boot screen and the first dark, non-blank picture after it, then a fine
sweep over that interval to place the frame exactly. The pair is judged with the M5 metric, mean
absolute RGB difference, plus a non-black-mask overlap so that two nearly black pictures cannot
pass by both being black.

| | ours | Flycast |
|---|---|---|
| first non-black picture | guest frame 103, the Crave logo fading in | the boot ROM's Sega licence screen (on screen into the 230s here) |
| first non-blank *game* picture | frame 103 | frame 240 |
| picture size | 960x720 | 960x720 |
| pair | **MAE 0.92**, RMSE 3.36, mask overlap 0.93, bbox IoU 0.99 | threshold 16 |

The frame numbers differ because the boot paths differ (about 137 frames here); the comparison is
content-aligned, and ours reaches the picture first. The M5 checkpoints show that after the boot
sequence the same guest frame is the same game moment (they match pose for pose), so this is a
boot-time difference, not a persistent shift.

## The VMU changes the flow, not just an overlay

With `--vmu work/test.vmu` the engine reports `memory card ...: created, formatted and
empty`, the warning disappears, and the game **skips the prompt and advances**:

* without a VMU, presented frame 900 is the title screen with the warning;
* with a VMU, presented frame 900 is already the **intro cinematic** (red sky, terrain, creatures,
  siege engine).

(These are presented-frame counts, from the hand captures above. On the guest-frame counter the M5
checkpoints use, guest frame 900 is still the title with a VMU; that is the frame its title
checkpoint compares.)

That is a 10+ second shift in the sequence, and it matters for any frame-indexed comparison:
two runs only line up if they agree on VMU presence. The checks attach a blank VMU on our side;
Flycast's default configuration has a card in slot A, which is why its title has no warning either.

## What this does for M6

Attaching a VMU did **not** change the title's silence (the capture is the same burst from
5-12 s then quiet), so the warning was not muting anything. Audio still appears only when the
game reaches menus/gameplay, which the 100 s capture shows as continuous from 25 s.

The digital capture settled the title question: Flycast is silent on the title screen too. With
START pressed at guest frame 1800, Flycast's intro runs from 7.55 s to 15.55 s, the title is silent
from 15.55 s to 33.5 s, and the menu music starts at 33.5 s. Ours has the same sequence eight
seconds earlier. The 10 s comparison and the ten-minute run are in `docs/13-M6-AUDIO-BASELINE.md`.

## What remains for M3

Nothing: `tools\m3-check.ps1` is the gate and has three clauses — 600-frame determinism, the F11
capture replay, and the first-frame pair above. Use `-SkipFlycast` when no oracle is available, or
`-SkipCapture` for the first frame alone. The accepted state difference is the always-attached
jump pack described under the title-screen section.
