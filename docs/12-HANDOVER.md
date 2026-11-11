# Handover — state of the project

Updated 2026-11-10, after the translated-path fault was found and fixed. The project's records are
elsewhere: `docs/ENGINE-CHANGES.md` is the running ledger with every trace and dead end,
`docs/UPSTREAM-REPORT.md` is the engine-side report, and `docs/07-ROADMAP.md` is the milestone plan
this is measured against. This file is the pick-up point.

## What works

| Thing | Command | Evidence |
|---|---|---|
| Disc validation and extraction | `python -m dracdisc verify "<own dump>.gdi"` | 15 tests; byte-identical to the engine's `dcdisc` |
| Play the game | `.\play-draconus.bat` | movies, menus, gameplay, input; deterministic |
| Play the machine-translated path | `.\play-draconus.bat -Translated` | **600 frames and 1,800 frames, no fault, 0 task switches** |
| Determinism check | `--rtc-seed 1000000` twice | identical cycles, GD-ROM sectors, TA chunks |
| Translated vs interpreted parity | same 600-frame run | identical PVR/Maple counters; 41 cycles apart in 1.97 billion |
| Instruction tracing | `DREAM_TRACE_INSNS=lo:hi:FILE` | filtered by range, cycle window and in-range index |
| Function differential | `--replay` (+ replay build) | 2,448,650 calls compared, **0 disagreements** (one P0/P1 alias in a newly seeded function) |
| Windowed parity | `tools\parity-check.ps1` | window renders; input recording and screenshot byte-identical to the interpreter |
| Speed | translated path | **3.7-3.9x headless, 1.0x windowed**; interpreter is 0.26x |
| Fresh clone | `setup.ps1 -SkipBuild`, `import-disc`, `setup.ps1` | engine patched, dump extracted, built, **600 frames clean** |
| Engine test suite | `ctest` in `engine/build-test` | 6/6 (76 runtime cases incl. the new regression) |

**The translated path is now the fast one (2026-11-11).** It had been 0.15x — slower than the
interpreter — because most of the title's code was running in the development interpreter. Three
things fixed it, in this order:

1. **Seeds** from `--suggest-config`, which found a 99-per-cent hotspot: `0x0C240710`, an empty
   function (`rts`) called ~98,000 times a frame (0.15x → 1.5x at 600 frames).
2. **The RAM fast path** inlined in `DcMemory` (1.5x → 1.9x), and **cached host memory** for the
   presenter's readback (windowed 0.8x → 1.0x).
3. **`pointers = true`** — the real fix: pointer-table discovery had been off, so the title's
   table-driven code was never translated. It finds 8,940 functions instead of 3,285, untranslated
   calls drop from 3.3 million to 1,412 in a 5,000-frame scene, and the seeds become unnecessary
   (removed).

| configuration | 600 frames | 1,800 frames |
|---|---|---|
| interpreter | 0.26x | 0.22-0.26x |
| translated, before any of this | 0.15x | — |
| translated, seeds + RAM fast path | 1.9x | 1.2x |
| translated, pointer tables (**current**) | **3.9x** | **3.7x** |

With a window the 1,800-frame run is **1.0x** (vsync-paced), and so is the heavier 5,000-frame menu
scene; at 4x resolution too. The build now takes about five minutes and generates ~100 MB of C++.

**One caution.** Do not add `0x8C233648` as a seed: it is the relocated exception handler's body and,
translated, its `rte` no longer unwinds through `enter_exception` (the run faults at pc 0 at frame
22). Pointer discovery does not name it, so it stays interpreted on its own. The `--replay` harness
also reports one disagreement in `fn_0c011e64` — `r0` differs only in the P0/P1 segment bits, the
known alias, not a behavioural difference.

If a later scene is still slow, `tools\diagnose-speed.bat` runs the game with
`DREAM_TRACE_UNTRANSLATED` and leaves `work\speed-report.txt` naming the hotspots.

## Open defect (2026-11-11): a crash in gameplay on the pointer-discovery build

The fast build (`pointers = true`, 8,940 functions) crashes in gameplay. It is deterministic and
reproduces headless:

```powershell
draconus_boot --config games\draconus\draconus.toml --max-frames 5000 --rtc-seed 1000000 `
              --press "start@1000,a@4000"
```

`fault: unimplemented instruction 0x0000 at 0x00000000`, frame 4,750 (79.07 s guest).

The controls say it is a translation defect introduced by the pointer pass, not a runtime limit:

* the interpreter runs the same input to frame 5,000 cleanly;
* the pre-pointer build (3,285 functions) also runs it cleanly, to frame 5,000;
* the trace ends with an `rte` whose saved frame is `{pc 0, sp 0}`, a switch to `0x0C16CDF4`, then an
  emitted `rts` whose target is its own entry (`nonlocal: rts from 0x0c16cdf4 to 0x0c16cdf4`), then
  a jump to 0. The shape is a context save/restore left one slot out of step, in code the pointer
  pass added.

Next: localise with the replay harness rebuilt from this config over the crashing input, or bisect by
leaving pointer-origin functions out of the translation set. Until it is fixed, `-Interpret` is the
stable path (0.25x), and reverting `pointers = false` gives back the stable 1.2x build.

## The fault that was fixed (2026-11-10)

The translated path used to stop at frame 54 with `unmapped read 0x60000040`. The cause was
`System::on_untranslated`: it ran interpreted code until it returned to `c.pr`, which is wrong for an
exception-handler entry because a handler does not return through PR — at that moment PR still
belongs to the interrupted code.

It only bit on a **nested** delivery. The VBlank handler runs an ISR through `jsr @r14`; an interrupt
delivered inside that ISR leaves PR equal to the ISR return address. The nested handler's own
`jsr @r14` sets PR to the same value, so its interpreted run stopped at the ISR's `rts`, abandoned the
handler before its epilogue, and left the handler's saved context on the guest stack. The outer
handler's epilogue then popped one slot out of step, loaded an SR value into SPC, and the `rte`
became a "task switch" to `0x60000040`.

The fix (patch 007) marks the handler entry in `enter_exception` and makes `on_untranslated` use stop
address 0 — stop at the handler's RTE — exactly what the `--interpret` path always did. Six
assertions in `runtime/tests/test_system.cpp` pin it; the test fails four of them with the line
reverted. Full evidence in `docs/ENGINE-CHANGES.md`.

**What this retires:** the task-switch theory (the single switch was this corruption being
misclassified; there are 0 now), the emitter/cycle-accounting suspects, and the need for
`DREAM_HANDLER_INTERP`. It also means the interpreter path's "0 task switches" was never a fidelity
gap of this title — it was the correct schedule.

**What it does not fix:** the previous slowness — that took the config seeds and the RAM fast path
(patch 009), described above.

## Windowed session parity (2026-11-10)

The translated path was exercised in a window with scripted input and compared against the
interpreter. One command, about four minutes:

```
tools\parity-check.ps1
stop     ok    stop: frame limit
frames   ok    1100 vs 1100
PVR      ok    287,744 TA chunks, 961 list inits, 956 renders, 957 frame swaps
Maple    ok    1,079 transfers, 4,316 frames, 1,078 pad polls
cycles   info  3,635,956,129 vs 3,635,956,168 (39 apart in 18.2 s)
irqs     info  57,629 vs 57,650 (21 more, 0.04%)
shot     ok    byte-identical at presented 900 (guest 987)
PARITY OK
```

The window opens and draws on the GPU (`NVIDIA RTX 3080, drawing at 640x480`; 22 textures decoded,
0 failed). Scripted presses reach the Maple controller identically: the recorded controller state is
byte-identical in both runs (`start` at guest 1000, released at 1008), and screenshots after that
press — guest 1587 and 2387, the title menu fading in — are byte-identical too.

Two method findings, recorded so they are not re-discovered:

* `--screenshot-at N` counts *presented* frames and captures the game's last rendered frame. Under
  `--present-mode immediate` the emulator runs several frames ahead of the presenter, so a shot
  labelled guest 987 can hold a later frame — one such pair differed because the shot caught the
  menu fade after the press. With the default vsync pacing the pair is byte-identical. Compare
  paced runs, or compare at a point where the screen is not changing.
* The write hash is per frame, and a write that lands either side of a frame tick (the two engines
  charge slightly different instruction costs) makes individual frames differ even when the write
  sequence is identical. The first 1.1 million writes — frames 0 to 4 — are identical field by
  field; the per-frame hash differences are boundary shifts, not state differences.

Not covered: feel. The check cannot judge pacing or responsiveness; with the seeds and the RAM fast
path the translated path is fast enough to judge now (1.2x headless, 0.8x windowed at 1,800 frames).

## Engine state (local, not committed)

`engine/` is fetched by `setup.ps1` and carries nine local changes, all validated:

| # | What | Upstream? |
|---|---|---|
| 001 | `--present-mode` guard so a renderer-free build compiles | yes |
| 002 | `DREAM_TRACE_HOOK` diagnostics (hooks, `rte`, replay children) | yes |
| 003 | Hook markers dispatched at the interpreter's fetch boundary | yes — bug fix |
| 004 | `--trace-insns` instruction-level tracer + interpreter hook | yes — feature |
| 005 | `--replay` skips stateful HLE calls (no more false positives) | yes — bug fix |
| 006 | SR-write rule | maybe |
| 007 | **Exception-handler entry stops at the RTE, not at the interrupted code's PR** | **yes — fixes the 54-frame fault** |
| 008 | Flash `FLASHROM_WRITE`/`FLASHROM_DELETE` mark a replay host-state side effect | yes |
| 009 | **RAM loads/stores inlined ahead of the resolve/journal path** (+ `DREAM_TRACE_UNTRANSLATED`) | **yes — 1.5x → 1.9x** |
| 010 | **Cached host memory for the offscreen readback** (+ `DREAM_TRACE_FRAME_TIME`) | **yes — windowed 0.8x → 1.0x** |

Build trees: `engine/build-render` (playable, Vulkan + SDL3), `engine/build-replay`
(`--replay-hooks`), `engine/build-test` (tests). Build them from a Developer Command Prompt (or call
`vcvars64.bat` first) — `cl` needs the MSVC include paths.

The engine changes are in `patches/0001-engine-local-changes.patch`; `setup.ps1` applies them.

## Next phase

Order is by value per unit of risk, not by size:

1. **Human play-through.** The build is at real time in a window; judge feel — movie sync, menu
   responsiveness, input latency — and note anything that only shows up in play.
2. **Translation coverage.** Still the long-term lever for heavier scenes: the full-set
   discovery/emission blocker in `docs/11-M2-RESULTS.md` (the seeds cover what the first 300 frames
   reached, not what later gameplay will). `DREAM_TRACE_UNTRANSLATED` names what a new scene is
   missing.
3. **M3 visual parity and M6 audio.** Flycast is installed and boots the disc; driving it and
   capturing is in `docs/14-M3-M6-FLYCAST-REFERENCE.md`. Audio still reaches a WAV file rather than
   the speakers, and the title screen is silent (`docs/13-M6-AUDIO-BASELINE.md`).

## Owner items

Nothing here blocks the next phase. Outstanding: delete the zero-byte CHDs and the stray `flycast/`
folder in the checkout, and an Apple Developer account for a macOS release build (WP3.6 will need
it).

The fresh-clone path is now closed: `setup.ps1` applies the engine patches from `patches/` after
fetching the pinned commit, keeps an already-imported disc image when re-run, and extracts the boot
executable from that dump when it is missing. Verified end to end on a clean clone.

## Things that cost time and should not be repeated

* `GdiImage.read` originally read a multi-sector request contiguously and returned ECC as data; that
  caused days of misdiagnosis. Fixed and regression-tested (`tools/draconus-disc/tests`).
* `--replay`'s old disagreement on `fn_0c22caa4` was a harness false positive, not a bug. Do not
  re-investigate it; patch 005 fixes the cause.
* Cross-run trace comparison does not work: the engines diverge from the first interrupt
  (`r15`/`spc` differ). Always use the within-run differential, or a range/window filter.
* The translator emits in P0 (`0x0C...`); the guest runs in P1 (`0x8C...`). Ranges for tracing must be
  masked to `0x1FFFFFFF`.
* An instruction trace of "every handler invocation" is unusable. Filter with
  `DREAM_TRACE_IDX_TO`, `DREAM_TRACE_FROM`/`TO`, or a narrow PC range — that is how the four-byte
  imbalance was found in one run.
* `tempfile.mkdtemp` directories cannot be deleted under this sandbox; use a directory inside the
  workspace.
* A control must remove the thing under suspicion. `DREAM_HANDLER_INTERP` moved the fault only
  because it replaced the handler entry path; the earlier check "does the nested run return early?"
  came out negative because it looked at non-nested invocations, which do end at their RTE.
