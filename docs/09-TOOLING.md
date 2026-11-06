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

## Emulation speed (measured 2026-11-06)

| configuration | guest time | host time | speed |
|---|---|---|---|
| `--interpret`, headless, title/idle, 600 frames | 9.84 s | 39.5 s | **0.25x** |
| `--interpret --window` (vsync), 300 frames | 4.83 s | 19.4 s | 0.25x |
| `--interpret --window --present-mode immediate` | 4.83 s | 18.9 s | 0.26x |
| `--interpret`, in-game with input, 900 frames | 14.84 s | 67.1 s | **0.22x** |
| translated path (stops at frame 54, so boot only) | 0.74 s | 0.99 s | 0.75x |

**This is expected.** `play-draconus.bat` defaults to `--interpret`, which runs every guest
instruction through the development interpreter — a bring-up tool, not a shipping core. It
costs roughly 4-5x real time, i.e. about 13 fps at 60 Hz.

Present mode makes no difference (vsync 19.4 s vs immediate 18.9 s), so the cost is CPU, not
presentation. Scaling the window will not help either.

The fix is the translated path: emitted C++ runs at native speed (the boot segment above is
0.75x even while the interpreter is warming up, and it would be far faster in-game). That path
currently stops at frame 54 on the task-switch defect (`docs/ENGINE-CHANGES.md`), so speed and
playability are the same open problem.

If the interpreter has to stay in use for a while, the levers in order of payoff are:

1. Fix the translated path — the only one that reaches real-time.
2. Profile and optimise the interpreter's dispatch/memory path (a decode cache and inlined
   memory access are the usual wins; expect tens of percent, not multiples).
3. Reduce the guest workload (not possible without changing the game).
