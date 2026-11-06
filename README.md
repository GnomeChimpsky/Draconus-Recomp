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

## Play it

```powershell
.\play-draconus.bat
```

That launches the recompiled build with a window, using the development interpreter for
game logic (the machine-translated path still faults at `0x8C001006`; see
`docs/ENGINE-CHANGES.md`). It needs `engine/build-render` to exist and the user's own
disc at the path in `engine/games/draconus/draconus.toml`. Extra arguments pass through,
e.g. `.\play-draconus.bat --max-frames 600 --rtc-seed 1000000 --screenshot-at 500`.

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

Status: the retail game **boots and renders** — Treyarch logo, title screen, VMU
prompt, and an in-game 3D scene (red sky, terrain, creatures, siege engine) at 640×480
through Vulkan on an RTX 3080, deterministically, from the user's own disc. Translation
covers 89.7 % of code bytes (3,285 functions); the translated path now gets **54 frames**
before stopping at `0x60000040` (it previously died at 29 frames on a hook-marker bug,
fixed in `docs/ENGINE-CHANGES.md` patch 003). Full playthroughs still use `--interpret`
via `play-draconus.bat`. The earlier retail boot failure was a bug in our own
multi-sector disc reader, fixed and regression-tested. See `docs/11-M2-RESULTS.md`.

## Licence

GPL-2.0 (`LICENSE`), because the project is a derivative work of `dream-recomp`. No game
code or data is included or distributed; you supply your own disc. Read `docs/LEGAL.md`
before publishing anything from this tree.
