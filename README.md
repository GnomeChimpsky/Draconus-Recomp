# DraconusRecomp

A native Windows x64 static recompilation of **Draconus: Cult of the Wyrm**
(Dreamcast, 2000, developed by Treyarch and published by Crave Entertainment; USA V1.000,
`F888` / `T-402`), built on [`dream-recomp`](https://github.com/phobos665/dream-recomp).

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

This repository deliberately does **not** contain the engine. `setup.ps1` fetches it at a
pinned commit, installs the title configuration over it, and builds:

```powershell
git clone <your fork> DraconusRecomp
cd DraconusRecomp
.\setup.ps1
```

Then edit `engine\games\draconus\draconus.toml` → `[disc] image` to point at your own
dump, and run `.\play-draconus.bat`. See `docs/09-TOOLING.md` for the Vulkan SDK and SDL3
requirements, and `docs/LEGAL.md` for what you must supply.

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

That launches the recompiled build with a window, using the development interpreter for
game logic. It verifies the disc path before starting and says so plainly if the dump is
missing or was never imported.

```powershell
.\play-draconus.bat                              # window, interpreter path
.\play-draconus.bat -Scale 2                     # 1280x960
.\play-draconus.bat -Translated                  # the incomplete translated path
.\play-draconus.bat --max-frames 600 --rtc-seed 1000000 --screenshot-at 500
```

The machine-translated path stops after about 54 frames at guest `0x60000040`. That is a
known, traced defect in the runtime's task switch, not a crash of the build:
`docs/ENGINE-CHANGES.md` has the chain, and the differential harness shows the translated
code itself agreeing with the interpreter (`0 disagreements` over the run).

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

Status: the retail game **boots, renders and plays** — Treyarch logo, title screen, VMU
prompt and an in-game 3D scene (red sky, terrain, creatures, siege engine) through Vulkan at
640x480, deterministically, from the owner's own disc. Translation covers 89.7 % of code
bytes (3,285 functions).

The development interpreter path (`--interpret`) is what `play-draconus.bat` uses and it is
solid. The *translated* path reaches 54 frames and then stops: a task switch resumes on a
corrupted context (`ldc.l @r15+,sr` reading a pointer where a saved SR belongs, at
`0x8C233756`). The chain is traced end to end in `docs/ENGINE-CHANGES.md`, and three engine
fixes have been contributed along the way — hook dispatch at the interpreter's fetch boundary,
an instruction-level tracer, and a `--replay` false-positive fix that now lets the
differential harness report **0 disagreements over a whole 400-frame run**, exonerating the
code generator. What remains is the runtime's interrupt/task-switch path.

The earlier retail boot failure was a bug in this project's own multi-sector disc reader,
fixed and regression-tested. See `docs/11-M2-RESULTS.md`.

## Licence

GPL-2.0 (`LICENSE`), because the project is a derivative work of `dream-recomp`. No game
code or data is included or distributed; you supply your own disc. Read `docs/LEGAL.md`
before publishing anything from this tree.
