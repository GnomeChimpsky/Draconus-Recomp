# Handover — state of the project

Written 2026-11-06, at the end of the session that built the disc tooling, proved the boot,
rendered the game, and reduced the remaining translated-path fault to one instruction.

## What works

| Thing | Command | Evidence |
|---|---|---|
| Disc validation and extraction | `python -m dracdisc verify "<own dump>.gdi"` | 15 tests; byte-identical to the engine's `dcdisc` |
| Play the game | `.\play-draconus.bat` | movies, menus, gameplay and input all work; deterministic (interpreter path, 0.22x) |
| Determinism check | `--rtc-seed 1000000` twice | identical cycles, GD-ROM sectors, TA chunks |
| Instruction tracing | `DREAM_TRACE_INSNS=lo:hi:FILE` | 855k-instruction windows diffed |
| Function differential | `--replay` (+ hooks build) | 2,458,232 calls, **0 disagreements** |
| Within-run differential | `DREAM_REPLAY_TRACE=prefix` + `DREAM_REPLAY_DUMP=addr` | `prefix.a.txt` vs `prefix.b.txt` |

## What does not work

The **translated** path stops at frame 54 (`0x60000040`). It is a task-context restore at
`0x8C233756` (`ldc.l @r15+,sr`) reading a pointer instead of a saved SR. The code generator
is exonerated (`--replay` is clean), so the defect is in the runtime's interrupt/task-switch
path. Full chain in `docs/ENGINE-CHANGES.md`, entry point for an engine author in
`docs/UPSTREAM-REPORT.md`.

## Engine state (local, not committed)

`engine/` is fetched by `setup.ps1` at commit `51ca2766` and carries five local changes:

| # | What | Upstream? |
|---|---|---|
| 001 | `--present-mode` guard so a renderer-free build compiles | yes |
| 002 | `DREAM_TRACE_HOOK` diagnostics (hooks, `rte`, replay children) | yes |
| 003 | Hook markers dispatched at the interpreter's fetch boundary | yes — bug fix |
| 004 | `--trace-insns` instruction-level tracer + interpreter hook | yes — feature |
| 005 | `--replay` skips stateful HLE calls (no more false positives) | yes — bug fix |

Build trees: `engine/build-render` (playable, Vulkan + SDL3), `engine/build-replay`
(`--replay-hooks --trace-insns`), `engine/build-trace` (tracer only, no renderer).

## Next three tasks, in order

1. **Fix the harness limitation for HLE reads.** Patch 005 covers GD-ROM. Timers, RNG and
   Maple still change host state; instrument them the same way (`hle::note_side_effect()`)
   so `--replay` stays trustworthy as more of the game runs.
2. **Task-switch investigation.** Read `engine/docs/emitter-design.md` ("Non-local returns"),
   then instrument `System::on_rte` and `sh4::resume_at` to log `frame_pcs`/`frame_sps`
   against `c.spc`/`c.r[15]` for the single switch in the run. The failing restore is at
   `0x8C233756`; the resumed task's stack is what to watch.
3. **Flycast reference (M3/M6).** Flycast is installed and boots the disc; how to drive and
   capture it is in `docs/14-M3-M6-FLYCAST-REFERENCE.md`. Visual reference works, audio
   capture does not (no recording option), so M6's spectra gate needs a loopback recorder.

4. **Launcher/disc import (M8).** Both halves exist: `tools/launcher.py` (GUI over verify/configure/play, `--selftest`), `tools/import-disc.bat` (scriptable), and the import half: `tools/import-disc.bat` verifies a
   dump and writes the config. What is missing is the graphical launcher (pick a dump, pick
   the disc, show settings) and the configuration UI. Then **visual parity (M3)** — Flycast is
   not installed here, so that needs a reference capture from elsewhere. Both are independent of the fault. Flycast
   is not installed here, so M3 needs a reference capture from another machine or a
   screenshot comparison against known-good footage.

## Things that cost time and should not be repeated

* `GdiImage.read` originally read a multi-sector request contiguously and returned ECC as
  data; that caused days of misdiagnosis. Fixed and regression-tested
  (`tools/draconus-disc/tests/test_dracdisc.py`).
* `--replay`'s disagreement on `fn_0c22caa4` was a harness false positive, not a bug. Do not
  re-investigate it; patch 005 fixes the cause.
* Cross-run trace comparison does not work: the engines diverge from the first interrupt
  (`r15`/`spc` differ). Always use the within-run differential.
* The translator emits in P0 (`0x0C...`); the guest runs in P1 (`0x8C...`). Ranges for
  tracing must be masked to `0x1FFFFFFF`.
* `tempfile.mkdtemp` directories cannot be deleted under this sandbox; use a directory
  inside the workspace.
