# Draconus-Recomp

A native Windows x64 static recompilation of **Draconus: Cult of the Wyrm**
(Dreamcast, 2000, developed by Treyarch and published by Crave Entertainment; USA V1.000,
`F888` / `T-402`), built on [`dream-recomp`](https://github.com/phobos665/dream-recomp).

The game is playable at real time, and the recompiled path is the fast one: 1.0x with a window and
3-4.5x headless depending on the scene (3.0x over 20,000 frames of gameplay). The development interpreter remains as a reference and a bring-up tool.

The game's SH-4 code is translated ahead of time into C++, and the Dreamcast hardware
(file system, controllers, video, sound, memory card) is replaced by native code. The
result runs from the user's own disc — no game data is included or distributed.

This repository holds the research, the disc tooling, the title configuration and the
engine fixes. The engine itself is fetched by `setup.ps1` at a pinned commit, so it is
not vendored here.

## Where the work stands

Audio (M6) is verified against Flycast: `docs/13-M6-AUDIO-BASELINE.md` has the captures, the
spectral match and the ten-minute dropout run. `tools\m6-check.ps1` reruns the gate.


`docs/12-HANDOVER.md` is the state of play: what works, what does not, the list of local
engine changes, and the next three tasks. The engine-side findings are in
`docs/UPSTREAM-REPORT.md` (one proposed fix, one fixed harness bug, one open fault), and
`docs/ENGINE-CHANGES.md` is the running ledger with every trace and dead end.
`docs/17-VMU-SAVES.md` covers the virtual memory card: where the per-user card lives, what
`tools\vmu.py` reads, and how the game's own save and load screens use it.

## From a fresh clone

This repository deliberately does **not** contain the engine or any game data. `setup.ps1` fetches
the engine at a pinned commit, applies the project's engine patches from `patches/` (ledgered in
`docs/ENGINE-CHANGES.md`), installs the title configurations, and builds:

```powershell
git clone <your fork> DraconusRecomp
cd DraconusRecomp
.\setup.ps1 -SkipBuild                              # fetch, patch, install
tools\import-disc.bat "D:\dumps\draconus.gdi"       # verify + point the config at your dump
.\setup.ps1                                         # extract the boot file, then build
```

The first run says there is nothing to translate yet; the second extracts the boot executable from
the dump you imported and builds. You need the Vulkan SDK and SDL3 — see `docs/09-TOOLING.md`; if
SDL3 is not in `work\sdl3`, pass `-Sdl3Dir <path>\cmake`. `docs/LEGAL.md` covers what you must
supply.

## Checking the translated path

```powershell
tools\repro-translated-path.ps1
```

One command, no changes: runs the machine-translated path under the diagnostics and prints the
exception entries, the task-switch decision, the SPC writes and the handler's saved-context stores.
The expected result is now a clean run (`stop: frame limit`, `task-switching RTEs: 0`); before patch
007 it stopped at frame 54 with `0x60000040`. The history and the root cause are in
`docs/ENGINE-CHANGES.md`.

To compare the two execution paths against each other — same seed, same scripted input, windowed,
counters and screenshot:

```powershell
tools\parity-check.ps1
```

It passes when the stop reason, frame count, PVR/Maple counters and the screenshot are identical.

The audio gate is one command. It compares ten seconds of spectra and ten minutes of dropouts
against Flycast, capturing whichever side is missing:

```powershell
tools\m6-check.ps1
```

`tools\flycast-m6.ps1` makes the Flycast reference on its own; `tools\audio-check.py` has the
individual `info`, `align`, `compare`, `gaps` and `raw2wav` commands.

## Graphical launcher

```powershell
tools\launcher.bat
```

Pick a `.gdi`, press **Verify** (it refuses anything that is not the USA V1.000 release and
writes the config on success), choose a resolution and a path, press **Play**. The logic
under the window is the same code the scripts use, and it has a headless self-test:

```powershell
python tools\launcher.py --selftest
```

## Import a disc

```powershell
tools\import-disc.bat "D:\dumps\draconus.gdi"          # verify + configure
tools\import-disc.bat "D:\dumps\draconus.gdi" --whatif # verify only
```

The helper checks the dump against the known boot-executable hash (refusing anything that is
not the USA V1.000 release, including the prototype), then points the engine-side config at
it. The dump stays where it is; nothing is copied.

## Play it

```powershell
.\play-draconus.bat
```

That launches the recompiled build with a window, running the machine-translated code. It verifies
the disc path before starting and says so plainly if the dump is missing or was never imported.

```powershell
.\play-draconus.bat                              # window, translated path
.\play-draconus.bat -Scale 2                     # 1280x960
.\play-draconus.bat -Interpret                   # the development interpreter, for comparison
.\play-draconus.bat --max-frames 600 --rtc-seed 1000000 --screenshot-at 500
```

Both paths run the game; the translated one is about five times faster (1.0x windowed, 1.2x
headless at 1,800 frames, against the interpreter's 0.25x) and their guest state matches — same
renders, same controller traffic, byte-identical screenshots. See `docs/12-HANDOVER.md` for the
remaining work.

Controls: arrows = d-pad, `Z` `X` `A` `S` = A, B, X, Y, Enter = Start, `Q`/`W` = triggers,
`F1` rebinds, `F10` frame counter, `F12` screenshot, Escape quits.

**Saves.** A windowed run always has a virtual VMU: the per-user card for this title,
`%APPDATA%\dream-recomp\saves\draconus\vmu_a1.bin`, created blank and formatted on the first run.
It is the standard 128 KB Dreamcast card image, so a save made here opens in Flycast and a card
from Flycast or another emulator opens here — point `-Vmu <card>` at an existing one to use it
instead. Writes go back to the file as the game saves, and a file that is not a card is refused
rather than overwritten. `python tools\vmu.py <card>` lists what a card holds, and
`python tools\vmu.py --new <card>` makes a blank one. Headless runs stay card-less unless `--vmu`
is passed, because a card answers Maple frames and would change their traces.

Saving and loading happen in the game itself, on its own VMU screens; the launcher has no card
settings of its own. Its bottom bar has **Open saves folder** and **Open settings folder** buttons,
which open the per-user card's folder and the one holding `launcher.json`.

**Display.** `-Widescreen` gives hor+ at 16:9: the game's projection is widened and 3D frames are
presented stretched, so more of the world is visible horizontally and nothing is distorted. The HUD
is screen-space art rather than projected geometry, so it is compressed by the same factor before
that stretch and keeps its shape and its place (the health bar stays centred, the compass in the
corner). The item wheel and its rotating item models are a HUD panel and are compressed with it, so
the wheel keeps its shape and the model stays in it. Menus, the title and loading cards are flat 2D
art, keep their 4:3 shape and are
pillarboxed inside the wide window. `-Aspect 21:9` takes any ratio, `-Scale 2` draws at twice the guest's resolution and
opens the window at that size (4x at 16:9 is 2560x1440, shrunk to fit a smaller screen), and
`-DisplayMode` chooses **windowed**, **borderless** (desktop fullscreen at the display's own size,
which changes no display mode) or **exclusive** (one of the display's fullscreen modes, which can
change the panel's refresh; a system that refuses it falls back to borderless). `-PresentRate 120`
presents the display at up to that rate while the game logic keeps its 60 Hz (the extra presents
repeat the current image; a slower display caps the rate instead of slowing the game down).
`-Interpolate` turns the repeats into drawn intermediate frames: the geometry between the two 60 Hz
submissions is rendered, so motion is smooth without changing game speed. Menus, movies and frames
whose strips changed keep the current picture.

**Controllers.** A pad works on first plug-in: the left stick is the Dreamcast analogue stick, the
face buttons are A/B/X/Y, the d-pad is the d-pad, Start is Start, the shoulders are C and Z, and the
triggers are L and R. A jump pack is always attached, so the game's rumble reaches the pad's own
rumble motors: the pack's single motor is played on both of a pad's motors at the strength and for
the duration the game asked for, and a stop stops them immediately. Draconus ships with that pack
switched off in its own settings, so enable **Options → JUMPPACK → PACK ON**; highlighting that row
plays a short test burst, which is the quickest way to confirm the pad is being reached. Pads SDL knows are mapped automatically; a generic pad that arrives as a raw
joystick gets the standard DirectInput layout instead (anything wrong can be rebound in `F1`). The
launcher prints which devices it found at start (`input: KEYBOARD, <pad>`), a pad can be plugged in
while the game runs, and `DREAM_INPUT_TRACE=1` prints the state the guest receives whenever it
changes, which is the quickest way to tell a host problem from a game one. If SDL cannot open the pad
because another driver has claimed it, the launcher falls back to XInput directly and lists the
device as `XINPUT`.

## Launcher

`tools\launcher.bat` (or `python tools\launcher.py`) opens the graphical launcher: the project's
emblem, the author credit and a link to the repository on the left, and Graphics, Audio and Gameplay
tabs on the right.

* **Graphics** -- the CPU clock at the top (200 MHz is the console; more is an overclock that gives
  a heavy scene more cycles inside each frame, and can affect game speed and audio on some titles),
  internal resolution (1x to 4x, which is also the window size: 4x at 16:9 is 2560x1440), widescreen
  (off, 16:9, 21:9 or a custom ratio, hor+), display mode (windowed, borderless or exclusive
  fullscreen), present rate (60/120/144 Hz against the fixed 60 Hz logic, capped to the display's
  refresh), frame interpolation for the extra presents (experimental, only at 120/144 Hz), VSync and
  the frame counter.
* **Audio** -- sound on/off, master volume, output device (the SDL playback devices, refreshed when
  the dropdown opens) and an audio buffer/latency choice. `--wav` still records the mixer's
  full-scale output regardless of the playback volume.
* **Gameplay** -- translated or interpreter engine path, and the game disc.
* **Bottom bar** -- **Open saves folder** and **Open settings folder** open the per-user card's
  folder (`%APPDATA%\dream-recomp\saves\draconus`) and the launcher's own
  (`%APPDATA%\DraconusRecomp`). Saving and loading are the game's own, so there is no card setting
  here.

The tabs are described by one table in the script (`TABS`) plus their keys in `DEFAULTS`, so adding
an option is a few lines rather than new layout code. Settings persist under
`%APPDATA%\DraconusRecomp\launcher.json`; `python tools\launcher.py --selftest` checks the command
each setting produces, and `--smoke` builds the window, checks that selecting 4x and 16:9 really
produces `--scale 4 --aspect 16:9`, and closes it.

The resolution list is the scale the 3D is drawn at and the size the window opens at: 4x is
2560x1920 at 4:3, or 2560x1440 at 16:9 (16:9 keeps the 2560 width and takes the height out of it).
A window larger than the screen is shrunk to fit, so on a 1080p display 4x opens at the largest
16:9 the screen allows; **Exclusive fullscreen** takes the display's own mode instead, which is how
4x 16:9 becomes exactly 2560x1440 on a 2560x1440 panel. The game itself always sees its 640x480
framebuffer, which is why captures and reports say 640x480 at every setting.

## Rebuild the renderer build

```powershell
# Vulkan SDK (winget), SDL3 built locally, then:
cmake -S engine -B engine/build-render -G Ninja -DCMAKE_BUILD_TYPE=Release `
      -DDREAM_DEV_INTERPRETER=ON -DDREAM_RENDERER=ON -DDREAM_BUILD_TESTS=OFF -DDREAM_WERROR=OFF `
      -DSDL3_DIR=<repo>/work/sdl3/cmake
cmake --build engine/build-render --target draconus_boot --parallel
```

Reproduce the reconnaissance:

```powershell
cd tools\draconus-disc
python -m dracdisc verify  "<path to retail .gdi>"
python -m dracdisc inspect "<path to retail .gdi>"
python -m dracdisc manifest "<path to retail .gdi>" -o ..\..\work\manifest.json
python -m dracdisc extract  "<path to retail .gdi>" -o ..\..\work\extracted
python -m unittest discover -s tests
```

Status: **playable at real time**. The retail game boots, plays its movies, shows its menus, loads
into gameplay and responds to input — menu navigation and character movement both work — from the
owner's own disc, deterministically. Translation now covers 8,940 functions (995,051 instructions),
up from 3,285: pointer-table discovery is on, and it is what makes the recompiled path fast.

**Speed** went from 0.15x to **1.0x in a window and 3-4.5x headless depending on the scene (3.0x over 20,000 frames of gameplay)**: the title config now turns
on pointer-table discovery, which finds 8,940 functions instead of 3,285 — this game reaches most of
its code through tables, so without it the translated build spent its time in the development
interpreter. Inlining the RAM fast path and moving the presenter's readback out of write-combined
memory finished the job (`docs/ENGINE-CHANGES.md`). Building now takes about five minutes because
the generated C++ is ~100 MB; if a later scene is still slow, `tools\diagnose-speed.bat` names the
hotspots.

**Audio (M6) is done.** Flycast's SDL disk driver gives a digital oracle, so the comparison is a WAV
diff rather than a loopback recording. Ten seconds of menu music after START match at **1.0000
sample correlation**, identical dominant peaks and octave-band levels within **0.01 dB**; the title
screen is **silent in Flycast too**, so our title silence is correct. A **600-second** run has seven
silent runs and every one is also silent in Flycast (the long ones are the game's attract-mode
gaps), with no dropouts (`docs/13-M6-AUDIO-BASELINE.md`). Visual comparison against Flycast has
started: the title screen matches apart from VMU state and aspect
(`docs/14-M3-M6-FLYCAST-REFERENCE.md`).

The engine fixes developed here are listed in `docs/UPSTREAM-REPORT.md`: hook dispatch at the
interpreter's fetch boundary, an instruction-level tracer, a `--replay` false-positive fix that
lets the differential harness report **0 disagreements** (2.45 million calls over 120 frames), the
handler-entry stop-address fix that closed the translated-path fault, and the inlined RAM fast
path. The full chain and the dead ends are in `docs/ENGINE-CHANGES.md`.

The earlier retail boot failure was a bug in this project's own multi-sector disc reader,
fixed and regression-tested. See `docs/11-M2-RESULTS.md`.

## Licence

GPL-2.0 (`LICENSE`), because the project is a derivative work of `dream-recomp`. No game
code or data is included or distributed; you supply your own disc. Read `docs/LEGAL.md`
before publishing anything from this tree.
