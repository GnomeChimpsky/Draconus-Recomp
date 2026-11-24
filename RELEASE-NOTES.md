# Release notes

Draconus-Recomp is a native Windows x64 static recompilation of *Draconus: Cult of the Wyrm*
(Dreamcast, 2000, developed by Treyarch and published by Crave Entertainment). It runs from your own
disc and ships no game data. The [README](README.md) is the manual; the
[quick start](README.md#quick-start) is the shortest way in.

## 1.2.1 — 2026-11-24

RecompLauncher support. Windows x64; the requirements, saves and settings are unchanged, and the
launcher updates itself in place as before.

* **Set up and play from RecompLauncher.** Every release now carries `recomplauncher.json` at the
  top of the folder. [RecompLauncher](https://recomplauncher.com) reads it to ask for your own dump
  once, verify it with the project's own checker, and show the game's display, controller and audio
  options on the game's page. Its Play starts the game with those settings and without the launcher
  window; the disc is handed over on every start, so an update never asks for it again.
* **The launcher can run without its window.** `--prepare --game <disc>` verifies a dump and prints
  `progress` lines for a setup screen, and `--play --game <disc>` starts the game with the saved
  `launcher.json` settings, waits for it and returns its exit code. Launch options after `--play`
  are passed on to the game. Running `DraconusLauncher.exe` by hand is exactly as it was, and a
  launcher that started the game (`RECOMPLAUNCHER=1`) no longer offers its own updater.
* Nothing about the game changed: no gameplay, graphics, audio, save or settings-format changes.

## 1.2.0 — 2026-11-23

The second update. Windows x64; the requirements and install steps are the same as 1.1, and the
launcher can update itself in place.

* **Controller haptics.** A new **Controller** tab — available with the **Modern** control layout,
  where the triggers block and attack — turns on RenHDrum, the haptics engine that reaches the parts
  of a modern pad the Dreamcast's own rumble pack never could: a DualSense's voice-coil actuators over
  its USB audio endpoint, a Switch Pro Controller's HD Rumble packets, and an Xbox pad's four motors.
  **Trigger feedback on blocks and hits** is a separate, HID-only switch: every rumble the game sends
  becomes a short buzz in the left trigger while you block, and in both triggers otherwise — it needs
  no HD rumble and never opens the pad's audio path. **Trigger resistance (both triggers)** puts a
  constant weight under both triggers from the moment the game starts, the left a little heavier than
  the right, with the buzzes playing through it. Every strength has its own slider: HD rumble, trigger
  buzz, each trigger's resistance, where the resistance begins, and the speaker level.
  **Controller speaker taps (experimental)** is there too, off by default. Everything degrades to the
  old two-motor rumble: a pad RenHDrum does not claim, a missing `renhdrum.dll`, or the option
  switched off all behave exactly as before. The DLL ships in the release folder under the MIT
  license (see `licenses/`), so there is nothing to download or install.
* **Opt-in crash logging.** The launcher's Game tab has a **Crash log** setting, off by default.
  Turned on, the run's console output is written to
  `%APPDATA%\dream-recomp\logs\draconus-<timestamp>.log`, and a crash appends a report with the
  exception, the host stack as module-relative addresses and the guest frame, pc, pr and registers.
  A run that ends normally leaves the same file with its console output and the end-of-run report,
  which is often enough to describe a problem on its own. The newest ten logs are kept, and
  `--crash-log` is the engine flag the setting passes; with the setting off nothing is written and
  no handler is installed. The report names the build from `BUILD-INFO.txt` and the executable's
  SHA-1, and each release publishes a separate `DraconusRecomp-<version>-symbols.zip` with the
  matching linker map and `tools/symbolize.py`, so its `module+offset` stack becomes function names.
* **The launcher notices how the game ended.** It keeps the process handle and says "crashed with
  an access violation (0xC0000005)", "an uncaught C++ exception", "could not start", or the plain
  exit code, instead of leaving "Running" on screen. With Crash log on it names the newest report
  and offers the logs folder; a new **Open logs folder** button opens it at any time.

## 1.1.0 — 2026-11-18

The first update. Windows x64; the requirements and install steps are the same as 1.0, and the
launcher can now update itself in place.

### New

* **Field of view.** `--fov DEG` replaces the title's vertical field of view; the game's own is 90°,
  the launcher offers 60–120°, and the title TOML names the FOV constant at `0x0C098648`. Above 90°
  the game can cull geometry at the far screen edges, so models may pop in when the camera turns —
  the launcher warns under the slider. The aspect and the FOV are separate projection inputs, so
  `-Fov 75` composes with `-Aspect 21:9`, and the item wheel's projected 3D model is scaled back
  about the wheel so the item stays inside its ring at any FOV.
* **Brightness / gamma.** `--gamma VALUE` (0.5–2.0; 1.0 is the original) applies a display curve to
  the finished picture at presentation, and the frame counter's overlay takes the same curve. 1.0
  takes the exact original path, so the default present is byte-identical, and the guest framebuffer
  is untouched: F11 and F12 still capture the unmodified game. The launcher's **Brightness / gamma**
  slider is 50–200%, and `--screenshot-presented` shows the adjusted screen.
* **The launcher names its version and updates itself.** The window title and the left panel show
  the version, and **Check for updates** asks GitHub for the latest published release once a day (or
  whenever it is pressed). When one exists the button names the new version: the release's Windows
  zip is downloaded, checked against the SHA-256 the release publishes when it has one, unpacked,
  and installed in place. The player's disc path in `draconus.toml` is kept and everything under
  `%APPDATA%\dream-recomp` — settings, controller bindings and the memory card — is untouched. A
  PowerShell helper waits for the launcher to close before replacing the executable and its DLLs,
  holds the previous files until the copy has succeeded, and restores them if it has not. Source
  trees are sent to the releases page (their files come from git), and a read-only release folder
  gets the manual route instead. `--check-updates` prints the comparison without opening the window,
  and `--version` prints the current version.
* **Three levels, and an answer on character LOD.** The first three levels have been played end to
  end from the owner's own disc (1.0 covered two); later levels and the credits remain open. The
  character LOD that breaks up non-player characters beyond roughly six units is the retail game's
  own behaviour — Flycast submits the same reduced mesh — so the recomp is faithful rather than
  faulty. `docs/18-CHARACTER-LOD-INVESTIGATION.md` records the measurements and the five rejected
  causes; `DREAM_TRACE_TEXTURE` is the trace that came out of it.

### Upgrading from 1.0

Unzip over the old folder, or press **Check for updates** in the launcher. The disc path in
`draconus.toml` is kept and `%APPDATA%\dream-recomp` (settings, bindings, memory card) is untouched;
a pre-1.0 settings file is still read as a fallback.

### Known limitations

* **The play-through is not finished.** The first three levels are played; later levels, the credits
  and any coverage gap they expose remain (M7).
* **FOV above 90° can pop models** at the screen edges, because the game culls by its original FOV.
* **Character LOD** beyond about six units is the retail behaviour, not a recomp fault.
* **Windows x64 only**, unsigned executables, no game data; the 1.0 notes have the rest.

## 1.0 — 2026-11-17

The first public release. Windows x64.

### What 1.0 is

The game's own SH-4 code runs natively: it is translated ahead of time into C++, and the Dreamcast
hardware — GD-ROM, controllers, video, AICA sound and the memory card — is replaced by native code.
The launcher checks your dump against the known boot-executable hash and plays it; the boot program
is read from the disc, so the release carries no disc assets.

The first two levels have been played end to end from the owner's own disc. Later levels and the
credits are not yet verified — that is the open M7 work, and the one thing to know before starting a
full play-through.

### Highlights

* **Playable at real time.** The translated path is the default: real time with a window, and
  3–4.5x headless on the development machine (3.0x over 20,000 frames of gameplay), against the
  development interpreter's 0.25x. 9,126 functions (1,071,709 instructions) are translated.
* **A launcher that needs no Python or compiler.** `DraconusLauncher.exe` is a frozen build: pick a
  `.gdi` or `.chd`, verify it, choose resolution, widescreen, display mode, present rate and
  interpolation, CPU clock, audio device and volume, controls and engine path, then press **Play**.
* **Optional enhancements.** Hor+ widescreen and ultrawide (16:9, 21:9, custom) with the HUD, menus
  and loading screens handled; 1x–4x internal resolution; windowed, borderless and exclusive
  fullscreen; display-derived present rates, with frame interpolation for the extra presents; and a
  modern twin-stick control layout.
* **Controllers and rumble.** A pad is mapped on first plug-in, with an XInput fallback when SDL
  cannot open it. A jump pack is always attached and drives the pad's own rumble motors; enable
  **Options → JUMPPACK → PACK ON** in the game to feel it.
* **Saves that travel.** A windowed run attaches a standard 128 KB VMU card per user, created and
  formatted on first run, and the game's own Save and Load screens use it. The card opens in Flycast
  and a Flycast card opens here; the engine's `--vmu` takes an existing one instead.
* **Measured, not assumed.** Audio, the first frame and the in-game path are checked against Flycast,
  and the translated and interpreted paths are compared frame for frame. The numbers are under
  [Verification](#verification).

### Requirements

| Requirement | Note |
|---|---|
| Windows x64 | The only target; there is no Linux, macOS or 32-bit build. |
| A Vulkan-capable GPU driver | The renderer is Vulkan; `vulkan-1.dll` comes from the driver, not the bundle. |
| Your own dump | *Draconus: Cult of the Wyrm*, USA V1.000 (`F888` / `T-402`), `.gdi` with its tracks or `.chd`. |
| A gamepad | Optional; the keyboard works out of the box. |

### Install

1. Unzip the release folder anywhere. There is no installer and no admin rights are needed.
2. Run `DraconusLauncher.exe`, press **Browse...** and pick your dump — it is verified as soon as it
   is selected — then press **Play**.
3. Settings live in `%APPDATA%\dream-recomp\launcher.json`; the virtual memory card is
   `%APPDATA%\dream-recomp\saves\draconus\vmu_a1.bin`. The launcher's bottom bar opens both folders.

**Upgrading.** There is nothing to uninstall: replace the folder and keep your per-user data. The
launcher reads a pre-1.0 `%APPDATA%\DraconusRecomp\launcher.json` as a fallback, and old bindings are
migrated into `%APPDATA%\dream-recomp`, so settings and controls survive the move.

### Known limitations

* **The play-through is not finished.** Later levels, the credits and any coverage gap they expose
  are unverified (M7). The first two levels, including saving and loading, have been played.
* **Windows x64 only.** There is no Linux, macOS or 32-bit build, and no installer — the release is
  a folder you unzip.
* **A source build needs a GDI.** `dracdisc extract` does not decode CHD. The release runtime reads
  a `.chd` directly, and `chdman` converts one for a source build.
* **The executables are unsigned,** so Windows SmartScreen or an antivirus may warn.
  `BUILD-INFO.txt` names the commit the folder was assembled from.
* **No game data is included.** Disc images, extracted files, saves, screenshots and the generated
  C++ are not distributed; only the compiled program is.

### Verification

| Gate | Result |
|---|---|
| First frame (M3) | 600-frame determinism, F11 capture replay, and the first non-blank picture against Flycast's at **MAE 0.92** (threshold 16). |
| In-game (M5) | **0 untranslated calls over 8,200 frames** (60 s of gameplay); ten checkpoints compared with Flycast at **MAE 1.46–13.58** (threshold 16). |
| Audio (M6) | Ten seconds of menu music at **1.0000 sample correlation**, octave-band levels within **0.01 dB**; a 600-second run with no dropout that Flycast does not also have. |
| Translated vs interpreted | Same renders, controller traffic and byte-identical screenshots; PVR and Maple counters match. |
| Save / load | Owner saved in-game and loaded it back through the game's own VMU screens. |
| Play-through (M7) | First two levels played end to end; later levels and the credits are open. |

The emulated jump pack is always attached, so the title screen shows a "JUMPPACK OPERATIONAL" line
where Flycast shows none; the M3 pair is unaffected and the M5 title checkpoint stays within
tolerance.

### Under the hood

* **Engine.** `dream-recomp` at a pinned commit plus this project's engine patches (`patches/`),
  applied by `setup.ps1`. `docs/ENGINE-CHANGES.md` is the ledger with every trace and dead end.
* **Discovery.** Pointer-table discovery finds the code this title reaches through tables — 9,126
  functions instead of 3,285. The in-game work raised the constructor-scan cap and retried resume
  misses, taking a 60 s gameplay run to zero untranslated calls.
* **The translated-path crash.** A function-entry interrupt poll could deliver a context at a tail
  jump whose `PR` belonged to the jumper; resuming ran the epilogue twice and jumped to 0. The entry
  poll is off (`entry_polls = false`), and interrupts are still delivered at loop back-edges and
  call returns.
* **Renderer.** Textures the guest rewrites in video memory are decoded again (the VMU menu text,
  the intro background and the loading screen were one bug); a finished frame stays on the GPU for
  the presenter; widescreen overlays keep depth and move their projected models without squeezing
  them twice.
* **Audio.** The AICA path is verified against Flycast's SDL disk driver, so the comparison is a WAV
  diff rather than a loopback recording.
* **Packaging.** The launcher is frozen with PyInstaller and carries `dracdisc`; the boot program is
  read from the player's disc (GDI or CHD) and hash-checked; paths are UTF-8 and per-user data lives
  in one folder.

### Credits

*Draconus: Cult of the Wyrm* was developed by Treyarch and published by Crave Entertainment in 2000.
The engine is [`dream-recomp`](https://github.com/phobos665/dream-recomp). CHD reading comes from
libchdr; windowing, input and audio output come from SDL3; Flycast is the behavioural oracle every
fidelity gate is measured against. The launcher emblem is fan artwork for this project; see
`docs/LEGAL.md`.

### Licence and distribution

The project's code and the engine are GPL-2.0 (`LICENSE`); `docs/LEGAL.md` has the full policy and
`THIRD-PARTY-NOTICES.md` the bundled components. The release contains a machine translation of the
game's code but no disc assets — no textures, models, music, movies or extracted files — and you
must supply your own disc. The generated C++ is not published.

*Draconus: Cult of the Wyrm* is a trademark of its respective owners. This project is not
affiliated with, endorsed by or sponsored by Sega, Treyarch or Crave Entertainment.
