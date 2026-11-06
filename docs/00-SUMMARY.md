# 00 — Summary

## What the project is

A static recompilation of *Draconus: Cult of the Wyrm* (Dreamcast, Treyarch, 2000)
into native Windows x64, faithful by default, with optional enhancements
(widescreen/ultrawide, high resolution, high frame rate, modern input, a graphical
launcher with disc import).

## What was verified (this machine, this dump)

| Question | Answer | Evidence |
|---|---|---|
| Which build? | USA `F888`, `T40203N`, V1.000, 2000-05-19, region `U` | IP.BIN in the dump |
| Is the boot program a plain SH-4 binary? | Yes: 2,339,580 bytes, loads at `0x8C010000`, SHA-256 `a59ff87c…4567da`, starts with a CRT stub; no compression, no scrambling, no WinCE | hash + opcode scan (matches the engine's own extractor) |
| How big is the code? | ~1,169,790 SH-4 instructions, ~7,000 `rts`, ~12,909 `bsr`, ≈10.5 % FPU-class | 16-bit opcode histogram |
| What SDK? | Sega **Katana**: KAMUI animation, Audio64 9.0.b.3 ARM7 sound driver, `syRtc` 1.02, Purupuru, VMU, `gdFs*` GD-ROM calls | strings in the boot program |
| Any middleware traps? | **No** CRI Sofdec/ADX; no WinCE; no coprocessor beyond standard Dreamcast hardware | case-sensitive string scan |
| Where is the data? | One ISO9660 volume spanning **two data tracks**, plus a second, engine-private index (`DIRENT.DIR`) that lists far more files than the ISO tree | track map + file inventory |
| Is the lineage real? | Yes: internal namespace `die2\`, prototype volume id `DIE21`, `InterplayCreditsText`, `ATD`/`sword` strings; Wikipedia confirms spiritual sequel to *Die by the Sword* | strings + primary sources |
| Which framework? | `phobos665/dream-recomp` (GPL-2.0), with `SARecomp` as a **reference-only** benchmark | `docs/05-ADR-0001-ENGINE.md` |

## Disc facts in one line

5-track GDI; `track01` = 606-sector licence volume (`DRACONUS1`, 4 text files);
`track03` = 22,138 sectors; `track05` = 481,261 sectors (~985.6 MB of user data);
boot program at LBA 547,857 inside `track05`.

## Inventory, honestly stated

* ISO9660 tree: **3,690 files in 60 directories, 936.6 MB, 0 resync events,
  0 truncations.**
* `DIRENT.DIR` engine index: **3,713 records / 3,653 files, 946.1 MB.**
* The two agree closely; the small difference is duplicates and the index's own copy.

> Correction (2026-11-05): earlier numbers in this workspace (1,079 files / 419.5 MB /
> 34 truncations, and boot hash `86fc4486…`) came from a **reader bug** that copied
> raw bytes contiguously across sectors, so every sector after the first was ECC and
> header data. Single-sector reads — the boot stub included — were correct, which is
> what hid it. The bug is fixed and covered by a regression test; the extraction is now
> byte-identical to the engine's own `dcdisc`. The corrected SHA-256 is
> `a59ff87c15b7cff926fc77089ae315cf30905586e34504a18b426d634f4567da`.

## Decisions requested

1. **Base engine** `dream-recomp` (GPL-2.0) — a distributed binary derived from it
   must be GPL-2.0, which is the normal settlement for this kind of preservation work.
2. **Reference-only** use of `SARecomp`/KatanaRecomp: legally blocked for code
   reuse pending explicit permission; technically the best benchmark we have.
3. Repo lives beside the dumps (`DraconusRecomp/`), `work/` is generated and ignored.

## Next step

M2 is effectively met: the retail build now boots through 29 frames with GD-ROM,
flash and PVR activity before faulting at `0x8C001006`, and the prototype boot
reaches 53 frames. The next task is to translate more of the binary (pointer
discovery works; `emit` must be fixed for a full set) and chase that fault.
