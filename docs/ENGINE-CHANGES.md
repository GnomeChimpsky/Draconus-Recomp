# Engine changes ledger

Engine source lives in `engine/` (a pinned copy of `phobos665/dream-recomp`, GPL-2.0).
It is **not hand-edited**: every change is a minimal patch recorded here, so it can be
offered upstream and so an engine update can be re-applied deliberately.

| # | Date | Version | File(s) | Why | Upstreamable |
|---|---|---|---|---|---|
| 001 | 2026-11-05 | dream-recomp 0.1.0 (`main` @ 2026-10-29) | `runtime/boot/boot_main.cpp` | `--present-mode` referenced `dream::render::vk::Window::PresentMode` outside `#ifdef DREAM_WITH_RENDERER`, so **any** renderer-free build of a title's launcher failed to compile (`C3083`/`C2039`). Guarded the option; a renderer-free build now prints an error instead. | yes — bug fix |
| 002 | 2026-11-06 | same | `runtime/src/sh4/abi_bare.cpp` (`call_indirect`), `runtime/src/system.cpp` (`on_rte`), `runtime/src/devinterp/interpreter.cpp` | Diagnostic only: `DREAM_TRACE_HOOK=1` logs every dispatch into the hook page and every `rte` with `spc`/`frame_pc`/`r15`/`frame_sp`/`sr`/`ssr`. Off unless the variable is set; no behaviour change. | no — local aid |
| 003 | 2026-11-06 | same | `runtime/src/devinterp/interpreter.cpp` (fetch loop), `runtime/src/system.cpp` (`on_untranslated`) | **Fixes the `0x8C001006` fault.** A hook marker has no guest code, but the interpreter only dispatched hooks on call/jump transfers, so control arriving *on* a marker (a task resumed on the GD-ROM vector after a scheduler switch) fetched `0xFF` as an instruction. The fetch loop now dispatches an exact entry inside `[native_lo, native_hi)`; `on_untranslated` declares the BIOS hook page as that range. | yes — bug fix |
| 004 | 2026-11-06 | same | `runtime/include/dream/runtime/trace.h`, `runtime/src/trace.cpp`, `runtime/CMakeLists.txt`, `translator/src/main.cpp`, `translator/include/dream/translator/emit.h`, `translator/src/emit/emit.cpp`, `runtime/src/devinterp/interpreter.cpp` | **Instruction-level differential tracer.** `--trace-insns LO:HI` emits a guarded `dream::trace::insn()` before every instruction in range; `DREAM_TRACE_INSNS=lo:hi:FILE` records `pc r15 t sr spc ssr` from both engines. Addresses are masked to P0 because the translator emits in P0 while the guest runs in P1. Off by default; no behaviour change when unused. | yes — new feature |
| 005 | 2026-11-06 | same | `runtime/include/dream/runtime/hle/side_effects.h`, `runtime/src/hle/side_effects.cpp`, `runtime/src/hle/bios.cpp`, `runtime/src/devinterp/replay.cpp`, `runtime/include/dream/runtime/devinterp/replay.h`, `runtime/boot/boot_main.cpp` | **Fixes a `--replay` false positive.** A call whose subtree entered a stateful HLE hook (GD-ROM position, timers, RNG, Maple) was compared, but the journal only restores memory, so the replay observed different host state and reported a disagreement. `Bios::sys_gdrom` now notes the side effect and the harness skips such calls (`skipped_host_state`). | yes — bug fix |
| 006 | 2026-11-07 | same | `runtime/src/devinterp/interpreter.cpp` | **SH-4 rule: no interrupt immediately after an SR write.** `poll()` now skips one poll after `ldc Rm,SR` / `ldc.l @Rm+,SR`, as the manual requires. Harmless (the 600-frame interpreter run is unchanged) but it did **not** fix the translated-path fault. | yes — correctness |

## Patch detail — 001

```diff
         else if (!std::strcmp(argv[i], "--present-mode") && i + 1 < argc) {
+#ifdef DREAM_WITH_RENDERER
             const char* m = argv[++i];
             using PM = dream::render::vk::Window::PresentMode;
             ...
+#else
+            std::fprintf(stderr, "--present-mode needs a build with the Vulkan renderer\n");
+            return 2;
+#endif
         } else if (!std::strcmp(argv[i], "--bindings") && i + 1 < argc) {
```

Reproduce: configure with `-DDREAM_RENDERER=OFF` and build `<id>_boot`; without the
patch the launcher fails at `boot_main.cpp:1304`.

## Known engine issues (not patched — reported, worked around)

| Issue | Evidence | Workaround in this tree |
|---|---|---|
| Aggressive discovery sweep (`sweep = true`) does not complete | >15 min CPU, no output, on a 2.34 MB binary; the other modes finish in <1 s | `sweep = false` in `draconus.toml` |
| Full-set `emit` produces no unit | 14,913 functions: 308 s, no file; 500 functions: 0.2 s, normal output | translate a small set and rely on the development interpreter until fixed |
| Only `r15` of the boot registers is corrected | engine `docs/boot-state.md`; Draconus's IP.BIN sets `SP = 0x7E001000` while the engine hands over `0x8C00F400` | M2b: oracle trace before changing anything |

These are engine-side findings from M2; the first two must be fixed (or upstreamed)
before a complete translation of this title is practical.

**Root cause narrowed (2026-11-06): SPC/SSR are swapped at the handler's `rte`, and only
when the handler's entry is translated.**

* `DREAM_TRACE_HOOK=1` on the failing run shows exactly one bad `rte`:

  ```
  rte: spc 0x60000040 frame_pc 0x8c22ac4e r15 0x8c483944 sr 0x20000100 ssr 0x8c2336fa
  ```

  `0x60000040` is a plausible **SR** (MD|RB|mask) and `0x8C2336FA` a plausible **PC**, so
  the pair is swapped, not random.

* The same trace on `--interpret` shows **19,180 `rte`s and not one `spc` in
  `0x6000xxxx`** — the swap is specific to the translated path.

* The handler is installed at `0x8C000600` by copying 0x38 bytes from image
  `0x0C233614`. Only that first 0x28 bytes are a translated **relocation unit**
  (`draconus_reloc_8c000600.cpp`), whose generated code is faithful, including the
  self-modifying `mova` store and a real re-read of the patched literal
  (`c.r[0] = m.read32(0x0c00062cu);`).
* The handler then jumps to `0x8C233648`, which is **not translated** — it runs in the
  interpreter, and that is where `stc.l ssr,@-r15` / `stc.l spc,@-r15` and the later
  `ldc.l`/`lds.l` restore live.

So the divergence is at the boundary between the translated relocation unit and the
interpreted handler body — most likely the entry/interrupt-poll semantics of the
generated relocation unit (`if (c.cycles >= c.next_event) { c.pc = 0x0c000600u;
deliver_irq(c, m); }`) re-entering an interrupt at a point the interpreter does not, and
leaving SSR/SPC from the wrong frame.

**Next probe:** set `DREAM_INTERP_FUNCS=0x8C000600:0x8C000628` so the relocation unit is
interpreted too; if the fault disappears, the bug is in the relocation unit's
entry/poll behaviour and not in the handler body.

**Result of that probe: no change** (still `0x60000040`, frame 54). So the relocation
unit is not the trigger; the divergence is inside a translated function on the interrupt
path.

**Refined hypothesis:** the swap is *mechanical* — a 4-byte stack imbalance. The handler
pushes `stc.l ssr` then `stc.l spc`, so a restore that starts one slot low reads exactly
SSR where SPC belongs and vice versa, which turns `SPC=0x8C2336FA, SSR=0x60000040` into
the observed `SPC=0x60000040, SSR=0x8C2336FA`. A translated function that leaves `r15`
4 bytes off on the interrupt path would produce precisely this, and would explain why
pure interpretation never sees it.

**Next probe:** log `r15` at every `enter_exception` and at the matching `rte`, and diff
the pair against `--interpret`; the first frame where they disagree by 4 locates the
function that imbalanced the stack.

**Attempted 2026-11-06: cross-mode interrupt diff does not work.** The very first
interrupt already differs between the modes:

| | pc | pr | r15 |
|---|---|---|---|
| translated | `0x0C22B502` | `0x0C0131BC` | `0x8C00F3B4` |
| interpreter | `0x8C22B540` | `0x8C22B540` | `0x8C00F380` |

Translated code polls for interrupts at different points than the interpreter, so the
interrupt streams are not comparable item by item. The stack-balance check has to be
done **within one run** — `r15` at `enter_exception` versus `r15` at the matching `rte`
for the same frame — not by diffing two runs.

## Differential replay found the first disagreement (2026-11-06)

The engine ships a per-function differential harness, which is the piece everything above
was missing: `--replay` runs each translated function and compares its result against the
interpreter executing the same function from the same input state. It needs
`-DDREAM_TRANSLATE_EXTRA_FLAGS=--replay-hooks` at configure time.

Built as `engine/build-replay` and run with `--replay`:

```
replay: comparing every function against the interpreter
replay: 2,281,329 calls compared, 84,612 skipped
        (device writes 84,291, interrupts 289, non-local returns 9, too long 23),
        0 disagreements
```

At 400 frames the first disagreement appears:

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

`fn_0c22caa4` is `0x0C22CAA4..0x0C22CB8E` (234 bytes, origin `call`). Its generated code is
faithful for the prologue and the first three blocks (checked instruction by instruction),
so the divergence is later in the function or in one of its callees.

**Isolated further (2026-11-06):** `--replay-only 0x0C22CAA4` still reports the
disagreement, so it is inside this function's own execution (its callees included).

**The diverging register is the T flag.** The function ends with the classic SH-4
critical-section exit:

```
8c22cb62  mov.l @r15,r0        ; saved SR
8c22cb64  stc sr,r3            ; r3 = current SR
8c22cb66  mov.w 0x8c22cc3a,r2  ; mask
8c22cb68  and #15,r0
8c22cb6a  shll2 r0
8c22cb6c  and r2,r3
8c22cb6e  shll2 r0
8c22cb70  or r3,r0
8c22cb72  ldc r0,sr            ; SR = r0
```

`r3` is `stc sr`, and the reported values differ in exactly one bit: **bit 0, `T`**
(`0x40000000` translated vs `0x40000001` interpreted). The `t: 0 vs 1` entry in the
register diff is the same fact seen through the cached condition flag.

So the two engines disagree about **T at the point of `stc sr`** — either T is not
preserved across the call at `0x8C22CB56` (`jsr @r1`) in one engine, or the emitted
sequence around the `ldc r0,sr` / `tst` pair leaves the cached flag and the SR bit
inconsistent.

**Next:** compare the two executions from the entry state at the instruction
`0x8C22CB62` — print `c.t`, `SR`, and the saved word at `[r15]` immediately before it in
both engines. That pins whether T was already wrong on entry to that block or whether
`stc`/`ldc` handling desynchronises the cached flag.

**Resolved further (2026-11-06): the emitter is not at fault.**

* The emitted block is faithful: `c.r[3] = read_sr(c);` … `write_sr(c, c.r[0]);`.
* `read_sr(c)` is `(c.sr & ~SR_T) | (c.t & 1u)` — it composes T from `c.t`, and
  `write_sr` sets it back. So the T bit cannot be stale in the emitted sequence.
* Therefore `c.t` **already differed** when the block at `0x8C22CB62` was reached, i.e.
  the split happened earlier in the function or in one of its callees.

That reframes the bug: the function's own code is correct, so the divergence comes from a
call. The harness's skip list is the key — **84,291 calls were skipped because they write
devices**, plus 289 interrupts, 9 non-local returns and 23 "too long". A callee that
writes a device register is not compared at all, so a divergence inside one would surface
only downstream, exactly as here.

**Next probe:** replay-check the callees reached from `fn_0c22caa4` (the `jsr @r1` at
`0x8C22CB2C` and `0x8C22CB56` and the `jsr` inside the block at `0x8C22CAF2`) one at a
time with `--replay-only`, and look for one that is skipped as a "device write". If a
skipped callee diverges, the fix belongs in that function's device path (most likely a
PVR or AICA register read), not in the emitter.

**That probe is moot — the harness structure disproves it (2026-11-06).** Reading
`Replay::enter`/`exit`:

* nested calls are **not** compared: `enter` returns early when `active_ != 0`, so a
  comparison covers a whole outer call and everything it calls;
* the parent's journal records **every** write in that subtree, including children's;
* a parent whose journal saw a device write is **skipped**, never reported as
  disagreeing (`++skipped_device; return;`).

Because `fn_0c22caa4` was reported as *disagreeing*, no device write happened anywhere in
its subtree. So no callee diverged through a device path — the divergence is an ordinary
code-path difference inside the subtree, and the harness cannot localise it further
because it only compares outermost calls.

**Child tracing added (patch 002 extension, `DREAM_REPLAY_CHILDREN=1`) and what it shows:**
the harness reported 12 disagreements for `fn_0c22caa4` and **zero nested child calls**.
`Replay::enter` is reached only from the generated wrapper `ReplayScope`, so a callee that
is *untranslated* never reaches it — the callees here run in the interpreter on both
sides. Their behaviour is therefore identical by construction, and the disagreement must
come from `fn_0c22caa4`'s own translated code or from the entry state the harness records.

Every block of that function has now been compared against the disassembly —
prologue, `0x8C22CAC2`/`CAC6`/`CACE`/`CAD8`/`CAEA`/`CAF2`/`CAFE`/`CB02`/`CB0C`/`CB20`/
`CB36`/`CB5E`/`CB62`/`CB78`/`CB7C`/`CB7E` — and the emitted code matches instruction for
instruction (`cmp/gt` signed, `shlr2` logical, `read_sr`/`write_sr` composing T).

**Remaining suspicion: the entry state the harness records.** `Replay::enter` runs inside
the generated wrapper `fn_0c22caa4(...) { ReplayScope _replay(0x0c22caa4u, ...); ... }`, so
it snapshots `Ctx` at wrapper entry. The disagreement message reports `pr=0` at that
point. If the wrapper is entered by a path where `PR` is not yet the caller's return
address (a tail jump, or a call through `call_indirect` that restores PR afterwards), the
recorded state is not reproducible by the interpreter's replay, and the comparison is
invalid rather than the function being wrong.

**Instruction-level tracer built and the false positive proven (2026-11-06).** The tracer
now exists: `--trace-insns LO:HI` makes the translator emit a `dream::trace::insn()` call
before every instruction in the range, `DREAM_TRACE_INSNS=lo:hi:FILE` records them from
both engines, and the interpreter calls the same hook at its fetch point. Addresses are
masked to P0 (`0x0C...`) because the translator emits in P0 space while the guest runs in
P1.

Result for the suspect function (`DREAM_INTERP_FUNCS=0x8C22CAA4:0x8C22CB8E` forces it back
to the interpreter, and the run prints `interpreting 1 named functions` to confirm):

* translated trace: 1,130 instructions in range;
* interpreted trace: 1,130 instructions;
* **identical on every line** — same `pc`, `r15`, `t` and `sr` at every step.

So the function executes identically in both engines in the real run, and `--replay`'s
disagreement for it is a **harness false positive**, now proven rather than suspected.

**The faulting `rte` names the real lead.** The report prints

```
rte from pc 0x8c22ac4e sp 0x8c483a3c -> pc 0x60000040 sp 0x8c483944
```

i.e. the handler returns to a PC restored from `SPC = 0x60000040`. The corruption therefore
happens *before* that `rte`: either the interrupt entry saved a bogus PC, or the handler
wrote `SPC` itself.

**First trace window (2026-11-06, `DREAM_TRACE_INSNS=0x8C22AC00:0x8C22AD00`, now also
printing `spc`/`ssr`).** 427,640 recorded instructions. The tail is a tight call loop:

```
8c22ac46  sts.l pr,@-r15
8c22ac48  mov.l 0x8c22acac,r3
8c22ac4a  jsr @r3
8c22ac4c  nop
8c22ac4e  lds.l @r15+,pr      <- the address the report called "rte from pc"
8c22ac50  rts
```

so `0x8C22AC4E` is not an `rte` at all: it is the epilogue of a yield/scheduler call that
the guest executes over and over. In the last iteration `ssr` collapses to `0x00000004`
while `spc` is still `0x0C17B6D0`, and the fault PC is `0x60000040`. So the bogus PC is
**not** in `SPC` at that point — it is written after `0x8C22AC50`, i.e. just outside this
window.

**Second trace window (2026-11-06, `DREAM_TRACE_INSNS=0x8C175B00:0x8C175C00`).**
855,454 instructions. The tail is the syscall stub that jumps to the GD-ROM hook:

```
8c175b6c  mov.l 0x8c175b78,r0      ; r0 = [0x8C175B78] = 0x8C0000BC (the GD vector slot)
8c175b6e  mov.l @r0,r0             ; r0 = the HLE hook address
8c175b70  jmp @r0                  ; -> 0x8C001006
```

and on the final iteration `ssr` changes from `0x40000000` to **`0x04000000`** between
`0x8C175B6C` and `0x8C175B6E`, while `sr` stays `0x40000000` on every one of the 855,454
lines. `0x04000000` is exactly `0x40000000 >> 4` — a four-bit shift of the MD bit.

No instruction in the window writes `SSR`, and no line in the window has an invalid `SR`,
so the value is written by the interrupt/task-switch machinery, not by guest code. A
value that is `SR >> 4` points at a context save/restore that reads the SR/SSR pair at a
wrong offset or stride.

**SSR writers instrumented (2026-11-06, `DREAM_TRACE_SSR=1`; 238 writes in 120 frames).**
The last events before the fault:

```
ssr-write exception pc 0x8c22ac4e value 0x40000000
ssr-write exception pc 0x8c233122 value 0x60000040    <- SR itself is corrupt here
ssr-write ldc.l     pc 0x8c233782 value 0x8c2336fa    <- SSR receives a code address
```

Two facts follow, and they are the clearest statement of the bug so far:

1. The exception taken at `0x8C233122` already has **SR = `0x60000040`** (`read_sr` returns
   it), so SR was corrupted *before* that point. `0x60000040` is MD|RB with IMASK 4 — a
   plausible-looking status word, which is why nothing rejects it.
2. The handler's epilogue then loads **SSR from a stack slot holding `0x8C2336FA`**, a code
   address. The epilogue itself is correct guest code:

   ```
   8c23377e  lds.l @r15+,pr
   8c233780  ldc.l @r15+,spc
   8c233782  ldc.l @r15+,ssr
   8c233784  rte
   ```

   so SPC and SSR are being popped from a stack whose contents are already crossed.

Both the exception site (`0x8C233122`) and the epilogue (`0x8C233782`) are **untranslated**
— the interpreter runs them — so the interpreter is executing correct code over a corrupted
saved context. The corruption is therefore in whatever set SR/SPC before the exception, or
in the task context the runtime switched to.

**ROOT CAUSE LOCATED (2026-11-06, `DREAM_TRACE_SR=1`).** Every `write_sr` is now logged
with its PC. The last writes before the fault:

```
sr-write pc 0x8c2336d4 value 0x600000f0 old 0x70000000
sr-write pc 0x8c233100 value 0x60000041 old 0x600000f0
sr-write pc 0x8c233122 value 0x70000040 old 0x60000041
sr-write pc 0x8c233756 value 0xa05f6900 old 0x700000f1     <- the corruption
sr-write pc 0x8c233784 value 0x8c2336fa old 0x20000100
```

`0x8C233756` is `ldc.l @r15+,sr` — part of the game's own task-context restore:

```
8c233752  lds.l @r15+,fpscr
8c233754  lds.l @r15+,fpul
8c233756  ldc.l @r15+,sr
```

It loads **`0xA05F6900`** — a Holly/PVR register address — into SR, i.e. the stack slot it
reads holds a pointer instead of a saved SR. `0x8C233784` is the `rte` at the handler
epilogue, which then loads `0x8C2336FA` (a code address) into SR from the crossed pair.

So the fault is a **task-context restore reading the task's saved stack at the wrong
offset** — the save side and the restore side disagree by one slot. Every downstream
symptom (SR = `0x60000040`, SPC/SSR swapped, PC = `0x60000040`) follows from this.

**False positive fixed, and the harness now runs clean (2026-11-06).** With stateful HLE
calls skipped (patch 005):

```
--replay --max-frames 400
replay: 2,458,232 calls compared, 151,659 skipped
        (device writes 150,246, host state 169, interrupts 1,181,
         non-local returns 18, too long 45), 0 disagreements
```

**Zero disagreements over the whole run.** Every translated function the harness can compare
agrees with the interpreter, so the code generator is exonerated for this title: the
remaining fault is in the runtime's interrupt/task-switch machinery, exactly where the traced
chain (SR <- `0xA05F6900` at `ldc.l @r15+,sr`) points.

**Within-run differential built, and the false positive explained (2026-11-06).** The replay
harness now records both sides of a comparison in one process: `DREAM_REPLAY_TRACE=<prefix>`
plus `DREAM_REPLAY_DUMP=<addr>` writes `<prefix>.a.txt` (the translated execution) and
`<prefix>.b.txt` (the interpreter replay of the same call, same entry state, memory undone
by the journal). The instruction trace prints all 16 registers plus `t`, `sr`, `spc`, `ssr`,
`fpscr`, `pr`, `gbr`.

Result for `fn_0c22caa4`: the traces are identical for 52 instructions, then diverge at
`0x0C22CB30` — the instruction *after* the call at `0x0C22CB2C`:

```
A (translated) r0=4      r2=8c232824  r3=8c2325d0  r4=8c257020
B (replay)     r0=0      r2=8c175b54  r3=1         r4=0x11
```

The callee (`0x8C22A966`) is **untranslated**, so both runs execute identical interpreted
code — and yet they part, with the replay going through the syscall stub area
(`0x8C175B54`).

That is the explanation of the false positive: the journal restores **memory**, but it does
not restore **host-side state** reached through a BIOS HLE hook (GD-ROM file position,
timers, RNG, Maple). The first execution consumes that state; the replay observes it moved
on, takes a different branch, and the comparison reports a disagreement that is not a code
bug. The harness already skips calls whose journal saw a *device* access
(`journal_saw_device`, both read and write), but an HLE hook is not an MMIO access and is
not caught.

**Upstream fix to suggest:** mark the call as uncomparable when its subtree entered a
stateful HLE hook (GD-ROM especially), or snapshot/restore the hook's host state alongside
the journal.

**Superseded:** **Device-writing calls compared too (2026-11-06, `DREAM_REPLAY_ALLOW_DEVICE=1`).** The harness
normally skips a call whose subtree wrote a device, because the write cannot be undone. For a
diagnostic run that restriction was lifted (the device sees the write twice, which is fine
when the question is whether registers diverge):

```
replay: 2,284,637 calls compared, 87,938 skipped
        (device writes 0, host state 19, interrupts 248, non-local returns 87,653, too long 18),
        0 disagreements
```

**Zero disagreements again**, now covering the category that was previously the blind spot.
(The non-local count jumps to 87,653 because calls with device side effects are more likely to
unwind differently in the replay; those are skipped, not compared.)

This closes the question of the code generator for this title: every translated call the
harness can compare — with or without device writes — matches the interpreter. The fault is
therefore in the **runtime's interrupt/task-switch path**, not in emitted code.

**Skip set shrunk (2026-11-06, `DREAM_REPLAY_JOURNAL_LIMIT=200000`).** Raising the journal bound
moves the "too long" and "non-local" categories almost to zero:

```
default     : 2,458,232 compared, 151,659 skipped (device 150,246, host 169, interrupts 1,181,
              non-local 18, too long 45), 0 disagreements
bound 200k  : 2,051,024 compared,  75,126 skipped (device 75,095, host 1, interrupts 23,
              non-local 0,  too long 7), 0 disagreements
```

(Compared count *falls* with a larger bound because a bigger parent comparison absorbs the
nested calls that were previously compared on their own.)

**Still zero disagreements.** The only substantial category left is device writes (75,095),
which by definition cannot be replayed: the call is skipped, so a divergence inside one stays
invisible. That is now the entire remaining blind spot of the harness.

**Where this leaves the investigation.** The fault is a 4-byte stack imbalance in an
interpreted exception handler whose callees are all interpreted, in a run where every
translated call the harness *can* compare agrees with the interpreter. The blind spot is
device-writing calls. Closing it needs the engine author (state that can be snapshotted and
restored) or a Flycast reference run, not another local trace.

**The handler's callee is identified (2026-11-06, `DREAM_TRACE_CALL_AT=0x8C2336F6`).** The
dispatch at `0x8C2336F6` calls one of three functions, all of them **untranslated**:

| target | calls in 120 frames |
|---|---|
| `0x8C2330D6` | 45 |
| `0x8C232228` | 40 |
| `0x8C23FDD0` | 34 |

Because they are untranslated they run in the interpreter in **both** modes, and `--replay`
reports no translated function that unbalances `r15` (`r15` is compared at every compared
call). So the 4-byte drift is not produced by a translated function's prologue/epilogue.

What remains is the skip set: in the 400-frame run the harness skipped 151,659 calls
(device writes 150,246, host state 169, interrupts 1,181, non-local returns 18, too long 45).
A skipped call is not compared, so a difference inside one is invisible — and the handler's
stack is written by whatever ran inside those.

**Next:** shrink the skip set. `too long` (45) and `non-local` (18) are visible in small
numbers and can be compared by raising the journal bound or by using the within-run
differential on them; that is the cheapest remaining experiment.

**Superseded:** **Correction and a sharper statement (2026-11-06).** `SR = 0x60000040` is *legitimate*: the
code at `0x8C2330F8` is `stc sr,r0 / and r1,r0 / or #64,r0 / ldc r0,sr`, i.e. a critical
section setting IMASK=4. It is not corruption.

The corruption is the value the handler's epilogue loads into `SSR`: **`0x8C2336FA`**, which
is the return address `jsr @r14` at `0x8C2336F6` stores in `PR`. So the `SSR` slot receives
**PR's value** — the restore is **one 4-byte slot out of step** inside the handler.

The handler saves in this order: `ssr, spc, pr, gbr, vbr, mach, macl, r14..r0, sr, fpul,
fpscr, fr15..fr0`, and restores in the exact reverse, so the imbalance is not in the save
prologue. It must be introduced between them — by the call the handler makes at
`0x8C2336F6` (`jsr @r14`), which is a function pointer.

**Next:** identify `[r14]` at `0x8C2336F6`, check whether that function was among the
`--replay` skips (169 in the 400-frame run), and compare `r15` at its entry and exit. A
4-byte delta there is the whole bug.

**Superseded:** **Save/restore inspected (2026-11-06).** The two sides are symmetric guest code and both are
**untranslated**, so the interpreter executes them in both modes:

```
save  (0x8C23364A..)  stc.l ssr / stc.l spc / sts.l pr / stc.l gbr / stc.l vbr / sts.l mach /
                      sts.l macl / r14..r0 / stc.l sr / sts.l fpul / sts.l fpscr / fr15..fr0
restore (0x8C233730..) frchg / fmov fr0..fr15 / lds.l fpscr / lds.l fpul / ldc.l sr / ...
```

The pop order is the exact reverse of the push order, and `fpscr` is `0x00040001` at the
first restore in **both** runs, so the FP-mode stride hypothesis does not explain it at that
point.

The trace does show how early the runs diverge: at that same instruction the translated
run has `r15 = 0x8C00F350`, `spc = 0x0C22B502`, while the interpreted run has
`r15 = 0x8C00F31C`, `spc = 0x8C22B540` — different call paths, not just different code. So
cross-run comparison is confounded by interrupt timing from the very first interrupt, and
cannot be used to compare this function call by call.

**Conclusion of this investigation pass.** The chain is established from symptom to a
concrete instruction (`ldc.l @r15+,sr` reading a pointer slot), but the step that makes the
two runs take different paths happens earlier and needs a *within-run* differential (capture
state at a chosen point, then execute both engines from that identical state). That is the
snapshot/step harness described above, not another trace window.

**Superseded:** **Next:** find the matching save (`stc.l sr,@-r15` for the same task) and compare `r15` at
save and at restore. A 4-byte delta names the push/pop that is unbalanced — most likely in
the runtime's task switch (`nonlocal_return` / `resume_at`), which is where translated and
interpreted execution differ.

**Superseded:** **Next:** log every `write_sr` with the writing PC (emit `write_sr_at(c, v, pc)` instead of
`write_sr(c, v)`, or add pc to the helper) and find who writes `0x60000040` into SR. That is
the last hop of the chain.

**Superseded:** **Next:** find every write to `c.ssr` (only `enter_exception` and the guest `ldc rN,ssr`
should exist) and print the writer with a tag; the one that produces `0x04000000` names the
bug.

**Superseded:** **Next:** widen the window to the caller (`0x8C17B6D0`, `0x8C17B600:0x8C17B800`) or trace the
`jsr @r3` target at `[0x8C22ACAC]`, and watch `spc` until it becomes `0x60000040`.

**Superseded note:** **Next:** trace the window around the handler (`0x8C000600`, `0x8C2336FA`, `0x8C22AC4E`)
with the same tool and watch `SPC` — the tracer is now the instrument this needs.

**SR audit (2026-11-06): every SR read is composed.** Against the stale-T idea:

* generated code: `0` direct `c.sr` uses, `110` `read_sr`, `77` `write_sr`;
* the emitter touches `c.sr` only for `clrs`/`sets` (the S bit, `emit.cpp:1483/1487`); `stc
  sr` and `ldc sr` go through `read_sr`/`write_sr`;
* the runtime touches `c.sr` only in the interpreter's `clrs`/`sets` and the reset
  (`system.cpp:31`).

So no path can see a stale T bit: three hypotheses are now eliminated with evidence — the
entry snapshot (identical), the FPSCR `pr`/`sz` bits (they are FPSCR bits 19/20, not the PR
register), and stale T (all reads composed).

**Snapshot verified (2026-11-06, `DREAM_REPLAY_DUMP=0x0C22CAA4`).** The harness was
instrumented to print the state it records at a function's entry and the state its
interpreter replay starts from. They are identical (`pr 0x0c22c978`, `sr 0x400000f0`,
`fpscr 0x00040001`, `t 1`, `r15 0x8c00f30c`), so the replay does **not** start from a
different state: the entry-snapshot hypothesis is dead.

The dumps do show that `Ctx::sr` and `Ctx::t` are not kept in sync (`sr 0x400000f0` with
`t 1`); T lives in `c.t` and `read_sr` composes it. That is by design, but it means any
path that reads `c.sr` directly instead of `read_sr` sees a stale T — worth auditing, and
the next thing to check.

**Correction (2026-11-06): the replay disagreement is probably a harness artifact.**
Forcing the function back to the interpreter with
`DREAM_INTERP_FUNCS=0x8C22CAA4:0x8C22CB8E` leaves the boot failure **exactly** as it was (54
frames, `0x60000040`, same counters). If that function's translation were the cause,
interpreting it would move the failure. It does not, so `--replay`'s single disagreement does
not correspond to the actual defect. The strongest evidence remains the independent one: an
`rte` with `spc 0x60000040, ssr 0x8c2336fa` — SPC and SSR swapped.

**Next:** print the full entry `Ctx` (all registers, `pr`, `sr`, `fpscr`, `pc`) at the
wrapper for both the translated call and its replay, and diff them *before* the function
body runs. If they differ, the bug is in the harness's snapshot point, not the game.

## Next open issue — translated path stops at `0x60000040` (frame 54)

After patch 003 the translated path reaches 54 frames / 350 GD-ROM sectors and stops
here:

```
fault: unimplemented instruction 0x0000 at 0x60000040
guest: 0.744 s (148,710,301 cycles), 54 frames
interrupts delivered: 119 (max nesting 2), traps: 0
task-switching RTEs: 1
```

`DREAM_TRACE_NONLOCAL=1` shows the end of the run:

```
irq: vector 0x600 at pc 0x8c233122 pr 0x8c2336fa r15 0x8c483940 nesting 2
irq done: pr 0x8c2336fa -> 0x8c2336fa, r15 0x8c483940 -> 0x8c48385c
nonlocal: rts from pc 0x60000040 to 0x60000040 (r15 0x8c483944)
irq done: pr 0x8c22ac4e -> 0x8c233122, r15 0x8c483a3c -> 0x8c483944
resume: 0x60000040 -> untranslated (pr 0x8c233122 r15 0x8c483944)
```

What it says:

* an `rts` executes **at** `0x60000040` and returns **to** `0x60000040` (PC == PR), so the
  guest was already executing at that address before the rts;
* `0x60000000` is not in the Dreamcast memory map, so that fetch reads zeros;
* the value is not stored as a 32-bit literal in the executable (the single byte match is
  unaligned), so it is computed or restored from a task context, not loaded from data;
* `task-switching RTEs: 1` confirms the scheduler switch now happens correctly — this is
  a *different* bug from patch 003, in the saved/restored context of a switched task.

**Next probe:** log `SPC`/`SSR`/`PR`/`r15` at every `enter_exception` and at each
`rte` that changes the task, and find the first time a context slot receives
`0x6000xxxx`. The value looks like a register written into a PC slot — i.e. a
save/restore mix-up in the scheduler path.

## Bug report for upstream — RESOLVED (patch 003)

**Status 2026-11-06: fixed.** The fault was the interpreter fetching a hook marker as an
instruction; with the fetch-time dispatch in patch 003 the translated path reaches
**54 frames and 350 GD-ROM sectors** (previously 29 frames / 37 sectors) and then stops
at a *different* address, `0x60000040`, which is the next investigation.

The sections below are the diagnosis that led there, kept as the record.

## Bug report for upstream — any translation breaks the run at `0x8C001006`

**Title:** A title that runs perfectly under `--interpret` faults at a BIOS hook address
as soon as *any* code is translated.

**Reproduction (minimal):**

```powershell
draconus_boot.exe --config games/draconus/draconus.toml --max-frames 60 --rtc-seed 1000000
# -> fault: unimplemented instruction 0xffff at 0x8c001006, 29 frames
# hide every translated function except the 32-byte entry stub:
$env:DREAM_INTERP_FUNCS = "0x0C010020:0x0C250000"
# -> same fault, same frame
draconus_boot.exe --config games/draconus/draconus.toml --interpret --max-frames 1800 --rtc-seed 1000000
# -> 1800 frames, no fault
```

**Evidence gathered:**

* Both modes reach **PC `0x8C001006` at frame 29 with identical cycle counts
  (`62,703,530`) and identical interrupt counts (16)**. The interpreter continues past
  that PC; the mixed build executes guest memory there (`0xFFFF`) and faults.
* `0x8C001006` is the fourth entry of the SYSINFO hook block the engine writes at
  `0x8C0000B0` (the GD-ROM hook). The page at `0x8C001000` is untouched `0xFF`, and
  `DREAM_WATCH_WRITE=0x8C001000:0x20` records no CPU writes to it.
* The fault survives: hiding the interrupt handler at `0x8C000600`; hiding either half
  of the image; hiding every function except the entry; `DREAM_NO_WRITEBACK_INVALIDATE`;
  `DREAM_NO_G1_STUB`.
* The generated code for the entry stub is faithful (`read32`/`write32` on
  `0xFF00001C`, then `call_indirect(0x8C175A6C)` for the `jmp @r0`).
* A `DREAM_TRACE_NONLOCAL` trace shows the last interrupt returning with `pr`
  unchanged but `r15` moved by `0x15C` (a task switch), while the report says
  `task-switching RTEs: 0`.

**Final trace result (2026-11-06, `DREAM_TRACE_HOOK=1`, interpreter dispatch also logged):**

```
hook: interp 0x8c001006 from pc 0x8c175b84 pr 0x8c22ac4e r15 0x8c483e14
hook: interp 0x8c001006 from pc 0x8c175b84 pr 0x8c22ac4e r15 0x8c483cb8   <- post-switch stack
fault: unimplemented instruction 0xffff at 0x8c001006
```

So the GD-ROM hook **is** dispatched — from interpreted code at `0x8C175B84`, with the
return address in `PR` — and the run then continues **at the marker** (`0x8C001006`)
instead of at the call's return site. Nothing else lands there: no `rte` targets it, no
`rts` returns to it, and no `call_indirect` goes to it.

That is the whole bug in one line: after the HLE hook returns (or signals a wait), the
PC is left on the marker, and the fetch loop executes the marker as an instruction.
A fix belongs at the fetch/dispatch boundary — a PC that is a registered entry should be
dispatched rather than interpreted — not in `Ret`, `resume_at`, or `on_rte`, where three
attempts had no effect.

**Candidate code locations (patched locally and reverted — none fixed it):**

* `runtime/src/devinterp/interpreter.cpp`, `case Flow::Ret:` — a return sets `c.pc = t`
  without dispatch, unlike `Flow::Jump`/`Flow::Call`, which consult `find_function`.
* `runtime/src/sh4/abi_bare.cpp`, `resume_at()` — matches by *containing extent*
  (`find_containing`), so an exact entry with no extent (an HLE hook marker) misses.
  Adding an exact `find_function(pc)` match before it did **not** change the fault.
* `runtime/src/sh4/abi_bare.cpp`, `deliver_irq()` / `rte()` →
  `g_hooks->on_rte()` — the last trace line before the fault is an `irq done` whose
  handler returns with `r15` changed by `0x15C`. The handover after that RTE is the
  remaining suspect: it sets a PC that is an HLE hook marker, and nothing re-dispatches
  it.

**Trace result (2026-11-06, `DREAM_TRACE_HOOK=1`):** the last events before the fault are

```
hook: call_indirect 0x8c001000 from pc 0x0c175c86 pr 0x0c2324aa r15 0x8c484084
rte: spc 0x0c22cdc4 frame_pc 0x0c22cdc4 r15 0x8c483e1c ...
rte: spc 0x8c22ac4e frame_pc 0x8c22ac4e r15 0x8c483e14 ...
rte: spc 0x8c22aa68 frame_pc 0x8c22aa68 r15 0x8c483dc0 ...
rte: spc 0x8c22ac4e frame_pc 0x8c22ac4e r15 0x8c483e14 ...
fault: unimplemented instruction 0xffff at 0x8c001006
```

* No `rte` lands on `0x8C001006`, and there is **no `call_indirect` to `0x8C001006`** at all
  (the hook calls logged are `0x8C001000` and `0x8C001004`).
* Every observed `rte` returns to the same PC it interrupted (`spc == frame_pc`), so
  `switched` is false and `task-switching RTEs: 0` is consistent.
* Therefore the PC becomes `0x8C001006` **inside translated code** — a return or jump the
  emitter performs without going through `call_indirect` — immediately after an `rte`
  resumes at `0x8C22AC4E`.

**Next probe:** trace the emitter's return/jump path (`c.pc = ...` in emitted code, or
`NonLocalReturn`) whenever the new `c.pc` falls in `[0x8C001000, 0x8C00100C)`. That is the
only remaining unlogged way the PC can reach a hook marker.

**Inconsistency worth chasing (last clue):** `System::on_rte()`
(`runtime/src/system.cpp:137`) decides a task switch happened by comparing
`c.spc`/`c.r[15]` against the suspended frame (`frame_pcs`/`frame_sps`). The run reports
`task-switching RTEs: 0`, yet the interrupt trace shows the handler returning with
`r15` moved by `0x15C`. So either that stack move is *not* a task switch and something
else restores PC `0x8C001006`, or the detection misses the switch. Note also that when
`switched` is false, `on_rte` ends with `c.pc = c.spc` and **no dispatch** — the same
hook-marker gap as `Flow::Ret`.

Both local patches kept the interpreter path working (600 frames) but left the mixed
fault unchanged, so they were reverted rather than carried unverified.

**Most likely area:** hook dispatch when the guest reaches a hook address through a
path other than a translated call — e.g. after an interrupt/task switch — or the
interaction between the entry stub's tail `jmp` and the interpreter.

## ROOT CAUSE (2026-11-06): the handler's restore is one 4-byte slot out of step

Two new diagnostics (`DREAM_TRACE_SWITCH`, `DREAM_TRACE_SPC`) and an instruction trace over the
handler range pin the fault to the guest's own exception epilogue.

The switch report:

```
exc:    vec 0x600 pc 0x8c22ac4e  spc 0x8c22ac4e  r15 0x8c483a3c  nesting 1
exc:    vec 0x600 pc 0x8c233122  spc 0x8c233122  r15 0x8c483940  nesting 2
switch: spc 0x60000040 sp 0x8c483944 frame_pc 0x8c22ac4e frame_sp 0x8c483a3c
```

and the instruction trace across the epilogue:

```
save (r15 0x8c4838f8 downwards)   spc 0x8c233122   ssr 0x60000040   pr 0x8c2336fa
8c23377e  lds.l @r15+,pr
8c233780  ldc.l @r15+,spc
8c233782  ldc.l @r15+,ssr
8c233784  rte

restore (r15 0x8c483938 upwards)  pr <- 0x8c233122   spc <- 0x60000040   ssr <- 0x8c2336fa
```

Each pop takes the **next slot's value**: PR receives the saved SPC, SPC receives the saved SSR,
SSR receives the saved PR. The restore starts exactly **4 bytes too high**.

**Why:** the FPU mode differs between the two sides. The save explicitly sets
`fpscr = 0x00040001` before pushing the FR registers; at the restore `fpscr = 0x00000000`. An
`fmov` on SH-4 moves 4 or 8 bytes depending on FPSCR.FR/SZ, so the save and the restore do not
move the same number of bytes and every later slot shifts.

This is the same hazard the emitter documents for translated `fmov` ("the emitter decides the
size of an `fmov` from a static guess at it", `replay.cpp`), except here it is the **interpreter**
executing the guest's own save/restore with a mode that changed in between.

**Byte accounting: the drift is one call (2026-11-06).** Walking the handler from its entry:

```
entry r15        0x8c48393c
after entry pop  0x8c483940   = SP at exception entry (correct)
lowest (save)    0x8c48385c   the save pushed 57 words
before restore   0x8c483860   <-- +4 appeared here, with no push in between
final (rte)      0x8c483944   = expected +4
```

Between the last save push (`0x8C2336CC`, r15 `0x8C48385C`) and the restore
(`0x8C2336FA`, r15 `0x8C483860`) the only stack-moving event is the call at
`0x8C2336F6` (`jsr @r14`, the VBR-dispatched game handler). **That callee returns with r15 one
word higher than it was called with**, and every later pop is therefore one slot off: PR takes
SPC, SPC takes SSR, SSR takes PR — which is exactly the corruption observed, and why the `rte`
resumes at `0x60000040`.

The three possible callees (`0x8C232228`, `0x8C2330D6`, `0x8C23FDD0`) are all **untranslated**,
so the interpreter runs them in both modes. That makes the next question sharp: either one of
those functions has an instruction the interpreter implements with an unbalanced stack, or the
call/return around it is mishandled (delay slot, `rte` inside the callee, or a non-local return).

**The callee is a trampoline (2026-11-06).** `0x8C232228` does not push anything; it clears
two device bits and tail-jumps:

```
8c232228  mov.l 0x8c2322f4,r3      ; a register byte
8c23222c  and #251,r0 / mov.b r0,@r3
8c232230  mov.l 0x8c232304,r4      ; another register
8c232238  mov.w r2,@r4 / ...
8c232242  mov.l 0x8c232308,r1
8c232246  mov.l @r1,r0
8c232248  jmp @r0                  ; tail call
```

The trace confirms `r15` is unchanged through all 17 instructions (`0x8C48385C`), so the +4 is
introduced **after** the tail jump, by the function at `[0x8C232308]`. The whole chain is
untranslated, hence interpreted in both modes, which is why `--replay` never saw it: the harness
compares calls, and these are interpreted on both sides — if the interpreter mishandles an
instruction here, both sides are "consistent" and the harness stays silent.

**Chain followed one level further (2026-11-06).** The trampoline's tail jump is logged by
`DREAM_TRACE_CALL_AT` (extended to `Flow::Jump`):

```
jump-at 0x8c232248 -> 0x8c1a62ec r15 0x8c48385c     (the failing call)
jump-at 0x8c232248 -> 0x8c1a62ec r15 0x8c4839e4     (earlier calls, other stack depths)
```

So the chain is `0x8C2336F6` → `0x8C232228` (trampoline) → `0x8C1A62EC`. That last function is
untranslated (interpreted in both modes) and its own frame is balanced over the traced window
(`r15` returns to its entry value), so the +4 is not introduced there either.

The fault is therefore in a call chain of **interpreted** functions, which is exactly the region
the differential harness cannot see: both engines run the same interpreter there.

**Call-balance logger built (2026-11-06, `DREAM_TRACE_BALANCE=1`).** The interpreter now pairs
every call with its return and reports any call whose stack pointer differs. Result:

| run | unbalanced calls |
|---|---|
| translated (faults at frame 54) | **1** |
| interpreter (works) | **0** |

and the single one is:

```
unbalanced: call 0x8c2336f6 -> 0x8c2330d6 r15 in 0x8c483958 out 0x8c483860 (-248)
```

`0x8C2330D6` is one of the three VBR-dispatched handler functions, untranslated in both modes —
so this is the guest's own scheduler entry, and the `-248` is a **task switch** (the stack moves
to another task). In the working run the same call is either balanced or never paired, so the
switch path differs between the modes.

That reframes the remaining work: the defect is not a wild stack pointer inside a function, it is
**when and how the scheduler's switch is taken**. The translated path reaches a switch that the
interpreter path does not, or reaches it in a different state.

**Balance-logger statistics (2026-11-06).** The logger only observes *interpreted* code, so:

| run | calls paired | unbalanced |
|---|---|---|
| interpreter | **2,231,260** | **0** |
| translated | a handful (only the interpreted fragments) | 1 (the task switch) |

That is strong evidence the interpreter's call/return and stack handling are sound over 2.23 M
calls, and it also shows the instrument cannot discriminate the two modes — the same blindness as
`--replay`: the code that differs is not the code being observed.

**New hypothesis: the SH-4 rule about SR-modifying instructions is not implemented.** The trace
around the fault is:

```
exc:    vec 0x600 pc 0x8c22ac4e  r15 0x8c483a3c  nesting 1
exc:    vec 0x600 pc 0x8c233122  r15 0x8c483940  nesting 2     <- nested, taken inside the handler
switch: spc 0x60000040 sp 0x8c483944 frame_pc 0x8c22ac4e frame_sp 0x8c483a3c
nonlocal: rts from pc 0x60000040 to 0x60000040
```

The guest's handler restores `SR` (`ldc.l @r15+,sr` at `0x8C233756`) and *then* pops the remaining
saved context (r0-r14, macl, mach, vbr, gbr, pr, spc, ssr) before `rte`. Once SR is restored the
interrupt mask is the interrupted task's again, so an interrupt delivered in that window pushes a
frame **over the slots still waiting to be popped** — which is exactly the crossed
`pr`/`spc`/`ssr` observed.

On real SH-4 hardware an interrupt is **not accepted immediately after an instruction that writes
SR** (`LDC Rm,SR`, `LDC.L @Rm+,SR`, `RTE`); the following instruction always executes first. A
search of the runtime finds no such rule — `poll()` is just `if (c.cycles >= c.next_event)
deliver_irq(...)`. Honouring it would push the nested interrupt past the epilogue's pops.

**Tested and refuted (2026-11-07).** The inhibit was implemented in the interpreter (patch 006)
and the translated path still stops at the same place:

```
stop: fault
guest: 0.744 s (148710312 cycles), 54 frames, pc 0x60000040
task-switching RTEs: 1
```

identical to before apart from 11 cycles of the added check. The 600-frame interpreter run is
unchanged (same cycles, same PVR counters), so the rule is kept as a correctness fix and the
hypothesis is closed: the nested interrupt is **not** delivered immediately after an SR write.

**Where the remaining question sits:** the nested exception is taken at `0x8C233122` with
`r15 = 0x8C483940` — the outer handler's *entry* stack pointer, i.e. after its whole frame was
popped — while `nesting` is 2. So the scheduler switched stacks and an interrupt arrived in the
new context. Comparing what the interpreter run does at that same point (it never takes this
switch) is the next discriminator, and it needs a within-run trace rather than a cross-run diff.

**Superseded:** **Next:** implement the one-instruction inhibit after SR writes in both engines (emitter label
after `ldc ...sr`, interpreter flag in `poll`), and see whether the translated path gets past frame
54. This is the first hypothesis that explains *why an interrupt lands in the wrong window* rather
than where the stack went wrong.

**Superseded:** **Next:** compare the two runs at this call — the same `(pc, target, r15)` pair in both modes,
around frame 54 — and see whether the switch itself is taken in the interpreter run. If it is not,
the difference is interrupt timing, and the emitter's poll placement (function entry and backward
branches) is the mechanism to examine.

**Superseded:** **Better tool for the next session:** log every interpreted call and return with `(pc, target,
r15)` and pair them, flagging any call whose `r15` on return differs from `r15` at entry. That
finds the unbalanced function directly instead of walking one frame per trace window.

**Superseded:** **Next:** trace `r15` from the tail-jump target (`[0x8C232308]`) to the return at `0x8C2336FA`,
and compare the net stack delta with the disassembly of that function. This is now a short walk
through one call chain rather than an open search.

**Superseded:** **Next:** trace r15 through the callee at `[r14]` — entry, every push/pop, and the return — with
`DREAM_TRACE_INSNS` over that function's range, and compare its stack delta with what the
disassembly says it should be. A `+4` there is the whole bug.

**Superseded:** **Next:** find what clears FPSCR to 0 between the save and the restore (the nested exception at
`0x8C233122` is the prime suspect — its handler may leave FPSCR cleared), and check whether the
save should be restoring FPSCR before the FR pops rather than after.

## The working path never exercises the task switch (2026-11-07)

Counting switches in each mode with `DREAM_TRACE_SWITCH`:

| run | frames | task-switching RTEs |
|---|---|---|
| interpreter | 600 | **0** |
| translated | 54 | **1** |

The interpreter path — the one that plays the game — **never takes a task switch at all**. So:

1. Every hour of "it works on the interpreter path" testing never covered the guest's scheduler.
   The failing code is not "the same game running faster"; it is code the working path never
   enters.
2. The translated path reaches the switch once, and that single switch is where the context is
   corrupted. The defect is inside the runtime's handling of a guest task switch, which until now
   had no working reference at all.
3. It also means the playable build is running a **degenerate schedule** — one task, no switches.
   That may be why it plays at all while the switch is broken, and it is a fidelity gap in its own
   right: a title that streamed, played music on a separate task, or ran a second thread would
   behave differently.

**Why the modes differ:** the switch is taken when the guest's scheduler decides to, which depends
on state that interrupt timing has already changed. Translated code polls at function entry and
backward branches; the interpreter polls at its own points, so the same run gets interrupts at
different instruction boundaries and the scheduler reaches a different decision.

**What this means for the fix:** there is no "known-good" behaviour to copy for the task switch,
because the good path has never executed it. The switch has to be validated against the
architecture (what the guest sets before its `rte`, and what the runtime may legally assume),
which is exactly the question for the engine author — and it is now a much better-posed question
than "translation breaks at frame 54".

### Repair experiment (2026-11-07): the corruption is in guest memory

A sanity rule was tried (`DREAM_REPAIR_SWITCH=1`): when a "switch" resumes at an `SPC` that is not a
guest code address, treat it as corruption and resume the interrupted frame instead.

```
repair: implausible spc 0x60000040 at sp 0x8c483944, resuming frame pc 0x8c22ac4e sp 0x8c483a3c
stop: fault
guest: 0.744 s (148749561 cycles), 54 frames, pc 0xac000010
```

It fires and repairs the frame correctly, then the run faults at `0xAC000010` instead — another
implausible address. So the runtime's bookkeeping is not the only damage: **guest memory itself was
overwritten** (the handler's saved context on its own stack), and re-entering from the interrupted
frame walks into the next piece of corruption.

That closes the "just fix the frame" family of fixes: whatever writes `0x60000040` into the saved
SPC slot writes real memory, and it happens while the handler's frame is still live.

### Watchpoint: who writes the saved context (2026-11-07)

`DREAM_WATCH_WRITE=0x8C483938:0x0C` logs every store into the three slots the epilogue will pop
(`pr` 0x938, `spc` 0x93C, `ssr` 0x940). The whole sequence, in order:

```
write 0x8c48393c = 0x00000001 at pc 0x8c233042  r15 0x8c48393c
write 0x8c483938 = 0x8c233136 at pc 0x8c23304a  r15 0x8c483938
write 0x8c483940 = 0x00088a03 at pc 0x8c2330de  r15 0x8c483940
write 0x8c48393c = 0x00000000 at pc 0x8c2330e2  r15 0x8c48393c
write 0x8c483938 = 0x00ee6b28 at pc 0x8c2330e6  r15 0x8c483938
write 0x8c483938 = 0x8c22bb68 at pc 0x8c22ab6c  r15 0x8c483938
write 0x8c48393c = 0x00000001 at pc 0x8c001006  r15 0x8c483938   <- HLE hook
write 0x8c483940 = 0x00000080 at pc 0x8c001006  r15 0x8c483938   <- HLE hook
write 0x8c483940 = 0x8c2336fa at pc 0x8c2330e8  r15 0x8c483940
write 0x8c48393c = 0xffffff0f at pc 0x0c000600  r15 0x8c48393c   <- relocation unit
write 0x8c48393c = 0x60000040 at pc 0x8c23364a  r15 0x8c48393c   <- handler saves SSR
write 0x8c483938 = 0x8c233122 at pc 0x8c23364c  r15 0x8c483938   <- handler saves SPC
```

Three things this shows:

1. **The regions overlap.** The functions at `0x8C2330xx` write 0x938/0x93C/0x940 — the same slots
   the handler will later pop as `pr`/`spc`/`ssr` — and they do it with `r15` around `0x940`, i.e.
   from a *shallower* stack than the handler's own frame (which had descended to `0x85C`). So the
   corruption is not a wild pointer: two different contexts are using the same stack addresses.
2. **The HLE hook writes there too** (`pc 0x8c001006`, the GD-ROM vector), with `r15 0x8c483938`.
   That is the runtime's own hand-off running on a stack that belongs to the interrupted frame.
3. **The handler's save is correct** (`0x8C23364A` writes SSR=0x60000040 at 0x93C, `0x8C23364C`
   writes SPC=0x8C233122 at 0x938), which confirms the save side was never wrong — the slots were
   already being used by another context before it saved them.

**Conclusion:** the guest is switching stacks somewhere in the `0x8C2330xx` path (a scheduler), and
the runtime keeps executing the HLE hook and the exception handler on the *old* stack address. The
fix is on the runtime side: it must not run handler/hook work on a stack another context is using,
or must not let a context switch leave the exception frame behind.

### Re-corrected: they **are** in lockstep, and the tracer had the bug (2026-11-09)

Tracing both engines from boot with a translate-everything build
(`--trace-insns 0x8C000000:0x8C300000`) and normalising the P0/P1 alias gives the answer:

```
instructions compared: 1,666,115
result: identical
```

**The engines execute the same guest instruction stream from boot.** The earlier "18,073 of 18,099
cycles differ" result was an artefact: those window traces began at different instructions because
the cycle filter engaged at different points, so the comparison was between different parts of the
stream. Both the "lockstep" claim and its "correction" were wrong for instrumentation reasons.

**A real tracer bug was found and fixed while establishing this:** emitted code did not trace
delay-slot instructions (`emit_delayed` emitted code but no hook), and the interpreter's inline
delay-slot execution (line 955, `mc.fetch(pc + 2)`) bypassed its hook too. A traced loop therefore
recorded two instructions per iteration where three execute, and any comparison drifted by one
entry per loop iteration. Both sides now trace delay slots.

**What remains impractical:** comparing the fault window (from 146 M cycles) requires aligning both
streams by instruction index from boot, which is ~120 M traced instructions per side (~20 GB). That
is not a viable technique. The genuine next tool is a **checkpointed state hash** — let both engines
run, and every N instructions record a hash of `(pc, r0-r15, sr, t, pc-regs)`; compare checkpoints
to find the first divergence in bounded memory. That is a small change to the tracer and settles the
question without dumping streams.

### CORRECTION (2026-11-09 evening): they are **not** in lockstep

The prior entry concluded the engines are in lockstep because they report equal cycles at frame
boundaries. That inference was wrong, and here is the measurement that shows it.

Tracing both runs over the same cycle window and comparing **at equal cycle counts**:

```
cycle 146045159: translated executes 0x8C1A8AD8, interpreted executes 0x8C180D38
cycle 146045160: translated 0x8C1A8ADA, interpreted 0x8C180D3A
first such difference: 18,073 of 18,099 compared cycles differ
```

At the same virtual time the two engines are running **different guest instructions**. The cycle
counts merely *resynchronise at device events* (the scheduler advances the clock to event
deadlines), so equal totals at frame boundaries say nothing about the instruction stream.

Two consequences:

1. The earlier "2.6 M-cycle window entered from identical state" framing is void: the runs diverge
   well before it. The original observation stands — the two modes part company at the first
   interrupt — and every cross-run comparison remains invalid.
2. The failure is not a drift, a poll-density issue, or a cycle-accounting bug. It is that the two
   engines take different code paths early, so by frame 54 they are running different code that
   happens to cost the same time.

**Why this was hard to see:** the interpreter's tracer output for the first 3 M cycles is 519 MB
(3 M interpreted instructions), while the translated run's is **empty** — with no `--trace-insns`
hooks in that build, emitted code never calls the tracer at all. Comparing streams therefore needs
either a wide tracer build or the snapshot harness that runs both engines from one captured state.

### The engines are in lockstep (2026-11-09)

Rather than assume the clocks drift, the cycle counts were compared frame by frame:

| frames | translated cycles | interpreted cycles | delta |
|---|---|---|---|
| 5 | 10,931,460 | 10,931,468 | −8 |
| 10 | 19,282,592 | 19,282,588 | +4 |
| 20 | 35,997,552 | 35,997,552 | **0** |
| 30 | 66,033,875 | 66,033,923 | −48 |
| 40 | 99,400,156 | 99,400,147 | +9 |
| 50 | 132,766,397 | 132,766,397 | **0** |
| 54 | 146,100,238 | 146,100,236 | +2 |

The deltas oscillate and reconverge; there is no accumulating drift. At frame 54 both runs report
69 interrupts and the same PC (`0x0C17B6D0` / `0x8C17B6D0` — the same physical address). **The two
engines are effectively in lockstep up to the fault.**

So neither poll placement nor cycle accounting explains the difference. And note where the fault
actually happens: at `148,710,312` cycles — about **2.6 million cycles after** the frame-54 report.
The divergence therefore lies in the window *after* frame 54, in code both engines reach from
identical state.

That is the narrowest the fault has ever been: a 2.6-million-cycle window entered from identical
state, where one engine corrupts the exception frame and the other does not.

**Next:** with the within-run differential (`DREAM_REPLAY_TRACE`), compare the functions executed in
that window — starting with whichever translated functions run between `146.1M` and `148.7M`
cycles. The interpreter's own run of the same window is the reference, and unlike earlier attempts
the two runs are in the same state when the window opens.

### Poll-density hypothesis tested and refuted (2026-11-09)

The engine's ADR 7 says check density is title-dependent and may need tuning, so two variants were
built and run on the translated path:

| build | emitted polls | result |
|---|---|---|
| `--no-irq` | none | the run **hangs** (no VBlank reaches the guest) |
| `--irq-dense` (new `--irq-dense` flag: a poll before every instruction) | every instruction | **same fault**: `0x60000040`, 54 frames, 148,710,312 cycles, 119 interrupts, 1 switch |
| default | entries and back-edges | same fault, identical counters |

The dense build reproduces the default build **digit for digit** — same cycles, same interrupt
count, same switch. So poll placement is not what decides when this interrupt lands; the delivery
point is fixed by the virtual clock, not by where we chose to look at it.

**What that leaves:** the two engines must be disagreeing about *time*, not about polling. Emitted
code advances `Ctx::cycles` by per-block **estimates** (`runtime-interrupts.md`: "advances
`Ctx::cycles` by its per-block estimates"), while the interpreter advances by 1 per instruction and
per cycle counts it decodes. If the estimates drift from the interpreter's accounting, the guest
reaches the same interrupt at a different virtual time, with different state — which is exactly the
shape of every difference observed so far.

**Next:** compare `Ctx::cycles` between the two engines at the same guest point (e.g. the first
VBlank) and see whether the estimates drift. If they do, the fix is in the per-block cycle model,
and `--irq-dense`/`--no-irq` are both red herrings.

## Validation against the engine's own tests (2026-11-06)

All five local changes are carried by a build with `-DDREAM_BUILD_TESTS=ON`
(`engine/build-test`) and the suite passes:

```
100% tests passed, 0 tests failed out of 6
  runtime.unit        75/75 cases
  translator.unit     15/15 cases
  emit/translator/version/programs  passed
  dcdisc.pytest       skipped (pytest not configured in that build)
```

**Sandbox caveat:** the file-writing tests need a writable `%TEMP%`. Under this environment
`C:\Users\<user>\AppData\Local\Temp` is denied, which makes the memcard, CDI and symbols
tests fail or crash with `0xC0000409`. Pointing `TMP`/`TEMP` at a workspace directory makes
every case pass — the failures were environmental, not code.

## How to update the engine

1. Re-download the pinned commit into a scratch directory.
2. Diff against `engine/` and re-apply the entries above.
3. Record any new local changes here before building.
4. Re-run the M1/M2 acceptance checks.
