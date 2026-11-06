# Legal notes

This repository contains **no game code and no game data**. It contains research notes,
tooling, and a title configuration (addresses and settings only). Everything derived from
the disc — the extracted executable, any files, screenshots, saves — is produced on the
owner's machine and is ignored by git.

## What you must supply

A dump you made yourself from a disc you own:

* **Draconus: Cult of the Wyrm** (USA, `F888`, licence `T-402`, V1.000, 2000-05-19),
  as `.gdi` with its track files (or a `.chd`).
* Nothing else. The engine replaces the BIOS and the GD-ROM filesystem with native
  code, so no boot ROM is needed. (`dream-recomp` supports an optional `--bios` for
  system fonts; this project does not require it.)

`dracdisc verify` checks the boot executable against a known hash and refuses anything
else, so a wrong or damaged dump fails immediately instead of producing nonsense.

## What is in the repository, and under what licence

| Part | Licence | Notes |
|---|---|---|
| This project's own code (`tools/`, `game/`, scripts) | GPL-2.0 | See `LICENSE` |
| `engine/` (not committed) | GPL-2.0 | `phobos665/dream-recomp`, fetched by `setup.ps1` at a pinned commit |
| `third_party/libchdr` (not committed) | BSD-3-Clause | fetched by `setup.ps1`; not pinned |

The project is a derivative work of `dream-recomp`, so the combined work is GPL-2.0 and
a distributed binary must be accompanied by its source. That is the intended model for
this project: non-commercial preservation, with the build reproducible from a public
clone plus the user's own disc.

## What must never be published

* The disc, any track file, or any extracted file (`1ST_READ.BIN`, `.PVR`, `.IMG`, …).
* Generated C++ from the translator — it is a derivative of the game's code.
* Screenshots or video captures of the running game (guest pixels).
* Saves, VMU images, or a boot ROM.
* The Die by the Sword GOG installation used here as a format reference.

`.gitignore` enforces the mechanical cases; the rest is a review rule.

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
