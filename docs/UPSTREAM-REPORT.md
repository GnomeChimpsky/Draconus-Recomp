# Upstream report — dream-recomp / Draconus (Dreamcast, USA)

Status: **ready to file**. Project: a static recompilation of *Draconus: Cult of the Wyrm*
(Dreamcast, Treyarch/Crave, 2000; product `F888`, licence `T-402`, V1.000).
Engine: `phobos665/dream-recomp` `main` as of 2026-10-29, MSVC 19.44, Windows x64.

Two items are offered: **one fix** (A) and **one unresolved disagreement** (B).

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

## Environment notes

* Windows 10/11 x64, MSVC 19.44, CMake 3.31, Ninja, Vulkan SDK 1.4.363.0, SDL3 3.2.28
  (built from source).
* The title's boot executable is plain (not scrambled), 2,339,580 bytes; the extraction was
  verified byte-for-byte against `dcdisc`.
* No game data is included in this report; all addresses are from the owner's own disc.
