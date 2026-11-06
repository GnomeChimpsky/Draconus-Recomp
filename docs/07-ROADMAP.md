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

**Translated path: first blocker fixed, next one open.** The `0x8C001006` fault (a hook
marker fetched as code after a task switch) was fixed by dispatching hook entries at the
interpreter's fetch boundary — `docs/ENGINE-CHANGES.md` patch 003, offered upstream in
`docs/UPSTREAM-REPORT.md`. The translated path now reaches **54 frames / 350 GD-ROM
sectors**, deterministically, and stops at `0x60000040` where an `rte` restores a swapped
`SPC`/`SSR`.

**Investigated and eliminated** (evidence in `docs/ENGINE-CHANGES.md`): hook dispatch on
returns, `resume_at` matching, the interpreter's fetch path (fixed), the interrupt frame,
a 4-byte stack imbalance, the replay harness's entry snapshot, the FPSCR PR/SZ bits, and a
stale T flag. `--replay` reports one disagreement, but forcing that function to interpret
does not move the failure, so it is a harness false positive, not the defect.

**Next:** an instruction-level differential tracer (per-instruction trace hook in emitted
code + the same hook in the interpreter, compared from a captured entry state). That is
the only tool that can localise the remaining fault, and it retires the whole class.
`docs/UPSTREAM-REPORT.md` specifies it.

### M2b — boot-state analysis

Use the engine's Flycast oracle to compare the first cycles and identify which
register or entry assumption differs, before translating more of the binary.

### M3–M7 — fidelity

Order is deliberate: boot, then frontend, then one level, then audio, then everything.
Audio is late because the ARM7 program is the most self-contained subsystem and its
failure mode (silence) does not block visual parity.

### M8–M10 — product

Launcher/disc-import workflows are informed by SARecomp's installer design but
reimplemented. Enhancements live behind a profile switch so "Original" is always
available and provably unmodified.

## Effort model

Sizes are relative, not calendar estimates: S ≈ days, M ≈ 2–6 weeks, L ≈ 1–3 months,
XL ≈ multi-month. The honest expectation is that M5 and M7 dominate total effort, and
that M2's result materially changes the plan.
