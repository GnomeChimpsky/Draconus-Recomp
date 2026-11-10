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
| Function differential | `--replay` (+ replay build) | 2,448,650 calls compared, **0 disagreements** |
| Fresh clone | `setup.ps1 -SkipBuild`, `import-disc`, `setup.ps1` | engine patched, dump extracted, built, **600 frames clean** |
| Engine test suite | `ctest` in `engine/build-test` | 6/6 (76 runtime cases incl. the new regression) |

The translated path stops being a curiosity and becomes the build to develop: it is now correct, but
in this configuration it is **slower** than the interpreter (600 frames in 68 s against 38 s). Most of
the title is still intercepted by the development interpreter, and the translated build pays a
`devinterp::run` for every call it cannot make natively. Translation coverage, not the runtime, is the
next speed lever.

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

**What it does not fix:** speed. The translated build is still mostly interpreter. See below.

## Engine state (local, not committed)

`engine/` is fetched by `setup.ps1` and carries eight local changes, all validated:

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

Build trees: `engine/build-render` (playable, Vulkan + SDL3), `engine/build-replay`
(`--replay-hooks`), `engine/build-test` (tests). Build them from a Developer Command Prompt (or call
`vcvars64.bat` first) — `cl` needs the MSVC include paths.

## Next phase

Order is by value per unit of risk, not by size:

1. **Interactive check of the translated path.** All evidence so far is headless runs with a fixed
   seed. Launch `-Translated` with `--window`, play through the movies and into gameplay, and confirm
   the window, input and pacing behave as the interpreter path does. Record it; this is the gate that
   turns "runs" into "playable".
2. **Translation coverage (the speed lever).** The full-set discovery/emission blocker in
   `docs/11-M2-RESULTS.md` is now the only thing between this build and a usable frame rate. The
   translated path is correct and slow; making it fast is a translation problem.
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
