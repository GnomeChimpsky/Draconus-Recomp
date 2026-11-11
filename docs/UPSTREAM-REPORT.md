# Upstream report — dream-recomp / Draconus (Dreamcast, USA)

Status: **ready to file**. Project: a static recompilation of *Draconus: Cult of the Wyrm*
(Dreamcast, Treyarch/Crave, 2000; product `F888`, licence `T-402`, V1.000).
Engine: `phobos665/dream-recomp` `main` as of 2026-10-29, MSVC 19.44, Windows x64.

Two fixes are offered: **A2** is the one that closed this title's translated-path fault (a handler
entry must stop at its RTE, not at the interrupted code's PR), and **A** is the earlier hook-dispatch
fix. **A3** and **A4** are the performance changes — the RAM fast path and the cached readback
memory — implemented and measured. **B** is the `--replay` false positive, now root-caused and
fixed. Sections C and D are the investigation that led to A2 and are kept as evidence; the fault
they describe no longer reproduces.

---

## A3. Measured: the RAM fast path from `docs/cpu-performance-study.md`

The study proposed inlining a mask-and-index fast path for main RAM ahead of `DcMemory::resolve()`
and measured 3.5x -> 5.8x on Crazy Taxi. This is that change, taken as far as the current accessor
interface allows, with the project's validation.

**Patch.** The eight `DcMemory` accessors are inline in `dc_memory.h`: an area-3 test
(`(a & 0x1C000000) == 0x0C000000`), a mask and a memcpy. The previous bodies remain as `*_slow` for
everything else — device dispatch, store queues, CCN registers, the replay journal, the write hash
and the write watch. The fast path is skipped whenever `journaling || tracing_writes()`, so the
differential harness and `--write-hash` see every store exactly as before; that is the one
correctness rule the change must not break, and it is covered by the existing replay runs.

**Measured on Draconus (Windows x64, MSVC 19.44, RTX 3080 host):** 600 frames 6.48 s -> 5.09 s
(1.5x -> 1.9x), 1,800 frames 28.72 s -> 23.39 s (1.04x -> 1.2x). Guest counters unchanged in both
(length-for-length TA chunks, list inits, renders, swaps, interrupts); engine tests 6/6; `--replay`
still clean apart from one known P0/P1 alias register value.

**Caveat.** This reproduces the *inline* half of the study's finding. The other half — removing the
virtual dispatch on the `Memory` interface — is not attempted here; emitted code still calls through
the abstract interface, and the compiler may or may not devirtualise it per call site. A follow-up
that template-binds emitted code to `DcMemory` would likely find more.

---

## A4. Measured: the offscreen readback wants cached host memory

The engine's performance study (§4.4) measured the offscreen round trip as a real windowed cost but
attributed it to the fence stall. On this title the stall was small; the *copy out* was not.

`HostBuffer::ensure` asked for `HOST_VISIBLE | HOST_COHERENT`. On a discrete NVIDIA GPU that resolves
to the device-local host-visible heap (BAR memory), which is write-combined: reading a 640x480 frame
out of it ran at roughly 180 MB/s, **6.6 ms per presented frame** on an RTX 3080, and 73 ms at
2560x1920. The GPU was idle for none of that; the CPU was simply reading uncached memory.

**Patch.** `HostBuffer::ensure` takes a `cpu_reads` flag that asks for `HOST_CACHED` first and falls
back to the old type. `Offscreen`'s readback passes it; transfer staging buffers do not.

| measurement | before | after |
|---|---|---|
| present, 640x480 | 6.71 ms | **0.16 ms** |
| windowed 1,800 frames | 36.28 s (0.8x) | **29.85 s (1.0x)** |
| windowed 600 frames at scale 4 | 43.75 s | **9.83 s (1.0x)** |

Screenshots are unchanged (byte-identical against the interpreter), and the headless figure is
within noise. The `DREAM_TRACE_FRAME_TIME` diagnostic that split draw from present is part of the
same patch; without it the cost looked like "the window is slow" rather than "the readback is
uncached".

---

## A2. Fix (closes the fault): a handler entry must stop at its RTE, not at PR

**Symptom.** The translated path stopped after 54 frames with an `rte` restoring
`0x60000040` into PC. It ran 600 frames (deterministic) if the exception handlers were forced
through the interpreter (`DREAM_HANDLER_INTERP`), which localised the defect to the handler entry
path but not to any instruction of the handler.

**Cause.** `System::on_untranslated` ran interpreted code until it returned to `c.pr`. That is right
for an ordinary call and wrong when the untranslated code is an exception handler: a handler does
not return through PR, and when the VBR+0x600 stub hands the body to the interpreter, PR still
belongs to the interrupted code.

It only matters on a **nested delivery**. The VBlank handler calls an ISR with `jsr @r14`, so PR is
that call's return address. An interrupt delivered inside the ISR makes a nested handler whose own
`jsr @r14` sets PR to the same value, so the interpreted run stopped at the ISR's `rts`, abandoned
the handler before its epilogue, and left its saved context on the guest stack. The outer handler's
epilogue then popped one slot out of step: SR landed in SPC, and the `rte` was classified as a task
switch to an implausible address.

**Patch.** `System::enter_exception` marks the handler entry; `on_untranslated` consumes the mark
and passes stop address 0 (stop only at the RTE):

```cpp
// system.h
bool handler_entry_ = false;

// enter_exception, around the entry call
handler_entry_ = true;
sh4::call_indirect(c, m, handler);
handler_entry_ = false;

// on_untranslated
const bool handler_entry = handler_entry_;
handler_entry_ = false;
const std::uint32_t return_to = handler_entry ? 0u : c.pr;
```

That is the stop address the `--interpret` path already used in `enter_exception`
(`devinterp::run(c, m, 0, iopt, nullptr)`), which is why it was immune.

**Measured effect.** 54 frames with a fault -> **600 frames and 1,800 frames, deterministic, no
fault, `task-switching RTEs: 0`**, and the guest state matches the interpreter: at 600 frames,
34,022 TA chunks, 508 list inits, 503 renders, 504 frame swaps, identical Maple counters, and
1,967,764,531 cycles against the interpreter's 1,967,764,490. `--replay` still reports 0
disagreements (2,448,650 calls over 120 frames).

**Regression test.** `runtime/tests/test_system.cpp`, "system: a nested handler's interpreted run
ends at its RTE, not at a stale PR". It builds a handler at an unregistered vector that pushes a
register, calls an ISR whose return address equals the stale PR, marks completion and RTEs. All six
assertions pass with the patch; reverting the one line fails four of them.

---

## A. Proposed fix: a hook marker must be dispatched at fetch time

**Symptom.** With a title whose boot path is mostly *interpreted* (the development
interpreter filling gaps), the guest faults after 29 frames with
`unimplemented instruction 0xffff at 0x8c001006`. `0x8C001006` is `Bios::kHookGd`, one of
the HLE hook markers; the page there is untouched `0xFF`.

**Cause.** Hooks are dispatched on call and jump transfers (`Flow::Call` / `Flow::Jump`
in `devinterp`, and `call_indirect`). A task that is resumed *on* a hook marker after a
scheduler switch arrives without either transfer kind, so the fetch loop reads the marker
as an instruction.

**Patch.** In `runtime/src/devinterp/interpreter.cpp`, at the top of the fetch loop:

```cpp
if (pc >= opt.native_lo && pc < opt.native_hi) {
    if (sh4::GuestFn fn = sh4::find_function(pc, &m)) {
        ++st.native_calls;
        c.pc = pc;
        if (!native(fn))
            c.pc = c.pr;
        mc.poll();
        continue;
    }
}
```

and in `runtime/src/system.cpp`, `on_untranslated` passes the hook range instead of empty
options:

```cpp
devinterp::Options iopt;
iopt.native_lo = hle::Bios::kHookSystem;
iopt.native_hi = hle::Bios::kHookGd2 + 2;
devinterp::run(c, m, return_to, iopt, &st);
```

**Measured effect on this title.** 29 frames / 37 GD-ROM sectors → **54 frames / 350
GD-ROM sectors**, deterministic across runs, and the fault moves to an unrelated address
(item B). The pure-interpreter path is unchanged (600 frames, byte-identical counters).

**Caveat.** Something similar may belong in `Flow::Ret` and `resume_at`; both were patched
locally and had no effect on this title, so they are not part of the proposal — the
fetch-time check alone was sufficient and is the smallest change that works.

---

## B. Unresolved: `--replay` reports one function disagreeing on the T flag

### Reproduction

```powershell
cmake -S . -B build-replay -G Ninja -DCMAKE_BUILD_TYPE=Release `
      -DDREAM_DEV_INTERPRETER=ON -DDREAM_RENDERER=ON -DCMAKE_BUILD_TESTS=OFF `
      -DDREAM_WERROR=OFF -DDREAM_TRANSLATE_EXTRA_FLAGS=--replay-hooks
cmake --build build-replay --target <title>_boot
<title>_boot --config games/<title>/<title>.toml --replay --max-frames 400 --rtc-seed 1000000
```

### Result

```
replay: 2,281,329 calls compared, 84,612 skipped
        (device writes 84,291, interrupts 289, non-local returns 9, too long 23),
        0 disagreements                      # --max-frames 60
```

At 400 frames:

```
replay: fn_0c22caa4 disagrees with the interpreter (entry fpscr 00040001, pr=0 sz=0)
  r0: translated 1,          interpreted 0
  r1: translated 0x8c22ac46, interpreted 0x8c22a966
  r3: translated 0x40000000, interpreted 0x40000001
  r4: translated 0x8c4ca200, interpreted 0x11
  r5: translated 0,          interpreted 0x8c483e90
  r7: translated 2,          interpreted 0
  t : translated 0,          interpreted 1
```

`fn_0c22caa4` is `0x0C22CAA4..0x0C22CB8E` (234 bytes, origin `call`). `--replay-only
0x0C22CAA4` still reports it.

### What has been checked

* **The differing register is `stc sr`.** The function ends with the critical-section exit
  `mov.l @r15,r0 / stc sr,r3 / … / ldc r0,sr`, and `r3` differs in exactly bit 0, `T`.
* **Every block of the function matches its translation** on inspection: prologue,
  `CAC2`, `CAC6`, `CACE`, `CAD8`, `CAEA`, `CAF2`, `CAFE`, `CB02`, `CB0C`, `CB20`, `CB36`,
  `CB5E`, `CB62`, `CB78`, `CB7C`, `CB7E` — including signed `cmp/gt`, logical `shlr2`, and
  `read_sr`/`write_sr` (which compose `T` from `c.t`, so `stc` cannot be stale).
* **The callees are not the cause.** With `DREAM_REPLAY_CHILDREN=1` added to
  `Replay::enter` (a local diagnostic) the run reports 12 disagreements and **zero nested
  children**: the callees are untranslated, so they never reach `Replay::enter` and run in
  the interpreter on both sides.

### FIXED: the replay false positive was a harness bug (2026-11-06)

Root cause found and fixed. The journal restores memory, but not host state reached through a
stateful HLE hook (GD-ROM file position, timers, RNG, Maple). Re-running such a call let the
replay observe a world the first execution had already changed, and the comparison reported a
disagreement that was not a code bug.

Fix: `Bios::sys_gdrom` marks the side effect (`runtime/src/hle/side_effects.*`), and
`Replay::exit` skips a call whose subtree set it, counted as `skipped_host_state`. After the
fix:

```
replay: 2,458,232 calls compared, 151,659 skipped
        (device writes 150,246, host state 169, interrupts 1,181,
         non-local returns 18, too long 45), 0 disagreements
```

**Zero disagreements over a whole 400-frame run** — the translated code matches the
interpreter everywhere the harness can check.

### Proven false positive (2026-11-06, instruction-level tracer)

The project's own tracer was used to execute `fn_0c22caa4` in both engines and record
every instruction: 1,130 instructions in range, **identical on every line** (`pc`, `r15`,
`t`, `sr`). With `DREAM_INTERP_FUNCS` forcing the function back to the interpreter (the run
confirms `interpreting 1 named functions`), the traces still match.

So this function behaves identically in both engines, and the replay disagreement is
definitively a **harness false positive** — the comparison method, not the code, is at
fault. A differential harness that reports a divergence here should be fixed before its
output is trusted on other titles.

### Important caveat (2026-11-06)

Forcing this function back to the interpreter
(`DREAM_INTERP_FUNCS=0x8C22CAA4:0x8C22CB8E`) leaves the boot failure **unchanged** — same
frame, same address, same counters. If the function's translation were the cause,
interpreting it would move the failure. So this disagreement is most likely a **harness
artifact** (the entry snapshot is not reproducible by the interpreter), not the game's
defect. It is reported because a differential harness that disagrees when nothing is wrong
is itself a bug worth fixing.

The stronger, independent evidence for the real defect is a swapped `SPC`/`SSR` at an
`rte`: `spc 0x60000040, ssr 0x8c2336fa` — `0x60000040` is a plausible `SR` and
`0x8C2336FA` a plausible `PC`.

### Important caveat (2026-11-06)

Forcing this function back to the interpreter
(`DREAM_INTERP_FUNCS=0x8C22CAA4:0x8C22CB8E`) leaves the boot failure **unchanged** — same
frame, same address, same counters. If the function's translation were the cause,
interpreting it would move the failure. So this disagreement is most likely a **harness
artifact** (the entry snapshot is not reproducible by the interpreter), not the game's
defect. It is still reported: a differential harness that disagrees when nothing is wrong
is itself a bug worth fixing.

The stronger, independent evidence for the real defect is a swapped `SPC`/`SSR` at an
`rte`: `spc 0x60000040, ssr 0x8c2336fa` — `0x60000040` is a plausible `SR` and `0x8C2336FA`
a plausible `PC`.

### Why it matters

The 54-frame boot stops at `0x60000040` (not in the Dreamcast map) with `SPC`/`SSR`
swapped at an `rte`. A wrong `T` is sufficient to explain that: it changes a branch, which
changes the path, which eventually restores a bad context.

### Suspicions, in order

1. **The entry snapshot is not reproducible.** `ReplayScope` is constructed at the top of
   the generated wrapper, so `entry_` is the `Ctx` at wrapper entry (`pr=0` in the message
   above). If the wrapper can be entered where `PR` is not yet the caller's return address
   (tail jump, or `call_indirect` restoring `PR` afterwards), the interpreter replay starts
   from a state the translated run never had.
2. **Re-entrancy.** `Replay::enter` keys on a single `active_`/`entry_`; comparing the same
   function from a nested context may overwrite the parent's snapshot.
3. **A block not matched one-to-one.** The `resume` label set contains block starts that a
   linear disassembly does not show; one of those may carry the defect.

### What would settle it

A snapshot/step mode: capture `Ctx` + the dirty-memory journal at a chosen function entry,
run the function in both engines from that state, and stop at the first differing
instruction. The pieces exist (`devinterp::run` from a captured `Ctx`, the journal,
`trace_return`); what is missing is the driver and per-instruction tracing in emitted code.

---

## C. The fault chain (most useful evidence for the real defect)

Independent of the harness question, the translated run's fault has been traced to a single
instruction. With `DREAM_TRACE_SR=1` (a local diagnostic that logs every `write_sr` with its
PC), the last writes before the fault are:

```
sr-write pc 0x8c2336d4 value 0x600000f0 old 0x70000000
sr-write pc 0x8c233100 value 0x60000041 old 0x600000f0
sr-write pc 0x8c233122 value 0x70000040 old 0x60000041
sr-write pc 0x8c233756 value 0xa05f6900 old 0x700000f1    <- corruption
sr-write pc 0x8c233784 value 0x8c2336fa old 0x20000100
```

`0x8C233756` is `ldc.l @r15+,sr`, the third pop of the title's own task-context restore:

```
8c233752  lds.l @r15+,fpscr
8c233754  lds.l @r15+,fpul
8c233756  ldc.l @r15+,sr      ; loads 0xA05F6900, a Holly/PVR register address
```

The matching save side is symmetric and in the same (untranslated) code:

```
8c233676  stc.l sr,@-r15
8c233678  sts.l fpul,@-r15
8c23367a  sts.l fpscr,@-r15
```

so the save and restore orders agree, yet the restore reads a slot holding a pointer instead
of a saved SR. Consequences, in order: `SR` becomes `0x60000040`, the next exception saves
that as `SSR`, the handler epilogue pops `SPC`/`SSR` crossed, and its `rte` restores
`PC = 0x60000040` — the observed fault.

Also ruled out by measurement: IMASK is honoured (`runtime/src/sh4/intc.cpp:82-89`), the
entry FP mode matches between engines (`fpscr = 0x00040001` at the restore), and both the
save and restore are interpreted in both modes.

**What this suggests:** the save and restore disagree because the *stack contents* differ,
which points at whatever runs between them — the task switch. `task-switching RTEs: 1` is
reported for the run. A within-run differential (snapshot the state, then execute both
engines from it) is needed to see the first divergent instruction; cross-run tracing is
confounded because the two runs take different paths from the first interrupt
(`r15 = 0x8C00F350 / `0x8C00F31C`, `spc = 0x0C22B502 / 0x8C22B540`).

## D. The remaining fault: the runtime's guest-task-switch path

> **Resolved 2026-11-10 by A2.** The task switch was never a property of the guest: it was the
> classifier reacting to a handler whose context frame had been left on the stack by an early
> stop. With A2 there are zero task-switching RTEs and the run is clean. The analysis below is kept
> because it is the evidence that led to A2, and because its closing question is still worth a
> maintainer's answer for titles that *do* switch tasks inside a handler.

**Reproduce in one command:** `tools\repro-translated-path.ps1` runs the translated path under
the diagnostics and prints the exception entries, the switch decision, the SPC writes, the writes
into the handler's saved slots, and the outcome. It needs only `engine/build-render` plus the
owner's disc, and modifies nothing.


This is the item worth the maintainer's attention, and it is now much better posed than "any
translation breaks at 0x8C001006" (that was fixed, see A).

**Observation.** Counting guest task switches with a local diagnostic (`DREAM_TRACE_SWITCH`):

| run | frames | task-switching RTEs |
|---|---|---|
| interpreter (`--interpret`) | 600 | **0** |
| translated | 54 | **1** |

The interpreter path — the one that plays the game — **never executes a task switch**. The
translated path takes exactly one, and that switch is where the resumed context is corrupted:
`SPC` is restored from a stack slot holding an SR value, so its `rte` resumes at `0x60000040` and
the run faults.

**Consequences.**

1. The differential harness cannot find this: `--replay` compares translated calls against the
   interpreter (2,284,637 compared, 0 disagreements, including device-writing calls), and the
   interpreter call-balance checker pairs 2,231,260 calls with 0 unbalanced — but neither ever
   observes a switch, because the interpreter never takes one.
2. There is therefore **no known-good reference** for the switch in this configuration. It is not
   "the same code, slower"; it is code the working path never enters.
3. The playable configuration is running a **degenerate schedule** (one task, no switches). That
   is likely why it works, and it is a fidelity gap: a title that streams or runs audio on another
   task would behave differently.

**Why the modes differ.** The guest's scheduler decides whether to switch from its own state,
which interrupt timing has already perturbed: translated code polls at function entry and backward
branches, the interpreter at its own points, so the same run takes interrupts at different
instruction boundaries and reaches a different decision.

**The question for the maintainer:** what may the runtime assume about a guest task switch? The
guest sets up `SPC`/`SSR` itself and then `rte`s; the runtime's `System::on_rte` interprets
"`spc` differs from the suspended frame" as a switch and throws to the new `SPC`. If a guest's
handler legitimately modifies `SPC` (as a scheduler does), when is that a switch and when is it a
corrupted frame — and should the runtime validate the `SPC` it resumes at (e.g. reject a value
outside the guest's code ranges) rather than resuming anywhere?

## Environment notes

* Windows 10/11 x64, MSVC 19.44, CMake 3.31, Ninja, Vulkan SDK 1.4.363.0, SDL3 3.2.28
  (built from source).
* The title's boot executable is plain (not scrambled), 2,339,580 bytes; the extraction was
  verified byte-for-byte against `dcdisc`.
* No game data is included in this report; all addresses are from the owner's own disc.
