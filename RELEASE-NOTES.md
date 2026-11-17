# Release notes

Draconus-Recomp is a native Windows x64 static recompilation of *Draconus: Cult of the Wyrm*
(Dreamcast, 2000, developed by Treyarch and published by Crave Entertainment). It runs from your own
disc and ships no game data. The [README](README.md) is the manual; the
[quick start](README.md#quick-start) is the shortest way in.

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
