# 08 — Risks and unknowns

Ordered by how much they can invalidate the plan.

## 1. Function discovery coverage (high)

**What:** C++ vtables, script dispatch tables and terrain callbacks reach code that a
call-graph walk never sees. This game is explicitly data-driven (`script class`,
`PFE_SCRIPT`, `move script chunk`).

**Why it matters:** at ~7,000 `rts` sites, a 79 % discovery rate leaves hundreds of
functions missing, and the game will stop at the first one it needs.

**Mitigation:** the engine's development interpreter plus `--suggest-config` loop;
pointer-table scanning (voldorium's approach found 150 extra entries in a comparable
game); treat coverage % as a first-class metric from M2 onward.

**Trigger to act:** coverage below ~60 % after one seeding round → invoke the
ADR-0001 fallback plan.

## 2. Base-engine maturity (high)

**What:** every reference project is one to three months old and partly AI-authored.
"Crazy Taxi plays" is a claim we have not reproduced.

**Evidence so far (M2):** two concrete defects in one day —
renderer-free builds failed to compile (`--present-mode` outside `#ifdef`), and
full-set `emit` does not terminate usefully (308 s, no output) while a 500-function
subset emits in 0.2 s. The aggressive discovery sweep also fails to complete on this
binary. None of these are fatal, but they confirm the engine needs work for a title
of this size.

**Mitigation:** M2 is a deliberate go/no-go probe; keep engine changes as ledgered
patches; BlueStingerRecomp (MIT) is a fallback donor for runtime pieces. If `emit`
cannot be made to scale, translate in chunks or improve the emitter upstream first.

## 2b. Translated↔interpreted boundary and task switching (current blocker)

**What:** the mixed build (3,285 translated functions + interpreter) faults at
`0x8C001006` after 29 frames; pure interpretation runs 1,800 frames without a fault.
`DREAM_TRACE_NONLOCAL` shows the last interrupt returning with `pr` unchanged but
`r15` moved by `0x15C` — the game's scheduler switching tasks — while the engine
reports `task-switching RTEs: 0`. The next instruction fetch then lands on the
unpopulated hook page.

**Mitigation:** isolate the switching function with `DREAM_INTERP_FUNCS`, compare its
translated and interpreted behaviour, and report the emitter/hook-dispatch defect
upstream. Until then the working configuration is `--interpret`.

## 3. Disc structures — **resolved, and a lesson** (was: medium)

**What we thought:** directory extents declared allocated size (34 of 50 directories),
the root listing reached only `DIE2/`, and the engine's `DIRENT.DIR` index disagreed
with the ISO tree.

**What was actually true:** the disc is a well-formed ISO9660 with 3,690 files in 60
directories (936.6 MB), and the engine index agrees with it (3,713 records / 946.1 MB).
Every anomaly was caused by a bug in our own reader: `GdiImage.read` copied contiguous
bytes for multi-sector reads, so sector 0 was right and every later sector was ECC and
header data.

**Lesson (now enforced):** compare an extractor against an independent implementation
before drawing conclusions from it. The check that found it — same length, different
hash, first difference exactly at `0x800` — took one command; the reasoning that
preceded it took hours. A regression test now covers multi-sector raw reads.

**Remaining unknown:** the `DIRENT.DIR` tag byte semantics (harmless; the scanner does
not depend on it).

## 4. Proprietary asset formats (medium, late)

**What:** `.IMG`, `.PFE`, `.TPM`, `.SX`, `.STR`, `.APM`, `.ENT`, `.TBB` are
undocumented. No format has been decoded yet.

**Mitigation:** the Die by the Sword GOG data (`.ATD`, `.DMV`) is the intended
Rosetta stone; Ghidra on the loaders; asset work starts only at M4/M5 when there is a
running game to validate against.

## 5. FPU and timing exactness (medium)

**What:** SH-4 FPU modes, `FTRV`/`FSCA`, denormal handling; tight loops that poll
interrupt flags (voldorium documented exactly this freeze in another title).

**Mitigation:** the engine's differential harness; frame-hash tests; pin the RTC in
tests.

## 6. AICA / ARM7 (medium)

**What:** the game ships `AUDIO64.DRV`; audio is an ARM7 program with DMA, timers and
ADPCM loop behaviour. Getting registers "close enough" produces silence or artefacts.

**Mitigation:** M6 is isolated; compare against Flycast spectra; use WAV capture diffs.

## 7. Dump validity and scope (low, checkable)

**What:** the dump is large (`track05` ≈ 1.13 GB file); a bad rip would poison every
downstream result.

**Mitigation:** `dracdisc verify` fails closed on the boot hash; confirm the disc boots
in Flycast before M2; keep the CHD as a cross-check (needs `chdman`).

## 8. Widescreen (medium, late)

**What:** HUD and frontend are 2D/`PFE`-driven and may assume 640×480; 3D culling may
be tied to the 4:3 frustum. Every reference port reports per-scene fixes.

**Mitigation:** M9 only; keep "Original" profile provably untouched; add HUD anchors
per element rather than globally stretching.

## 9. Legal (medium)

**What:** GPL-2.0 obligations for a `dream-recomp` derivative; Treyarch/Crave rights in
generated code; prototype provenance; SARecomp reuse boundary.

**Mitigation:** never ship game data or generated code; document the build-from-your-own-
disc model; get a written grant before any SARecomp code reuse; keep `docs/04` rules
enforced in review.

## 10. Bus factor / upstream drift (low)

**What:** a young engine may change shape or stall.

**Mitigation:** pin commits; keep our code outside `engine/`; the engine-change ledger
also serves as a migration checklist.
