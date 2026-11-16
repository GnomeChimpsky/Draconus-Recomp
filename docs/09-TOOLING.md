# 09 — Tooling and environment

## Environment as surveyed (2026-11-04, this machine)

| Tool | State | Version / path |
|---|---|---|
| Visual Studio 2022 Build Tools (`cl.exe`) | present | `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools` |
| CMake | present | 3.31.12 |
| Ninja | present | bundled with clang toolchain |
| Clang | present | 22.1.8 (x86_64-w64-windows-gnu) |
| Python | present | 3.14.3 (note: very new) |
| .NET SDK | present | — |
| Node.js | present | — |
| **git** | **missing** | install first — blocks cloning anything |
| **Vulkan SDK + `glslc`** | **missing** | required for the renderer |
| SDL3 | missing | obtainable via CMake FetchContent |
| `chdman` | missing | only needed for the `.chd` convenience path |
| Ghidra | missing | needed for asset/loader reverse engineering (M4+) |

Recommendation: create a **Python 3.12 virtual environment** for tooling. Python 3.14
is newer than most third-party wheels are built for; the M1 tool itself is stdlib-only
and currently runs fine on 3.14.

## Minimum to reach M2

1. `git` (install via winget or the Visual Studio installer).
2. Vulkan SDK (renderer); `glslc` on `PATH`.
3. Clone `dream-recomp` with submodules; `pip install -e tools/dcdisc`.
4. `cmake -S . -B build -DDREAM_DEV_INTERPRETER=ON`, build, `ctest`.

## To reach M3+ (parity work)

* A local **Flycast** build to act as the oracle (GPL-2.0).
* `ffmpeg` for audio/video capture comparisons.
* Disk space: the dump is ~1.2 GB; extracted data ~1 GB; builds and captures add
  several GB. Keep `work/` on the same drive as the dumps.

## This workspace's tools

`tools/draconus-disc` — stdlib-only Python, no dependencies:

```powershell
cd tools\draconus-disc
python -m dracdisc verify   "<retail .gdi>"     # fail closed on wrong dump
python -m dracdisc inspect  "<retail .gdi>"     # tracks, volume, boot hash, inventory
python -m dracdisc manifest "<retail .gdi>" -o ..\..\work\manifest.json
python -m dracdisc extract  "<retail .gdi>" -o ..\..\work\extracted [--all] [--force]
python -m unittest discover -s tests
```

Design constraints honoured by the tool:

* No third-party packages (works offline, no supply chain).
* No writes outside `work/`.
* Audio tracks are never read as user data.
* Wrong dumps are refused by SHA-256 rather than half-processed.

## Launcher (tools\launcher.py, tools\launcher.bat)

A tabbed settings window: the project's emblem, author credit and repository link on the left,
Game / Graphics / Audio on the right, and Play. It builds the boot command line from the
settings through a pure `build_command`, so every setting the window changes is also reachable from
the command line:

| tab | option | flag |
|---|---|---|
| Game | game disc | the `.gdi`/`.chd` picker; the disc is checked before Play is enabled |
| | controls | `--controls classic/modern` |
| | engine path | `--interpret` |
| Graphics | CPU clock | `--sh4-clock 200..800` (MHz; 200 is the console, more cycles per frame) |
| | resolution | `--scale 1..4` (also the window size) |
| | widescreen | `--aspect 16:9`, `21:9`, `W:H` |
| | display mode | `--display windowed/borderless/exclusive` (`--fullscreen` = borderless) |
| | present rate | `--present-rate 60/120/144` (capped to the display's refresh) |
| | frame interpolation | `--frame-interpolation` (at 120/144 Hz, experimental) |
| | VSync off | `--present-mode immediate` |
| | frame counter | `--fps` |
| Audio | sound off | `--no-audio` |
| | volume | `--audio-volume 0..100` |
| | output device | `--audio-device NAME` (the engine lists them with `--list-audio-devices`) |
| | buffer / latency | `--audio-buffer 93/186/372` ms |

Saving and loading are the game's own: the launcher has no card settings and attaches no card, so a
windowed launch gets the engine's per-user card. Its bottom bar's **Open saves folder** and **Open
settings folder** buttons open that card's folder (`%APPDATA%\dream-recomp\saves\draconus`) and the
launcher's own (`%APPDATA%\DraconusRecomp`).

Settings persist in `%APPDATA%\DraconusRecomp\launcher.json`. `--selftest` checks the command each
setting produces without opening a window; `--smoke` (optionally `--shot FILE`) builds the window and
exits, which is also how the layout is reviewed. The tabs are one table (`TABS`) plus their keys in
`DEFAULTS`, so a new option is a few lines rather than new layout code.

## Frozen launcher (release)

`tools\build-launcher.ps1` builds the launcher a player runs, with no Python on their machine:

```powershell
tools\build-launcher.ps1                        # work\launcher-dist\DraconusLauncher
tools\build-launcher.ps1 -Dist D:\out -Clean    # elsewhere, fresh environment
```

It pins Python 3.11 and PyInstaller 6.22.3, keeps its environment and intermediates under
`work\launcher-build\`, and writes an onedir build (onefile re-extracts ~50 MB to `%TEMP%` on every
launch and is the variant antivirus dislikes most). The frozen launcher looks for `draconus.toml`
beside itself or one folder below, runs `DraconusRecomp.exe` from that folder, and verifies the disc
with the bundled `dracdisc` (GDI or CHD) — no system Python. The chosen image is written into that
TOML. `--selftest` and `--smoke` still work; screenshots are skipped because Pillow is not bundled.

## Audio checks (M6)

`tools/audio-check.py` measures WAV captures with numpy/scipy: format and level, a per-second RMS
table, non-silent runs, octave-band levels, dominant peaks and spectral correlation. It also converts
the raw PCM that Flycast's SDL disk driver writes.

```powershell
python tools\audio-check.py info      work\m6\ours_10min.wav
python tools\audio-check.py align     work\m6\flycast_90s.wav work\m6\ours_90s.wav
python tools\audio-check.py compare   work\m6\flycast_90s.wav work\m6\ours_90s.wav --gate
python tools\audio-check.py gaps      work\m6\ours_10min.wav --reference work\m6\flycast_10min.wav --gate
python tools\audio-check.py raw2wav   work\fc.raw work\fc.wav
```

The ten-second comparison aligns the two captures from their loudness envelopes, refines to the
sample, then reports sample correlation, sample difference in 16-bit LSB, per-frame spectral
correlation, octave-band differences, dominant-peak agreement and spectral centroid. The gate is
`--gate`; without it the command only reports.

`tools/m6-check.ps1` runs the whole milestone: it captures our 90 s and 600 s runs, captures the
Flycast reference if it is missing, and calls `compare` and `gaps --reference`. The reference
capture uses `tools/flycast-m6.ps1`, which drives Flycast with its Lua scripting and records through
SDL's disk audio driver:

```powershell
tools\flycast-m6.ps1 -Seconds 600 -Out work\m6\flycast_10min.wav
tools\m6-check.ps1
```

`SDL_AUDIODRIVER=disk` plus `SDL_DISKAUDIOFILE` makes Flycast write raw s16le stereo 44.1 kHz; no
loopback device and no system sound is involved. The generated Lua file presses START at guest frame
1800 and A at 2100, waits 30 frames per press, and exits at the requested frame. The schedule gives
Flycast's slower boot and longer title screen time to settle before the same menus/gameplay ours
reaches at frames 1150 and 1400.

## M5 gate (tools\m5-check.ps1)

```powershell
tools\m5-check.ps1                 # zero-untranslated run + 10 Flycast checkpoints
tools\m5-check.ps1 -SkipFlycast    # the zero-untranslated half alone
tools\m5-check.ps1 -Threshold 12   # tighter frame diff
```

The schedule reaches gameplay at about frame 4,600 and runs to 8,200, so the last 60 s are in-game.
The first half runs it with `DREAM_TRACE_UNTRANSLATED=1` and fails unless the report says
`untranslated call targets: 0`. The second half renders checkpoints from our display lists, then
runs `tools/m5_flycast_capture.py`: a generated Lua script presses the same buttons on the same
guest frames, freezes at each checkpoint in a busy-wait, and the host copies Flycast's client area
with `PrintWindow` so the frame is held still and window focus cannot change it. `tools/m5_frame_diff.py`
prints the mean absolute RGB difference and fails above the threshold (16 by default; correct pairs
here measure 1.5-13.6, wrong-screen pairs 27-38). Artifacts and side-by-side review images are under
`work\m5-check`.

Flycast is found at `$env:FLYCAST_EXE`, the local install, or `tools\flycast\flycast.exe`; override
with `-Flycast PATH`. The engine must be built with patches 0001-0003 applied.

## Engine build (already staged under `engine/`)

The engine archive has **no submodules**, and CMake hard-fails without
`third_party/libchdr`, so fetch it once:

```powershell
curl.exe -L -o libchdr.zip https://codeload.github.com/rtissera/libchdr/zip/refs/heads/master
# expand the inner folder into engine\third_party\libchdr
```

Configure and build with MSVC in a Developer shell (or via `vcvars64.bat`):

```powershell
cmd /c "`"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat`" >nul && `
  cmake -S engine -B engine/build -G Ninja -DCMAKE_BUILD_TYPE=Release `
        -DDREAM_DEV_INTERPRETER=ON -DDREAM_RENDERER=OFF -DDREAM_BUILD_TESTS=OFF -DDREAM_WERROR=OFF"
cmd /c "...vcvars64.bat... && cmake --build engine/build --target draconus_boot --parallel"
```

`-DDREAM_RENDERER=OFF` is required on this machine (no Vulkan SDK/SDL3) and needs the
local patch in `docs/ENGINE-CHANGES.md` 001.

Measured costs on this machine (12 cores, MSVC 19.44):

| Operation | Time |
|---|---|
| call-graph discovery | 0.1 s |
| + pointer-table discovery | 0.6 s |
| + aggressive sweep | **>15 min, no completion** |
| emit, 500 functions | 0.2 s |
| emit, 14,913 functions | 308 s, **no output file** (engine defect) |

## Environment gotchas found while building it

* Some sandboxed environments deny access to the system temp directory. Tests
  therefore create scratch directories inside the workspace with `os.makedirs`.
* **Never use `tempfile.mkdtemp` in this workspace.** Directories created by
  `mkdtemp` receive an ACL that the sandbox cannot modify, so they cannot be listed or
  deleted afterwards (`Access is denied`, and `icacls` cannot fix it either). Two such
  directories are currently stranded under `tools/draconus-disc/.tmp` and
  `.../scratch`; they are ignored by `.gitignore` and harmless, but they are a good
  argument for keeping test scratch paths explicit.
* PowerShell treats a native program's stderr as an error record; `unittest` prints
  progress to stderr, so a green run can still show a non-zero shell exit. Check the
  `OK (n tests)` line, not the exit code, when running tests through PowerShell.

## Running the engine's test suite here

```powershell
cmake -S . -B build-test -G Ninja -DCMAKE_BUILD_TYPE=Release `
      -DDREAM_DEV_INTERPRETER=ON -DDREAM_RENDERER=OFF -DDREAM_BUILD_TESTS=ON -DDREAM_WERROR=OFF
cmake --build build-test --parallel
$env:TMP = "$PWD\..\work\tmp"; $env:TEMP = $env:TMP   # the sandbox denies %TEMP%
ctest --test-dir build-test --output-on-failure
```

Without the `TMP`/`TEMP` override, the memcard, CDI and symbol-table tests fail (they create
files under `%LOCALAPPDATA%\Temp`, which this environment denies); one of them crashes with
`0xC0000409`. That is the environment, not the code.

## Emulation speed (re-measured 2026-11-11)

| configuration | guest time | host time | speed |
|---|---|---|---|
| translated, headless, 600 frames | 9.84 s | 2.30 s | **4.2x** |
| translated, headless, 1,800 frames | 29.86 s | 7.54 s | **3.9x** |
| translated, window, 1,800 frames | 29.86 s | 29.9 s | **1.0x** (vsync) |
| translated, window, 5,000 frames, menu scene | 83.24 s | 83.19 s | **1.0x** |
| translated, headless, 20,000 frames, gameplay | 333.5 s | 184.9 s | **1.8x** |
| `--interpret`, headless, 600 frames | 9.84 s | 38 s | 0.26x |
| `--interpret`, in-game with input, 900 frames | 14.84 s | 67.1 s | 0.22x |

**The translated path is the fast path now.** The decisive change on 2026-11-11 was turning on
pointer-table discovery (`pointers = true`): this title reaches most of its code through tables, and
without it 3,285 functions were translated and the rest ran in the development interpreter. It now
translates 9,126 functions (~110 MB of generated C++, about five minutes to build), and untranslated
calls in a 5,000-frame scene fell from 3.3 million to 1,412; patch 037 later took a 60 s in-game run
to **zero**. Inlining `DcMemory`'s RAM fast path and
moving the presenter's readback to cached host memory did the rest. Details in
`docs/ENGINE-CHANGES.md`; `DREAM_TRACE_FRAME_TIME` and `DREAM_TRACE_UNTRANSLATED` are the diagnostics
that found the last two.

`play-draconus.bat` defaults to the translated path; `-Interpret` selects the development
interpreter, which is kept as the reference and the bring-up tool (about 0.25x).

The levers in order of payoff:

1. Translation coverage for scenes the table pass does not reach — `tools\diagnose-speed.bat` names
   what a slow scene is missing.
2. Reduce the guest workload (not possible without changing the game).
