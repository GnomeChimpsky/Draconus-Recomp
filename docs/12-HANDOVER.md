# Handover — state of the project

Updated 2026-11-17, after the first two levels were played and M3 (first frame) closed. The
project's records are elsewhere: `docs/ENGINE-CHANGES.md` is the running ledger with every trace and dead end,
`docs/UPSTREAM-REPORT.md` is the engine-side report, and `docs/07-ROADMAP.md` is the milestone plan
this is measured against. This file is the pick-up point.

## What works

| Thing | Command | Evidence |
|---|---|---|
| Disc validation and extraction | `python -m dracdisc verify "<own dump>.gdi"` | 15 tests; byte-identical to the engine's `dcdisc` |
| Play the game | `.\play-draconus.bat` | movies, menus, gameplay, input; deterministic |
| Field of view | launcher **Field of view**, `-Fov 75` or `--fov 75` | vertical FOV 60-120 (90 default); zooms both axes, HUD unchanged, item wheel's model scaled/raised to stay in its ring; composes with widescreen. Above 90° the launcher warns that the game's region visibility can cull at the far edges and models can pop in when the camera turns |
| Right-stick look | right stick Y, **Invert right-stick look**, `-LookInvert` | soft 20° camera pitch applied after projection and eased back to centre; HUD and the item wheel's model stay put; `--look` checks it in captures; default no-input frames byte-identical |
| Play the machine-translated path | `.\play-draconus.bat -Translated` | **600 frames and 1,800 frames, no fault, 0 task switches** |
| Determinism check | `--rtc-seed 1000000` twice | identical cycles, GD-ROM sectors, TA chunks |
| Translated vs interpreted parity | same 600-frame run | identical PVR/Maple counters; 41 cycles apart in 1.97 billion |
| Instruction tracing | `DREAM_TRACE_INSNS=lo:hi:FILE` | filtered by range, cycle window and in-range index |
| Function differential | `--replay` (+ replay build) | 2,448,650 calls compared, **0 disagreements** (one P0/P1 alias in a newly seeded function) |
| Windowed parity | `tools\parity-check.ps1` | window renders; input recording and screenshot byte-identical to the interpreter |
| Speed | translated path | **4.5x at 400 frames, 3.6x at 5,000, 3.0x over 20,000 frames of gameplay; 1.0x windowed** |
| Fresh clone | `setup.ps1 -SkipBuild`, `import-disc`, `setup.ps1` | engine patched, dump extracted, built, **600 frames clean** |
| Engine test suite | `ctest` in `engine/build-test` | 6/6 (76 runtime cases incl. the new regression) |
| Audio (M6) | `tools\m6-check.ps1` | 10 s spectra at 1.0000 sample correlation; 600 s with no gap that Flycast does not also have |
| In-game (M5) | `tools\m5-check.ps1` | **0 untranslated calls over 8,200 frames (60 s in gameplay); 10 Flycast checkpoints at MAE 1.46-13.58, threshold 16** |
| First frame (M3) | `tools\m3-check.ps1` | **600-frame determinism, F11 replay, and the first non-blank pair vs Flycast at MAE 0.92 (threshold 16)** |
| Play-through (M7) | first two levels, 2026-11-17 | owner played through; the faults it surfaced are fixed in patches 0009-0012; later levels, credits and zero gaps remain |
| Save / load | the title's own Save and Load Game screens | **owner saved in-game and reloaded it, 2026-11-15** |

**The translated path is now the fast one (2026-11-11).** It had been 0.15x — slower than the
interpreter — because most of the title's code was running in the development interpreter. Three
things fixed it, in this order:

1. **Seeds** from `--suggest-config`, which found a 99-per-cent hotspot: `0x0C240710`, an empty
   function (`rts`) called ~98,000 times a frame (0.15x → 1.5x at 600 frames).
2. **The RAM fast path** inlined in `DcMemory` (1.5x → 1.9x), and **cached host memory** for the
   presenter's readback (windowed 0.8x → 1.0x).
3. **`pointers = true`** — the real fix: pointer-table discovery had been off, so the title's
   table-driven code was never translated. It finds 8,940 functions instead of 3,285 (9,126 after
   patch 037, below), untranslated calls drop from 3.3 million to 1,412 in a 5,000-frame scene,
   and the seeds become unnecessary (removed).

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

**Lanterns: closed as native game behaviour (2026-11-15).** Reported from the tree-village
level as flicker; the captures below show it is the title's own pulse, and the owner confirmed it
is how the game behaves. Two `F11` bundles were taken at the moment -- guest frames 13,305 and
13,520, at 4x (2560x1920) -- and both replay through `dream_render_view` to the pictures the run
presented (mean 2.7/255 after the 4x downscale, the differences at resampling edges and thin HUD
lines), so each bundle is complete and the renderer is faithful to it.

At the near lantern:

| | capture 000 | capture 001 |
|---|---|---|
| lantern body (640x480 guest px) | 33.7 x 37.0 | 33.5 x 36.8 |
| glow quad sizes (px) | 92.8 / 57.4 / 21.9 | 77.0 / 41.8 / 6.5 |
| their vertex alphas | 45 / 202 / 105 | 111 / 201 / 31 |
| glow 1/w | 0.1041 / 0.1041 / 0.1040 | 0.1037 / 0.1036 / 0.1036 |
| lantern front pane 1/w | 0.1059 | 0.1055 |

The body is the same size, and the glow texture -- `tcw c80c5ff0`, a 64x64 VQ RGB565 mipmap at
0x62FF80 -- is byte-identical in both captures. Only the three additive screen-space quads behind
the lamp change (`tsp 849024db`, source alpha / one, four vertices at one 1/w each). The far lantern
changes with them: outer and middle sizes shrink by nearly the same factors (x0.84 and x0.76 there
against x0.83 and x0.73 here), and the outer/inner alphas move by the same amounts (+64/-74 against
+66/-74). So the pulse is one shared parameter applied to every lantern, not per-lamp noise. The
middle layer does not follow a single scale (alpha +47 there, -1 here), so it is not one uniform
factor either.

That is evidence against the open theory. The glow is not intersecting the surface it lights: it sits
at 1/w 0.104, behind the lantern's own front pane (0.1055-0.1059, a gap of 0.0018) and well in front
of the wall behind (about 0.05). That order and that gap hold in both frames, so the glow cannot
cross into depth rejection. Nor is it the texture cache or a pipeline: the same list replays to the
same picture, and the texture bytes do not change.

So the flicker is in the guest's own list: a global pulse moves light between the outer halo and the
inner core and scales all three quads. **Closed (2026-11-15): the owner confirms this is native game
behaviour — the title's intended lantern animation, not a recompilation defect. No renderer change.**
The capture method stays recorded because it is how the quads are read out:
`dream_render_view capture-NNN.ta --polygons`, then the `tcw c80c5ff0` lines with four vertices.

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

### Modern controls (2026-11-15)

`--controls modern`, the launcher's **Controls** setting and `play-draconus.ps1 -ModernControls`
layer a twin-stick preset over the player's gamepad bindings: left stick left/right strafes (up/down
stays forward/back), right stick left/right turns, the left trigger blocks and the right trigger
attacks. A remains A and X remains X; LT and RT are **additional** sources for them, so the game's
own block/action and attack buttons still work. The two triggers are the only controls whose old
strafing role is replaced; the rest of the pad and the whole keyboard set are untouched.

The game already combines strafe and turn: with a scripted controller recording, forward,
strafe-left, turn-left and forward+turn+strafe were captured at the same point in gameplay. The
combined frame shows the strafe pose and the rotated camera, so both actions apply at once. The game
also combines the trigger strafe with the stick turn on its own; the preset only changes which axis
reaches which guest input.

The preset is applied inside `Window`: `effective_bindings` in `render/input.cpp` returns the
player's sets plus the overrides and two extra sources, and `Window::poll` evaluates the extras with
the same dead zone as the primary binding. The XInput fallback gets the same remap directly. The
generic DirectInput mapping also gains `rightx`/`righty`, which it had omitted; without them an
unmapped pad's right stick was not visible to SDL. Trigger extras use a half-travel threshold
rather than the stick dead zone: this pad's triggers rest at 96/255, so the first build held block
and attack permanently. F1 still edits the player's layout, and Classic
removes the layer. Because the game reads the analog stick for menus, the right stick (or the d-pad)
moves menu cursors under Modern; and because LT is block, the game's both-triggers User Mode chord
is no longer available as it was.

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

## M3 status (2026-11-16)

The gate is green and is one script: `tools\m3-check.ps1` (run it with `-SkipFlycast` for the
two clauses that need no oracle).

- **Determinism: passes.** Two 600-frame headless runs with `--write-hash` write the same
  603-line file (SHA-256 `212f28f1…`). The check compares the whole file, so every frame's hash
  matches, not just the last.
- **Capture replay: passes.** The windowed run captures the F11 bundle at presented frame 320
  (guest frame 422) from 600 frames, and `dream_render_view` draws it again (13 polygons, 960x720).
  Two faults were found and fixed on 2026-11-16: the 420-frame version of the run presented only
  317 pictures, three short of the capture point, and the engine's display notice on stderr
  terminated the script under `$ErrorActionPreference = "Stop"` plus `*>` in Windows PowerShell.
  The check now runs 600 frames and relaxes the preference around native tools, deciding on their
  exit codes.
- **First non-blank frame: passes, like-for-like.** Our first non-blank picture is the game's first
  render at **guest frame 103** (the Crave logo fading in, 2.6-2.9 s wall on this machine).
  Flycast's first non-black picture is its **boot ROM's Sega licence screen**, not game content
  (it is on screen into the 230s here; the comparison sweep starts at frame 60), so
  `tools\m3_first_frame.py` drives Flycast with the M5
  Lua/PrintWindow path and finds the first non-blank **game** frame: **frame 240**, the same Crave
  logo. The pair measures **MAE 0.92** against the M5 tolerance of 16 (RMSE 3.36, mask overlap
  0.93, bounding-box IoU 0.99). Absolute frame numbers differ because our engine boots
  `1ST_READ.BIN` directly; the comparison is content-aligned, and ours reaches the picture first.
- **Known state difference.** The engine always attaches a jump pack (patch 029), so our title
  screen draws "JUMPPACK OPERATIONAL" where Flycast draws nothing. The M3 pair is the logo before
  that line exists and is unaffected; M5's title checkpoint contains the line and stays within its
  threshold. This is deliberate — the pack is what makes the game's rumble work (README, Game
  controls), so a strict title-screen diff would need a jump pack configured in Flycast. We accept
  the difference instead.

## M9 plan (2026-11-13)

M9 is done as of 2026-11-13, with a HUD correction on 2026-11-14: all three parts are implemented
and checked.

1. **Internal resolution scaling — done.** `--scale N` draws the geometry at N x 640x480 and resamples
   on the way into video memory, so the guest still sees 640x480. Checked at N=2: "drawing at
   1280x960".
2. **16:9/21:9 with undistorted HUD — done as hor+ for 3D, 4:3 for flat screens, and an overlay
   pass for the HUD.** The PVR receives already projected coordinates at 4:3, so the alternatives
   were pillarbox, a stretched 3D frame with a per-polygon HUD split, or hor+. The title's projection
   x scale turned out to be a plain float, so hor+ is what shipped. The HUD, however, is **not**
   part of that projection: it is screen-space 2D, and the presenter's stretch made it 4/3 too wide.
   Patch 027 compresses the HUD's quads by the same factor about their own anchors, so the stretch
   restores their shape and keeps the health bar centred and the compass in the corner. Patch 033
   extends the rule to the item wheel's large flat panel; patch 035 corrects that extension, which
   was also catching the standing stones' world-space light shafts (128-230 px particle billboards
   at depth 0.2 against a near plane at 7) and moving them sideways. Flat 2D
   frames (title, menus, loading cards) do not use that projection and are pillarboxed at 4:3
   instead of stretched; see below.
3. **Render rate decoupled from 60 Hz logic — done.** `--present-rate N` (launcher `-PresentRate`)
   presents each guest frame `N/60` times with an even cadence; the guest is untouched. 300-frame
   runs at 60/120/144 give identical guest reports (same cycles and pc) with presented counts
   212/424/508. The remaining M9 text, "suite passes at 60/120/144", holds for the guest-facing
   checks (determinism, parity counters); only screenshot/capture targeting is expressed in
   presented frames and shifts with the rate.

**hor+ found and implemented (2026-11-13).** The title's projection is not a matrix in RAM, but its
x scale is a plain float at **0x0C098640** (0.75 = 4:3). It was found by patching every 0.75
candidate to 0.5625 and diffing the frame: only that address changes the whole picture, the rest
are inert or touch one object. Implementation:

```toml
[widescreen]
x_scale_address = 0x0C098640
x_scale_base = 0.75
```

with `--aspect 16:9` (launcher: `-Widescreen`, or `-Aspect 21:9`). The boot patches the x scale to
`base * (4/3)/aspect` and re-applies it every vertical blank, opens a window of that aspect, and the
presenter stretches the frames that carry depth. Verified at 1280x720 and 1680x720: more world
horizontally, no distortion. 4:3 stays the default and parity is unaffected.

**The HUD is screen-space, not projected (2026-11-14).** The earlier claim that it rides the
title's projection was wrong, and a user reported the consequence at 16:9. The same guest frame
captured at 4:3 and 16:9 has **identical** HUD coordinates (health bar x 192..448, compass
x 568..632, at 640x480), while the 3D geometry moves: the patch at `0x0C098640` never touches the
HUD. The presenter then stretches the frame x2/1.5, so the HUD came out 4/3 too wide (the compass
ring measured 188x141 against 141x139 at 4:3). `compress_screen_overlays()` in the render library now
compresses the flat quads that sit beyond the frame's nearest world depth by the projection's own
`(4/3)/aspect`. Parts of one element that overlap or sit within 16 px -- the compass ring and its
needle, the health bar and its digits -- share one anchor, and a small glyph joins a nearby larger
element (the wisp counter sits inside the compass cluster); only a genuinely stand-alone glyph is
scaled about its own centre. The presenter's stretch restores their shape without moving them: the
compass is 140x139, the health bar's red fill 252 pixels wide (4:3: 141x139 and 251), the needle
keeps the same 30-pixel offset from the ring's centre, and the wisp counter sits within one pixel
of the wisp's centre, as at 4:3. See `docs/ENGINE-CHANGES.md` patch 027.

**4:3 menus and loading screens (2026-11-13).** The title, menus, story/location cards and loading
screens are flat 2D art. They do not use the projection (a menu frame rendered with the x scale
patched is byte-identical to the 4:3 one), so stretching them to the wide window was pure
distortion. The boot now classifies each submitted display list with `frame_uses_depth` (any polygon
with a depth span = 3D) and stretches only a 3D frame that came from the renderer; everything else
is fitted at 4:3 and pillarboxed inside the wide window. (A pause or quit dialog drawn over the live
world stays widescreen, because the frame still contains the world; separating a 2D overlay from the
3D scene needs its own signal. Its text is screen-space, so patch 027 keeps that text's 4:3 shape
even though the world behind it stays wide.) Verified at 1280x720: a 960x720 centred
image with 160-pixel black bars for the title and menu cards, and an in-game cutscene frame that is
byte-identical to the pre-change widescreen capture. The presenter also discards fragments outside
the image now, which fixes the edge smear that used to appear in letterbox bars. See
`docs/ENGINE-CHANGES.md` patch 021.

**The item wheel's 3D model (2026-11-14).** The wheel that appears left of the health bar when
switching item is a 256x256 flat HUD panel at depth 7.07, with the item's rotating 3D model
submitted inside it at depth 7.3-7.9. The panel sits *below* the frame's nearest world depth, so the
first overlay pass skipped it; at 16:9 the wheel stretched and the model drifted right into the
health bar. A large flat four-vertex quad (128 px or more each way, not full-screen) is now treated
as a panel, and the panel and the contents within 1.5 depth of it inside its rectangle are
compressed about the panel's anchor. The wheel and its models keep their 4:3 size and left-edge
placement; the world behind the panel is untouched. The near-depth window also stops the pass from
tearing the pause menu's black splash, which overlaps the wheel's rectangle but is drawn at depth
10.87. See `docs/ENGINE-CHANGES.md` patch 033.

## Saves: a virtual VMU always present (2026-11-14)

A windowed run now always has a memory card — the per-user one for this title
(`%APPDATA%\dream-recomp\saves\draconus\vmu_a1.bin`), created blank and formatted on the first run
— so the save and load screens work with no flags. `--vmu FILE` (play script `-Vmu`) still names a
specific image. Headless runs stay card-less so their traces repeat.

**Saving and loading are the game's own (2026-11-14).** The launcher's Saves tab was removed: no card
selection, no save list, no launch-into-a-save. A windowed launch attaches nothing, so the engine's
per-user card above is what the title's own Save and Load Game screens write to and read from. The
launcher's bottom bar has **Open saves folder** and **Open settings folder** buttons: the second opens
`%APPDATA%\dream-recomp`, which now holds `launcher.json`, `bindings.txt` and the `saves` folder, so
one per-user folder carries everything the game and launcher write (2026-11-16). The `--press` walk
through those screens was measured frame by frame and still works from the command line (the table is
in `docs/17-VMU-SAVES.md`); it is no longer part of the launcher.

**Owner-verified (2026-11-15): a save written through the title's Save screen loads back through its
Load Game screen.** That closes the save/load round-trip for M7; the remaining M7 work is the full
play-through (credits, every level, zero coverage gaps).

The card reader's numbers, kept for reference: the load list is the card's directory order, so entry
*n* on screen is entry *n* in `tools/vmu.py`'s listing; verified with eight synthetic entries (two
Downs → `.003`, five → `.006`, A on the first → the game's own `LOAD ERROR!` for the fake data).

One measured surprise: the pause menu's **Set Mark** is a checkpoint, not a card save — accepting it
reports **0 block writes** and returns to play. A VMU save is written through the game's
`VMSSavePage` → `SavePage` flow at the title's own save points/level transitions, and a Draconus
card file is `DRACONUS.001`…`.008`. `docs/17-VMU-SAVES.md` has the frame table, the checks and the
risks; `docs/ENGINE-CHANGES.md` patch 025 has the engine side.

## Launcher book-keeping (2026-11-14)

**Left empty for now.** The launcher records nothing about a launch beyond its own settings file
(`%APPDATA%\dream-recomp\launcher.json`); this is the place to keep that record if it is ever
wanted.

## M6 audio: done (2026-11-14)

The missing half of M6 was a Flycast audio reference. Flycast's SDL2 backend can be forced onto
SDL's disk audio driver, so it writes raw s16le stereo 44.1 kHz with no loopback and no system
sounds:

```powershell
tools\flycast-m6.ps1 -Seconds 600 -Out work\m6\flycast_10min.wav
tools\m6-check.ps1
```

`flycast-m6.ps1` also drives the emulator through its Lua API: START on guest frame 1800, A on 2100,
30-frame holds, exit on 36000. It prefers the retail v1.000 GDI by name and refuses ambiguous discs.

**Ten seconds of menu music** at 34.0 s in Flycast / 26.1 s in ours: sample correlation **1.0000**,
99.55 % of samples differ by an RMS of **1.1 LSB** (worst 5), spectral correlation median **1.0000**
(min 0.9999), every octave band within **0.00 dB**, **12/12** dominant peaks, centroid 286.0 Hz both.

**The title is silent in Flycast too** (15.55-33.55 s), so the baseline's open question is closed;
ours is silent 12.8-25.6 s only because START is scripted earlier.

**Ten minutes:** ours has seven silent runs; Flycast has the same seven at the same points. The three
long ones (about 54.5 s each, every ~145 s) are the game's **DEMO PLAY** attract screen, which stops
its music; a screenshot at 474 s shows it. No gap in ours is sounding in Flycast, so there are no
dropouts. The 600 s run has 1,870 key-ons, 6 active channels and 0 faults; its first 90 s are
byte-identical to the separate 90 s run. No engine change was needed for any of this.

`docs/13-M6-AUDIO-BASELINE.md` has the tables and the capture commands; `tools/audio-check.py` is the
measurement tool (info, align, compare, gaps, raw2wav).

## Launcher audio controls (2026-11-14)

The Audio tab now has a **volume slider** (0-100 %), an **output-device combo** filled from
`draconus_boot --list-audio-devices` and refreshed when it opens, and a **buffer/latency** choice
(93 / 186 / 372 ms). The engine side is `--audio-volume`, `--audio-device` and `--audio-buffer`:
volume is applied only to playback (so `--wav` stays full-scale), a named device that has gone away
falls back to the system default with a printed message, and the buffer sets the sink's queue
high-water mark. The CLI rejects out-of-range values rather than clamping them silently.

Verified: this machine lists six playback devices; a named device opens, a missing one falls back;
0/100 % volume and 93/372 ms buffers are accepted, 101 and 10 ms are refused. A 90 s run at volume
100 with the sink open produced the same WAV SHA-256 as the M6 capture, so the pass-through path is
unchanged. `launcher.py --selftest` and `--smoke` pass, including the slider-to-command-line check.
`docs/ENGINE-CHANGES.md` patch 034 has the details; the engine patch now also carries `audio/`.

## M5 — in-game (2026-11-15)

`tools\m5-check.ps1` is the gate. Its schedule reaches gameplay at about frame 4,600 and runs to
8,200 frames, so the last 60 s are in-game. It reported **101 untranslated calls**, not the four
or five the earlier scenes suggested. Two engine fixes close it, and the same run now reports
**`untranslated call targets: 0`** with unchanged PVR/Maple/interrupt counters:

1. **The constructor table was invisible to discovery (patch 037).** Ninety-seven of the calls
   were one each from `0x0C17D556`, the static-constructor loop over a 125-entry pointer table at
   `0x8C1FAD98`. The pointers are real functions, but pointer discovery accepted only targets whose
   forward scan found `RTS`/`BRA`/`JMP` within 200 instructions. These constructors begin with
   hundreds of straight-line calls; the first, `0x0C012A68`, reaches its first `BRA` at instruction
   498. The cap is 1,024, discovery goes from 8,936 to 9,126 functions, and the count falls to 4.
2. **A resume miss now tries the other owners (patch 038).** The last four are switch-case labels of
   a `mov.w` table at `0x0C234F38`. The root function at `0x0C234E7E` lists all four in its resume
   switch, but discovery also keeps the smaller fragment at `0x0C234F1C`, and `find_containing`
   returned that nearest fragment first; its miss went to the interpreter, which called the label
   again (hence "called from itself"). `resume_miss` now retries the other containing functions,
   nearest-first and never the same one twice, before the interpreter. The count is 0 over 8,200
   frames.

**Frame diff.** Ten checkpoints — title 900, character select 2400, Celanarin card 3000, story
3600, and gameplay 5400/5600/6000/6200/6600/6800 — are rendered from our side and captured from
Flycast at the same guest frames. Flycast's Lua presses the same buttons, then freezes each
checkpoint in a busy-wait while the host copies the client area with `PrintWindow` (window-minimize
and focus problems made a screen grab unreliable). Mean absolute RGB difference: **1.46-13.58**
against a threshold of **16**; a wrong-screen pair measures 27-38. The largest in-game values are
the title's own additive glow and idle pose at a different animation phase, plus the two renderers'
different texture filtering; composition, camera and HUD match. `tools\m5-check.ps1 -SkipFlycast`
runs only the zero-call half. Engine patch `patches/0003-m5-coverage.patch` carries 037-038.

## M7 — first two levels played (2026-11-17)

The owner played through the first two levels. The faults that surfaced were in presentation and
launch, not in the game logic, and are fixed:

* **Three 16:9 HUD faults from level play.** The death screen's black fade split into tiles with the
  world showing through two gaps, the map's destination markers did not move with the map, and the
  item wheel's rotating model was squeezed twice. The overlay pass now has a near-depth slab, treats
  a map and its markers as one element, and moves the wheel's model without rescaling it. The arena
  floor also sorted in front of a character strip; translucent strips now sort by the mean of their
  vertices' 1/w. Carried by `patches/0009-widescreen-overlay-depth.patch`.
* **Launch and upgrade faults.** Old nested bindings are migrated to the one per-user folder, a
  present rate above the panel's is clamped, and the Vulkan device is chosen after the window
  surface exists so a hybrid laptop uses a GPU that can present to it. Carried by patches
  0010-0012.

M7 remains open for the later levels, the credits, and any coverage gap they expose.

## Next phase

Order is by value per unit of risk, not by size:

1. **Human play-through.** The build is at real time in a window; judge feel — movie sync, menu
   responsiveness, input latency — and note anything that only shows up in play.
2. **Translation coverage beyond the first level.** M5 closes the first 60 s; the full-set
   discovery/emission blocker in `docs/11-M2-RESULTS.md` still limits heavier, later scenes.
   `DREAM_TRACE_UNTRANSLATED` names what a new scene is missing, and `--suggest-config` turns the
   report into seeds.
3. **M7 full play-through.** The first two levels are played (2026-11-17); the later levels, the
   credits and any coverage gap they expose remain. The save/load round-trip is owner-verified.

## Owner items

Nothing here blocks the next phase. Outstanding: delete the zero-byte CHDs and the stray `flycast/`
folder in the checkout, and an Apple Developer account for a macOS release build (WP3.6 will need
it).

The fresh-clone path is now closed: `setup.ps1` applies the engine patches from `patches/` after
fetching the pinned commit, keeps an already-imported disc image when re-run, and extracts the boot
executable from that dump when it is missing. Verified end to end on a clean clone.

## Performance pass: 60 Hz at 1440p (2026-11-14)

The target is 60 fps all the time at 1440p 16:9 (`--fullscreen --scale 4 --aspect 16:9`), hitches
and loads aside. The renderer was deciding it: **every presented frame went GPU → CPU → GPU**, a
19.7 MB readback and a 19.7 MB upload at 4x, plus a fence wait that stopped the CPU every frame.
`Offscreen` now keeps the frame in `SHADER_READ_ONLY` for the presenter to sample where it lies
(`Presenter::use_image`), and only brings the pixels back for the callers that need them — a render
to texture, `--framebuffer-writeback`, a screenshot, a capture, the frame counter.

| measure (4x 16:9, 6,500-frame title/intro run) | before | after |
|---|---|---|
| vblank cost (draw + present) | 1.49 ms | **0.29 ms** |
| present | 1.51 ms | **0.28 ms** |
| frame mean | 8.45 ms | **6.64 ms** |
| frames over 16.67 ms | 19 | **4** |
| worst frame | 297 ms | 29 ms (a load) |

The new `DREAM_TRACE_FRAME_HIST=1` measures what matters — the distribution, not the average, plus
CPU per frame and a line every 600 frames. An 18,000-frame run through the first level (title →
main menu → character select → Celanarin), fullscreen 1440p: **6.14 ms of CPU per frame over the
whole run, 12.4 ms in the heaviest gameplay window, and 13 frames of 18,000 over 16.67 ms** — every
one of them a load, with under 0.3 ms spent in the vblank. `DREAM_PROFILE=<ms>` and
`tools\profile-map.py` are the host profiler that says where the rest goes (emitted code, then the
non-RAM memory accesses, then the AICA). Parity and determinism are unchanged; see
`docs/ENGINE-CHANGES.md` patch 028.

### The frame counter was not free either (patch 030)

One of the things that list says still needs host pixels is the frame counter, and that turned out
to be ruinously expensive rather than merely un-optimised. With `F10`/`--fps` on at `--scale 4`,
CPU per frame went from **5.20 ms to 16.06 ms** and frames over 20 ms from 4 to 47 — the "dips into
the 40s" that made the game feel like it was slowing down, with the audio crackling because the
AICA queue is filled from the same thread once a frame.

The counter's translucent panel blends src-over-dst, so it read each destination pixel from
`Presenter`'s staging buffer, which is write-combined memory: ~175 ns a pixel, 9.5 ms a frame at 4x,
scaling with the panel's area rather than with anything that was being drawn. The overlay now takes
the frame as `under` — a cached-memory source for the destination side of the blend — so the staging
buffer is only written. The counter costs **1.5 ms** again. If you want it to cost nothing, the
remaining change is to composite it in `present.frag` on the GPU, which is named at the end of patch
030 and deliberately not done here.

### Judder with a steady frame rate (patch 031)

A steady 59-60 fps that does not feel smooth is not a frame rate problem, and no frame rate counter
can show it. A picture only changes on a vertical blank, so it is held for a whole number of
refreshes, and the number is `refresh / pictures-per-second`. `--display exclusive` was taking the
highest refresh the panel offers — 165.00 Hz against 59.94 pictures a second is **2.753**, so
pictures were held for two refreshes and then three: a 33 % swing in how long each is displayed,
about fifteen times a second. Exclusive fullscreen now takes the highest refresh that is a whole
multiple of the picture rate (119.98 Hz here, two refreshes each), states what it achieved, and names
the rates that would work when none divides evenly.

`DREAM_TRACE_PACING=1` reports the ratio, and whether presents are repeating a picture the title did
not re-render. That second number cleared the renderer: where it happens the guest asked for fewer
renders than there were presents, so the title was skipping them itself. Read the counter with that
in mind — it counts presents, so a title rendering 52 pictures a second still reads 60 FPS.

`DREAM_TRACE_FRAMES=<file>` dumps every frame's interval and vblank cost. It also settled the pacing
sleep: sd 0.76 ms with a lag-1 autocorrelation of -0.46, real but sub-millisecond and not what judder
looks like. A sleep-then-spin pacer cut it to 0.49 ms for 7 % of a core; rejected, with the numbers
in the comment.

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