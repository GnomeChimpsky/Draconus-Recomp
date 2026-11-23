<p align="center"><img src="Draconus%20Recomped%20Emblem%20light.png" alt="Draconus Recomped" width="720"></p>

# Draconus-Recomped

**Version 1.1.0** — current release ([release notes](RELEASE-NOTES.md)).

A native Windows x64 static recompilation of **Draconus: Cult of the Wyrm**
(Dreamcast, 2000, developed by Treyarch and published by Crave Entertainment; USA V1.000,
`F888` / `T-402`), built on [`dream-recomp`](https://github.com/phobos665/dream-recomp).

The game's SH-4 code is translated ahead of time into C++, and the Dreamcast hardware
(file system, controllers, video, sound, memory card) is replaced by native code. The
result runs from the user's own disc, no disc data or extracted game files are included or
distributed. A prebuilt release contains translated code but no disc assets; see
`docs/LEGAL.md`.

The first three levels have been played end to end from the owner's own disc. Later levels are not yet verified.

This repository holds the research, the disc tooling, the title configuration and the
engine fixes. The engine itself is fetched by `setup.ps1` at a pinned commit, so it is
not vendored here. The project lives at
<https://github.com/GnomeChimpsky/Draconus-Recomp>.

## Quick start

Two paths: run the prebuilt release, or build it from source.

### Play the release

1. Download the release from
   [Releases](https://github.com/GnomeChimpsky/Draconus-Recomp/releases) and unzip it anywhere.
   There is no installer to run.
2. Have your own dump ready: **Draconus: Cult of the Wyrm**, USA V1.000 (`F888` / `T-402`), as a
   `.gdi` with its track files or a `.chd`. This is the only game data involved — the boot program
   is read from your disc — and a dump that is not the USA V1.000 release (another region, or the
   January 2000 prototype) is refused by hash.
3. Double-click `DraconusLauncher.exe`, press **Browse...** and pick your dump — it is verified as
   soon as it is selected — then press **Play**. The launcher shows its version and can update
   itself: **Check for updates** asks GitHub for the latest release and installs it in place,
   keeping your disc path, settings and saves.

The folder is self-contained: `DraconusRecomp.exe`, `draconus.toml`, `SDL3.dll` and the Visual C++
runtime sit beside the frozen launcher, so a machine with no Python and no compiler can run it
([Build the release](#build-the-release) lists what ships). What it does need:

| Requirement | Note |
|---|---|
| Windows x64 | The project's only target; there is no Linux, macOS or 32-bit build. |
| A Vulkan-capable GPU driver | The renderer is Vulkan, and `vulkan-1.dll` comes from the driver rather than the bundle. |
| A dump of your own | USA V1.000, `.gdi` with its tracks or `.chd`, as above. |
| A gamepad (optional) | The keyboard works out of the box; a pad is mapped on first plug-in. |

Settings and bindings live under `%APPDATA%\dream-recomp` (`launcher.json`, `bindings.txt`), and a
windowed run creates a blank 128 KB VMU card at `%APPDATA%\dream-recomp\saves\draconus\vmu_a1.bin`,
so the game's own Save and Load screens work with no setup. Non-ASCII account names, folders and file
names are supported.

The keyboard works out of the box: arrows are the d-pad, `Z` `X` `A` `S` are A/B/X/Y, `Enter` is
Start, `Q`/`W` are the triggers, `F1` rebinds, `F10` shows the frame counter, `F12` screenshots and
`Escape` quits. [Play it](#play-it) has the display, save, controller and modern-controls options.

To start the game without the launcher, from the release folder:

```powershell
.\DraconusRecomp.exe --config draconus.toml --disc "D:\dumps\draconus.gdi" --window
```

### Build from source

```powershell
git clone https://github.com/GnomeChimpsky/Draconus-Recomp DraconusRecomp
cd DraconusRecomp
.\setup.ps1 -SkipBuild                          # fetch the engine, patch it, install the title config
tools\import-disc.bat "D:\dumps\draconus.gdi"   # verify the dump and point the config at it
.\setup.ps1                                     # extract the boot file from the dump, then build
.\play-draconus.bat                             # play the translated path
```

You need Visual Studio 2022 C++ build tools, CMake, Ninja, Python 3.9+, the Vulkan SDK and an SDL3
build (`-Sdl3Dir <path>\cmake`); [Toolchain](#toolchain) has the notes and `docs/09-TOOLING.md` the
full list. The build takes about five minutes and generates ~110 MB of C++.

A source build needs a `.gdi`: `dracdisc extract` does not decode CHD. The release runtime reads a
`.chd` directly, and `chdman extractcd -i game.chd -o game.gdi` converts one for a source build.

## Status

Audio (M6) is verified against Flycast: `docs/13-M6-AUDIO-BASELINE.md` has the captures, the
spectral match and the ten-minute dropout run. `tools\m6-check.ps1` reruns the gate. The first
frame (M3) and the in-game path (M5) are closed too; the open work is the full play-through (M7).

`docs/12-HANDOVER.md` is the state of play: what works, what does not, the list of local
engine changes, and the next three tasks. The engine-side findings are in
`docs/UPSTREAM-REPORT.md` (one proposed fix, one fixed harness bug, one open fault), and
`docs/ENGINE-CHANGES.md` is the running ledger with every trace and dead end.
`docs/17-VMU-SAVES.md` covers the virtual memory card: where the per-user card lives, what
`tools\vmu.py` reads, and how the game's own save and load screens use it.

## Toolchain

This repository deliberately does **not** contain the engine or any game data. `setup.ps1` fetches
the engine at a pinned commit, applies the project's engine patches from `patches/` (ledgered in
`docs/ENGINE-CHANGES.md`) and installs the title configurations. The two-stage flow in the quick
start is deliberate: the first run has nothing to translate yet and prepares the tree, and the
second extracts the boot executable from the dump you imported and builds.

`docs/09-TOOLING.md` has the exact versions and the gotchas found while building this tree. SDL3 is
not fetched: a build under `work\sdl3` is picked up automatically, otherwise pass
`-Sdl3Dir <path>\cmake`. If PowerShell script execution is blocked, `setup.bat` runs the same script
with `-ExecutionPolicy Bypass`. `docs/LEGAL.md` covers what you must supply.

## Build the release

For players, the release is a prebuilt Windows x64 folder: `DraconusLauncher.exe` (with the
`_internal` folder beside it), `DraconusRecomp.exe`, `draconus.toml`, `SDL3.dll`, the Visual C++
runtime DLLs, the `LICENSE`, `LEGAL.md`, `THIRD-PARTY-NOTICES.md`, `README.md` and `RELEASE-NOTES.md`
files, and a `BUILD-INFO.txt` recording the version, commit and build time. It needs no Python or
compiler, but does need a Vulkan-capable GPU driver. The launcher verifies your own GDI/CHD and runs
the game with `--disc` pointing at it; the boot program is read from your disc, so no extracted
`1ST_READ.BIN` ships. Non-ASCII account names, disc folders and file names are supported.

Build the release from a configured tree:

```powershell
tools\build-release.ps1                 # work\release
tools\build-release.ps1 -Out D:\out     # elsewhere
```

The script sanitizes `draconus.toml` to the `CHANGE-ME` placeholder, copies the VC++ runtime,
rebuilds the frozen launcher unless `-SkipLauncher`, and fails if the output contains a disc
image, an extracted file, or other game data. It also refuses to assemble a release when
`RELEASE-NOTES.md` has no section for the launcher's `VERSION`, so the number, the notes and the
package are bumped together; `BUILD-INFO.txt` carries that version for the updater to check against
the release tag. `tools\build-launcher.ps1` builds only the launcher.

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
.\play-draconus.bat -Fov 75                      # a wider vertical field of view
.\play-draconus.bat -Interpret                   # the development interpreter, for comparison
.\play-draconus.bat --max-frames 600 --rtc-seed 1000000 --screenshot-at 500
```

Both paths run the game; the translated one is the fast path (about 1.0x windowed and 3-4.5x
headless on the development machine, against the interpreter's 0.25x) and their guest state
matches — same renders, same controller traffic, byte-identical screenshots. See
`docs/12-HANDOVER.md` for the remaining work.

Controls: arrows = d-pad, `Z` `X` `A` `S` = A, B, X, Y, Enter = Start, `Q`/`W` = triggers,
`F1` rebinds, `F10` frame counter, `F12` screenshot, Escape quits. `-ModernControls` (or the
launcher's **Controls > Modern**) gives the pad a twin-stick layout: left stick strafes and still
moves forward/back, right stick turns, the left trigger blocks and the right trigger attacks.

**Saves.** A windowed run always has a virtual VMU: the per-user card for this title,
`%APPDATA%\dream-recomp\saves\draconus\vmu_a1.bin`, created blank and formatted on the first run.
It is the standard 128 KB Dreamcast card image, so a save made here opens in Flycast and a card
from Flycast or another emulator opens here — point `-Vmu <card>` at an existing one to use it
instead. Writes go back to the file as the game saves, and a file that is not a card is refused
rather than overwritten. `python tools\vmu.py <card>` lists what a card holds, and
`python tools\vmu.py --new <card>` makes a blank one. Headless runs stay card-less unless `--vmu`
is passed, because a card answers Maple frames and would change their traces.

Saving and loading happen in the game itself, on its own VMU screens; the launcher has no card
settings of its own. Its bottom bar has **Open saves folder** and **Open settings folder** buttons:
the first opens the card's folder, the second opens `%APPDATA%\dream-recomp`, which holds
`launcher.json`, `bindings.txt` and the `saves` folder.

**Display.** `-Widescreen` gives hor+ at 16:9: the game's projection is widened and 3D frames are
presented stretched, so more of the world is visible horizontally and nothing is distorted. The HUD
is screen-space art rather than projected geometry, so it is compressed by the same factor before
that stretch and keeps its shape and its place (the health bar stays centred, the compass in the
corner). The item wheel is a HUD panel and is compressed with it, so the wheel keeps its shape and
its place; the rotating item model inside it takes only its scale from the projection and is moved
with the wheel rather than squeezed a second time, so it keeps the size it has at 4:3 and stays in
the wheel. Menus, the title and
loading cards are flat 2D art, keep their 4:3 shape and are pillarboxed inside the wide window.
`-Aspect 21:9` takes any ratio. `-Fov 75` sets the vertical field of view (90 is the game's own;
60-120 is the range the launcher offers); it shows more or less world above and below without
changing the HUD, and composes with widescreen because the aspect and the FOV are separate
projection inputs. The item wheel's model is scaled back about the wheel so the item stays inside
its ring at any FOV. `-Gamma 1.25` sets the finished picture's display gamma (1.0 is the title's own;
above 1.0 lifts the dark and mid tones, below 1.0 deepens them); it is applied at presentation, so
F11 and F12 keep the guest's unmodified framebuffer. `-Scale 2` draws at twice the guest's resolution and
opens the window at that size (4x at 16:9 is 2560x1440, shrunk to fit a smaller screen), and
`-DisplayMode` chooses **windowed**, **borderless** (desktop fullscreen at the display's own size,
which changes no display mode) or **exclusive** (one of the display's fullscreen modes, which can
change the panel's refresh; a system that refuses it falls back to borderless). `-PresentRate`
takes a rate that divides the display's own refresh — for example 165 on a 165 Hz panel, or 120
in a 120 Hz mode — and presents up to that rate while the game logic keeps its 60 Hz (the extra
presents repeat the current image; a slower display caps the rate instead of slowing the game
down).
`-Interpolate` turns the repeats into drawn intermediate frames: the geometry between the two 60 Hz
submissions is rendered, so motion is smooth without changing game speed. Every corner moves by its
screen position, so two strips that share one move it together and a seam cannot part; menus, movies
and frames whose strips changed keep the current picture, and so does a frame that has not moved and
one whose pairing mostly failed (a cut or a fade). The intermediate is a second renderer target and is
presented from the GPU like any other frame, so it costs no copy through the host. F11 captures the
picture on the glass: when that is an intermediate frame, the capture says so and writes a `.interp`
file with the geometry that drew it.

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

**Modern controls.** The Game tab's **Controls** setting (or `play-draconus.ps1
-ModernControls`) switches the pad to the optional twin-stick layout. The left stick's left/right
movement strafes and its up/down still moves forward and back, the right stick turns, the left
trigger blocks and the right trigger attacks. A still blocks/acts and X still attacks: the
triggers are second sources for those buttons, not replacements. The left stick covers both strafe directions, so the
old trigger strafes are gone from LT/RT; B, Y, Start, C, Z, the d-pad and the shoulders keep their
Dreamcast meanings. The game reads its own analog stick for menus, so with Modern controls the right
stick (or the d-pad) moves menu cursors; and because the left trigger is now block, the game's
both-triggers **User Mode** chord is not available as it was. Modern is a layer over the player's
bindings, not a separate file: `F1` still edits the base layout, and **Classic** restores it exactly.

**Controller haptics.** With **Modern** controls selected, the Controller tab (or
`play-draconus.ps1 -Haptics`) hands the jump pack's effects to
[RenHDrum](https://github.com/trzz1214/RenHDrum) instead of the pad's two motors. A DualSense then
plays them on its voice-coil actuators through its own USB audio endpoint, a Switch Pro Controller gets
real HD Rumble packets, and an Xbox pad gets all four motors. Three switches sit under it. **Trigger
feedback on blocks and hits** turns every rumble the game sends into a short buzz — the left trigger
only while you hold block, both otherwise — and needs no HD rumble at all, so it never opens the pad's
audio path. **Trigger resistance (both triggers)** puts a constant weight under both triggers from the
moment the game starts, the left a little heavier than the right, with the buzzes playing through it.
**Controller speaker taps (experimental)** makes the rumble audible from the DualSense's own speaker,
off by default. Each strength has its own slider: HD rumble, trigger buzz, the resistance on each
trigger and where it begins, and the speaker level. The trigger options are DualSense-only and need it
**wired**; over Bluetooth the pad keeps the plain rumble, and a pad RenHDrum does not claim always
falls back to it. `renhdrum.dll` ships in the release folder and is loaded from beside the executable;
a source tree gets it from `third_party\renhdrum\`. With it missing, or with the options off, nothing
changes from the paragraph above. `DREAM_RENHDRUM_TRACE=1` prints what was claimed and every effect
sent — `tools\haptics-trace.bat` runs the game with those traces and writes a log — and
`DREAM_RENHDRUM=0` switches the whole path off for a comparison. What each option does, and what to
check when a pad does nothing, is in [docs/19-CONTROLLER-HAPTICS.md](docs/19-CONTROLLER-HAPTICS.md).

## Launcher

Release players run `DraconusLauncher.exe` from the release folder and need no Python. From a source
tree, `tools\launcher.bat` (or `python tools\launcher.py`) opens the same window: the project's
emblem, the author credit and a link to the repository on the left, and Game, Graphics, Audio and
Controller tabs on the right.

Pick your `.gdi` or `.chd` with **Browse...**; it is verified as soon as it is selected and the path
is saved when the config is writable. **Check disc** re-checks the current selection, and Play stays
disabled until a disc passes. Choose a resolution and an engine path, press **Play**. A read-only
config does not block Play: the selected image is passed with `--disc` for that session. The logic
under the window is the same code the scripts use, and it has a headless self-test:

```powershell
python tools\launcher.py --selftest
```

* **Graphics** -- the CPU clock at the top (200 MHz is the console; more is an overclock that gives
  a heavy scene more cycles inside each frame, and can affect game speed and audio on some titles),
  internal resolution (1x to 4x; the list names the window each scale opens at for the selected
  aspect — 4x is 2560x1440 at 16:9, not 4:3's 2560x1920, and 1x is upscaled to the 720-line
  minimum), widescreen
  (off, 16:9, 21:9 or a custom ratio, hor+), field of view (60-120°; 90 is the game's own, and
  above it the game can cull geometry at the far screen edges, so models may pop in when the
  camera turns), display mode (windowed, borderless or exclusive
  fullscreen), present rate (the list is built from this display's own rates: each refresh it
  reports, so 60/72/120/144/165/180/240 on a 165 Hz panel, and 60/120/144/165/240 when it cannot be
  asked), frame interpolation for the extra presents, VSync and the frame counter. What looks smooth
  is whether the rate divides the display's own refresh, not the number itself: on a 165 Hz panel the
  display holds a 120 Hz picture for one refresh and then two, which judders, while 165 is held for
  one every time -- and exclusive fullscreen can put the panel into a mode that matches
  (`docs/ENGINE-CHANGES.md`, patch 039).
* **Audio** -- sound on/off, master volume, output device (the SDL playback devices, refreshed when
  the dropdown opens) and an audio buffer/latency choice. `--wav` still records the mixer's
  full-scale output regardless of the playback volume.
* **Game** -- **Controls** (Classic Dreamcast pad, or Modern: left stick strafe, right stick
  turn, LT block, RT attack), **Brightness / gamma** (50-200%; 100% is the original),
  translated or interpreter engine path, **Crash log** (off by default; see below) and the game
  disc. The gamma is a
  display curve on the finished picture: above 100% lifts dark and mid tones, below 100% deepens
  them. It is applied when the picture is presented, so F11 and F12 still capture the game's own
  framebuffer; `--screenshot-presented` shows the adjusted screen when comparing.
* **Bottom bar** -- **Open saves folder** and **Open settings folder** open the per-user card's
  folder (`%APPDATA%\dream-recomp\saves\draconus`) and the per-user root
  (`%APPDATA%\dream-recomp`, with `launcher.json`, `bindings.txt` and `saves`). Saving and loading
  are the game's own, so there is no card setting here.
* **Updates** -- the window title and the left panel show the launcher's version, and **Check for
  updates** asks GitHub for the latest published release (once a day automatically, or whenever the
  button is pressed). When one exists the button becomes **Update to 1.1**: a release build
  downloads the Windows zip, checks the SHA-256 the release publishes when it has one, unpacks it,
  and closes so a small PowerShell helper can replace the running executable and its DLLs. The
  helper keeps the player's `image` line in `draconus.toml`, leaves everything under
  `%APPDATA%\dream-recomp` (settings, bindings, memory card) alone, holds the previous files until
  the copy succeeds, and restores them if it does not. A source tree is pointed at the releases page
  instead, because its files come from git; a read-only release folder is also refused, with the
  manual route named. `--check-updates` prints the same comparison without opening the window, and
  `--version` prints the current version.

* **Crash log** (Game tab, off by default) -- turned on, the engine writes the run's console output
  to `%APPDATA%\dream-recomp\logs\draconus-YYYYMMDD-HHMMSS.log` and, if the game dies, appends a
  crash report: the build from `BUILD-INFO.txt`, the executable's SHA-1, the exception and its
  address, the host stack as module-relative addresses, and the guest frame, pc, pr and registers at
  that moment. A run that ends normally leaves the same file with its console output and the
  end-of-run report, which is often enough to describe a problem on its own. The newest ten logs are
  kept. Nothing is written and no handler is installed while the setting is off; `--crash-log` is the
  flag the setting passes, and the game's console window is empty while it is on because its output
  goes to the file. A release also publishes `DraconusRecomp-<version>-symbols.zip` beside the game
  download: the matching linker map and `tools/symbolize.py`, which turn the stack's `module+offset`
  lines into function names. The log's `exe sha1:` line and the bundle's `BUILD-INFO.txt` are what
  pair a report with the right map.

**If the game stops.** The launcher watches the process it started and says how it ended: an access
violation, an uncaught C++ exception, a setup error, or a plain exit code. With **Crash log** on it
names the newest report and offers the logs folder; **Open logs folder** in the bottom bar opens it
at any time. Turn the setting on, reproduce the problem, and attach that file — with the release's
symbols zip the addresses become function names:

```powershell
python tools\symbolize.py crash.log draconus_boot.map --exe DraconusRecomp.exe
```

`--exe` refuses a map and a report from different builds (the `exe sha1:` line must match), which is
why each release bundle carries the hash it was built from.

The tabs are described by one table in the script (`TABS`) plus their keys in `DEFAULTS`, so adding
an option is a few lines rather than new layout code. Settings persist under
`%APPDATA%\dream-recomp\launcher.json` (the pre-release `%APPDATA%\DraconusRecomp` file is read as a
fallback, so an upgrade keeps its choices); `--selftest` checks the command
each setting produces, and `--smoke` builds the window, checks that selecting 4x and 16:9 really
produces `--scale 4 --aspect 16:9`, and closes it.

The resolution list names the window each scale opens at for the selected aspect: 4x is 2560x1920
at 4:3, or 2560x1440 at 16:9 (16:9 keeps the 2560 width and takes the height out of it). The 3D is
drawn at 640x480 times the scale, and the engine's 720-line floor upscales 1x on a wide aspect. A
window larger than the desktop's work area is shrunk to fit and centred above the taskbar, and the
bottom bar is laid out before the settings page, so Play and the folder buttons stay clickable when
a short screen has to clip the page. When a tab's options are taller than the page, that tab shows a
vertical scrollbar (the mouse wheel scrolls it too), so every option stays reachable after a resize.
On a 1080p display 4x opens at the largest
16:9 the screen allows; **Exclusive fullscreen** takes the display's own mode instead, which is how
4x 16:9 becomes exactly 2560x1440 on a 2560x1440 panel. The game itself always sees its 640x480
framebuffer, which is why captures and reports say 640x480 at every setting.

## Build the game by hand

`setup.ps1` runs this for you; the manual commands are here for rebuilds and unusual layouts.

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

## Results and evidence

The 1.1.0 build is playable at real time. The retail game boots, plays its movies, shows its menus,
loads into gameplay and responds to input — menu navigation and character movement both work — from
the owner's own disc, deterministically. Translation now covers 9,126 functions (1,071,709
instructions), up from 3,285: pointer-table discovery is on, and it is what makes the recompiled
path fast. A 60 s in-game scripted run now reports **0 untranslated calls**, and ten frame
checkpoints compared with Flycast are within the M5 threshold (`tools\m5-check.ps1`).

**Speed** went from 0.15x to **1.0x in a window and 3-4.5x headless depending on the scene (3.0x over 20,000 frames of gameplay)**: the title config now turns
on pointer-table discovery, which finds 9,126 functions instead of 3,285 — this game reaches most of
its code through tables, so without it the translated build spent its time in the development
interpreter. Inlining the RAM fast path and moving the presenter's readback out of write-combined
memory finished the job (`docs/ENGINE-CHANGES.md`). Building now takes about five minutes because
the generated C++ is ~110 MB; if a later scene is still slow, `tools\diagnose-speed.bat` names the
hotspots.

**Audio (M6) is done.** Flycast's SDL disk driver gives a digital oracle, so the comparison is a WAV
diff rather than a loopback recording. Ten seconds of menu music after START match at **1.0000
sample correlation**, identical dominant peaks and octave-band levels within **0.01 dB**; the title
screen is **silent in Flycast too**, so our title silence is correct. A **600-second** run has seven
silent runs and every one is also silent in Flycast (the long ones are the game's attract-mode
gaps), with no dropouts (`docs/13-M6-AUDIO-BASELINE.md`).

**The first frame (M3) is done too.** `tools\m3-check.ps1` checks 600-frame determinism and the F11
capture replay, then compares our first non-blank picture (guest frame 103, the Crave logo fading
in) with Flycast's first non-blank *game* picture (frame 240, after its boot ROM's licence screen):
the same logo at **MAE 0.92** against the M5 tolerance of 16 (`docs/14-M3-M6-FLYCAST-REFERENCE.md`).
Ten further checkpoints are compared in M5.

The engine fixes developed here are listed in `docs/UPSTREAM-REPORT.md`: hook dispatch at the
interpreter's fetch boundary, an instruction-level tracer, a `--replay` false-positive fix that
lets the differential harness report **0 disagreements** (2.45 million calls over 120 frames), the
handler-entry stop-address fix that closed the translated-path fault, and the inlined RAM fast
path. The full chain and the dead ends are in `docs/ENGINE-CHANGES.md`.

The earlier retail boot failure was a bug in this project's own multi-sector disc reader,
fixed and regression-tested. See `docs/11-M2-RESULTS.md`.

## Documentation

The release bundle carries this README, `RELEASE-NOTES.md` and `docs/LEGAL.md`; the rest lives in the
repository.

| To | Read |
|---|---|
| see what 1.1.0 contains and what is known to be missing | [`RELEASE-NOTES.md`](RELEASE-NOTES.md) |
| see what works, what does not and what is next | [`docs/12-HANDOVER.md`](docs/12-HANDOVER.md) |
| follow every engine change, trace and dead end | [`docs/ENGINE-CHANGES.md`](docs/ENGINE-CHANGES.md) |
| understand the disc, the boot program and the title | [`docs/01-DISC-FORENSICS.md`](docs/01-DISC-FORENSICS.md), [`docs/02-DRACONUS-TECHNICAL.md`](docs/02-DRACONUS-TECHNICAL.md) |
| set up the toolchain | [`docs/09-TOOLING.md`](docs/09-TOOLING.md) |
| see the milestone plan | [`docs/07-ROADMAP.md`](docs/07-ROADMAP.md) |
| check the fidelity gates | [`docs/13-M6-AUDIO-BASELINE.md`](docs/13-M6-AUDIO-BASELINE.md), [`docs/14-M3-M6-FLYCAST-REFERENCE.md`](docs/14-M3-M6-FLYCAST-REFERENCE.md) |
| work with saves and the VMU | [`docs/17-VMU-SAVES.md`](docs/17-VMU-SAVES.md) |
| know what may be published | [`docs/LEGAL.md`](docs/LEGAL.md) |

## Licence

GPL-2.0 (`LICENSE`), because the project is a derivative work of `dream-recomp`. No game
code or data is included or distributed; you supply your own disc. Read `docs/LEGAL.md`
before publishing anything from this tree.
