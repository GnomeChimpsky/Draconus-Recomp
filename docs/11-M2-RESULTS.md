# 11 — M2 results: first translation and boot attempt

Date: 2026-11-04/05. Engine: `phobos665/dream-recomp` 0.1.0, `main` as fetched (tree dated
2026-10-29), MSVC 19.44, Ninja, `-DDREAM_DEV_INTERPRETER=ON -DDREAM_RENDERER=OFF`.

## Resolution (2026-11-05) — the fault was our extraction, not the game

Everything below about the entry chain was chasing a symptom. The cause was the
disc reader:

* `GdiImage.read` copied `count * 2048` contiguous bytes from a 2352-byte track. The
  first sector of every multi-sector read was correct; every sector after it was ECC
  and header data. Single-sector reads — including the boot stub — were fine, which is
  why the stub looked valid while everything it pointed at did not.
* Corrected, the extracted executable is byte-identical to the engine's own `dcdisc`
  output and its SHA-256 is `a59ff87c…4567da` (the previously recorded `86fc4486…`
  was the corrupted extraction).
* With the correct binary and the documented entry `0x8C010000`, the retail build now
  runs:

```
stop: fault
guest: 0.329 s (65,999,437 cycles), 29 frames, pc 0x8C001006
syscalls: flashrom=6 gdrom=19107 sysinfo=4
GD-ROM sectors read: 37
PVR: 0 TA chunks, 5 list inits, 0 renders (0 done), 2 frame swaps
untranslated call targets: 13,917
```

Boot, GD-ROM, flash, PVR list processing and frame swaps all happen; the next blocker
is a fault at `0x8C001006`, not the entry. The prototype still boots as before
(53 frames).

The sections below are kept as the record of how the symptom was diagnosed, but their
conclusions about "retail image inconsistency" and "dump integrity" are **withdrawn**.

## Working boot (2026-11-05, later) — the retail game runs and renders

With the corrected binary, the **development interpreter** boots the retail game and
keeps it running:

```
--interpret --max-frames 1800 --rtc-seed 1000000

stop: frame limit
guest: 29.857 s (5,971,411,749 cycles), 1800 frames, pc 0x8c09eda6
interrupts delivered: 96,068 (max nesting 2), traps: 0
GD-ROM sectors read: 1,474
PVR: 704,111 TA chunks, 1,684 list inits, 1,679 renders (1,678 done),
     1,680 frame swaps
```

* Two 600-frame runs are **byte-identical** in cycles, GD reads, TA chunks, list
  inits and swaps, so the boot is deterministic with a fixed RTC seed.
* `--stop-on-ta` stops at the first display-list write at frame 86, which is the
  first point the game draws anything.
* A **mixed** run (the three translated functions plus the interpreter) faults at
  `0x8C001006` after 29 frames. Pure interpretation does not. So the fault is a
  **translated↔interpreted boundary problem**, not guest logic: the address is the
  fourth entry of the engine's SYSINFO hook block (`0x8C0000B0`), i.e. the GD-ROM
  hook, and the handler page at `0x8C001000` is untouched `0xFF` in RAM.

For now the working configuration is `--interpret`; making the translated path work is
the next engine task.

### What `0x8C001006` is

* `0x8C0000B0` is the SYSINFO vector block the engine writes at boot:
  `0x8C001000, 0x8C001002, 0x8C001004, 0x8C001006, 0x8C00100A, 0x8C001008` for
  system, font, flash, GD-ROM, GD2 and misc.
* The fault PC is the GD-ROM hook (`0x8C001006`), which the game calls 19,107 times
  successfully before this failure.
* `DREAM_WATCH_WRITE=0x8C001000:0x20` shows **no CPU writes** to that page, and the
  dump at the stop shows `FFFFFFFF` there, so the engine dispatches hooks by address
  match rather than by executing stubs.
* The fault only occurs when a translated unit returns into interpreter-managed code
  (or vice versa); pure interpretation never hits it.

## Bisection: the fault is the translated→interpreted transition itself

`DREAM_INTERP_RANGE` hides translations in a range so the interpreter runs them. Two
constraints learned with it:

* the launcher refuses to start if the **entry function** is hidden
  (`no translated function at entry 0x8c010000`), so bisection must keep
  `0x0C010000` translated;
* with the entry translated and everything else hidden
  (`0x0C010100-0x0C250000`), and with either half hidden separately, the run **still
  faults at `0x8C001006` after 29 frames**.

Together with the fact that full interpretation (`--interpret`) runs 1,800 frames
cleanly, this rules out "one bad translated function". **Any** translated code present
at all is enough to break the run, so the defect is at the transition between
translated and interpreted code (the stub's tail-jump into interpreted code, or the
interpreter resuming a task at a hook address after a switch) — not in a particular
routine.

That is a much better bug report: it reproduces with a three-function translation, at a
fixed frame, and disappears when nothing is translated.

Next, in order: (1) translate *only* the entry stub and single-step the transition
(`DREAM_TRACE_NONLOCAL` plus a narrow watch), which is a small enough surface to read;
(2) if that stalls, take the renderer route and keep the interpreter for logic.

## Mixed-mode fault: latest evidence (task switch / RTE)

With the corrected binary, ordinary call-graph discovery from `0x8C010000` finds **3,285
functions** (30.9 MB of generated C++, which compiles). So "mixed mode" is not three
functions — it is most of the game translated with the interpreter filling the rest.

`DREAM_TRACE_NONLOCAL=1` shows the last events before the fault:

```
irq: vector 0x600 at pc 0x8c22ac4e pr 0x8c22ac4e r15 0x8c483e14 nesting 1
irq done: pr 0x8c22ac4e -> 0x8c22ac4e, r15 0x8c483e14 -> 0x8c483cb8
fault: unimplemented instruction 0xffff at 0x8c001006
```

The handler returns with `pr` unchanged but **`r15` moved by 0x15C** — a task switch or
longjmp performed by the game's own scheduler. The engine's report says
`task-switching RTEs: 0`, so it does not recognise it as a task switch, and control then
lands on the (unpopulated) hook page. That is a much more specific lead than "the hook
page is empty": the bug is in the interrupt-return / task-switch path of the translated
code, not in the hook table.

Next: reproduce this with the interpreter forced only around the switching function
(`DREAM_INTERP_FUNCS`), which will show whether the switch itself is correct and only its
translation is wrong.

## Rendered: first frames, title screen, and in-game 3D (2026-11-05, final)

The Vulkan renderer is now built and the retail game renders correctly.

Setup:

| Piece | Version / location |
|---|---|
| Vulkan SDK | 1.4.363.0, `C:\VulkanSDK\1.4.363.0` (installed via winget; needs admin for the VC++ redist) |
| SDL3 | 3.2.28, built from source into `work/sdl3` (`SDL3_DIR=work/sdl3/cmake`) |
| Build tree | `engine/build-render`, `-DDREAM_RENDERER=ON -DDREAM_DEV_INTERPRETER=ON` |
| Device | NVIDIA GeForce RTX 3080, 640×480 RGB565 |

Translation on this build: **599,526 of 668,478 bytes decoded (89.7 %)** — 3,285
functions, 302,381 instructions, 13 not lowered, 14,676 FP runtime branches, 34 switch
tables. Coverage roughly tripled compared with the corrupted-binary measurement.

Run (interpreter path, deterministic):

```
--interpret --window --max-frames 2400 --rtc-seed 1000000 --press start@1150,a@1400 --screenshot-at 2200
```

Milestones observed, in order:

| Presented frame | What is on screen |
|---|---|
| ~300 | Treyarch logo with its blue glow |
| ~900 | Title screen: Draconus logo, "PRESS START BUTTON", "COPYRIGHT(C)2000 TREYARCH LLC", "No VMU Found" notice |
| ~1600 (after Start) | The game's own VMU prompt: "You will not be able to save without a VMU", PLAY ANYWAY / NO VMU |
| ~2200 (after A) | **In-game 3D scene**: red sky, terrain, creatures, siege engine, brazier — 7.3 M TA chunks, 2,140 renders, 3,329 GD-ROM sectors |

The renderer reports 0 failed texture decodes (13 → 21 textures), 0 render-to-texture
writes, and a background plane on every drawn frame.

Screenshots are in `work/` (`first-frame.png`, `title-screen.png`, `after-start2.png`,
`ingame.png`); they are generated from the user's own disc and are not part of the
source tree.

The only remaining functional blocker is the translated-path fault at `0x8C001006`
(all runs above use `--interpret`).

## What was achieved

| Step | Result |
|---|---|
| Engine downloaded and configured | ✓ (needed `libchdr` fetched separately; the archive has no submodules) |
| Engine builds | ✓ after one local patch (see below) |
| Title config `games/draconus/draconus.toml` | ✓ load `0x8C010000`, link `0x0C010000` |
| Translator runs on the real binary | ✓ |
| Generated C++ compiles | ✓ |
| `draconus_boot.exe` links and runs | ✓ (headless) |
| Game reaches its first frame | ✗ — faults after 19–23 guest cycles |

## Discovery measurements (the useful numbers)

| Configuration | Time | Functions | Code bytes |
|---|---|---|---|
| call graph only | 0.1 s | 3 | 0.0 % |
| + pointer tables | 0.6 s | **14,913** | **26.1 %** (610,736 / 2,339,580) |
| + aggressive sweep | **>15 min, never completed** | — | — |

Pointer stats: 27,693 of 41,025 candidates accepted, 23 switch tables recovered.

**Why the call graph finds almost nothing:** the binary's entry at `0x8C010000` ends in
`jmp @r0` with a literal target, so a call-following walk stops immediately. Every
other title in the engine's list must hit similar stubs; Draconus's is unusually
indirect.

**The aggressive sweep is pathological on this title.** It does not finish in 15
minutes on one core; the other configurations finish in under a second. This is
reported as an engine issue, not worked around.

## Two engine defects found

1. **Renderer-free builds do not compile.** `runtime/boot/boot_main.cpp` handled
   `--present-mode` with `dream::render::vk::Window::PresentMode` outside
   `#ifdef DREAM_WITH_RENDERER`. Any launcher built with the Vulkan/SDL3 path
   unavailable fails with C3083/C2039. Patched locally — `docs/ENGINE-CHANGES.md` 001.
2. **Full-set `emit` does not terminate usefully.** With 14,913 functions, `emit`
   ran 308 s and produced **no output file**; a 500-function subset emits in 0.2 s and
   writes normally. The `game` command with the full set also never produced a unit.
   Emission, not discovery, is the current blocker for a complete translation.

## The boot fault, precisely

With the minimal configuration (entry stub only translated, everything else
interpreted), the run stops after 23 cycles:

```
fault: unimplemented instruction 0x0000 at 0x960dcfe9
untranslated call targets: 1
  0x960dcfe9 called from 0x0c175a74
```

A pure-interpreter run (`--interpret`) faults at the same place, so this is **not** a
translation artifact.

Trace:

* `0x8C010000`: `nop` sled, then it reads `CCR` (`0xFF00001C`), clears bits with
  `0x89AF`, sets `0x0800` (operand-cache enable), and does `jmp @r0` with
  `r0 = 0x8C175A6C` (literal at `0x8C01002C`, the only occurrence of that value).
* `0x8C175A6C` is **in the middle of a function** whose prologue is at `0x8C175A44`
  (`mov.l r14,@-r15` … `mov r15,r14`). Entering mid-prologue leaves `r14/r13/r12`
  unset.
* The code then does `mov.l @(0x18,PC),r0` → literal at `0x8C175AD0`, whose bytes are
  `e9 cf 0d 96` — high-entropy data, not a pointer — and `jsr @r0` jumps to
  `0x960DCFE9`.

Starting at the prologue `0x8C175A44` instead produces the same class of failure
(another jump through non-pointer data), so the region is not self-consistent as
position-independent code.

### What was ruled out

* **Translation:** interpreter-only run is identical.
* **Scrambling:** `dcdisc`'s own module documents that a GD-ROM stores
  `1ST_READ.BIN` *plain*, and that descrambling destroys it (verified by the engine
  author on other titles). Blindly descrambling produced a different binary that
  faults elsewhere, so the plain extraction used here is correct. **The M1 hash is the
  canonical one.**
* **Extraction:** the ISO entry is the only `1ST_READ.BIN`; size and hash are stable;
  the first bytes decode to a coherent CRT stub.

### What remains open

1. Whether the boot register state is wrong for this title. The engine's
   `docs/boot-state.md` says only `r15` has been corrected and that `r0`–`r7`, `gbr`,
   `vbr`, `pr`, `sgr` still come from a capture of the wrong instant. Draconus's
   IP.BIN bootstrap sets `SP = 0x7E001000` (operand-cache window) and `CCR = 0x092B`,
   while the engine hands over `r15 = 0x8C00F400`. That is a measurable difference,
   and the engine provides the method to test it (`--write-hash` A/B plus the Flycast
   oracle).
2. Whether the entry address is really `0x8C010000`. The stub's jump target is
   suspicious, but the BIOS does jump to `0x8C010000` and the engine does the same.
3. Whether the image is expected to be patched by the IP.BIN bootstrap. The bootstrap
   traced so far sets cache, stack, clears BSS and performs GD reads; the handover
   point was not yet isolated.

## M2b addendum — the prototype boots, the retail entry chain does not

Two new experiments changed the picture.

### 1. The prototype build boots

A second title (`engine/games/draconus_proto/`) was configured against the Jan-2000
prototype's `1ST_READ.BIN` (2,182,340 bytes, `6bbb73fd…`, SHA-1
`d258da92…` — note: different build). With the same engine and the standard entry:

```
guest: 0.723 s (144,662,863 cycles), 53 frames, pc 0x60000140
GD-ROM sectors read: 473
untranslated call targets: 13,466
```

So the engine, the HLE BIOS/GD-ROM and the build pipeline all work for this game
family. The retail failure is specific to the retail image's startup path.

### 2. The retail image's entry chain is inconsistent

Measured facts:

* Both builds' first 16 instructions are byte-identical: `nop` sled, then a
  read-modify-write of `CCR` at `0xFF00001C`, then `jmp @r0`.
* The literal at `0x8C01002C` differs by build:
  * prototype → `0x8C15AEAC`, which **is a trampoline**
    (`mov.l 0x8C15AEB4,r0; jmp @r0`) whose literal `0x8C15AEB8` is the startup code.
  * retail → `0x8C175A6C`, which is **not a trampoline**; it is the middle of a
    function, and the literals it loads (`0x8C175AC8`…`0x8C175AD4`) are
    high-entropy data (`0x544ED840`, `0x960DCFE9`, …), not pointers.
* The retail image *does* contain the prototype's startup code, at `0x8C1AAB88`, but
  **nothing references it** (no absolute pointer to it exists in the file).
* `IP.BIN` contains the literal `0x8C010000` at offset `0x6648` — the BIOS's handover
  really is `0x8C010000`, and the bootstrap does not reference `0x8C175A6C`.
* The executable exists in exactly **one** copy on the disc (searched all tracks for
  the 44-byte stub signature).
* Sector mode at the executable's LBA is **Mode 1**, user data at +16, matching the
  extraction; the engine's `codescan` reports "looks like SH-4 code: yes; ordered
  (not scrambled): yes" with a literal-pointer ratio of 0.80.

### 3. A working (but unverified) entry

Starting the retail binary at `0x8C1AAB88` — the copy of the prototype's startup code —
produces a stable run:

```
stop: frame limit
guest: 8.292 s (1,658,467,726 cycles), 1130 frames, pc 0x0c1aabe0
GD-ROM sectors read: 0
PVR: 1 renders (0 done), 1 frame swaps
untranslated call targets: 0
```

1,130 frames with no fault, but **no disc activity and essentially no rendering**, so
this is a running idle path, not a boot. It is recorded as an experiment, not as the
title's entry: the configuration keeps it with a comment saying so.

### Remaining hypotheses, in order

*(Superseded — see Resolution above. Kept as the diagnosis record.)*

1. **Superseded — the dump is fine** (it boots in Flycast). The actual cause was the
   multi-sector read bug in our own extractor.
2. **Superseded — the IP.BIN bootstrap does not patch the image.**
3. **Superseded — boot register state was not the cause of this fault.**

Build the engine's Flycast oracle (`tools/flycast/oracle`) and compare the first 23
cycles instruction-by-instruction:

```
dream-translate game --config ... --trace
```

with the oracle's syscall/register trace. That turns "which register is wrong"
into a measurement instead of a guess, and it is the engine's own documented method
(`docs/differential-harness.md`).

Only after that is it worth fixing `emit`/`sweep` for a complete translation: the
first gap must be understood before translating 26 % (or 100 %) of the binary.

## Reproduce

```powershell
# engine (already staged in engine/, with libchdr fetched)
cmake -S engine -B engine/build -G Ninja -DCMAKE_BUILD_TYPE=Release `
      -DDREAM_DEV_INTERPRETER=ON -DDREAM_RENDERER=OFF -DDREAM_BUILD_TESTS=OFF -DDREAM_WERROR=OFF
cmake --build engine/build --target draconus_boot --parallel
engine/build/games/draconus/draconus_boot.exe --config engine/games/draconus/draconus.toml --max-frames 120
```
