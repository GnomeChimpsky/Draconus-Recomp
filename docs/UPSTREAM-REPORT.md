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

## Environment notes

* Windows 10/11 x64, MSVC 19.44, CMake 3.31, Ninja, Vulkan SDK 1.4.363.0, SDL3 3.2.28
  (built from source).
* The title's boot executable is plain (not scrambled), 2,339,580 bytes; the extraction was
  verified byte-for-byte against `dcdisc`.
* No game data is included in this report; all addresses are from the owner's own disc.
