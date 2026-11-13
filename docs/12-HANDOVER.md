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
| Speed | translated path | **4.5x at 400 frames, 3.6x at 5,000, 3.0x over 20,000 frames of gameplay; 1.0x windowed** |
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
| translated, pointer tables (**current**) | **4.2x** | **3.9x** |
| same, deeper gameplay (20,000 frames) | — | **1.8x** |

With a window the 1,800-frame run is **1.0x** (vsync-paced), and so is the heavier 5,000-frame menu
scene; at 4x resolution too. The build now takes about five minutes and generates ~100 MB of C++.

**One caution.** Do not add `0x8C233648` as a seed: it is the relocated exception handler's body and,
translated, its `rte` no longer unwinds through `enter_exception` (the run faults at pc 0 at frame
22). Pointer discovery does not name it, so it stays interpreted on its own. The `--replay` harness
also reports one disagreement in `fn_0c011e64` — `r0` differs only in the P0/P1 segment bits, the
known alias, not a behavioural difference.

If a later scene is still slow, `tools\diagnose-speed.bat` runs the game with
`DREAM_TRACE_UNTRANSLATED` and leaves `work\speed-report.txt` naming the hotspots.
## The gameplay crash: fixed at the root (2026-11-13)

Three reproductions faulted at pc 0: frame 4,750 (`start@1000,a@4000`), frame 192 (a burst of d-pad
presses on the main menu), and frame 18,690 (a menu-heavy sequence). The interpreter ran all three
cleanly. The fault always followed an `rte` whose saved context had **PC at a function entry and PR
inside that same function** -- `spc 0x0C0C7F7C` with `pr 0x0C0C7FBE`, the return address of the call
at `0x0C0C7FBA`, which is that function's own epilogue. Resuming at the entry ran the prologue again,
the epilogue returned to `0x0C0C7FBE` a second time, popped a frame that was not there, and the next
indirect call read zero.

The context came from the **function-entry interrupt poll**. That poll can deliver an interrupt at an
entry reached by a tail jump, where PR still holds the jumper's return address -- a state the
interpreter never delivers at (13,698 deliveries on the same input, none at that address). Leaving the
entry poll out is the fix:

```toml
[functions]
entry_polls = false
```

Validation with **nothing excluded from translation** (8,940 functions):

| run | before | after |
|---|---|---|
| menu burst, 400 frames | fault at 192 | clean, 4.5x |
| `start@1000,a@4000`, 5,000 frames | fault at 4,750 | clean, 3.6x |
| menu-heavy sequence, 20,000 frames | fault at 18,690 | clean, 3.0x |
| windowed parity, 1,100 frames | — | **byte-identical**, counters match |

It is also faster: an entry poll is a compare per call, and interrupts are still delivered at loop
back-edges and call returns (57,688 deliveries against the interpreter's 57,629 over the parity run).
`DREAM_TRACE_RTE=path` logs the state at every `rte` from both engines and is what found this.


## Renderer: textures updated in place (2026-11-13)

A play-through of the first level surfaced three visual faults: corrupted text in the VMU save menu,
the intro background replaced by a broken-up Crave logo, and the same on the tree-village loading
screen. They are one bug: a texture decoded once was kept for ever, so art the guest rewrites in
video memory -- including everything the PVR's YUV converter produces for streamed backgrounds and
video -- kept showing the older picture.

`DcMemory::on_vram_write` now reports video-memory writes, the boot merges the ranges, and the
texture cache drops the covered entries (`invalidate_ranges`) before the next display list is drawn.
The cache's "overwritten by a render" counter, previously zero on these screens, now shows the
refreshes happening. Parity is unchanged and the harness is byte-identical.

**Open from the same session: a period of slow simulation with audio crackling**, about three times
in a level, each lasting around a minute, followed by a brief catch-up. The suspects are scenes that
fall back to the interpreter (a burst of untranslated calls), a first-use renderer stall (pipeline or
texture work), or audio-buffer starvation when a frame runs long. The cheap next measurement is
`DREAM_TRACE_UNTRANSLATED=1` on a run that reaches one of those scenes: the exit report ranks the
targets, and a dominant entry means discovery missed a routine rather than the renderer stalling.

## Coverage anomaly found by the untranslated trace (2026-11-13)

`DREAM_TRACE_UNTRANSLATED=1` over an 8,000-frame scripted run had one target that mattered:
`0x8C187B1C`, **2,736 calls** (about one every three frames), plus 97 single-call bootstrap entries.
It is a real function entry -- standard prologue -- sitting exactly at the end of the pointer-
discovered function before it, and the table pass never added it. Seeded in `[functions] extra`;
the next trace shows only the 97 one-off calls. Parity is unchanged.

This is not the slowdown: 2,736 interpreted calls over 8,000 frames is noise. The slowdown did not
reproduce for the owner either; it stays on the list as an unexplained, intermittent one.

**Lanterns flicker (open).** Reported from the tree-village level. The renderer draws translucent
polygons back to front per strip (`renderer.cpp`, the `items` sort) and tests depth without writing
it; a glow sprite that intersects the surface it lights can therefore alternate between drawn and
depth-rejected as the camera moves, which reads as flicker. It needs a capture to tell that apart
from a texture or pipeline cause: `F11` at the moment it flickers gives the display list and video
memory, and `--polygons` on the capture diffs two frames' polygon lists.

## Controllers (2026-11-12)

A pad works on first plug-in and no configuration file is needed. The left stick is the Dreamcast
analogue stick, the face buttons are A/B/X/Y, the d-pad is the d-pad, Start is Start, the shoulders
are C and Z (the two buttons the pad has that a modern one spells as shoulders), and the analogue
triggers are L and R. SDL's own mappings cover commercial pads; a pad that arrives as a raw joystick
(a DirectInput stick, an 8BitDo in DInput mode) is given the standard DirectInput layout, so it is
playable instead of invisible. `F1` rebinds everything, including the dead zone.

A pad that SDL enumerates but cannot open (another driver holding it, a device that answers a
moment after launch) is polled through **XInput directly**, and the device row reads `XINPUT`. That
was the GameSir Cyclone 3 case: SDL listed an "XInput Controller #1" gamepad, `SDL_OpenGamepad` still
failed, and the XInput fallback is what made the pad appear and work.

The launcher prints `input: KEYBOARD, <pad>` at start, and `DREAM_INPUT_TRACE=1` prints the pad state
the guest actually receives whenever it changes -- the quickest way to tell a host-side problem from
a game-side one. `DREAM_VIRTUAL_PAD=1` attaches a synthetic pad (buttons, stick, hat, scripted) so
the path can be exercised on a machine with no hardware; that is how the buttons and the stick were
verified end to end here while no pad was attached.

**The menu crash, found while testing the pad (2026-11-12).** Navigating the main menu with a burst of
d-pad presses (`--press "down@150,down@170,...,down@270"`) faults the translated build at frame 192,
pc 0; the interpreter runs the same input cleanly. A single down press does not fault. The fault is
an indirect call through a null vtable slot:

```
hook: call_indirect 0x00000000 from pc 0x0c0c70ee r0 00000000 r2 be10ff21
0c0c70ea  mov.l @r4,r0      ; r0 = object->vtable
0c0c70ec  mov.l @(32,r0),r0 ; r0 = vtable[8]
0c0c70ee  jsr @r0           ; null
```

The fault-time stack walk (RVAs resolved through the link map) is
`unimplemented <- exec <- on_untranslated <- call_indirect <- fn_0c0c70cc <- fn_0c0c7f7c <- resume_at`:
a non-local return resumed `0x0C0C7F7C`, and the call chain from there reached a null vtable slot.
Whether the object or the vtable is wrong, or the menu path is being resumed at the wrong point, is
open. This is the same translated-code class as the crash above, but it reproduces in 192 frames, so
it is the fast case to work from: compare the object at the `r12`/`r4` of `0x0C0C70CC` between the two
paths, and the non-local return that resumed `0x0C0C7F7C`.

**What is still open.** Whether `fn_0c16cdf4`'s *translation* is wrong or whether hiding it merely
shifts interrupt timing is not proven. It is called only late in gameplay, so the differential replay
of that call is expensive; the next measurement is `--replay-only 0x0C16CDF4` over a run that reaches
it (the replay harness at this size needs a long run, or a checkpoint that does not exist yet). The
config comment carries the same note; remove the exclusion when this is settled.

Also fixed on the way: MSVC needs `/bigobj` for a 9,000-function generated unit, so
`cmake/DreamAddGame.cmake` adds it to the game target (patch 011).


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

## M3 status (2026-11-13)

- **Determinism: passes.** Two 600-frame headless runs with `--write-hash` produce byte-identical
  files (same SHA-256), so the translated path is deterministic run to run.
- **Capture replay: passes.** `tools\m3-check.ps1` runs the determinism check, takes an F11 bundle and
  replays it through `dream_render_view`; both checks are green. The replay tool used to hang when
  given `--screenshot` without `--frames` -- it opened a window and waited -- and now renders one
  frame and exits in that case.
- **First non-blank frame vs Flycast: not yet measured.** Flycast is present at the documented path;
  the capture procedure is in `docs/14-M3-M6-FLYCAST-REFERENCE.md`.

## M9 plan (2026-11-13)

M9 has three parts; one is already done, two need a decision and real work.

1. **Internal resolution scaling — done.** `--scale N` draws the geometry at N x 640x480 and resamples
   on the way into video memory, so the guest still sees 640x480. Checked at N=2: "drawing at
   1280x960".
2. **16:9/21:9 with undistorted HUD — needs a choice of semantics.** The PVR receives already
   projected coordinates at 4:3, so three behaviours are possible and they are not interchangeable:
   * **pillarbox** -- 4:3 content, black bars. Correct picture, no extra view. Trivial.
   * **stretch, HUD kept square** -- the 3D fills the wide frame and is horizontally stretched; HUD
     polygons are drawn at their 4:3 scale. This is what the milestone wording implies, and what
     widescreen launchers for other 3D titles do. Costs a per-polygon "is this HUD" split, which the
     display list can only guess from sprite-vs-strip and screen-space coordinates.
   * **hor+** -- widen the field of view. Needs the title's projection matrix, i.e. a per-title hook
     the way Flycast's widescreen hack works. Best result, most work, and it is title-specific.
3. **Render rate decoupled from 60 Hz logic — not started.** Two steps: present the last frame at the
   panel's rate first (each guest frame shown N times, no interpolation), then optionally interpolate.
   The frame limiter in the boot already knows the guest's 60 Hz cadence, so the first step is
   contained.

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