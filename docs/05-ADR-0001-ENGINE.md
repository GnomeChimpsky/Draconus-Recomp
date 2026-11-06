# ADR-0001 — Recompilation framework and runtime

* Status: **proposed** (requires owner approval)
* Date: 2026-11-04
* Deciders: project owner

## Context

Draconus is a vanilla Katana-era Dreamcast title: SH-4 + FPU, PVR2, AICA with a
game-supplied ARM7 driver, GD-ROM, Maple, RTC. The boot program is 2.34 MB with
~1.17 M instructions and ~7,000 `rts`, i.e. large enough that "translate everything
first, then run" is impractical without tooling for partial coverage.

Five candidate approaches were surveyed (`docs/04-REFERENCE-REPOS.md`). Two of the
strongest are unusable as code bases for non-technical reasons: SARecomp has no
licence, and voldorium's licence is non-commercial and bespoke.

## Decision

**Use `phobos665/dream-recomp` (GPL-2.0) as the pinned engine**, kept pristine, and
add Draconus as `games/draconus/` plus our own `game/`, `port/`, `tools/` trees.
**Use Flycast (GPL-2.0) as the oracle.** Use SARecomp strictly as a read-only
benchmark and design reference. Track every engine modification in a ledger so fixes
can go upstream.

## Rationale

1. **Title-first design.** `dream-recomp` is built so a new game is a directory plus a
   TOML config, not a fork.
2. **No BIOS requirement.** BIOS and GD-ROM are HLE-replaced. Legally cleaner and one
   fewer user-supplied file.
3. **Partial-coverage workflow.** A development interpreter plus
   `--suggest-config` turns "it stopped at address X" into a repeatable loop. For
   ~7,000 functions with data-driven dispatch this is the single most important
   feature any candidate offers.
4. **Objective verification.** Differential comparison against Flycast at fixed
   checkpoints is the method we intend to gate milestones on.
5. **Hardware-level renderer.** A PVR2→Vulkan path (rather than a per-game renderer
   rewrite) is what makes widescreen and high resolution tractable later.
6. **Licence compatibility.** GPL-2.0 composes with Flycast and with the Dreamcast
   knowledge embedded in these projects.

## Consequences

* **Accept:** the distributed binary must be GPL-2.0 with source available. This is
  the normal settlement for preservation work, and the project is non-commercial.
* **Accept:** no game code, generated code, disc data, BIOS or SDK headers in the
  repository. Generated output lives in `work/` and is never committed.
* **Accept:** the engine is young (created 2026-09-13). M2 is therefore a deliberate
  go/no-go probe; failure triggers the fallback plan below.
* **Accept:** our improvements to the engine are patches, ledgered, offered upstream.

## Rejected options

| Option | Why not |
|---|---|
| SARecomp / KatanaRecomp | no licence; code reuse unlawful without permission. Kept as reference only. |
| voldorium | non-commercial bespoke licence; per-game translator. Methodology reference. |
| dcrecomp | hardware far too incomplete; would end up porting Flycast anyway. |
| BlueStingerRecomp (MIT) | permissive, but a single-game codebase; strong fallback donor for MIT runtime pieces. |
| Write our own recompiler | months before the first frame; no reuse of proven SH-4/FPU work. |

## Fallback plan (if M2 fails)

1. Contribute the blocking fixes upstream (preferred; keeps us on a maintained base).
2. Take permissively licensed runtime pieces from BlueStingerRecomp (MIT) into our
   GPL tree, keeping attribution.
3. Only then consider a bespoke translator, using voldorium's and dcrecomp's
   approaches as design references.

## Review trigger

Revisit this ADR if: SARecomp receives a licence and the author grants permission;
`dream-recomp` becomes unmaintained; or M2 shows coverage below ~60 % after two
seeding rounds.
