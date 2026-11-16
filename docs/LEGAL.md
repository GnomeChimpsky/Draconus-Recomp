# Legal notes

This is a non-commercial preservation project. It is not affiliated with, endorsed by, or
sponsored by Sega, Treyarch, Crave Entertainment, or the owners of the *Draconus* trademark.

## What you must supply

A dump you made yourself from a disc you own:

* **Draconus: Cult of the Wyrm** (USA, `F888`, licence `T-402`, V1.000, 2000-05-19),
  as `.gdi` with its track files (or a `.chd`).
* Nothing else. The engine replaces the BIOS and the GD-ROM filesystem with native
  code, so no boot ROM is needed. (`dream-recomp` supports an optional `--bios` for
  system fonts; this project does not require it.)

`dracdisc verify` checks the boot executable against a known hash and refuses anything
else, so a wrong or damaged dump fails immediately instead of producing nonsense.

Keep the dump outside this repository, or under a `dumps/` folder: `.gitignore` covers that name
and the common disc extensions, and nothing derived from the disc is ever committed.

## The source repository

This repository contains **no game data**: no disc image, track files, extracted files, saves,
screenshots, or generated C++ translation. It contains the project's own tooling, title
configuration (addresses and settings only), engine patches, documentation, and the artwork used
by the launcher and this README. Everything derived from the disc is produced on the owner's
machine and is ignored by git.

## The compiled release

A public release may include prebuilt binaries: `DraconusRecomp.exe`, the frozen
`DraconusLauncher`, `SDL3.dll`, the Visual C++ runtime DLLs, and the title TOML. A compiled
binary is not the same thing as the source repository:

* It contains the project's engine code and a machine translation of the game's SH-4 program,
  generated from the owner's own disc. It contains **no disc assets** — no textures, models,
  music, movies, or extracted `1ST_READ.BIN`. The player still supplies their own disc.
* It exists so a player can run the project without installing a compiler or Python. The
  generated C++ translation is **not published**; only the compiled program is distributed.
* The engine and this project's patches are GPL-2.0 and their source is in this repository. The
  compiled release is a combined work that also contains translated game code. Anyone
  redistributing it must make their own assessment of the rights in that game code and comply
  with GPL-2.0 for the engine portions. This document states the project's distribution policy;
  it is not legal advice.
* A release bundle must include `LICENSE`, this file, `THIRD-PARTY-NOTICES.md`, and a link to
  this repository. Do not add a disc image, extracted files, saves, screenshots, or generated
  C++ to it.

`tools/build-release.ps1` assembles the release and refuses common game-data extensions. The
release tree must not contain an `extracted/` directory: the runtime reads the boot program from
the player's own disc.

## Artwork

The launcher emblem (`tools/launcher-emblem.png`), the README header image
(`Draconus Recomped Emblem light.png`), and the frozen launcher's bundled copy are a fan-made
title treatment that incorporates the *Draconus* wordmark. They identify this project; they are
not disc data and the project claims no ownership of the wordmark or the game. The wordmark and
the game are trademarks of their respective owners. The artwork must not be reused separately
from this project. If a rights holder asks for its removal, remove it from the repository and
from any release.

## What is in the repository, and under what licence

| Part | Licence | Notes |
|---|---|---|
| This project's own code (`tools/`, `game/`, scripts) | GPL-2.0 | See `LICENSE` |
| `engine/` (not committed) | GPL-2.0 | `phobos665/dream-recomp`, fetched by `setup.ps1` at a pinned commit |
| `third_party/libchdr` (not committed) | BSD-3-Clause | fetched by `setup.ps1` |
| Launcher/README artwork | Project fan artwork | See **Artwork** above |

The project is a derivative work of `dream-recomp`, so the combined work is GPL-2.0 and a
distributed binary must be accompanied by the corresponding source for the GPL-covered parts.
That source is this repository plus the pinned engine and its patches. The translated game code
is the part that is not published as source; the binary release exists instead of publishing it.

## Third-party components

The frozen launcher and the game executable include third-party components. Their notices and
licences are recorded in `THIRD-PARTY-NOTICES.md`, which ships beside this file. At minimum the
release contains:

* SDL3 (zlib licence) and the Vulkan loader supplied by the player's GPU driver.
* Python 3.11, Tcl/Tk, OpenSSL and the PyInstaller bootloader in the frozen launcher.
* The Microsoft Visual C++ runtime DLLs, redistributed under Microsoft's redistributable terms.
* The engine's libraries, including libchdr and its bundled codecs.

## What must never be published

* The disc, any track file, or any extracted file (`1ST_READ.BIN`, `.PVR`, `.IMG`, …).
* Generated C++ from the translator — it is a derivative of the game's code.
* Screenshots or video captures of the running game (guest pixels).
* Saves, VMU images, or a boot ROM.
* Any release tree containing `extracted/`, a `.gdi`/`.chd`, or a save/capture.

The compiled `DraconusRecomp.exe` described above is the project's deliberate release artifact;
it is not a licence to publish the extracted files or the generated source. `.gitignore`
enforces the mechanical cases; the rest is a review rule.

## Relationship to other projects

`docs/04-REFERENCE-REPOS.md` records what was studied and the boundary rules. In short:
`SARecomp`/KatanaRecomp and `voldorium` are read as **references only** — no code is
copied — and their licences (none, and a bespoke non-commercial one) are respected.
`dream-recomp` is used as the licensed base. Flycast is the behavioural oracle.

## Trademarks

*Draconus: Cult of the Wyrm* is a trademark of its respective owners; the game was
developed by Treyarch and published by Crave Entertainment. Dreamcast and Sega are
trademarks of Sega Corporation. This project is not affiliated with, endorsed by, or
sponsored by any of them.
