# Draconus-Recomp

A native Windows x64 static recompilation of **Draconus: Cult of the Wyrm**
(Dreamcast, 2000, developed by Treyarch and published by Crave Entertainment; USA V1.000,
`F888` / `T-402`), built on [`dream-recomp`](https://github.com/phobos665/dream-recomp).

The game is playable, and the recompiled path is the fast one: 1.2x real time headless, about 0.8x
with a window at 1,800 frames. The development interpreter remains as a reference and a bring-up
tool.

The game's SH-4 code is translated ahead of time into C++, and the Dreamcast hardware
(file system, controllers, video, sound, memory card) is replaced by native code. The
result runs from the user's own disc — no game data is included or distributed.

This repository holds the research, the disc tooling, the title configuration and the
engine fixes. The engine itself is fetched by `setup.ps1` at a pinned commit, so it is
not vendored here.

## Where the work stands

Audio baseline: `docs/13-M6-AUDIO-BASELINE.md` (what plays, what does not, and why).


`docs/12-HANDOVER.md` is the state of play: what works, what does not, the list of local
engine changes, and the next three tasks. The engine-side findings are in
`docs/UPSTREAM-REPORT.md` (one proposed fix, one fixed harness bug, one open fault), and
`docs/ENGINE-CHANGES.md` is the running ledger with every trace and dead end.

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

## Graphical launcher

```powershell
tools\launcher.bat
```

Pick a `.gdi`, press **Verify** (it refuses anything that is not the USA V1.000 release and
writes the config on success), choose a window scale and a path, press **Play**. The logic
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

Both paths run the game; the translated one is about five times faster (1.2x real time headless,
0.8x windowed at 1,800 frames, against the interpreter's 0.25x) and their guest state matches —
same renders, same controller traffic, byte-identical screenshots. The renderer's per-frame draw
cost is what keeps the windowed path just under real time; see `docs/12-HANDOVER.md`.

Controls: arrows = d-pad, `Z` `X` `A` `S` = A, B, X, Y, Enter = Start, `Q`/`W` = triggers,
`F1` rebinds, `F10` frame counter, `F12` screenshot, Escape quits.

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

Status: **playable**. The retail game boots, plays its movies, shows its menus, loads into
gameplay and responds to input — menu navigation and character movement both work — from the
owner's own disc, deterministically. Translation covers 89.7 % of code bytes (3,285
functions).

**Speed** went from 0.15x to **1.2x real time headless** at 1,800 frames (0.8x windowed) by seeding
the fifteen call targets that were taking 99 per cent of the interpreter boundary traffic and
inlining the RAM fast path in the runtime (`docs/ENGINE-CHANGES.md`). The remaining windowed gap is
the renderer's per-frame draw cost. Discovery and emission still do not scale to the whole binary,
so scenes that reach untranslated code will pay for it until that is fixed.

Audio works in menus and gameplay but not on the title screen, and the title's silence is
unexplained (`docs/13-M6-AUDIO-BASELINE.md`). Visual comparison against Flycast has started:
the title screen matches apart from VMU state and aspect (`docs/14-M3-M6-FLYCAST-REFERENCE.md`).

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
