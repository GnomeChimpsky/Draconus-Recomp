# 03 — Lineage: Treyarch, *Die by the Sword*, and *Draconus*

## Primary sources

* **Draconus: Cult of the Wyrm** — hack-and-slash developed by **Treyarch**, published
  by **Crave Entertainment**, Dreamcast, 2000; released in Europe as *Dragon's Blood*;
  described as a **spiritual sequel to Treyarch's *Die by the Sword***.
  ([Wikipedia summary](https://en.wikipedia.org/wiki/Draconus:_Cult_of_the_Wyrm))
* **Die by the Sword** — swordfighting action-adventure by **Treyarch**, published by
  **Interplay** under its Tantrum Entertainment imprint on **1998-03-27**; famous for
  independently controlled movement and sword arm.
  ([Wikipedia summary](https://en.wikipedia.org/wiki/Die_by_the_Sword))

## Machine evidence from this dump

| Observation | Where | What it shows |
|---|---|---|
| Internal root path `\die2\` (`\die2\current.img`, `\die2\data\…`) | boot program strings | the engine's project name is **DIE2** — "Die by the Sword 2" |
| Prototype volume id `DIE21` | prototype PVD | the prototype literally identifies as DIE2 |
| Windows backslash paths throughout | boot program strings | PC codebase carried to Dreamcast |
| `InterplayCreditsText` **and** `CraveCreditsText` | boot program strings | both publishers are credited in-game |
| `ATD`, `sword` strings | boot program | shared terminology/data with the PC title |
| `.ATD` / `.DMV` files in the GOG *Die by the Sword* install | this workspace | the PC engine used `.ATD` data files and `.DMV` move files |

The two credit strings are the strongest single piece of evidence: a Dreamcast-only
game would not credit Interplay, and Draconus does.

## What that means for the port

1. **Shared data vocabulary.** The PC game's `.ATD` containers and `.DMV` move files
   are likely ancestors of Draconus's `.IMG`/`.PFE` structures. The GOG install is a
   legitimate format reference (the user owns it) and should be used before any
   hand-reverse-engineering.
2. **The engine is a PC engine with a Dreamcast back-end.** Expect:
   * little-endian assumptions that happen to match;
   * Windows-ish path handling and file-layer indirection;
   * engine code that was already portable, so game logic is comparatively
     well-behaved and the console-specific code is concentrated in the SDK layer.
3. **Content pipeline leftovers are documentation.** `\die2\merger.txt`,
   `\die2\dump\scriptdump.txt`, `onscreen_errors.txt`, `frameinfo.txt` describe how
   content was built and debugged; they are clues for the asset work.

## Correction recorded for the record

An early automated scan appeared to show "Terra" (suggesting the studio *Terra Nova*).
That was a false positive: every hit was `TERRAIN` (`TERRAIN MEM`, `AFFECTS_TERRAIN`).
The developer is **Treyarch**. This is exactly the class of mistake the
"verified vs claimed" discipline exists to prevent, so it is documented rather than
quietly fixed.

## Prototype vs retail

| | Retail (supported) | Jan-2000 prototype |
|---|---|---|
| Volume id | `DRACONUS1` | `DIE21` |
| Product code | `F888` | `E8A9` |
| IP.BIN version | `V1.000` | `V1.001` |
| Region | `U` (USA) | `JUE` |
| IP.BIN date | 2000-05-19 | 1999-08-20 |
| ISO inventory | 3,690 files / 60 dirs (936.6 MB) | 3,208 files / 56 dirs (935.1 MB) |

Two honest notes. First, the folder is named "Jan 27, 2000 prototype" but the
IP.BIN inside it is dated 1999-08-20 — the folder date is probably the dump or
redistribution date, not the build date; do not treat either date as authoritative
without corroboration. Second, the prototype's ISO tree is *far* more complete than
the retail disc's (3,208 files reachable vs 1,079, with zero truncated directories),
which makes it a genuinely useful cross-reference for the retail disc's missing
directory entries.

The prototype is **not** the target, but it is a useful second build for differential
work later.
