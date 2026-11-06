# 06 — Proposed architecture

## Layers

```
+---------------------------------------------------------------+
| launcher (port/)  disc import, settings, VMU manager, updates |
+---------------------------------------------------------------+
| port layer        native input, widescreen/HUD policy,        |
|                   frame pacing, subtitles, texture packs      |
+---------------------------------------------------------------+
| game code         game/ hooks & overrides; games/draconus/    |
| (generated C++)   TOML: addresses, seeds, relocations         |
+---------------------------------------------------------------+
| engine            dream-recomp (pinned): SH-4 translator,     |
|                   memory, PVR2→Vulkan, AICA/ARM7, Maple,      |
|                   HLE BIOS + GD-ROM                           |
+---------------------------------------------------------------+
| data              the user's own disc (never in the repo)     |
+---------------------------------------------------------------+
```

## Repository layout

```
DraconusRecomp/
  engine/                 dream-recomp at a pinned commit (subtree/submodule)
  games/draconus/         draconus.toml
  game/                   our hooks, symbol names, overrides
  port/                   launcher, input, widescreen, settings, packaging
  tools/draconus-disc/    dump validation & extraction (built first)
  tools/draconus-assets/  .IMG/.PVE/.PFE/.TPM/.PVR converters (later)
  tests/                  unit, golden manifests, oracle and playthrough scripts
  docs/                   ADRs, engine-change ledger, reference notes
  work/                   generated: extracted/, generated/, build/  (ignored)
```

## Title configuration (from the verified dump)

```toml
[game]
id      = "draconus"
title   = "Draconus: Cult of the Wyrm"
region  = "U"
product = "F888"          # licence T-402, dev code T40203N
binary.path         = "extracted/fs/1ST_READ.BIN"
binary.load_address = 0x8C010000
binary.link_address = 0x0C010000
binary.entry        = 0x8C010000
```

The boot file's SHA-256 is enforced by `dracdisc verify` before it is handed to the
translator, so a wrong dump fails early with a clear message rather than producing
nonsense coverage numbers.

## Data flow at build time

1. `dracdisc verify` — refuse anything that is not `a59ff87c…`.
2. `dracdisc extract` — boot program + (optionally) the ISO tree into `work/`.
3. Translator — emits one C++ function per guest function plus a coverage report.
4. CMake — builds game module + runtime.
5. Tests — headless determinism, frame hashes, oracle diffs.

## Data flow at run time

* Guest memory is the real address map (16 MB RAM, 8 MB VRAM) — game code keeps using
  its original addresses.
* BIOS and GD-ROM are HLE-replaced; file reads are served from the user's disc image.
* PVR2 display lists are decoded and drawn through Vulkan; the software renderer is
  the reference for parity checks.
* AICA runs the game's own ARM7 program; the SH-4 side sees the emulated registers.

## Rules for the tree

1. No disc data, no generated code, no BIOS, no SDK headers. CI audit script.
2. `engine/` is never hand-edited; fixes are patches recorded in
   `docs/ENGINE-CHANGES.md` and offered upstream.
3. Every title-specific address lives in `games/draconus/`, never in the engine.
4. `work/` is disposable: deleting it and re-running the two commands above must
   reproduce the manifest byte-for-byte.

## Why these boundaries

* Keeping the engine pristine makes upstream sync possible in a project that will
  live for years.
* Keeping the port layer separate means enhancements never contaminate fidelity
  tests: the "Original" profile must be provably the untouched path.
* Keeping tools outside the build means the disc can be inspected even when the game
  build is broken.
