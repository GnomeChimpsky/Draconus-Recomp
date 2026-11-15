# 07 — Milestone roadmap

Gates are objective and automatable. A milestone is done when its gate passes on a
clean checkout plus the user's own disc — not when it "looks right".

| # | Milestone | Size | Gate (all must pass) |
|---|---|---|---|
| **M0** | Reconnaissance & decisions | S | Docs cite a command or URL for every claim; no game data in the tree; `dracdisc verify` green |
| **M1** | Disc & asset foundation | M | `1ST_READ.BIN` extracted with matching SHA-256 (fail closed); full inventory reproducible; test suite green; 0 resync events on the retail dump; proto parses as `DIE21` |
| **M2** | **First translation (go/no-go for the engine)** | M | Title config translates; coverage % reported; first untranslated address printed; one `--suggest-config` round cuts gaps ≥ 50 %; two consecutive runs identical |
| **M2b** | **Boot-state analysis (new, blocking)** | M | Flycast oracle trace compared with the translated run for the first ~25 guest cycles; the wrong register (or entry assumption) is identified and fixed or documented |
| **M3** | First frame | L | 600-frame deterministic headless run, identical frame hashes across runs; F11 capture bundle replays; first non-blank frame within Flycast tolerance |
| **M4** | Frontend | M | Scripted input reaches the title screen and starts a new game, asserted by frame hashes |
| **M5** | In-game | XL | 60 s scripted play with zero untranslated calls; per-checkpoint frame diff vs Flycast under threshold |
| **M6** | Audio | L | 10 s of music spectra matched vs Flycast; 10 min without dropouts; WAV capture diff |
| **M7** | Full playthrough parity | XL | Credits reachable without crash; every level entered; save/load round-trip; zero coverage gaps |
| **M8** | Native port | L | Launcher imports a disc and rejects a wrong one by hash; native pad/mouse/key mapping; settings persist; installs on a machine without dev tools |
| **M9** | Enhancements | L | 16:9/21:9 with undistorted HUD; internal resolution scaling; render rate decoupled from 60 Hz logic; suite passes at 60/120/144 Hz |
| **M10** | Release | M | Reproducible build from a clean checkout + user disc; installer; legal notices; reproduction guide |

## Milestone detail

### M1 — done

Delivered: `tools/draconus-disc` with a multi-track GDI reader, an ISO9660 walker that
distinguishes truncation from corruption, a `DIRENT.DIR` scanner, `verify`/`inspect`/
`extract`/`manifest` commands, and 14 unit tests including a 1,000-case fuzz test.

Measured on the retail dump: 0 resync events, 0 truncations, 3,690 ISO files / 936.6 MB, 3,713 engine-index records / 946.1 MB. The extraction is byte-identical to the engine's own `dcdisc`.

### M2 — in progress, and it is a decision point

The point of M2 is not progress; it is to find out whether `dream-recomp` is good
enough for *this* game before investing in it. Results so far are in
`docs/11-M2-RESULTS.md`:

* Discovery is measured: 3 functions by call graph, **14,913 (26.1 % of code bytes)
  with pointer tables**, and the aggressive sweep does not complete.
* Full-set `emit` runs >300 s and produces no unit; a 500-function subset emits in
  0.2 s. Emission is the blocker to a *complete* translation.

**Gate status: met on the interpreter path.** The retail game boots and keeps running:
**1,800 frames (29.9 s guest), 5.97 billion cycles, 1,474 GD-ROM sectors, 704,111 TA
chunks, 1,680 frame swaps, 96,068 interrupts, no faults**, and two 600-frame runs are
byte-identical. The first display-list write is at frame 86. The earlier "retail won't
boot" blocker was a bug in our own multi-sector disc reader, fixed and regression-tested.

**Translated path: both blockers fixed (2026-11-10).** The `0x8C001006` fault (a hook marker
fetched as code after a task switch) was fixed by dispatching hook entries at the interpreter's
fetch boundary (`docs/ENGINE-CHANGES.md` patch 003). The `0x60000040` fault was a handler entry
stopping at the interrupted code's PR instead of the handler's RTE (patch 007), which left the
handler's saved context on the guest stack and corrupted the outer epilogue. With it fixed the
translated path runs 600 and 1,800 frames deterministically, with PVR/Maple counters identical to
the interpreter's (41 cycles apart in 1.97 billion over 600 frames), and `--replay` still reports 0
disagreements.

**Speed: met for the measured scenes (2026-11-11).** Seeding the fifteen call targets that took
99 per cent of the interpreter boundary traffic, plus an inlined RAM fast path in the runtime, took
the translated path from 0.15x to **1.2x real time headless** at 1,800 frames (0.8x windowed). The
windowed gap is the renderer's per-frame cost, not emulation.

**Still open for M2's goal:** full-set discovery and emission (`emit` over the whole set did not
complete; a 500-function subset emits in 0.2 s). The seeds cover what the first 300 frames reached,
not later gameplay, so the long-term speed lever is still emission over the full set.

**Next:** close emission over the full discovery set, then re-measure; and cut the windowed
renderer cost. The instruction-level differential tracer built during the investigation stays as
the tool for any new divergence; it is described in `docs/UPSTREAM-REPORT.md`.

### M2b — boot-state analysis

Use the engine's Flycast oracle to compare the first cycles and identify which
register or entry assumption differs, before translating more of the binary.

### M5 — done (2026-11-15)

A single scripted schedule — START at 1,000, START at 1,800, A at 2,300/2,800/3,100, START at
4,500 to skip the story, then movement pulses — reaches the title, character select, the Celanarin
loading card, the story, and gameplay at about frame 4,600. The run is 8,200 frames (136.6 s guest),
so its last **60 s are in-game**.

**Zero untranslated calls.** `DREAM_TRACE_UNTRANSLATED=1` reported 101 calls. Ninety-seven were
one call each into the 125-entry static-constructor table at `0x8C1FAD98`: pointer discovery only
accepted a target whose forward scan found a branch within 200 instructions, and these functions
run for up to 498 instructions before theirs (engine patch 037). The last four were case labels of
a `mov.w` switch whose root function's resume switch knew them but whose nearest containing
fragment did not; `resume_miss` now retries the other containing functions before the interpreter
(patch 038). The 8,200-frame run reports **`untranslated call targets: 0`**, with the same PVR,
Maple and interrupt counters as before.

**Per-checkpoint frame diff.** `tools\m5-check.ps1` renders ten checkpoints (title, character
select, loading card, story, and six in-game frames), drives Flycast's Lua API with the same
controller schedule, freezes Flycast at each guest frame until its client area is copied, and
compares mean absolute RGB difference. The ten checkpoints measure **1.46-13.58** against a
threshold of **16**; a pair from two different screens measures 27-38. The largest values are
in-game frames whose additive glow and idle pose are the title's own animation, and the two
renderers' texture filtering differs at the pixel level; the scene composition, camera and HUD
match. Windowed parity (`tools\parity-check.ps1`) remains byte-identical.

The gate is reproducible with `tools\m5-check.ps1` (`-SkipFlycast` for the zero-call half alone),
and engine patches 037–038 are carried by `patches/0003-m5-coverage.patch`.

### M6 — done (2026-11-14)

Flycast's SDL2 audio backend can write to SDL's disk driver, so the project now has a digital audio
oracle (`tools/flycast-m6.ps1`). Ten seconds of menu music after START match ours at sample
correlation 1.0000 (RMS difference 1.1 LSB, worst 5 LSB), identical dominant peaks, and octave-band
levels within 0.01 dB. Flycast is silent on the title screen too, so the baseline's title silence is
correct behaviour, not a missing cue. A 600-second run has seven silent runs and every one is also
silent in Flycast at the same point; the long ones are the game's own attract-mode gaps. The gate and
the measurements are in `docs/13-M6-AUDIO-BASELINE.md`; `tools/m6-check.ps1` reruns it.

### M3–M7 — fidelity

Order is deliberate: boot, then frontend, then one level, then audio, then everything.
Audio is late because the ARM7 program is the most self-contained subsystem and its
failure mode (silence) does not block visual parity. M4's scripted-input path is now exercised by
M5, M5 and M6 are done; M3's remaining clause is a like-for-like Flycast frame comparison, and M7
continues on coverage and the full play-through.

### M8–M10 — product

Launcher/disc-import workflows are informed by SARecomp's installer design but
reimplemented. Enhancements live behind a profile switch so "Original" is always
available and provably unmodified.

## Effort model

Sizes are relative, not calendar estimates: S ≈ days, M ≈ 2–6 weeks, L ≈ 1–3 months,
XL ≈ multi-month. The honest expectation is that M5 and M7 dominate total effort, and
that M2's result materially changes the plan.
