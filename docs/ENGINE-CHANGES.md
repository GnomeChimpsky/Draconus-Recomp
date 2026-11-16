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

## FOUND: the difference is *when* an interrupt is delivered (2026-11-09)

Checkpoint hashing over `(pc, r15, t, sr)` — added as `DREAM_TRACE_HASH=file:interval`, with
instruction-index filtering (`DREAM_TRACE_IDX_FROM/TO`) so both engines can be compared by stream
position rather than by wall-clock cycle — found the first behavioural divergence:

| checkpoint | result |
|---|---|
| 4,300,000 | differs, but only in `r0` (`0x0C232D40` vs `0x8C232D40`) — the `mova` P0/P1 alias, **benign** (confirmed: re-translating with `link_address = 0x8C010000` gives identical behaviour) |
| **38,500,000** | first divergence in `(pc, r15, t, sr)` |

Narrowed to the exact instruction (stream index 38,437,570):

```
translated   pc 0c000600  sr 70000000   <- entered the exception handler (VBR+0x600)
interpreted  pc 0c22b502  sr 40000000   <- still executing normal code
```

**The engines deliver the same interrupt at different guest instructions.** Everything observed
over this investigation follows from that: the translated run's handler runs at a point where the
guest's stack holds a partially-built context, the nested delivery overwrites the saved
`pr`/`spc`/`ssr`, the `rte` restores `SPC = 0x60000040`, and the run faults. The interpreter simply
takes the same interrupt at a different instruction and never enters that window.

**Cause:** the emitted code advances `cycles` by per-block **estimates** while the interpreter
counts exactly; the two clocks differ by a few cycles around the deadline (measured earlier as
±tens, oscillating), so a delivery that falls between those values lands on different instructions.

**Implication:** this is not a stack bug, a task-switch bug, or a polling bug — it is a **cycle
accounting difference at interrupt-delivery boundaries**. Fixing it means making the two engines
agree on `cycles` exactly (emitter estimates derived from the same table the interpreter uses), or
making delivery independent of the small difference (deliver on a guest *instruction* basis).

**Tools added:** `DREAM_TRACE_HASH=path:interval` (FNV-1a over pc/r15/t/sr per checkpoint),
`DREAM_TRACE_IDX_FROM/TO` (compare by instruction index), and the delay-slot trace fix that made
any of this comparable.

### Cycle-phase alignment tried (2026-11-09)

The first block already disagreed on cycles (translated 16, interpreted 15 at instruction 15),
because the emitter flushed the delay slot's cycle **before** executing the slot while the
interpreter counts it when it executes. The emitter was changed to count the branch before the
slot and the slot after it, matching the interpreter's phase (verified in the generated code:
`c.cycles += 15` before the slot, `c.cycles += 1` after).

**Result: no behavioural change.** The translated path still faults at `0x60000040`, 54 frames,
148,710,312 cycles — the identical total. So the phase was not what moves the interrupt.

Also re-verified: the earlier poll-density test was valid (the dense build really does carry polls
before 91 % of instructions: 276,129 polls for 302,381 instructions), so poll placement is genuinely
not the cause.

**Where the delivery difference must therefore live:** not in the per-instruction cost table, not in
poll placement, and not in the phase. That leaves the *scheduling* of the next event
(`next_event`) and the exact poll at a callee entry — emitted code polls at function entry, and the
interpreter's equivalent poll sits at a different point in its own loop. Comparing `next_event` and
`cycles` at the divergent instruction (0x0C176FE8 → handler vs 0x0C176FEA) is the next measurement.

## The first interrupt is where the engines part (2026-11-09)

Logging every delivery (`DREAM_TRACE_IRQ`, added: `pc cycles now intevt sr` in
`System::deliver_pending`) at 54 frames gives both engines **69 deliveries at the same PCs** — and
the first one is already different:

```
#0  translated  pc 0c22b502  cycles 39,374,652
    interpreted pc 0c22a960  cycles 39,375,004     (+352 cycles, a different instruction)
```

That is the origin of everything downstream. The instruction streams are identical until this point;
the translated clock then reaches the VBlank deadline 352 cycles earlier, so the interrupt lands on a
different instruction, the handler runs at a different stack depth, and (much later) the guest's saved
context is overwritten.

**Why 352 cycles:** a small per-block cost difference accumulating over ~20 M instructions — one
cycle every ~110 k instructions. Tiny, but decisive at a delivery boundary.

**The concrete next step (option 1 made measurable):** rebuild the trace-everything build with the
delay-slot phase fix and compare `cycles` at every **flush point** over the first ~1 M instructions;
the first flush that disagrees names the instruction whose cost differs. Earlier the first block
already showed +1 (translated 16 vs interpreted 15), which the phase fix was meant to remove — that
measurement now has to be repeated on the fixed emitter.

### Cycle accounting agrees at flushes; the poll reads a stale clock (2026-11-09)

With the delay-slot phase fixed, two measurements:

1. **Flush points agree exactly** over the first **1,000,001 instructions** — no mismatch at all.
2. Checkpoint `cycles` (now recorded in `DREAM_TRACE_HASH` output) first differ at instruction
   2,600,000 by **−1**, but that checkpoint sits *mid-block*, where the translated clock has not
   been flushed yet while the interpreter has already counted each instruction.

So the cost table is right and the phase is right. What differs is **when the poll reads the
clock**: emitted code advances `cycles` in bursts (flushed at block ends), and a poll at a function
entry or back-edge can read a clock that is still short of the instructions already executed in the
current block. The interpreter, counting per instruction, always polls with an exact clock. Over
~20 M instructions those unflushed tail cycles accumulate to the 352-cycle difference measured at
the first interrupt.

**Next measurement, precise:** log `cycles` at **every poll** (not only deliveries) in both engines
and compare at the same instruction. The first poll where the two clocks differ by more than the
block's pending cost confirms the mechanism; the fix is then to flush pending cycles immediately
before every poll (and before every call, since a callee entry is a poll).

**Tooling note:** `DREAM_TRACE_HASH` now prints `cycles` with each checkpoint, and
`DREAM_TRACE_IRQ` logs every delivery with `pc cycles now intevt sr`.

### Flush-before-call tried (2026-11-09): correct, but not the cause

Because a callee's entry is a poll, the emitter now flushes pending cycles immediately before every
call (tail calls and `jsr`/`bsr`, direct and indirect): seven sites, verified in the generated code.
The change is right on its own terms — a callee can no longer start with the caller's cost missing
from the clock.

**Result: no behavioural change.** The translated path still faults at `0x60000040`, 54 frames,
148,710,312 cycles. So the 352-cycle delivery offset does not come from unflushed call cost either.

### Where the cycle work stands

Three changes have been made to the emitter's clock, all correct and all kept:

1. the delay-slot cycle is counted after the slot (phase),
2. flush-before-call at every call site,
3. nothing regressed: flush points agree exactly over the first 1,000,001 instructions.

None of them changes the fault, and the 352-cycle offset at the **first** interrupt (39,374,652 vs
39,375,004) is still unexplained. The remaining measurement is to log `cycles` at **every poll**
rather than only at deliveries: the first poll where the two clocks differ by less than a block's
pending cost identifies the instruction whose cost is still being counted at the wrong moment.

## BREAKTHROUGH: stale-clock polls confirmed, and fixed (2026-11-09)

The first differing deadline crossing was:

```
deadline 5,120,015
  translated crosses at pc 0c23ebe0, cycles 5,120,035   (20 late)
  interpreted crosses at pc 0c17bb18, cycles 5,120,019   (4 late)
```

Both PCs are in translated functions, but `0x0C17BB18` is an **interior** instruction: the
interpreter polls there, and emitted code does not (it polls at entries and back-edges only). And
even the dense-poll build faulted — because a poll only *reads* `c.cycles`, which is advanced in
bursts at flushes, so a dense poll still sees a **stale clock** (short by the block's pending cost)
and crosses the deadline late.

**Fix:** make the dense poll pending-aware — the emitted check adds the cost already emitted since
the last flush, and consumes it when it fires:

```cpp
if (c.cycles + <pending> >= c.next_event) { c.cycles += <pending>; c.pc = ...; deliver_irq(...); }
```

**Effect (measured, deterministic across runs):**

| build | result |
|---|---|
| before | fault `0x60000040`, **54 frames**, 148,710,312 cycles |
| pending-aware dense polls | fault `0x60000140`, **59 frames**, 177,955,635 cycles |

Five more frames and a different fault address — the first time any change has moved this fault.
The interpreter path is unaffected (120 frames, identical counters).

**Next:** the new stop is a different address (`0x60000140`), so at least one more delivery-ordering
difference remains, but the mechanism is now proven: **a poll must be able to see the cycles it has
not yet flushed**. The follow-up is to apply the same pending-aware check to the entry and back-edge
polls (harmless where pending is zero) and re-measure.

### The new stop is the same corruption, later (2026-11-09)

The precise-poll build stops five frames later, but the shape is identical:

```
exc:    vec 0x600 pc 0x8c233122 r15 0x8c48273c nesting 2
switch: spc 0x60000140 sp 0x8c482740 frame_pc 0x8c22aa68 frame_sp 0x8c482838
```

`0x60000140` is an SR value (MD|RB|0x140) sitting in the SPC slot — the same "saved context
overwritten by a nested delivery" corruption, at a later point and a different stack address. So the
precise clock fixed the *first* delivery ordering difference and exposed the next one; it did not
remove the class.

**Speed of the precise build:** 0.5x real time at 59 frames (host 1.82 s for 0.89 s guest) — about
twice the interpreter's 0.22x, but far from playable, because a pool of `deliver_irq` checks per
instruction is expensive.

**Next:** re-run the polling comparison against the interpreter now that polls are precise; the next
crossing that differs is the next delivery-ordering bug. The instrument is already in place
(`DREAM_TRACE_POLL`, `DREAM_TRACE_SWITCH`).

### The poll offset is not a constant (2026-11-09)

Two variants of the pending-aware poll, same build otherwise:

| variant | result |
|---|---|
| `c.cycles + pending` | fault `0x60000140`, **59 frames** (kept) |
| `c.cycles + pending + 1` (counting the polled instruction too) | fault `0x60000040`, **47 frames** (reverted) |

Adding the current instruction's cost made it *worse*, so the offset is not a constant that can be
tuned: the interpreter adds the instruction's cycle in its fetch loop before the poll runs, but the
emitter's `pending_cycles_` at the poll site does not correspond to the same moment in every case
(polls are emitted at several different points: function entry, back-edge after the slot, and the
dense per-instruction site).

**The right next step is derivation, not another knob:** tabulate, for each poll site, exactly which
instructions' costs `pending_cycles_` contains at that point, compare that with the interpreter's
`cycles` at the same instruction, and make the emitted check match per site. That is a code-reading
task in `emit.cpp` (`emit_instruction`, `emit_delayed`, `irq_check_if_backedge`) against
`interpreter.cpp` (the fetch loop's `c.cycles += 1` and the delayed-branch path's extra `+1`).

**Best state so far:** precise polls without the extra cycle — **59 frames** at 0.5x real time,
fault `0x60000140` (same corruption class as before, later).

### Derivation of poll sites (2026-11-09)

Comparing the two engines' poll sites line by line:

| site | interpreter | emitted code |
|---|---|---|
| function entry | `interpreter.cpp:878` | yes |
| taken backward branch | `:944` (BT/BF), `:1056` (delayed jump) | yes (`irq_check_if_backedge`) |
| after a native call returns | `:924`, `:1045`, `:1051`, `:1076` | **was missing** |
| function return | `:1090+` | via the caller's site |

The one genuine omission was the post-call poll, now added after `jsr`/`bsr` (direct and indirect),
using the return address as the resume point. **It did not change the fault** (still 54 frames in the
standard build), because in this run the calls that matter are tail jumps, which have no
return-to-caller poll.

So the site table is now aligned as far as the code allows, and the remaining difference is not a
missing site: it is the **clock value** at a shared site, i.e. the dense pending-aware comparison
from the previous entry (59 frames) remains the best result.

**Best state: 59 frames** (precise pending-aware polls), 0.5x, fault `0x60000140`.
**Standard build: 54 frames**, now with the post-call poll (harmless, architecturally correct).

## BREAKTHROUGH: the translated path RUNS (2026-11-09)

Reading `System::enter_exception` revealed the clue:

```cpp
#ifdef DREAM_DEV_INTERPRETER
    if (interpret_all) {
        devinterp::run(c, m, 0, iopt, nullptr);   // handler always interpreted
    } else
#endif
        sh4::call_indirect(c, m, handler);        // handler enters translated code
```

In `--interpret` mode every exception handler runs through the interpreter. In the translated build the
same call goes through `call_indirect`, which finds the **translated relocation unit at `0x8C000600`**
(the game copies its exception stub there at boot) and executes emitted code before handing to the
interpreted body at `0x8C233648`. The handler therefore runs *differently in the two modes* — on the
exact path where the context is corrupted.

Forcing handlers through the interpreter in both modes (`DREAM_HANDLER_INTERP=1`) fixes it outright:

```
translated path, handlers interpreted:
  stop: frame limit
  guest: 9.838 s (1,967,764,531 cycles), 600 frames, pc 0x0c0112e4
  (identical on a repeat run — deterministic)
```

**600 frames, no fault.** Before this, the translated path died at 54 frames.

### What this establishes

1. **The compiled code is not the problem**, and neither is the cycle model or poll placement: with
   the same emitter and the same clocks, the run is clean as long as the handler is interpreted.
2. **The defect is in the translation of the relocated exception-handler unit** — 0x38 bytes at
   `0x8C000600`, translated as a separate image view. That unit, or its hand-off to `0x8C233648`,
   corrupts the handler's saved context.
3. **Cost:** handlers run every VBlank, so interpreting them makes the run *slower* than the
   interpreter path — 0.14x real time (69.5 s host for 9.8 s guest) vs 0.22x. Correct, but not the
   shipping configuration.

### Next

Diff that 0x38-byte unit's translated behaviour against the interpreter, instruction by instruction:
it is tiny (about twenty instructions), it is the only code whose execution differs between the two
modes on this path, and the machinery to compare it (`DREAM_TRACE_INSNS` with a narrow range,
`DREAM_TRACE_CALL_AT`) already exists.

### The handler unit's code is faithful; its *entry* is what differs (2026-11-09)

The generated relocation unit was read line by line against the disassembly — nops, `mov.l r1,@-r15`,
`mova`, the self-modified literal store, `shll16/shl11`-style INTEVT computation, the
`mov.l 0xc00062c,r0` **memory re-read** (not folded), and `jmp @r1`. All faithful.

What differs between the modes is how the handler is *entered*:

| mode | entry path |
|---|---|
| `--interpret` | `devinterp::run(c, m, /*return_to=*/0, iopt, nullptr)` — one run from `VBR+0x600` to the `rte` |
| translated | `sh4::call_indirect(c, m, 0x8C000600)` → the translated unit → `call_indirect(0x8C233648)` → **`on_untranslated` → a nested `devinterp::run` with `return_to = c.pr`** |

So in the translated build the handler body runs inside a nested interpreter run whose stop address is
the *interrupted task's* PR, while in `--interpret` it runs with `return_to = 0` (stop only at the
`rte`). If the handler's body ever reaches that PR, the nested run returns early, mid-handler — leaving
the handler's saved context on the stack and the delivery frame half-unwound. That matches the
observed corruption exactly: `pr`/`spc`/`ssr` popping one slot out of step.

**This is the next thing to verify:** log `c.pr` and the `return_to` at the handler entry in both
modes, and check whether the nested run in the translated build returns early (`Stop::Returned`)
rather than at the `rte`.

### The handler reaches its RTE; the difference is the unit's own execution (2026-11-09)

Two hypotheses tested with new diagnostics (`DREAM_TRACE_HANDLER`, `DREAM_HANDLER_NO_NATIVE`):

1. **"The nested run returns early at PR."** Measured false:
   `untranslated: target 0x8c233648 ended Rte` — the handler body runs to its `rte` correctly in the
   translated build too.
2. **"The handler calls translated functions natively, unlike `--interpret`."** Disabling
   `call_translated` inside handlers (`nesting > 0`) changes nothing: still `0x60000040`, 54 frames.

So the only execution difference left on this path is **the translated unit's own 0x38 bytes**
(`0x8C000600`–`0x8C000628`), which `--interpret` runs through `devinterp` and the translated build
runs as emitted code. Its instructions were read and are faithful; what remains is how it is
*counted and entered*:

* its emitted body totals **19 cycles** (`c.cycles += 19` before the `jmp`, plus `+1` for the delay
  slot = 20) against the interpreter's 20 one-cycle instructions — a candidate off-by-one at a
  delivery boundary, which is exactly the class that moved the fault before;
* the wrapper's entry does `if (c.cycles >= c.next_event) { c.pc = ...; deliver_irq(...); }` — a poll
  *inside* exception entry, which the `devinterp` path reaches at a slightly different point.

**Best state remains:** handlers interpreted → 600 frames, deterministic, 0.14x.
**Standard translated:** 54 frames, fault `0x60000040`.

### Handler path: what is proven, and what is next (2026-11-09)

Proven by measurement:

* forcing exception handlers through the interpreter makes the translated path run **600 frames,
  deterministic, no fault** (`DREAM_HANDLER_INTERP`);
* the handler body reaches its `rte` correctly in the translated build too (`ended Rte`), so it is
  not an early return;
* disabling `call_translated` inside handlers changes nothing;
* the relocated unit's instructions are faithful (self-modified literal re-read from memory,
  INTEVT read, `jmp @r1`).

So the only remaining execution difference is **the unit's own emitted body** versus `devinterp`
executing the same twenty instructions. Comparing their cycle accounting requires a *filtered*
extraction per invocation (the previous attempt dumped every invocation and was unusable); the next
session should extract only the first invocation's twenty (pc, cycles) pairs from each trace and
diff those.

**State:** translated path 54 frames standard, 59 frames with precise polls, **600 frames with
handlers interpreted** (0.14x, slower than the interpreter's 0.22x because handlers run every
VBlank).

## ROOT CAUSE FOUND AND FIXED: handler entry stopped at the interrupted code's PR (2026-11-10)

The fault is fixed, and it was not the stub's instruction encoding, its cycle accounting, or the
poll placement. The translated path now runs **600 frames deterministically, and its guest state
matches the interpreter**: 34,022 TA chunks, 508 list inits, 503 renders, 504 frame swaps and the
same Maple counters, with 1,967,764,531 cycles against the interpreter's 1,967,764,490 — a 41-cycle
difference over 9.8 guest seconds, and no task switch in either run.

### The defect

`System::on_untranslated` — the bridge emitted code calls for a target with no translation — ran the
interpreted code until it returned to `c.pr`. That is right for an ordinary call and wrong for an
exception-handler entry: a handler does not return through PR, and when the VBR+0x600 stub hands the
body to the interpreter, PR still belongs to the *interrupted* code.

It only bit on a **nested delivery**. When an interrupt lands inside another handler's ISR, the outer
handler is inside a `jsr @r14`, so PR is that ISR's return address — and the nested handler's own
`jsr @r14` sets PR to the same value. The interpreted run then stopped at the ISR's `rts`, abandoning
the handler before its epilogue with its saved context still on the guest stack. When the outer
handler's epilogue finally ran it was four bytes out of step: `ldc.l @r15+,spc` loaded the SSR slot
(`0x60000040`), `ldc.l @r15+,ssr` loaded the PR slot, and the `rte` was classified as a task switch
to `0x60000040`.

Evidence, `DREAM_TRACE_INSNS` over `0x0C233648..0x0C233790` in both engines:

* the handler body executed 119 times in the translated run; exactly one invocation left `r15` four
  bytes higher at its `jsr` return (`0x8C48385C` -> `0x8C483860`) than it entered it. All 450
  interpreted invocations were balanced;
* `DREAM_TRACE_HANDLER` named that invocation:
  `untranslated: target 0x8c233648 return_to(pr) 0x8c2336fa ... ended Returned(early) pc 0x8c1a632e r15 0x8c48385c`.
  `0x8C2336FA` is the return address of the outer handler's `jsr @r14`, which is also where the
  nested handler's own call returns;
* every other handler entry ended `Rte` — which is why the earlier "does the nested run return
  early?" check came out negative. The failure is specific to a nested delivery whose PR collides
  with the handler's own call return address.

### The fix (patch 007)

`enter_exception` marks the handler entry (`System::handler_entry_`); `on_untranslated` consumes the
mark and uses stop address 0 — stop only at the handler's RTE — instead of `c.pr`. This is exactly
the stop address the `--interpret` path has always passed in `enter_exception`
(`devinterp::run(c, m, 0, iopt, nullptr)`), which is why `--interpret` and `DREAM_HANDLER_INTERP`
were immune all along.

### Regression test

`runtime/tests/test_system.cpp`, "system: a nested handler's interpreted run ends at its RTE, not at
a stale PR": a handler at an unregistered vector pushes a register, calls an ISR whose return
address equals the stale PR, marks completion, acknowledges the source and RTEs. With the fix all
six assertions pass; reverting the one line fails four of them (marker not written, `r15` four low,
interrupted PC not restored, source not acknowledged). Both directions were run.

### What it means for the rest of the work

* **The task-switch theory is closed.** The transcript's `task-switching RTEs: 1` was this
  corruption being classified as a switch; with the handler finishing, it is 0, and
  `System::on_rte`'s switch detection was never wrong.
* **The poll work was not the cause.** Precise pending-aware polls, the post-call poll and the
  delay-slot phase alignment are still correct and are kept, but they moved the fault only because
  they moved the delivery that found the broken handler.
* **Speed did not improve.** 600 frames take 68 s translated against 38 s interpreted: with most of
  the title still untranslated, the translated build pays a `devinterp::run` for every call it cannot
  make natively. The speed lever remains translation coverage (M2 discovery/emission), not the
  runtime.

### Engine changes carried

001 present-mode guard, 002 diagnostics, 003 hook dispatch at the interpreter fetch boundary, 004
instruction tracer, 005 replay host-state skip, 006 SR-write rule, **007 handler-entry stop address**,
**008 flash host-state marking**, **009 inlined RAM fast path**, **010 cached readback memory**, **011 `/bigobj` for large generated units**, **012 `DREAM_REPLAY_MAX_INSNS`** (plus
the `DREAM_TRACE_UNTRANSLATED` and `DREAM_TRACE_FRAME_TIME` diagnostics), delay-slot tracing,
cycle-phase alignment, flush-before-call, the post-call poll and the pending-aware poll. 007 fixes
the fault; 009, 010 and the config seeds are the speed work.

## HLE host-state marking completed for flash (2026-11-10)

The replay harness cannot undo host state a syscall changes outside guest memory. GD-ROM was already
marked (patch 005). Flash was the remaining gap: `FLASHROM_WRITE` and `FLASHROM_DELETE` program and
erase the flash bytes through `Flash`, which writes the buffer directly instead of going through
`DcMemory::store`, so the journal never sees those stores and a replay would program the device twice
(flash writes only clear bits, so the second run observes a different device).

Both cases now call `hle::note_side_effect()`. Measured effect on this title: none yet — the run makes
no flash writes in 120 frames, and `--replay` stays at 0 disagreements with the same counters
(2,448,650 compared, 150,897 skipped, 71 host-state). Timers and Maple need no marking: both are MMIO
devices, and any comparison that touches a device register is already abandoned
(`journal_saw_device`), so the old handover's "timers, RNG and Maple still change host state" was
narrower than it read.

## The 99% boundary: an empty function called 98,000 times a frame (2026-11-11)

The translated path was 0.15x, slower than the interpreter's 0.26x. A 300-frame run reported
**29,705,083 untranslated call targets**, and a new diagnostic (`DREAM_TRACE_UNTRANSLATED`) showed
where they went:

```
untranslated top targets (159 distinct):
  0x8c240710  29454325 calls
  0x8c22ba92  200458 calls
  0x8c233648  13701 calls
  ...
```

`0x0C240710` is two instructions, `rts` / `nop` — an empty function. The game calls it about
**98,000 times per frame** (5.9 million per guest second, the same rate the engine's Crazy Taxi
study measured for indirect calls generally), and every call crossed from emitted code into
`devinterp::run` and back. That one function was 99.2 per cent of the boundary traffic.

Seeding it in the config (`[functions] extra`) removed essentially all of it:

| build | 600 frames, host | speed | untranslated calls |
|---|---|---|---|
| translated, before | 66.76 s | 0.15x | 29.7 M per 300 frames |
| + seed `0x0C240710` | 7.12 s | **1.3x** | 308 k per 600 frames |
| + 13 more hot seeds | 6.48 s | **1.5x** | — |

The remaining hot entries after that were *resume* addresses inside already-translated functions
(handled by `resume_at`, not full interpreter runs), plus the handler body at `0x8C233648`.

**Do not seed `0x8C233648`.** It is the body of the relocated exception handler. Translated, its
`rte` no longer unwinds through `enter_exception`'s interpreter run, and the run faults at pc 0 at
frame 22. It stays interpreted (the 20-instruction stub at `0x8C000600` remains translated).

The seed list is in `game/draconus/draconus.toml` with the reasoning; it is the output of
`--suggest-config` plus the diagnostic above.

## Patch 009: the RAM fast path, inlined (2026-11-11)

The engine's own study (`engine/docs/cpu-performance-study.md`) measured the out-of-line memory
resolve at 56 per cent of a fully translated profile. `DcMemory::read*/write*` were virtual calls
into a non-inlined `resolve()` that re-derived the address region on every access.

The eight accessors are now inline in `dc_memory.h`: an area-3 test, a mask and a memcpy for main
RAM, with the existing out-of-line bodies kept as `*_slow` for everything else (devices, store
queues, CCN registers, the replay journal, the write hash, the watch). The fast path is skipped
whenever `journaling` or `tracing_writes()` is armed, so the differential harness and `--write-hash`
see every store they did before.

Measured, same config and seed:

| frames | before | after | speed |
|---|---|---|---|
| 600 | 6.48 s | 5.09 s | 1.5x → **1.9x** |
| 1,800 | 28.72 s | 23.39 s | 1.04x → **1.2x** |

Counters unchanged at both lengths (34,022 TA chunks / 504 swaps at 600; 704,111 / 1,680 at 1,800),
engine tests 6/6, `--replay` still clean except one *alias* disagreement: `fn_0c011e64` returns
`r0 = 0x0C01214C` translated against `0x8C01214C` interpreted — the known P0/P1 segment alias, not
a behavioural difference (mask it with `--mask-segment` when comparing writes).

## Patch 010: the readback buffer was in write-combined memory (2026-11-11)

Headless the build ran at 1.2x at 1,800 frames; with a window it managed 0.8x, and the gap grew with
resolution. A new `DREAM_TRACE_FRAME_TIME` diagnostic split a windowed frame:

```
window: 0.34 ms per draw, 6.71 ms per present (1679 / 1712)
window: present split: begin 0.01, upload 6.62, draw 0.00, end 0.06 ms
```

The draw was 0.34 ms; the *present* was 6.71 ms and almost all of it was `Presenter::upload` — a
`memcpy` of the frame out of `Offscreen::readback_`. That buffer is host-visible, and
`HostBuffer::ensure` asked only for `HOST_VISIBLE | HOST_COHERENT`, which on this GPU resolves to
the device-local host-visible heap (the BAR). Reading it from the CPU is write-combined: 1.2 MB at
roughly 180 MB/s, 6.6 ms.

`HostBuffer::ensure` now takes `cpu_reads`, which asks for `HOST_CACHED` first and falls back to the
old type. The offscreen readback passes it; the presenter's staging buffer does not (the CPU only
writes that one, where write-combining is an advantage).

| measurement | before | after |
|---|---|---|
| present, 640x480 | 6.71 ms | **0.16 ms** |
| windowed 1,800 frames | 36.28 s (0.8x) | **29.85 s (1.0x)** |
| windowed 600 frames at scale 4 | 43.75 s | **9.83 s (1.0x)** |
| headless 600 frames | 5.09 s | 5.35 s (1.8x) |

Counters unchanged, `tools\parity-check.ps1` still reports a byte-identical screenshot, and the
headless figure is within noise of the previous build (the cached readback is marginally slower to
write from the GPU, which is why it is only used where the CPU reads).

## Config: pointer-table discovery was off, and it was the real coverage fix (2026-11-11)

The seed work above made the title screen and menus fast, but the title's code was still mostly
missing. The config had `pointers = false`: discovery followed calls from the entry point only, which
found 3,285 functions. This title reaches most of its code through data tables — function-pointer
tables, jump tables, dispatch structures — so with the seeds in place a 5,000-frame menu scene still
crossed into the interpreter **3.3 million times** and ran at 0.6x.

Setting `pointers = true` finds **8,940 functions** (995,051 instructions, 62 switch tables, about
100 MB of generated C++). The same 5,000-frame scene drops to **1,412 untranslated calls** and runs
at **1.0x**; 1,800 frames headless go from 1.2x to **3.7x** and 600 frames to **3.9x**. Guest
counters are unchanged (34,022 TA chunks / 504 swaps at 600; 704,111 / 1,680 at 1,800) and
`tools\parity-check.ps1` still reports a byte-identical screenshot.

The hand-added seeds become unnecessary once the table pass runs, so they were removed: the empty
function at `0x0C240710` and the menu cluster are all found. The build takes about five minutes.

**This corrects the M2 reading** (`docs/11-M2-RESULTS.md`): emitting the full set does complete — it
was the aggressive `sweep` pass that never terminated, and `sweep` is still off.

## Windowed cost: what remains

Nothing measurable, at native resolution: the window is at 1.0x for 1,800 frames and at 1.0x even at
4x resolution. The frame is still copied GPU → CPU → GPU to present (the study's "direct present"
change would remove that), but at 0.16 ms per present it no longer decides the frame rate. What
remains for heavier scenes is emulation time (translation coverage), not the renderer.

## The pointer-pass gameplay crash and the two-function workaround (2026-11-11/12)

With `pointers = true` the translated build faulted at pc 0 about 79 s into the menu scene
(`--press start@1000,a@4000`, frame 4,750, 79.07 s guest). The interpreter and the pre-pointer build
ran the same input to frame 5,000 cleanly, so it was translated code. The crash trace ended with an
`rte` to `0x0C16CDF4`, an emitted `rts` whose target was its own entry, then a jump to 0.

Ruling out candidates by exclusion did not move the fault (the first suspect, `0x0C22B508`, changed
nothing, and excluding interior pointer entries broke boot). One exclusion did: interpreting
**`0x0C16CDF4`**, a 4,914-byte FP function, removes the crash — 20,000 frames of gameplay run clean.

A second, much faster crash was found while wiring up a pad: a burst of d-pad presses on the main
menu (`--press "down@150,down@170,...,down@270"`) faults at frame 192 through a null vtable slot, and
interpreting **`0x0C0C7F7C`** removes it. The title config carries both exclusions; 500 frames of
menu navigation and 20,000 frames of gameplay are clean with them, and parity is unchanged.

Both crashes, and a third that is still open (a menu-heavy sequence faults at frame 18,690), end in
the same line:

```
nonlocal: rts from pc 0x0c0e4908 to 0x0c0e4908 (r15 0x8c483ae0 pr 0x0c0e4960)
```

That is not an `rts` despite the message: the emitted `rte` path calls
`nonlocal_return(c, m, c.pc)` when `rte()` reports no exception frame, so the guest's own task return
unwinds the C++ stack and resumes at SPC. When SPC is a function entry, `resume_at` takes the
`e->fn()` door (`resume_pc = 0`); the guest then jumps to 0. The common factor is that resume path,
not the functions, which is why excluding them moves the crash rather than explaining it.


The rte that triggers such a fault restores an **inconsistent context**: `spc 0x0C0C7F7C` (a function
entry) with `pr 0x0C0C7FBE` (a return address inside that same function). Resuming at the entry
re-runs the prologue with that stale PR, the function returns into its own middle, the epilogue pops
the wrong frame, and the next indirect call goes to 0. `DREAM_TRACE_RTE=path` logs the state at every
`rte` from both engines; the engines' rte paths differ early (interrupt timing), but the crashing
context itself is the evidence. Candidate producer: `c.pc` is only refreshed at poll points, so a
handler that saves "the interrupted PC" can read a function entry while the PR it saves is live from
inside the function. The next measurement is the save side, not the resume side.

Whether the function's *translation* is wrong or the exclusion merely shifts interrupt timing is not
settled. It is called only late in gameplay, and the differential replay at 8,940 functions is too
slow without a checkpoint. `--replay-only 0x0C16CDF4` over the crash run has now been tried and
cannot help: the call is made once and the harness skips it as "too long" — the 2,000,000-instruction
cap is exceeded, so the function loops far more than its size suggests. Raising the cap to 50,000,000
(the new `DREAM_REPLAY_MAX_INSNS`) still ends in "too long": the call does not return inside the
harness at all, so the differential replay cannot compare this function by construction. The
workaround therefore stays, with its cause unproven, until a checkpointed harness or a different
comparison exists.

## Patch 012: the replay instruction cap is a knob (2026-11-11)

The differential harness gives each compared call 2,000,000 interpreted instructions and then counts
it as "too long". One function (`0x0C16CDF4`) runs past even 50,000,000 without returning, so it can
never be compared by the harness as it stands. `DREAM_REPLAY_MAX_INSNS` overrides the cap for a run,
which lets a future harness (or a checkpointed comparison) raise it without a rebuild; the default is
unchanged.

## Patch 013: pad support that covers real hardware, and a fault-time stack (2026-11-12)

* The pad the title has always been able to bind now covers everything the Dreamcast pad has: **C and
  Z** were missing, so a player could not press the two buttons a modern pad spells as shoulders.
  They default to left/right shoulder; the analogue triggers stay on L/R.
* A pad that arrives as a **raw joystick** (no SDL gamepad mapping -- generic DirectInput sticks,
  8BitDo in DInput mode, arcade boxes) used to be invisible: `SDL_GetGamepads` returned nothing and
  the game got only the keyboard. `map_unrecognised_pads()` gives such a device the standard
  DirectInput layout, so it is playable and rebindable instead of absent.
* The launcher prints the devices it found (`input: KEYBOARD, <pad>`), and `DREAM_INPUT_TRACE=1`
  prints the pad state the guest receives when it changes. `DREAM_VIRTUAL_PAD=1` attaches a synthetic
  pad with a scripted button/stick/hat sequence, so the host-to-Maple path is testable with no
  hardware attached.
* `unimplemented()` now prints a **fault-time stack** of module-relative addresses under
  `DREAM_FAULT_TRACE=1`. Built with `/MAP`, those addresses resolve to the emitted `fn_*` frames, which
  is how the menu crash's chain (`fn_0c0c7f7c <- resume_at <- ...`) was found. The map file is a link
  option, not a CMake default: configure with `-DCMAKE_EXE_LINKER_FLAGS=/MAP` when a fault needs
  resolving.
* `call_indirect` logs calls whose target is outside the title's code (a null or wild pointer) with
  the calling pc and r0-r3, under `DREAM_TRACE_HOOK=1`.

## Patch 014: entry polls are optional, and they were the crash (2026-11-13)

`[functions] entry_polls = false` leaves the interrupt poll at each function entry out of the emitted
code; interrupts then arrive at loop back-edges and call returns. `EmitOptions::entry_polls` carries
the title's setting, parsed from `functions.entry_polls`.

The crash: an entry poll can deliver an interrupt at a function entry reached by a tail jump, where PR
still holds the jumper's return address. The handler saved that pair (`spc` = entry, `pr` = an address
inside the same function's epilogue); on `rte` the function was re-entered at its entry, and its
epilogue returned to that PR a second time, popping a frame that was not there -- then an indirect call
read zero. The interpreter never delivers at such an address, which is why it never crashed.

With entry polls off and nothing excluded, all three reproductions run clean (frames 4,750, 192 and
18,690), windowed parity is byte-identical, and the runs are faster: an entry poll is a compare per
call. Interrupt counts stay within 0.1% of the interpreter's.

## Patch 015: a texture updated in place is dropped (2026-11-13)

Textures were decoded once and kept. That is right for the eight megabytes of art a level loads and
never touches again, and wrong for the textures the console keeps rewriting: the PVR's YUV converter
(streamed backgrounds and video) and any art the guest uploads into video memory as it goes. The
symptom was a menu's old picture -- the Crave logo where the intro background should be, broken up
by whatever had been redrawn over it -- and corrupted text in the save menu.

`DcMemory::on_vram_write` reports every write that lands in video memory, as VRAM offsets; the boot
merges the ranges and calls the new `TextureCache::invalidate_ranges` once, before the next display
list is drawn. One `vkDeviceWaitIdle` per frame at most, and only when a cached texture actually
overlaps a written range.

`invalidate_ranges` reports its drops through the existing "overwritten by a render" counter, so a
run now shows the dynamic textures being refreshed (21 decoded, 11 overwritten on a title-screen
run) where it used to show none.

**Completed later the same day:** only the ordinary 32-bit store reported. A 64-bit store and a
store-queue burst -- which is how Katana's texture loader moves most of its bytes, including the
consecutive-word uploads a title does mid-level -- went straight into video memory without telling
the cache, so an upload that used them kept its old decode. `DcMemory::report_vram_write` is now
called from every path into video memory, and `runtime/tests/test_memory.cpp` covers the word,
64-bit and store-queue cases plus the main-RAM negative case.

## Patch 016: the capture replay exits after its screenshot (2026-11-13)

`dream_render_view FILE --screenshot OUT` used to open a window and keep drawing until it was closed,
which made a scripted capture replay a hang. With `--screenshot` and no `--frames` it now renders one
frame, writes the picture and exits. `tools\m3-check.ps1` uses that for the M3 capture-replay gate:
it takes an F11 bundle and replays it, alongside the 600-frame determinism check (two runs, identical
write-hash files).

## Patch 017: a projection-matrix scan for the widescreen work (2026-11-13)

`DREAM_SCAN_MATRIX=<frame>` (at the vertical blank) and `DREAM_SCAN_MATRIX_RENDER=<frame>` (at a
display-list submission) scan RAM once for 4x4 float matrices whose x/y scales are in a 4:3 (or
16:9) ratio, printing each candidate with its address and all sixteen floats. It is how the title's
projection was looked for. Neither scan point found one: the 4:3-shaped matrices that do appear are
view rotations (0.7071 = 45 degrees), and no matrix with a perspective row is present in RAM at
either instant. The projection is therefore built transiently, or is not matrix-shaped at all
(scale-per-vertex), which changes what the hor+ hook has to patch.

## Patch 018: --patch, a debug memory poke (2026-11-13)

`--patch ADDR=VALUE` writes guest memory once, after the image is loaded and before the first frame.
A value with a dot is written as a float, anything else as a 32-bit word, so an image constant found
by scanning can be replaced with the same kind of constant. It exists for the widescreen work: the
only way to tell what a constant controls is to change it and look at the frame.

Two projection candidates were ruled out this way: the 1.3333 aspect float at 0x0C0B1E90 and the
adjacent 320/240 screen pair at 0x0C0D8128/2C both leave a gameplay frame byte-identical.

## Patch 019: hor+ widescreen (2026-11-13)

The title's projection x scale is a plain float at `0x0C098640` (0.75 = 4:3), found by patching every
0.75 candidate and diffing the frame. `[widescreen]` in the title config names the address and its
4:3 value; `--aspect 16:9` (or `21:9`, or a decimal) makes the boot patch it to
`base * (4/3)/aspect`, re-apply it every vertical blank, and open a window of that aspect.
`Presenter::stretch` fills that window instead of fitting the image aspect inside it, so the
squeezed wider field of view is stretched back to correct proportions. 4:3 is unchanged when
`--aspect` is not given.

Verified at 1280x720 and 1680x720 in gameplay: more world horizontally, no distortion, and the HUD
goes through the same projection so it keeps its shape and moves outward with the frame. The cost is
one float write per frame.

## Patch 020: presentation decoupled from the 60 Hz logic (2026-11-13)

`--present-rate N` presents the display N times a second while the guest's logic keeps running at
60 Hz. Each guest frame is presented `N/60` times (2.4 for 144 Hz, carried as a fraction across
frames), with the repeats spaced across the frame so the cadence is even. It is presentation only:
the image is repeated, not interpolated, and the guest sees nothing different.

Measured on a 300-frame windowed run: guest report identical at 60, 120 and 144 (same cycles, same
pc), and presented counts 212, 424 and 508 -- exactly 1x, 2x and 2.4x. That compared guest state,
not wall time: it showed the guest saw the same frames, not that it reached them at the same speed.
Patch 023 fixes the speed when presentation cannot keep up. The parity suite runs at the default
rate and is unchanged; screenshot and capture frame numbers follow *presented* frames, so targeting
one with a raised rate means accounting for the repeats.

The launcher exposes it as `-PresentRate 120`.

## Patch 021: 4:3 menus and loading screens in widescreen (2026-11-13)

The hor+ projection widens the field of view of 3D geometry, but the title, menus and loading cards
are flat 2D art authored at 4:3. Presenting every frame stretched to the wide window distorted them.
The two kinds of frame can be told apart from the display list: a 2D screen is made of quads whose
vertices share one depth (`z = 1/w`), while a 3D scene has a depth span across its polygons. That is
also exactly the set of frames the widened projection applies to.

`frame_uses_depth(const Frame&)` (render library, unit-tested) makes the call. The boot runs it per
submitted display list, switches to "3D" on the first frame with depth, and switches back to "2D"
after two flat submissions so a single HUD-only or dropped world list cannot flash a pillarbox.
Presentation then stretches only when the aspect was asked for, the displayed buffer is the
renderer's, and the frame carried depth:

```cpp
presenter.stretch = wide_aspect > 0.0 && from_renderer && scene_3d;
```

Everything else -- title, options, save/load, the story and location cards, a movie decoded from
video memory -- is fitted at 4:3 inside the wide window and pillarboxed. An in-game pause or quit
dialog drawn over the live world is not one of those: the frame still carries the world, so it stays
in the widescreen presentation. Making that 4:3 needs a pause-state or UI-overlay signal, which is a
separate, title-specific job. Nothing is restored in the guest: a menu frame rendered with the x scale
patched at `0x0C098640` is byte-identical to the same frame at 4:3, so the projection does not touch
2D art and the 4:3 picture is the original one.
`DREAM_TRACE_SCENE=1` prints the classification per submitted frame (`2D`/`3D`, strips, sprites,
polygons) for checking a new screen.

The bars exposed an older presenter bug. The fullscreen triangle is deliberately larger than the
screen; when it is scaled down to letterbox, the part outside the image still rasterises and samples
the texture past its edge, so the bar showed smeared edge texels (the left bar was black because the
triangle starts exactly there, which is why it looked like a one-sided artifact). `present.frag` now
discards fragments whose interpolated `uv` leaves the unit square, so the bars are the render pass's
clear colour. This also fixes ordinary 4:3-in-a-wide-window letterboxing.

Verified on the retail disc at 1280x720: title and the location/menu cards present as a 960x720 image
centred with 160-pixel pure-black bars, no distortion; the in-game cutscene frame at the same guest
frame is byte-identical to the pre-change widescreen capture, so gameplay and movies are untouched;
the render suite passes 78/78 (1,350 assertions), including the new classifier test. 4:3 runs are
unchanged: the presenter is not stretched and never leaves the unit square.

## Patch 021: first-frame measurement (2026-11-13)

`DREAM_FIRST_FRAME=1` reports the first presented frame whose picture has a non-black pixel, with the
presented frame, the guest frame and the time since the window opened. It is the M3 gate's "first
non-blank frame" measurement and needs no screenshot.

Measured (2026-11-13): **our first non-blank is the Crave logo at 1.8-2.2 s** (presented 0,
guest ~88). Flycast's first non-black frame is the Sega license screen at 0.67 s, and it reaches the
same Crave logo at about 6 s because it plays the licence screen first
(`tools\flycast-first-frame.ps1`). Our picture therefore appears earlier than Flycast's for the
same content.

**Re-measured and made like-for-like (2026-11-16).** On the current build the first non-blank is
guest frame 103 (2.6-2.9 s wall here; the guest frame is the stable number and the seconds move with
the window and machine). Flycast's first non-black picture is its boot ROM's licence screen; its
first non-blank **game** picture is frame 240, the same Crave logo at a slightly earlier fade phase.
`tools\m3_first_frame.py` finds that pair automatically and measures **MAE 0.92** (RMSE 3.36, mask
overlap 0.93, bounding-box IoU 0.99) against the M5 threshold of 16; `tools\m3-check.ps1` runs it
with the determinism and capture-replay clauses. The 11-13 guest frame and time were taken before
later boot-sequence changes and should not be quoted as current.

## Patch 022: the window follows the scale, and fullscreen (2026-11-13)

`--scale` used to change only the offscreen image: the window stayed 960x720, or 1280x720 at 16:9,
so `--scale 4` drew 2560x1920 and then minified it into 960x720. The window now opens at the scale
it names (`render/window_size.h`, unit-tested):

| scale | 4:3 | 16:9 |
|---|---|---|
| 1 | 960x720 | 1280x720 |
| 2 | 1280x960 | 1280x720 |
| 3 | 1920x1440 | 1920x1080 |
| 4 | 2560x1920 | 2560x1440 |

The 720-line floor is what keeps 1x at the old default; 16:9 keeps the width the scale names and
takes the height out of it, so 3x and 4x land on 1080p and 1440p. A window that does not fit is
shrunk to 90% of the display's usable area (`fit_window`), preserving its aspect: on this
2560x1440 screen 4x 4:3 opens at 1669x1252 and 4x 16:9 at 2226x1252, the largest windows that leave
the frame and the taskbar room.

`--fullscreen` (implies `--window`) uses SDL desktop fullscreen instead, which is the only way to
get a 2560x1440 window on a 2560x1440 panel: a decorated window cannot fit around the screen.
Verified on the RTX 3080 / 2560x1440 machine: `--fullscreen --scale 4 --aspect 16:9` reports
`drawing at 2560x1920, showing 2560x1440`, with the projection patched to 0.5625 as before.

Presentation had to follow. `Presenter::stretch` was a boolean: fill the window, on the assumption
that the window's shape was the aspect the projection was patched for. A resized window, or a
fullscreen display of a different shape, broke that assumption and distorted the picture. It is now
`content_aspect`, the aspect the image was drawn for: the frame is fitted into a rectangle of that
aspect inside the window, so a mismatch gives bars instead of a stretch. A widescreen 3D frame
passes the patched aspect; flat 2D screens and 4:3 runs pass 0 and are fitted at 4:3 as before.

Verified: render suite 81/81 (1,379 assertions), including the new window-size cases; the
scale/aspect runs print the sizes above; the launcher's `--selftest` and `--smoke` pass, and the
smoke check asserts that 4x + 16:9 really produce `--scale 4 --aspect 16:9`.

## Patch 023: --present-rate is capped to the display (2026-11-13)

`--present-rate 120` on a 60 Hz display did not smooth anything: every guest frame presented two
pictures and each waited a vblank, so the guest ran at 30 Hz -- half speed. The rate is now capped
to the display's refresh (`presents_per_frame`, unit-tested, `render/present_rate.h`) and the cap
is announced: `present: 120 Hz requested, the display runs at 60 Hz; capping to it`.

The repeats are best-effort as well. A guest frame already behind its own clock presents once and
lets the pacing catch up instead of adding another repeat, so a display slower than the request, or
a frame that took too long, cannot drag the guest down: the guest stays at 60 Hz and presentation
drops the repeats it cannot afford. On a 165 Hz display at 4x fullscreen 16:9 over 6,000 frames,
the guest ran at 1.0x real time at 60, 120 and 144 present rates (120 measured 0.8x before this);
presented frames were 5,912 / 10,674 / 11,679.

Verified: render suite 85/85 (1,392 assertions), including the present-rate cap cases.

## Patch 024: frame interpolation for present rates above 60 (2026-11-14)

`--present-rate` decoupled presentation from the 60 Hz logic by repeating the current picture. That
smooths the display but cannot show motion the guest did not compute. `--frame-interpolation`
(launcher: **Interpolate extra frames**, play script: `-Interpolate`) draws the intermediate frame
from the two guest submissions instead.

The renderer already receives screen-space vertices with 1/w depth and texture coordinates, so two
consecutive frames of a scene carry the same corners twice. `render/interpolate.{h,cpp}` matches
polygons on their render state (vertex count and the PCW/ISP/TSP/TCW words, clip rectangle) in
submission order, and moves a matched polygon's corners halfway by `t`. Depth is interpolated as
1/w, which is what is linear in screen space; the depth range is recomputed for the result. The
matching is deliberately conservative: a pair is used only when its centroid is within 32 px, its
mean corner distance within 48 px and its mean w ratio within 0.7–1.4, and the first plausible of at
most two same-signature candidates is taken rather than the closest of a far group. A strip with no
plausible predecessor keeps its current corners, so a culled or streamed-away polygon can pop but
cannot smear. A frame whose matched corners move more than 48 px on average is a cut, and falls back
to the current picture rather than morphing one scene into another.

Wiring: `Live` keeps the decoded `Frame` of the previous and current renders (render-to-texture
draws are left out), builds the intermediate at the first present of each guest frame, and rasterises
it into a second offscreen target with the same renderer and geometry. The present loop spaces the
presents of one guest frame evenly and ends with the frame itself (`1/N … 1`), so for a 120 Hz
display the sequence is mid(N-1,N), N, mid(N,N+1), N+1; for 144 Hz it is two thirds, one third and
the frame. A frame that is not 3D (`frame_uses_depth`), a movie, a menu and a frame that is behind
its clock present the current picture, exactly as before.

Measured, windowed, 640x480, AMD/NVIDIA RTX 3080:

| run | interpolated | fell back | partial | render failures | speed |
|---|---|---|---|---|---|
| 5,750 guest frames, 120 Hz | 1,428 | 0 | 318 | 0 | 1.0x |
| 6,200 guest frames, 120 Hz | 1,800 | 0 | 373 | 0 | 1.0x |
| 4,000 guest frames, 144 Hz | 166 | 0 | 0 | 0 | 1.0x |

No fallback means every attempted pair had at least one match; "partial" counts frames where fewer
than half the strips matched (the forest scene has ~40–60% in most frames, the cutscene ~100%). The
extra render costs 0.57 ms per present against 0.22 ms for a repeat at native resolution (0.61 ms
per draw); the guest still runs at 1.0x, because the work fits the 8.3 ms 120 Hz interval.

Visual check at guest frame 5700 (previous, intermediate, current): the intermediate has the same
edge energy as the two source frames (2.493 against 2.491 and 2.493; a naive 50/50 blend measures
2.432), so it is a re-rasterised frame rather than a cross-fade, and only 0.3% of pixels move at
that instant. The limitation is visible there too: texture content is not interpolated, so a video
or streamed background snaps at the current frame, and unmatched strips are drawn at the current
position, which biases a partly matched frame towards the newer picture. The intermediate also
introduces half a present interval of latency.

Covered by `render/tests/test_interpolate.cpp`: matching, first-candidate and cut rejection, 1/w
depth, UV movement, unmatched/removed strips, modifiers and clamping. The render suite is 96 cases
(1,433 assertions).

## Patch 025: a memory card without asking for one (2026-11-14)

`--vmu FILE` had existed since the card work, but nothing attached a card unless the command line
named one. A windowed run therefore booted with an empty expansion slot: the title showed "No VMU
Found", refused to save, and a first-time player had no reason to know the flag existed. The
packet's `tools\launcher.py` now always passes a card, but a run started from
`play-draconus.bat` should not behave differently.

A windowed run now defaults to `%APPDATA%\dream-recomp\saves\<game id>\vmu_a1.bin`
(`Application Support` on macOS, `$XDG_DATA_HOME` or `~/.local/share` on Linux). The directories are
created and, when the file is missing, the same `MemoryCard::format()` blank card is written — so
the first run can save, and the card is the standard 128 KB image, shareable with Flycast. If the
platform's data directory cannot be made, the run continues without a card rather than failing to
start over a convenience.

**Headless runs stay card-less.** A card answers Maple frames and changes the write stream, which
would invalidate every golden trace; the default is guarded on `window_mode` for that reason, and
`--vmu` still attaches one explicitly when a scripted run needs it.

Verified with `APPDATA` redirected to a workspace directory (the development sandbox denies the
real one to child processes): `memory card: default card for draconus is …vmu_a1.bin`, then
`created, formatted and empty`, and the file is exactly 131,072 bytes. The card's bytes are
identical to `tools/vmu.py`'s `blank_image()`, and the launcher reads its saves with the same
module.

## Patch 026: windowed, borderless and exclusive display modes (2026-11-14)

The launcher's **Fullscreen** checkbox is now a **Display mode** choice: windowed, borderless or
exclusive. The engine gained `dream::render::vk::DisplayMode` and `Window::create` takes it instead
of a boolean.

`--display windowed|borderless|exclusive` selects it (`--fullscreen` remains as the old name for
borderless, and either implies `--window`). Windowed keeps the 90%-of-usable-area sizing.
Borderless is SDL's fullscreen window at desktop resolution (`SDL_WINDOW_FULLSCREEN`), which changes
no display mode; it is what the old `--fullscreen` did. Exclusive asks SDL for one of
`SDL_GetFullscreenDisplayModes`, preferring the display's **current** mode first (no resolution or
refresh change) and then the highest refresh at the desktop resolution, calls
`SDL_SetWindowFullscreenMode` + `SDL_SetWindowFullscreen`, and `SDL_SyncWindow` before the swapchain
is built. If the window system refuses the mode change, it falls back to borderless with a warning
rather than failing the launch. `DREAM_TRACE_DISPLAY=1` prints the desktop mode and the modes the
display reports.

This host refused every exclusive mode with `ChangeDisplaySettingsEx() failed: DISP_CHANGE_FAILED`,
including 640x480@60 and a standalone SDL3 probe that does nothing but request it, so the exclusive
path could not be observed succeeding here; the fallback to borderless is what the run reports.
Borderless was verified at 2560x1440, windowed at 960x720.

The launcher also gained the interpolation presentation rule from patch 024's review: **Interpolate
extra frames** is labelled experimental, is enabled only when the present rate is 120 or 144, and
`build_command` passes `--frame-interpolation` only above 60 Hz. Settings that only had the old
`fullscreen` boolean migrate to `display_mode = borderless` when it was true. The launcher selftest
covers windowed (no flag), borderless, exclusive and the 60 Hz interpolation case.

## Patch 027: the HUD does not ride the projection (2026-11-14)

Patch 019 shipped hor+ assuming the HUD went through the title's projection. It does not. The HUD
is screen-space geometry, and at 16:9 the presenter stretched it 4/3 too wide.

The reproduction boots the retail disc into gameplay with the schedule used for the VMU work
(`start@1150 ... a@11000, start@13500, down@13700, down@13850, a@14000, a@14200`) and captures the
same guest frame twice, at 4:3 and with `--aspect 16:9`. The two display lists differ only in the
3D geometry; the HUD quads have **identical** screen coordinates in both:

| element | coordinates (640x480 guest screen) | depth |
|---|---|---|
| health bar frame | x 192..448, y 400..464 | 8.071 |
| health bar fill | x 192..429, y 400..464 | 9.071 |
| "1000" digits | x 300..343, y 418.5..435.5 | 10.071 |
| compass | x 568..632, y 392..456 | 10900 |
| "0" / icons | x 532..628, y 304..434 | 10990..11102 |

The x-scale patch at `0x0C098640` never touches them, so the QVGA x squeeze that corrects the world
does not correct the HUD. The presenter then maps 640x480 to 1280x720 (x2 horizontally, 1.5x
vertically): the world, squeezed by 0.75 first, comes back correct; the HUD comes back 4/3 too wide.
Measured on the presented image at the same guest frame: the compass ring was **188x141** in 16:9
against **141x139** at 4:3, and the health bar's "1000" was visibly wide.

The fix is a render-library pass, `compress_screen_overlays(Frame& frame, float factor, float width)`,
unit-tested in `render/tests/test_display_list.cpp`:

* It finds the frame's nearest world depth from the polygons that carry a depth span. The title
  draws its HUD, menu text and counters beyond it, in front of the near plane, as flat four-vertex
  quads; the 3D effects that also sit in front of the world (the darkness around the player) are
  triangles and are left alone.
* Quads at one depth are grouped into one element (the digits of a counter, the glyphs of a menu
  line). Parts of one element that overlap or sit within 16 px of each other -- the compass ring,
  its needle and the icons above it; the health bar and its digits -- are clustered and share one
  anchor, so a child cannot drift inside its parent. A cluster's anchor is the centre line for a
  centred element and the near edge for one at the side.
* A small glyph joins a nearby larger element when it has one: the wisp counter sits inside the
  compass cluster and moves with it. Only a genuinely stand-alone glyph (a damage number) is
  scaled about its own centre, so it stays on the thing it labels.
* The group's x is multiplied by the same `(4/3)/aspect` the projection was multiplied by; the
  presenter's stretch then restores the original width and height. The anchor is what keeps the
  element where it was, so the health bar stays centred and the compass stays in the corner.
* Hardware clip rectangles move with their quad, for a bar clipped to its current value.
* 4:3 is a no-op. A title with no `[widescreen]` hook leaves `wide_x_factor` at 1.0, because its
  world was not squeezed and its overlays must not be either.

The boot calls it only for a frame that carries depth, which is exactly the set the presenter
stretches; a flat 2D screen (title, menus, loading cards) is pillarboxed and untouched.
`DREAM_TRACE_SCENE=1` prints the number of quads compressed per frame in a windowed run.

Verified on the retail disc at 1280x720, same guest frame: the compass is **140x139** (4:3:
141x139) and the health bar's red fill is 252 pixels wide (4:3: 251), so the HUD keeps its absolute
size and its anchors; the "SAVING" text and the pause-menu lines keep their 4:3 aspect. The
compass needle sits **30 pixels left of the ring's centre** at both 4:3 and 16:9, and the wisp
counter sits within **one pixel** of the wisp's centre (4:3: about 1.5 px); the first pass anchored
each depth layer separately and moved the needle 13 pixels too far left, which is what the cluster
pass fixes.
The world is untouched: every pixel that differs from the pre-fix capture is inside a HUD region
(the health bar, the right-hand icons, the "SAVING" text); every pixel outside them is
byte-identical. The render suite passes 97/97 cases (1,459 assertions), including grouping, anchor,
clip, full-screen and no-op cases. See also patch 019, whose claim that the HUD rides the projection was wrong, and patch 021,
which handles flat screens.

## Patch 028: the frame stays on the GPU, and the frame time is measured (2026-11-14)

The target is 60 Hz at 1440p 16:9 — `--fullscreen --scale 4 --aspect 16:9`, where the guest draws
2560x1920 and the window shows 2560x1440. The question was not the average frame time but the tail:
one frame in two hundred that takes 20 ms is a visible hitch even when the run averages 8 ms.

**Measured first.** Two diagnostics were added (below) and the whole run — title, menu, intro,
character select, first level — was timed frame by frame. Windowed 4x 16:9, unthrottled, 6,500
frames of the title and intro: **8.45 ms mean, p99 14.60 ms, 19 frames over 16.67 ms, one 297 ms
stall**. `DREAM_TRACE_FRAME_TIME` split it:

```
window: 1.57 ms per draw, 1.51 ms per present
window: present split: begin 0.02, upload 1.23, draw 0.00, end 0.08 ms
```

**The cause was the round trip, still.** Every presented frame went GPU → CPU → GPU.
`Offscreen::render` copied the whole colour image into a host-visible buffer and waited on the
fence; `Presenter::upload` copied it again into a staging buffer and recorded a buffer-to-image
copy; the window then sampled that copy. At 640x480 that is 1.2 MB each way per frame, which is why
it never showed up before — at 2560x1920 it is **19.7 MB each way, 60 times a second**, plus a
GPU→CPU synchronisation point that stops the CPU dead every frame. The 297 ms stall was this
machinery meeting a driver hiccup.

**The fix: the frame is shown where it lies.**

* The offscreen colour image is created with `VK_IMAGE_USAGE_SAMPLED_BIT` and its render pass now
  leaves it in `SHADER_READ_ONLY_OPTIMAL`, not `TRANSFER_SRC_OPTIMAL`.
* `Presenter::use_image(view, w, h)` binds a second descriptor set to that image; the present pass
  samples the renderer's own target. Nothing is copied for a frame the window shows.
* `Offscreen::render(..., readback=false)` skips the copy and the fence wait. The wait moved to the
  *start* of the next render, so the CPU runs the next guest frame while the GPU is still drawing
  this one, and the wait a frame later costs nothing.
* The host pixels are still produced when something needs them, through `Offscreen::read_back()`:
  a render to texture (which the guest samples), `--framebuffer-writeback`, a screenshot, a
  capture, the frame-time probe and the on-screen counter. The display path no longer pays for
  them. `DREAM_PRESENT_CPU=1` forces the old upload path so the two can be compared.

**Result, same run:** vblank cost **1.49 → 0.29 ms** mean, present **1.51 → 0.28 ms**, frame mean
**8.45 → 6.64 ms**, frames over 16.67 ms **19 → 4**, and the 297 ms stall is gone. The direct path's
screenshot is **byte-identical** to the upload path's (`DREAM_PRESENT_CPU`), so nothing about the
picture changed.

**Then a full run with gameplay.** 18,000 frames covering title → main menu → character select →
Celanarin (the first level), fullscreen 2560x1440, unthrottled:

| measure | value |
|---|---|
| CPU per frame, whole run | **6.14 ms** (36 % of one core at 60 Hz) |
| heavy gameplay window (frames 16,800-17,400) | **12.42 ms** CPU mean, p99 in-frame vblank 0.33 ms |
| frames over 16.67 ms | **13 of 18,000 (0.07 %)**, every one of them a load |
| frames whose vblank exceeded 3 ms | 356, worst 14.16 ms (texture/pipeline first use) |

The 13 misses all have **under 0.3 ms in the vblank**: the renderer and presenter were idle; the
time went into the guest's own work in that frame (level/scene transitions — the disc reads and the
decompression that follow them), which is the "loads and hitches" the target excludes. Steady
gameplay has 4.2 ms of headroom on this machine.

**Renderer CPU work, kept down as well.** Two per-frame costs in the draw path are gone: the polygon
scratch list is a member (`items_`) rather than a fresh `std::vector` per frame, and the pipeline
lookup goes through a direct-mapped 256-slot front (`pipeline_cache_`) before the hash map, which
mattered because neighbouring polygons almost always share render state. Pixel-identical at guest
frame 16,102; the timing gain is inside the noise, but neither allocates per polygon any more.

**Diagnostics added (all opt-in, no cost when unset).**

* `DREAM_TRACE_FRAME_HIST=1` — the distribution that matters: mean/p50/p90/p99/max, the count over
  16.67/20/25/33 ms, the worst frames by guest number, the vblanks over 3 ms, a line every 600
  frames (mean, max, vblank, **CPU per frame**), and the run's total CPU per frame.
* `DREAM_PROFILE=<ms>` — a sampling profiler for the *host*: a thread suspends the emulating thread
  on that interval, reads its instruction pointer and counts it; the report resolves each address to
  its module, and `tools\profile-map.py <draconus_boot.map> <run output>` turns the launcher's own
  addresses into `fn_0c…` / `DcMemory::read32` names. It is what showed that the round trip, the
  heap and the audio chip are worth measuring at all; at 2 ms it costs about 10 % of the run.
* `DREAM_PRESENT_CPU=1` — force the CPU upload path, for comparing the two presentations.

**Profile of the final build** (18,000 frames, 46,052 samples): the emitted game code is the bulk and
is spread across thousands of addresses, as it should be; then `DcMemory::read32`/`write32` ~10 %
(the non-RAM accesses: video memory, registers, sound RAM), the AICA (ARM7, mixer, DSP) ~5 %,
`call_indirect` ~1 %, `devinterp::run` 0.3 % (the residual untranslated calls). `ntdll` was 12 % in
an unthrottled run, almost all of it one `NtWaitForMultipleObjects` — the main thread waiting for a
swapchain image, which is wall time, not work; the CPU-per-frame figure above excludes it.

**Verified.** `tools\parity-check.ps1`: stop, frames, PVR and Maple counters identical, cycles
identical to the cycle (3,635,956,132 in both), screenshot byte-identical. Two 600-frame headless
runs with `--write-hash` and the same seed produce identical files. The direct-present screenshot
matches the upload path's, and the renderer change matches the previous build's at guest frame
16,102.

## Patch 029: the jump pack is a device, and its effects reach the pad (2026-11-14)

Draconus's options screen has had a **JUMPPACK / PACK OFF / PACK ON** row all along, and its script
language has `vibrate_purupuru(num,num,num,num)`, but the runtime had no vibration device, so the row
could not do anything. The game enumerates expansion devices from the controller's reply, so a pack
that is not there is not merely ignored: the title never has an effect to send.

`maple::JumpPack` is now attached to port A's second expansion slot, next to the memory card in the
first. It answers Device Request and All Status Request as a Puru Puru pack (function 0x00010000,
one motor, seven power levels, "Puru Puru Pack", 20/160 mA, Flycast's capability string), reports the
last effect from Get Condition, and implements Set Condition, Get Media Info, Block Read and Block
Write. The effect decoding is Flycast's `maple_sega_purupuru`: the two three-bit drive fields give
power, `freq` and the signed `inc` give the duration, and the pack's auto-stop time caps it.

The decoded effect goes to `Window::rumble`, which plays it on every attached pad's ordinary rumble
motors through `SDL_RumbleGamepad` (and `XInputSetState` when SDL found no pad and the input is coming
through the XInput fallback). Both motors get the same strength, because the Dreamcast pack has one
and splitting it would make the feel depend on which motors a particular pad has. A zero effect stops
immediately; a window that closes stops a running effect rather than leaving it to a driver's timeout.
A headless run leaves the handler empty, so traces and parity are unchanged.

**Verified.** The runtime unit suite passes (78 cases, 121,176 assertions), including a new case that
attaches a pack in slot 1, checks the controller advertises 0x22, sends the KallistiOS "basic thud"
(`0x011A7010`: power 1, 26 Hz, 269 ms) and checks that a zero effect reaches the host as a stop.

In the game, `DREAM_MAPLE_TRACE=1` shows the title probing address 0x02 on the sixth Maple frame,
which is the proof the device is visible; the first frame to 0x02 is a Device Request, not a timeout.
Opening **Options → JUMPPACK** sends `0x010FF010` (power 1, 15 Hz, convergent, 466 ms), and
`DREAM_RUMBLE_TRACE=1` shows the host call with that power and duration. The game's option is off by
default, so a player selects **PACK ON** on that row; the row previews the pack as it is highlighted,
which is the effect above. Gameplay rumble then uses the title's own `vibrate_purupuru` calls, exactly
as it would on hardware.

`DREAM_MAPLE_TRACE=1` (every frame, recipient, command and first arguments) and
`DREAM_RUMBLE_TRACE=1` (each host effect) are opt-in and cost nothing when unset.

## Patch 030: the overlay blends the frame, not the staging buffer (2026-11-14)

Turning on the on-screen counter (`F10`, `--fps`) cost **~11 ms of the 16.67 ms frame budget** at
`--scale 4`. `DREAM_TRACE_FRAME_HIST=1`, 1,800 frames, same scene, windowed:

| | counter off | counter on (before) |
|---|---:|---:|
| CPU per frame | 5.20 ms | **16.06 ms** |
| vblank (render + present) | 0.48 ms | **11.69 ms** |
| present | 0.50 ms | **12.40 ms** |
| frame p99 / max | 18.43 / 613 ms* | **25.13 / 612 ms*** |
| frames over 20 / 25 / 33 ms | 4 / 4 / 1 | **47 / 19 / 10** |

<sub>*the max in both runs is the first frame, before the window is up.</sub>

That is the reported "dips into the 40s". At 16.06 ms of work the frame no longer fits 16.67 ms, so
the pacer cannot sleep, the guest falls behind its own clock, and the AICA queue — filled from the
same thread once a frame — underruns. The crackle is not a separate fault; it is the same stall.

Two things composed, and only the second is a bug.

**The cost of the CPU path is known and bounded.** `overlay` (the counter, or the bindings screen)
drops presentation back to the upload path, because the direct-present change (patch 028) only
applies to a frame nothing is drawn over. That round trip — readback, fence waits, 19.7 MB out and
back — measures ~2.3 ms of the total at 4x.

**The bug: the overlay read the write-combined staging buffer, one uncached access per pixel.**
`draw_text`'s panel is translucent, so it blends src-over-dst and must read the destination pixel.
The destination is `Presenter`'s staging buffer, which is host-visible but deliberately *not*
host-cached — `HostBuffer::ensure` takes the plain coherent type unless `cpu_reads` is set — so it
is a write-combined window onto video memory. One blended pixel is therefore one uncached round
trip:

| `--scale` | panel pixels | upload (with decorate) | per pixel |
|---|---:|---:|---:|
| 1 (640x480) | 3,492 | 0.67 ms | 172 ns |
| 2 (1280x960) | 13,968 | 2.93 ms | 210 ns |
| 4 (2560x1920) | 55,872 | 10.76 ms | 171 ns |

A flat ~175 ns a pixel is **22 MB/s**, against 16 GB/s for that same buffer written in one `memcpy`
— so this was latency, not bandwidth, and it scaled with the panel's *area* rather than with the
picture. The isolation run makes it unambiguous: forcing the same CPU path with
`DREAM_PRESENT_CPU=1` and no counter costs 1.20 ms of upload at 4x, so 9.55 ms of the 10.76 ms was
the blend and 1.20 ms was the round trip. `--present-rate 120` doubled it again — the extra presents
are dropped once a frame is late, so the display gains nothing and the blend is paid twice.

`fill_rect` and `draw_text` now take the picture as `under`: the destination side of the blend comes
from the caller's own pixel buffer, which is ordinary cached memory, and the staging buffer is only
ever written. `Presenter::upload` passes its `rgba` to the decorate callback for exactly this, and
`InputMenu::draw` passes it to the one translucent fill it makes — the full-screen shade, which at
4x was 4.9 million read-modify-writes whenever the binding screen was open.

**Verified, same run after the change:**

| | counter off | counter on (before) | counter on (after) |
|---|---:|---:|---:|
| CPU per frame | 5.20 ms | 16.06 ms | **6.69 ms** |
| vblank | 0.48 ms | 11.69 ms | **2.35 ms** |
| present | 0.50 ms | 12.40 ms | **2.49 ms** |
| frames over 20 / 25 / 33 ms | 4 / 4 / 1 | 47 / 19 / 10 | **3 / 3 / 1** |

The counter now costs **1.5 ms** instead of 10.9 ms, and the tail is indistinguishable from not
having it on. `render.unit` passes — 100 cases, 1,907 assertions — with two new cases: a poison
destination proves the blend never reads what it overwrites, and a pixel-for-pixel comparison proves
drawing over `under` is identical to drawing over a copy of the frame. The binding screen gets its
own equivalence case. A presented screenshot diffed against the same frame taken with the counter
off differs in 2,560 pixels, all of them inside the panel's rectangle. `tools/parity-check.ps1`
still reports `PARITY OK`, screenshot byte-identical.

**Left on the table.** The counter still forces the upload path, so it costs 1.5 ms rather than
nothing. Removing that means compositing the counter in the presenter on the GPU — a small overlay
texture and a second sampler in `present.frag`, with the alpha blend done there instead of in cached
memory — which would leave `--fps` at the direct-present cost. Not done here because it changes the
present pipeline for a development readout, and the 1.5 ms no longer threatens the budget.

## Patch 031: the panel can show the picture evenly (2026-11-14)

Reported as: 59-60 fps on the counter, 0.98-0.99x, and visibly uneven motion — worst crossing the
bridge in the first area. The frame rate was never the problem, and no frame rate could have shown
this, because the picture was arriving at the right rate and being *held* for the wrong times.

**A picture can only change on a vertical blank.** It is therefore on the glass for a whole number
of refreshes, and the number is `refresh / pictures-per-second`. `--display exclusive` took the
highest refresh the panel offers — 165.00 Hz — and the title presents 59.94 pictures a second.
165 / 59.94 = **2.753**: not a whole number, so pictures were held for two refreshes (12.12 ms) and
then three (18.18 ms), a 33 % swing in how long each one is displayed, repeating about fifteen times
a second, everywhere in the game.

`DREAM_TRACE_PACING=1` reports the ratio and whether the cadence can be even:

```
pacing: display 165.00 Hz, 59.93 presents/s -> 2.753 refreshes per picture
pacing: NOT a whole number of refreshes per picture: the display has to hold some pictures for 2
        refreshes and others for 3, so the cadence is uneven whatever the frame rate says.
        A display at 59.9 Hz or 119.9 Hz would make it even
```

`Window::set_content_hz` now tells the window what rate pictures arrive at — the title's 60 Hz, or
`--present-rate` when that asks for more — and exclusive fullscreen prefers the highest refresh that
is a whole multiple of it. On this panel that is 119.98 Hz, which holds every picture for exactly two
refreshes; 120 Hz also gives 8 ms of slack for a frame that is late, where a 59.94 Hz mode would have
none. The window states what it achieved, measured from the mode actually running rather than the one
requested, and when nothing divides evenly it keeps the old choice and names the two rates that would
work:

```
display: 119.98 Hz holds 1.999 pictures per refresh -- a whole number, so every picture is shown
         for the same time
```

**Tried and rejected: a precise pacer.** The pacing sleep rounds up to the system timer, so intervals
alternate. `DREAM_TRACE_FRAMES=<file>` dumps every interval; over 1,600 frames of play the mean was
16.68 ms, sd 0.76 ms, lag-1 autocorrelation **-0.46**. Sleeping to within 1.2 ms of the deadline and
spinning the rest cut sd to 0.49 ms and put 96 % of frames within 1 ms of nominal (from 82 %), but
the alternation stayed — the work inside a frame varies by more than the sleep overshoot, because the
present blocks on the swapchain — and it cost 7 % of a core in idle spin. Sub-millisecond jitter is
not what judder looks like. Reverted; the measurement is in the comment so it is not tried again.

**Cleared: the presenter repeating frames.** Where motion stalls for a frame, a present shows a
picture that was not re-rendered. That is not the renderer dropping frames: the pacing report counts
the guest's *own* render starts alongside the repeats, and in the windows where it happens — the
intro movie, the menus — **460 renders were asked for and 461 pictures were new**. The title did not
request a render on those vblanks. A capture's `.txt` now reads
`renders N (M asked for by the guest)` so the two can be told apart in a bug report, and
`DREAM_TRACE_FRAMES` records the interval and the vblank cost of every frame.

This is worth knowing when reading the counter: it counts *presents*, so a title that renders 52
pictures a second and presents 60 still reads 60 FPS. The counter is honest about the window and
says nothing about how often the picture changed.

**Cleared as well: the modelled PVR render time.** `Core::start_render` schedules the render-done
interrupt at `200,000 + 4 x TA words` cycles and the guest waits for it, so the model sits on the
guest's critical path — the obvious suspect for a scene that draws less often than it presents. Two
experiments settle it. Inflating it tenfold (~11 ms a frame) collapsed gameplay from 600 renders per
600 vblanks to exactly **200**, a hard `frame budget / render time` floor, so the dependency is real.
Removing it entirely changed **nothing**: 460, 428, 599, 599 renders per window, identical to the
shipped values. It is not what limits this title today. Both measurements were taken with the model
restored afterwards; `pvr/core.h` is byte-identical to the pinned engine.

**What the counts look like in a real session** (4,000 frames, windowed, 4x): the title asked for
2,930 renders and got 2,930 — the renderer dropped nothing. Every repeated picture was a vblank the
title chose not to draw on, and the window lines say which: 599/600 in menus and 3D gameplay,
~460/600 through the 30 fps intro movie, 392/600 on a static story screen, and 513/600 in a heavy
spot (~51 pictures a second). A scene drawing 513 pictures a second cannot look like 60 pictures a
second, and no presenter change can invent the missing ones.

**Verified.** All six suites pass; `tools/parity-check.ps1` reports `PARITY OK` with a byte-identical
screenshot — this is display timing only and the guest is untouched. The frame rate and the cost of
the counter are unchanged (0.10 ms per draw, 2.47 ms per present at 4x with `--fps`).

## Patch 032: --sh4-clock, or making the console faster than the console (2026-11-14)

A guest frame is one vertical blank, and a vertical blank is a fixed number of cycles — 3,333,333
at 60 Hz. The console's budget for a frame is therefore fixed, and however fast the host is it does
not buy the guest a single extra cycle: the host's only job is to stay ahead of the clock. A title
whose work does not fit that budget does not slow down smoothly, it misses the blank and draws
nothing, which on screen is judder. That is what the bridge is.

The one lever that changes it is to give the guest more cycles per blank: `--sh4-clock MHz` raises
the clock the runtime schedules against. `sched::kSh4Clock` was already the single place the frame's
budget came from — the SPG derives a scanline's length from it (`spg.cpp`), and the TMU, the Maple
bus and the interrupt clamps convert their own real-time rates through it — so it became a runtime
value and those three conversions follow it. Video, audio and the disc keep their own timing — see
the amendment below, which is where the first cut of this got that claim wrong; the pacer divides by
the same clock, so the title still runs at its own speed (verified: 11,500 frames in 191.7 s at 2x,
exactly 60 fps).

Measured on the same scripted session, as a share of vertical blanks the title actually drew on:

| scene | 200 MHz | 300 MHz | 400 MHz |
|---|---:|---:|---:|
| 2D transition A | 460/600 (77 %) | 508/600 (85 %) | 531/600 (89 %) |
| 2D transition B | 428/600 (71 %) | 485/600 (81 %) | 514/600 (86 %) |
| open 3D gameplay | 599/600 | 599/600 | 599/600 |

So those scenes were cycle-starved rather than "30 fps by design" — a correction to the note in
patch 031. Half of the deficit goes at 1.5x, most of it at 2x, and what remains is the title not
drawing on every blank even with double the budget.

**Cost to the host**, at 4x 1440p with `--fps` and audio, 1,500 frames: 6.36 ms of CPU per frame at
200 MHz, 8.25 at 300, 10.07 at 400 — still 1.0x with 6.6 ms of the 16.67 ms frame to spare on this
machine.

**Not the default, deliberately.** 200 is the console, and defaulting to more would (a) stop the
emulator modelling the hardware, invalidating every recorded baseline and the Flycast comparisons;
(b) apply a timing assumption to every title in the tree that only some titles tolerate — anything
that measures elapsed time in CPU cycles rather than in blanks runs fast; (c) spend the host
headroom that keeps 1.0x, which on weaker hardware turns judder into slow motion (worse: it
desynchronises audio and input); and (d) erase the signal that we are slower than hardware, which is
exactly the evidence the next piece of work — a per-opcode cycle model — would need to calibrate
against. It is a tool for a title and a scene, not a default for a machine.

**Verified.** Default 200 is byte-identical: `tools/parity-check.ps1` reports `PARITY OK` with the
same cycle count (3,635,956,128) and an identical screenshot, and all six suites pass. A clock
outside 100–800 MHz is refused with a message rather than silently producing a run at a speed
nobody can explain.

### The first cut scaled the wrong devices, and the game ran fast

The first version above was wrong in a way that players found in one session: **the bridge stopped
juddering and everything else sped up.** The clue is the shape of the fault — 60 frames a second on
the counter, motion 1.5x too quick.

Only the devices that *divide by a real-time constant* had been moved onto the runtime clock (the
SPG's scanline, the Maple bus bit rate). Three things were left on the old 200 MHz assumption, and
all three are timer-like:

* **The timer unit** counts in cycles: `counter()` was `now() >> shift`, one tick per `2^shift`
  cycles, so at 300 MHz a tick was 1.5x shorter in real time. KallistiOS builds its millisecond
  clock on TMU0, so *every* game timer advanced 1.5x too fast — the game moved faster per frame
  while still drawing 60 frames a second. This is what "gameplay is sped up" was.
* **The sound chip** used `kSh4CyclesPerSample = 200'000'000 / 44100`, so 300 MHz produced 66,150
  samples a second: the music would play at the wrong pitch.
* **G2 DMA** used a hardcoded four cycles a byte, so disc and texture transfers completed 1.5x too
  fast.

`Tmu` now converts every cycle it looks at onto the console's 200 MHz timeline (`console_cycles()`,
a reduced fraction so it is a multiply and a divide, and the identity at 200), and converts the wait
back into CPU cycles when arming the event. `Aica::sh4_cycles_per_sample()` and `g2dma`'s
`cycles_per_byte()` derive their period from the runtime clock. The result is the model that was
wanted all along: **only the CPU gets more cycles per blank; the rest of the console keeps its own
timing.**

Measured after the fix: audio is 1,316,739 samples in 29.857 s at 200 MHz and 1,319,287 in 29.912 s
at 300 — both 44,100/s (it was ~66,150 before). A new runtime case runs one second of scheduler time
at each clock and checks the timer reading is identical, and that it really counted 12.5 million
ticks, so this cannot come back unnoticed.

The lesson worth keeping: an overclock is only correct if *every* device that converts a real-time
rate into cycles is enumerated, not just the ones that obviously look like they do.

## Patch 033: the item wheel is a panel with a 3D model inside it (2026-11-14)

The wheel that pops up left of the health bar when the player switches item is a **256x256 flat
four-vertex panel** at depth **7.0711**, drawn below the frame's nearest world depth (7.9831 in the
capture). Patch 027 only looked at flat quads beyond the world's near depth, so it skipped the
panel; the item's rotating 3D model is submitted **inside** the panel at depth 7.3-7.9 and was not
part of any flat group either. At 16:9 the panel was stretched 4/3, and the model, riding the wide
projection, drifted right toward the health bar.

The render-library pass now treats a large flat four-vertex quad (at least 128 pixels in both
directions, not the full-screen background) as a **HUD panel**. It compresses the panel and every
polygon whose rectangle lies inside the panel **and whose depth is within 1.5 of the panel's own
depth**, about the panel's anchor (the left edge for this wheel). The near-depth window is what
keeps the panel from swallowing a pass that happens to overlap it: the pause menu's black splash is
drawn at depth 10.87, far in front of the wheel's 7.07, and used to be torn where it crossed the
panel's rectangle. The world behind the panel is left alone, and the health bar only overlaps the
panel's rectangle partly, so it is not dragged into the panel's cluster. The item wheel and its
models therefore keep their 4:3 size and their place at the left edge; the panel's texture (the
wheel graphic) is compressed with it.

Verified on a user F11 capture of the phial preview: the frame contains one 256x256 panel at
`z=7.0711` with 300 polygons of model/glow inside it. With `dream_render_view --aspect 16:9` (the
new option applies the same compression to a capture), **301 polygons** are compressed; the model
stays at the wheel's left anchor and the simulated 16:9 presentation keeps it at 4:3 size, with no
pixels changed outside the wheel/model, health bar and compass. On a user F11 capture of the **pause
menu** (2,232 polygons), the same pass compresses 105 polygons — the wheel panel and its nearby
contents — while the pause splash, drawn far in front at depth 10.87, is untouched: the black
background is whole and the detached piece that used to appear at its lower left is gone. Normal
gameplay has no such panel, so the pass is a no-op there; the render suite passes 101/101 cases
(1,917 assertions), including the panel/model and far-overlay tests.

## Patch 034: the launcher can choose the sound device, volume and buffer (2026-11-14)

The Audio tab was only a sound on/off checkbox. Three settings now reach the sink:

* **Volume** (`--audio-volume 0..100`, default 100). `Sink::set_volume` scales each sample on its
  way to the device; a value of 100 is a pass-through, so the old output is byte-identical. `--wav`
  records the AICA's output before this scale, so a quiet play-through still produces a full-scale
  reference capture.
* **Output device** (`--audio-device NAME`, listed by `--list-audio-devices`). `Sink::open` takes the
  name, resolves it through `SDL_GetAudioPlaybackDevices`/`SDL_GetAudioDeviceName`, and opens that
  device. A name that has gone away (or refuses 44.1 kHz stereo) falls back to the system default;
  boot prints `could not use 'X'; playing through 'Y'` so the fallback is visible. The launcher fills
  its combo from the engine, keeps a vanished saved device as `(not found)`, and refreshes the list
  when the dropdown opens, so a headset plugged in after startup is selectable.
* **Buffer / latency** (`--audio-buffer MS`, default 186 ms). This sets the sink's `high_water`: the
  queue length at which a block is dropped rather than letting sound drift further behind the
  picture. Lower is tighter and more prone to a busy host dropping blocks; higher rides out longer
  stalls. The launcher offers 93 / 186 / 372 ms.

The option parser rejects a volume outside 0-100 and a buffer outside 20-1000 ms instead of clamping
silently. `--list-audio-devices` runs before the config check, prints one name per line and exits 0,
so it works without a title.

Verified on this machine: the list names six playback devices; `--audio-device "Speakers (GSP 370)"`
opens that device and prints its name; a missing name falls back to the system default with the
message above; `--audio-volume 0` opens and feeds silence; `--audio-buffer 93`/`372` are accepted and
`10`/`1001` are refused; the volume-100 path still produces the M6 capture bit for bit (the M6 gate
is unaffected). `tools\launcher.py --selftest` and `--smoke` pass, including a check that the volume
slider reaches `--audio-volume`, 100 % does not, and sound-off passes none of the three flags.

The patch adds `audio/` to the touched directories. `patches/0001-engine-local-changes.patch` was
regenerated from the pristine pinned tree; applying it to that tree reproduces `engine/`'s
`audio/`, `cmake/`, `render/`, `runtime/` and `translator/` exactly.

## Patch 035: a particle effect is not a HUD panel (2026-11-14)

Patch 033's panel test was "a large flat four-vertex quad is a HUD panel". The forest's standing
stones are ringed by translucent light shafts that are exactly that: 128-230 px flat quads at
z 0.13-0.25, submitted as particles while the effect plays. The panel pass treated each as a panel
and multiplied its x by `(4/3)/aspect` about a screen anchor, moving the shafts up to 25 % left.
The rocks' glow detached from the stones and snapped back when a shaft crossed the 128 px size
test or changed anchor -- the "geometry snaps apart and comes together" seen in play, always when a
particle effect was near the object.

The same frames also contain the wheel's panel (256 x 256 at z 7.0711, alpha 0 when closed), so the
pass cannot simply require `lo > world_z`: the wheel is below the near plane (0.89 of it in patch
033's capture). A panel is HUD, and HUD is drawn in the near-depth slab; a world-space particle
billboard is far behind it. The panel test now requires `lo >= world_z * 0.5`: the wheel passes
(0.89), the shafts do not (0.03). The contents window and the group pass are unchanged. This also
corrects patch 033's claim that normal gameplay has no such panel: the closed wheel panel is
present in every gameplay frame, invisible.

Measured on the four F11 captures from the report: the first frame's pass compressed **35**
polygons before and **15** after, and the other three settle at 15 too. The 20 removed from the
first are the particle quads (19) and one triangle dragged in with them. Rendering a capture with
`--aspect 16:9` and diffing it against the raw frame put the before-difference over the light
shafts and the HUD; after the fix every changed pixel is in the HUD, and the 3D scene above y =
360 is byte-identical. `render/tests/test_display_list.cpp` gains a case with a near plane at 7.5,
a 200 px particle at 0.2 and the wheel panel at 7.0: the particle stays put, the panel and its
model move. The render suite passes 102/102 cases (1,925 assertions).

## Patch 036: an optional modern control layer (2026-11-15)

Draconus' own scheme is tank-like on one stick: analog Y moves forward/back, analog X turns, and
the L/R triggers strafe. The manual also confirms A is Shield/Action, so a modern layout wants the
left stick to strafe, the right stick to turn, LT to block and RT to attack. The game already
supports the hard part. A scripted controller recording reached gameplay and captured forward,
strafe-left, turn-left and forward+turn+strafe at the same frame; the combined frame shows the
strafe animation and the rotated camera, so the game applies strafe and turn simultaneously. No
guest-code change is needed for movement.

What the input layer could not express was the button duplication: `DeviceBindings` held exactly one
`Binding` per `PadControl`, so A could answer the A button or the left trigger but not both. The
patch adds:

* `InputPreset` and `effective_bindings()` in `render/input.{h,cpp}`. Classic returns the player's
  sets unchanged. Modern overrides only the gamepad left/right trigger and stick controls
  (`ltrigger = leftx-`, `rtrigger = leftx+`, `stick_left/right = rightx-/+`, `stick_up/down =
  lefty-/+`) and adds `ExtraBinding`s for A from `lefttrigger+` and X from `righttrigger+`. The
  base `Bindings`, the keyboard set and every other control are untouched, so F1 keeps editing the
  player's layout and Classic restores it exactly.
* `Window::set_input_preset()` and `extra_gpad_` resolution in `render/src/vk/window.cpp`. Extras
  are evaluated exactly like the primary source, with the same dead zone and only while not
  capturing, then combined with it. The XInput fallback gets the same remap directly
  (`thumb_lx` → strafe triggers, `thumb_rx` → turn, `thumb_ly` → forward/back, LT/RT join A/X).
  The generic DirectInput mapping now names `rightx`/`righty`; it previously left them out, so a
  pad that arrived as a raw joystick had no right stick for SDL to read at all. `DREAM_INPUT_TRACE`
  now treats a trigger change as a change too, which is how the LT/RT path is visible. Trigger
  extras use a half-travel press threshold (`max(deadzone, 0.5)`), not the stick dead zone: this
  pad's triggers rest at 96/255 (0.38), above the default 20%, which held block and attack from
  startup in the first build. Sticks keep the configured dead zone.
* `--controls classic|modern` in `runtime/boot/boot_main.cpp`, passed through `Live` to the window.
  Modern is a layer over the loaded bindings and is re-applied whenever F1 saves; it is not written
  into the user's binding file.

The launcher's Gameplay tab gets **Controls** (Classic/Modern), `build_command` passes
`--controls modern`, `play-draconus.ps1` gets `-ModernControls`, and `--selftest` / `--smoke` check
that the option reaches the command line and that Classic does not. The engine test suite gains
`modern controls change only the gamepad sticks, triggers and the A/X extras`.

Consequences, documented rather than hidden: the game reads its analog stick for menu navigation,
so Modern moves menu cursors to the right stick (the d-pad still works); and because LT is now
block, the game's both-triggers User Mode chord is no longer available as it was. RT keeps no
guest trigger role in Modern: it is the attack source. The launcher help says all of this.

**Verified:** `--controls modern` prints the modern-controls line at startup and its window resolves
the overrides; `--controls classic` is the old path byte for byte. At rest this pad reports triggers
96/96 on the classic path; with the half-travel trigger threshold the modern run starts with every
button released (no `input:` change line), so block and attack are no longer held. With the synthetic pad,
left stick left/right reached the guest as L/R triggers 255/0 and 0/255 while `joy_x` stayed at
centre, and right stick left/right reached the guest as `joy_x` 0/255 while the triggers stayed
centred. The render suite (including the new input case) passes; a physical-pad test remains the
right check for feel and for the LT/RT extra sources. The patch adds `render/` and `runtime/` files
to the local delta and is carried by `patches/0002-modern-controls.patch`, regenerated from the
pristine pinned tree plus `0001-engine-local-changes.patch`.

## Patch 037: discovery reaches long constructor functions (2026-11-15)

`DREAM_TRACE_UNTRANSLATED=1` over 60 s of scripted play reported **101 untranslated calls**,
not the four or five the earlier seeded scenes suggested. Ninety-seven of them were one call each,
all from `0x0C17D556`: the static-constructor loop at `0x0C17D544`, which walks a 125-entry function
pointer table at `0x8C1FAD98` in RAM.

The functions were real (`mov.l r14,@-r15 ; ...`, ordinary prologues) and the table is in the
image, but pointer discovery rejected them. Its `plausible_entry` test accepts a pointer only if a
forward scan reaches `RTS`/`BRA`/`JMP`/`RTE` within **200 instructions**. These constructor
functions begin with hundreds of straight-line calls before their first branch; the first function
in the table, `0x0C012A68`, reaches its first `BRA` after **498 instructions**. The 200-instruction
cap was not a safety feature for this title, it was a blind spot.

The cap is now 1,024. Discovery goes from 8,936 to **9,126 functions** (1,071,709 instructions),
the constructor table is translated, and the run's untranslated count falls **101 → 4**. The four
that remain are switch-case labels, handled by patch 038. Guest counters are identical (at 3,600
frames: 7,338,501 TA chunks, 3,155 frame swaps, 195,177 interrupts) and `tools\parity-check.ps1`
is still byte-identical.

Reproduce: `DREAM_TRACE_UNTRANSLATED=1` on a run past frame 3,600; the 97 one-call targets from
`0x0C17D556` disappear after a rebuild.

## Patch 038: a resume miss tries the other functions that contain the block (2026-11-15)

The last four calls were `0x0C234F62`, `0x0C234F6A`, `0x0C234F6E` and `0x0C234F78`, one call each,
each recorded with **its own address as the call site**. They are case labels of a `mov.w` jump
table at `0x0C234F38`, used by the dispatcher at `0x0C234EF0`:

```
mov #21,r1 ; cmp/hs r1,r0 ; ... ; mova 0x0C234F38,r0 ; mov.w @(r0,r1),r0 ; braf r0
```

The table and its cases are translated; the resume switch of the function at `0x0C234E7E` lists
all four labels. The problem was ownership. Discovery also keeps smaller fragments that start
inside the same code (`0x0C234F1C` is one, the `shll/mova/mov.w/braf` tail itself), and
`find_containing` returns the **nearest** fragment. `call_indirect` therefore entered the fragment,
whose resume switch knows only its own first block; the case label missed, `resume_miss` handed it
to the interpreter, and the interpreter called the address again — which is why the recorded call
site equaled the target.

`resume_miss` now retries the other registered functions whose range contains the address,
nearest-first and never the same one twice, before falling back to the interpreter. This keeps the
normal nearest-fragment choice (the first attempt is unchanged) and only widens it on a miss. The
four labels resolve to the root's switch cases and the count is **0 over 8,200 frames** (136.6 s
guest, of which the last 60 s are in gameplay).

**Validation.** `tools\m5-check.ps1` runs the 8,200-frame scripted play, asserts zero untranslated
calls, renders ten checkpoints, drives Flycast's Lua at the same guest frames, freezes each frame
with a busy-wait, captures it with `PrintWindow`, and compares at or below MAE 16. The ten
checkpoints measure 1.46-13.58 (a wrong-screen pair measures 27-38). Windowed parity is
byte-identical; the headless parity counters match. The engine's own suite is unchanged.

Carried by `patches/0003-m5-coverage.patch`, which applies after 0001 and 0002.

## Patch 039: interpolation pairs the strips it was leaving behind (2026-11-15)

Reported from play, with `-Interpolate` on: seams in the environment break apart and flash, the same
on the character, and the red opening flyby shows a pink flash when Escape skips it. All three
disappear with interpolation off, so the picture the guest draws is right and the intermediate frame
is what is wrong.

The intermediate frame is `render/interpolate.cpp` matching each strip of the newer frame to the same
strip of the older one. That matcher had two faults, and both bias the frame towards pieces of the
world standing still while the rest moves — which on a moving camera is a seam that opens and snaps
shut again half a present later, i.e. flicker.

**Fault 1: the candidate window could not resynchronise.** Same-signature strips are paired in
submission order, and the cursor looked at most two candidates ahead (`patch 024`: "Two candidates
cover one culled or inserted strip"). A same-key group in this game is not two strips long: the
opaque list holds groups of 22, 244 and 426, and the translucent list groups of 120-569. One run of
two or more inserted strips stuck the cursor, and because it only advanced on a match, *every* later
strip of that group stayed unpaired. Measured on eight dumped frame pairs: at guest frame 4780 the
translucent list had 221 of 2041 strips paired (11 %), and 1483 of the 1690 visible translucent
strips in the newer frame had no predecessor, while a same-key candidate within 20 px existed for
1208 of them. That is the sword's glow, the character's own translucent pieces and the leaf quads
left behind while the world moves.

The window is now 16 and the scan runs only for the strips the first two candidates did not place, so
the common case costs what it did. On the dumped pairs this takes the translucent list at guest frame
4780 from 221 strips paired to 2,016, of which 1,962 move (the rest pair with no displacement), and
the frame as a whole from 4,093 to 6,353 of 6,530.

**Fault 2: a re-sorted list cannot be paired by order at all.** Translucent strips are sorted back to
front, so the guest necessarily submits them in a different order every frame. No window fixes that.
A strip's corner-by-corner texture coordinates do not change when the camera moves, so they identify
the strip independently of both its place in the list and its place on the screen; when the order
finds nothing, that signature is looked up in the nine 96 px screen cells around the strip (a
qualifying pair's centroid is within the scan's 64 px distance limit, so it cannot be outside them)
and the closest exact match is taken. The index is built on the first strip that needs it.

**The seam rule (revised the same day).** Even a partly-matched frame must not tear: neighbouring
strips in the newer frame share corner positions, and if only one of them moves, the shared edge
opens. The first cut of this looked up the *unmatched* corners in a cell table of the matched ones,
which closed the crack wherever one side had no pair — but not where both sides had one and the two
pairs disagreed. Those are the pairs chosen by a wrong owner, and there are more of them the more
strips pair: measured on the 6,594-strip frame at guest 4775, 22 shared corners per frame with the
old two-candidate rule (median 43 px apart), 175 with the widened window and uv rescue above. A crack
of 20-40 px at half a present interval, at 120 presents a second, is exactly "seams breaking apart as
fluctuating flashes".

The movement is now keyed on the corner *position*: one displacement per screen point, in a flat
hash table of quantised (x, y, 1/w) — a sixteenth of a pixel and a sixty-five-thousandth of the depth
range, far below anything that shows and far above a rounding difference between two writes of one
value. Every vertex, matched or not, takes the displacement of its own position, so two strips that
share a corner cannot move it differently and the seam cannot part; a strip the pairing missed moves
with the strips it touches; and a corner nothing shares keeps the newer frame's position, where
standing still is right because there is nothing beside it to tear against. A corner claimed twice
takes the claim that moves it least, which is the least visible way to be wrong. Measured on the same
dumps, shared corners that still separate: **none above 0.014 px** (the quantisation step), against
up to 97 px before. The picture then changes where the cracks were: on the 4x intermediate frame at
guest 4775 a flat fog-coloured wedge over the cliff — a displaced strip exposing the background —
disappears, and 3.9 % of the frame's pixels change with it.

**What the caller does with it.** `InterpolationStats` reports the median corner motion, and the
presenter repeats the current picture instead of drawing a frame that is not worth drawing: one whose
median motion is under 0.75 px (a still picture, where a re-draw can only differ from the original),
and one where fewer than half the strips paired (a cut or a fade, which would otherwise show one
scene morphing into another). The library still refuses a frame whose *average* motion is over 48 px;
the `<50 %` rule is the same intent applied to coverage, and `patch 024`'s documentation already
claimed it while the code only refused a frame with *no* pair at all.

**Presenting it, and capturing it.** The intermediate frame used to be read back to the host and
uploaded again, twice per guest frame's worth of presents at 4x: 20 MB down and 20 MB up, the same
round trip `Offscreen` documents as "the difference between a frame that fits 60 Hz with room to
spare and one that just fits". It is now presented from the GPU image like any other frame, which is
what makes the requested rate reachable: **119.8 presents/s** at `--present-rate 120`, `--scale 4`,
16:9, in gameplay, against 113.5 with the round trip. And F11 now captures the picture that is on the
glass: when that is the intermediate frame, `.ppm` is that image and a new `.interp` text file holds
the geometry that drew it (the `.ta` beside it is the guest's own display list, which did *not* draw
it). Without that, a report of a torn intermediate frame was a capture of the one frame that never
showed the fault.

**The on-screen counter moved to the GPU (same day).** It was the last thing dragging the frame back
to the host: `pixels_now()` and `upload()` ran on *every* present while it was on, 1.30 ms of CPU and
20 MB each way per present at 4x, and it cost 18-26 presents a second. The font is a grid of 5x7
filled squares, so text needs no texture at all — `overlay::text_rects()` returns the same rectangles
`draw_text()` would stamp, and the presenter draws them as solid quads in the pass that shows the
frame anyway (`shaders/overlay.vert`/`.frag`, a second pipeline sharing the presentation pipeline's
push constants, so a rectangle lands over exactly the picture pixel it covers). Measured, exclusive
fullscreen at 4x, 16:9, `--sh4-clock 400`, `--present-rate 120`:

| counter | opening 3D | menus |
|---|---|---|
| stamped into a host copy (before) | 93.6 presents/s | 99.1 |
| drawn on the GPU (after) | **111.6** | **119.8** |
| counter off, for comparison | 111.6 | 119.8 |

The counter is now free: the present path reports `upload 0.00 ms` and the picture rate with it on is
identical to the rate with it off. The F1 binding screen still composites on the host, because that
screen is a full-window panel and the game is stopped while it is up. `--present-cpu` and the
`DREAM_PRESENT_CPU` comparison are unchanged: that path still stamps, so the two paths remain
byte-comparable. A unit test pins the two paths together — painting `text_rects()`'s rectangles must
reproduce `draw_text()`'s pixels exactly.

**The launcher now offers the rates the display actually has.** A fixed 60/120/144 list is wrong on a
165 Hz panel, where 120 is held for one refresh and then two. `tools/launcher.py` asks Windows for the
primary display's modes (`EnumDisplaySettingsW`) and builds the list from them: each refresh as one
picture per refresh, half of one where that is still at least 60 Hz (72 from 144), and the common
targets 120/144/180/240 so a display that reports only its desktop rate still has the usual choices.
On this machine that is 60, 72, 75, 85, 100, 120, 144, 165, 180, 240; with no display to ask, the old
fixed list comes back. The rows are the rate alone — the divisibility note that explains why the list
is derived lives in the row's help text, not in every label. The interpolation checkbox follows
the same list, a saved rate the display no longer reports stays selectable rather than blanking the
box, and the self-test pins a 165 Hz panel, a 240 Hz panel, the fallback and the `DEVMODEW` layout
(`dmDisplayFrequency` at 184, size 220 — a struct that would be easy to get subtly wrong).

Measured on the same 4,800-frame scripted walk (`--present-rate 120`, windowed, unthrottled):

| | before | after |
|---|---|---|
| strips paired, the 6,530-strip gameplay frame | 4,093 | 6,353 |
| strips the interpolation moves, that frame's 2,041-strip translucent list | 221 | 1,962 |
| shared corners that move apart (guest 4775), worst | 97 px | 0.014 px |
| intermediates drawn | 1,155 | 326 |
| of those, under half matched | 183 | 1 |
| frames repeating a still picture | 0 | 828 |
| presents/s in gameplay, 4x 16:9, rate 120 | 113.5 | 119.8 |
| host time, 4,800 frames | 73.58 s | 74.75 s |

The 828 repeats are still pictures: the scripted walk stands still for most of the run, and a still
picture interpolated is the picture itself. The extra work is ~0.25 ms per interpolated present.

`render/tests/test_interpolate.cpp` gains four cases (a list that shifted by three strips, a list
submitted in reverse order, a shared seam, and the reported motion), each verified to fail when the
mechanism it covers is removed. The render suite is 108 cases (2,020 assertions).

**What is left, and why a rate can still look uneven.** Two things outside this change decide what the
frame-rate counter reads, and both were measured while chasing this:

* The on-screen counter is composited in the presenter's staging buffer, which needs the frame on the
  host: `pixels_now()` reads 20 MB back and `upload()` sends 20 MB out **per present** — 1.30 ms of
  CPU per present at 4x, against 0.00 ms when it is off, and it costs about ten presents a second.
  Drawing the counter on the GPU (its font is 5x7 rectangles, so it is a handful of solid quads) is
  the fix, and it is a presenter change, not an interpolation one.
* A 165 Hz panel cannot show 120 pictures a second evenly: 1.375 refreshes per picture means pictures
  are held 1 refresh and then 2, "so motion judders however fast the game is running", as the engine
  already says at startup. With interpolation on, the even rates are the refresh itself (165) or half
  of it; at 165 the app holds 141-146 presents a second in the densest scene with the counter off, and
  the rest of the way is the cost of rasterising 5,400 strips at 5 megapixels twice per guest frame.
  Exclusive fullscreen is the one mode that can pick a 120 Hz display mode for an even 120 (`patch
  031`), and borderless cannot.

**Measured hold pattern (2026-11-16, after a report that 60 fps feels smooth but 120 does not).** The
pacing trace now histograms how long each picture actually stayed on the panel, in refreshes, which is
the thing the eye judges and which no averaged rate can express. 165 Hz panel, `--scale 2`, 16:9,
2,400 frames of the scripted walk:

| requested | pictures held 1 / 2 / 3 / 4+ refreshes | picture rate | cadence |
|---|---|---|---|
| 60, no interpolation | 0.2 % / 1.8 % / **97.5 %** / 0.2 % | 55 Hz | **even** — three refreshes every time |
| 120, no interpolation | **50.0 % / 49.8 %** / 0.1 % | 110 Hz | uneven: 6 ms and 12 ms holds alternate |
| 120, interpolation | **44.5 % / 55.2 %** / 0.1 % | 106 Hz | uneven, the same mixture |
| 165, interpolation | **88.3 % / 11.4 %** / 0.1 % | ~148 Hz | nearly even; the app misses one vblank in nine |

So the report was right and the reasoning behind it was not: asking for 60 does *not* produce the
2.75-refresh mixture the arithmetic predicts. The app is slightly late every frame, so the display
holds each picture for three refreshes and the cadence is **even at 55 pictures a second** — slower,
but steady. Asking for 120 lands half the pictures on one refresh and half on two, which is the worst
mixture available: every other picture flashes past in 6 ms. That, and not the average rate, is what
"120 does not feel smooth" describes. The even choice on this panel is the refresh itself; 82.5 (two
refreshes) would be even as well but `--present-rate` is whole-number only, so it is not expressible.
A 120 Hz display mode would make both 60 and 120 whole numbers of refreshes (two and one), which is
why `--display exclusive` is worth trying on this panel, and borderless cannot change the mode.

**Exclusive fullscreen is the mode that can be even, and it is — when the rate is affordable.** The
same measurement in exclusive fullscreen (the engine picks a 120 Hz mode for a 120 Hz request and a
165 Hz one for 165), 1,700 frames reaching the opening 3D scene, `--scale 4`, 16:9:

| exclusive, 4x, opening scene | presents/s | pictures held 1 refresh | cadence |
|---|---|---|---|
| 120 Hz mode, counter off | **119.7** | 99.6 % | even |
| 120 Hz mode, counter on | 111.5 | 97.2 % | nearly even |
| 120 Hz mode, counter on, `--sh4-clock 400` (the reported settings) | 93.6 | 88.3 % | uneven again |
| 165 Hz mode, 165 requested, counter off | 126.8 | 73.2 % | uneven: 4x cannot hold 165 |
| 165 Hz mode, 165 requested, counter on | 101.0 | 51.1 % | the worst mixture |

Two things follow. The counter is worth 18-26 presents a second at 4x (it reads the frame back and
uploads it again, per present), and 4x cannot hold 165 — so on a 165 Hz panel the even rate is only
reachable by putting the panel into 120 Hz, which exclusive fullscreen can do and borderless cannot.
The launcher now offers 165 and 240 as well, for displays and scales where they are affordable, with
the refresh-divisibility note in the option's help.

**Interpolation does nothing in the opening scene, by design.** The red flyby moves less than a pixel
a frame, so every one of its frames reports `0 px now` and is repeated rather than redrawn — 196-449
repeats and *zero* intermediates in every run above. It is the worst place to judge the option: it
engages where there is motion (337 intermediates in the scripted walk), and it cannot raise the rate
in any scene, because each extra picture is a full extra render at the same resolution.

Carried by `patches/0004-frame-interpolation-pairing.patch`, which applies after 0001-0003. It
touches `render/{include,src,tests}` and `runtime/boot/boot_main.cpp`; the diagnostics it adds are
`DREAM_INTERP_PAIR` (the two frames behind an interpolation, as text) and a comma list for
`DREAM_INTERP_DUMP`, and F11's frame capture now writes the presented intermediate frame plus a
`.interp` geometry dump when that is what is on screen.

## Patch 040: the boot program comes from the disc (2026-11-16)

A release cannot carry `1ST_READ.BIN`. It is 2,339,580 bytes of the game's own executable, the
project's rule is that no extracted disc file is published, and the runtime used to stop at
`cannot read .../extracted/fs/1ST_READ.BIN` without it. The bytes are on the disc the player already
has, so the runtime now reads them there.

`[disc] boot_lba` and `boot_size` record the location: LBA 547,857 in this dump's track05, 1,143
sectors of 2,048 user bytes (the last one partial). `load_boot_image()` still prefers the extracted
file when it exists, so the development build is unchanged, and otherwise reads the sectors through
`Disc::read_user`, which already unwraps mode-1/mode-2 headers and works the same for a GDI and a
CHD. The result is checked against `sha1_1st_read` before it is copied into guest RAM: a wrong disc
now fails with one line naming both hashes instead of faulting inside translated code. The config's
hash was already there for the translator; this is its first run-time use.

`--disc FILE` overrides `[disc] image` for one run, so a launcher can point the game at the dump the
player picked without rewriting the title config, and a read-only install stays possible.

Verified on the retail dump: a 600-frame headless run (`--rtc-seed 1000000`) writes the same
`--write-hash` file — `212f28f1…`, byte for byte, 603 lines — whether the boot program comes from the
extracted file, from the GDI, or from the CHD (the last two with the extracted file renamed away).
Both disc sources print `boot program: 2339580 bytes from the disc at LBA 547857`. A wrong `boot_lba`
and a missing boot location exit 2 with one line (the hash mismatch names both hashes), a non-disc
`--disc` is refused before the read, and the SHA-1 implementation matches the standard vectors and
the boot file's known `936ef49f…`. The translator's config suite is green (16 cases, 125 assertions),
including the new both-fields-or-neither case.

Carried by `patches/0005-boot-from-disc.patch`, which applies after 0001–0004. It touches
`runtime/boot/boot_main.cpp`, adds `runtime/include/dream/runtime/hash/sha1.h`, extends
`translator/{include,src}/.../game_config.*` with the two fields, adds the config test, and documents
both in `docs/game-config.md`.

## Patch 041: UTF-8 paths on Windows (2026-11-16)

The player picks the disc and the release lives wherever they unpacked it, so paths are not
guaranteed to be ASCII. Windows' narrow `main(char**)` and `std::ifstream`/`std::fopen` interpret
bytes as the active ANSI code page, while SDL and the Python launcher pass UTF-8. On a profile such
as `C:\Users\José` that silently broke the config, the selected disc, the bindings file, the VMU and
every debug output.

`boot_main` now enters through `wmain` and converts each UTF-16 argument to UTF-8 once. All
runtime paths stay UTF-8 at the boundary: `[disc] image` and `[binary] path` are resolved with
`std::filesystem::u8path`, `--disc`/`--config`/`--vmu`/`--bindings` go through the same
conversion, and the debug outputs (`--report`, `--wav`, `--dump-*`, `--write-hash`, `--write-log`)
open through a UTF-8 `fopen`. The GDI and CDI readers use `_wfopen`, the CHD reader opens the file
wide and hands the `FILE*` to `chd_open_file` (libchdr never closes it), and the memory card stores
a `std::filesystem::path` rather than a lossy ANSI string. The config loader's relative
`disc.image`, `binary.path` and `symbols` joins use `u8path` too.

Verified with a hard-linked retail CHD under `work\utf8-test\Draconus-测试-é`: the run read the
config, the CHD, created and then re-opened a `card-é.vmu`, and wrote `out-é.wav` and
`report-é.txt`, printing `boot program: 2339580 bytes from the disc at LBA 547857` and exiting 0.
A second run with `[disc] image = "Draconus-测试.chd"` and no `--disc` also booted from the disc.

Carried by `patches/0006-utf8-paths.patch`, which applies after 0001–0005. It touches
`runtime/boot/boot_main.cpp`, `runtime/src/gdrom/disc.cpp`, `runtime/src/maple/maple.cpp`,
`runtime/include/dream/runtime/maple/maple.h` and `translator/src/config/game_config.cpp`. The
translator's own command-line path handling is unchanged; a source build under a non-ASCII checkout
path is a separate build-tooling task.

## Patch 042: one per-user folder (2026-11-16)

The game and the launcher wrote three separate per-user folders: the launcher's settings in
`%APPDATA%\DraconusRecomp`, the memory card in `%APPDATA%\dream-recomp\saves\draconus`, and the
controller bindings in `%APPDATA%\dream-recomp\dream-recomp`. The nested last one came from
`SDL_GetPrefPath("dream-recomp", "dream-recomp")` — SDL joins organisation and application, so the
engine's name appeared twice. A player looking for their bindings, or for what the launcher had
saved, had three places to search, and the launcher's **Open settings folder** button showed only one
of them.

Everything now lives under the engine's per-user root, `%APPDATA%\dream-recomp`:
`launcher.json`, `bindings.txt`, and `saves\<game id>\vmu_a1.bin`. The card already used
`host_data_dir()`. `default_bindings_path()` now asks SDL for an application-only folder,
`SDL_GetPrefPath("", "dream-recomp")`; with no organisation SDL builds `<data>/dream-recomp/` on
Windows, macOS and Linux alike, which is the same root the card uses. The launcher's settings move in
`tools/launcher.py`, which reads the old `%APPDATA%\DraconusRecomp\launcher.json` when the new file
does not exist, so an upgrade keeps its choices; the next save writes the new path.

Carried by `patches/0007-user-data-folder.patch`, which applies after 0001–0006 and touches
`render/src/vk/window.cpp`. Verified by building `draconus_boot` and `dream_render_view`, by the
launcher's `--selftest`/`--smoke`, and by calling SDL3's `SDL_GetPrefPath("", "dream-recomp")`
directly on this machine: it returns `C:\Users\<user>\AppData\Roaming\dream-recomp\`, the same root
`host_data_dir()` uses for the card.

## Patch 043: `--present-rate` is validated (2026-11-16)

`--present-rate` was parsed with `std::strtoul` and cast straight to `unsigned`, with no range check.
A negative argument (`--present-rate -5`) wrapped to a huge unsigned rate, and any number was accepted
even though the display cannot show it; the run then capped it silently or behaved unpredictably. The
parser now uses `std::strtol`, rejects trailing characters, negatives and anything above 1000 Hz, and
prints a usage line and exits 2 — the same fail-closed pattern as `--sh4-clock`. `0` still means the
default of one present per guest frame.

Carried by `patches/0008-present-rate-bound.patch`, which applies after 0007 and touches
`runtime/boot/boot_main.cpp`.

## Patch 044: the widescreen overlay pass stops at the HUD's depth (2026-11-16)

Reported from play at 16:9 in three F11 captures: the item model at the left of the HUD was a quarter
too thin, the death screen's background was torn into vertical strips, and a map marker sat slightly
off. All three are one pass.

`compress_screen_overlays` squeezes screen-space overlays by (4/3)/aspect so the presenter's stretch
does not make them 4/3 too wide. Three faults:

* **The panel test had no upper depth bound.** A large flat quad was a HUD panel if it was at least
  half the world's near depth. The death screen's black fade is six quads at `z` 32700 and its skull
  image one 384x384 quad at 32701 — 4,600 times the near depth — so each fade quad became a panel
  and was compressed about its own anchor (left, centre, right). The six tiles no longer met: the
  fade covered x 0-96, 176-368 and 448-640, and the world showed through the two gaps. The map art
  at `z` 23999 was a panel for the same reason. The test now requires the near slab,
  `world_z * 0.5 <= lo <= world_z * 4`: the item wheel is 0.65-0.89 of the near depth and the pause
  menu's splash 1.36, while an overlay depth is thousands of times it.
* **A panel's contents were compressed twice.** The rotating item model inside the wheel takes only
  its *scale* from the title's projection (the widened projection squeezes it by the same factor),
  but its *place* is the wheel's centre, which the game sets in screen space; scaling it again about
  the panel's anchor left the HUD item 25 % too thin. The model is now moved by as much as the
  panel's centre moves — `(factor - 1) * (centre - anchor)` — and keeps its already compressed
  width, so it stays centred in the wheel at its 4:3 size. The wheel graphic itself (the panel quad)
  is compressed as before. The first cut of this moved the model by the *projection's* centre
  instead, which put the item against the screen edge, outside the wheel it belongs to: a 16:9 F11
  capture of the open wheel showed the vial at the left border with the wheel's middle empty.
* **A small element inside a bigger one kept its own anchor.** The map's destination markers are
  32x32 quads at `z` 25000 inside the 384x384 map image at `z` 23999. The map was a panel and was
  removed from the element grouping, so each marker fell back to "a small glyph stays centred on
  itself" and stayed put while the map shrank: up to 30 guest pixels off (the map's right-hand
  marker). With the map no longer taken as a panel it is grouped with its markers, and the union's
  centre is the anchor for all of them.

Verified on the three captures with `dream_render_view --aspect 16:9`, which applies the same pass:
299/27/301 polygons compressed against 299/39/301 before. The death frame's replay is now a clean
black fade with the skull and text (the twelve fade quads are untouched, the skull shrinks about its
centre); the map's markers move with the map; the HUD item keeps its 4:3 width (22 pixels of glass,
against 17 before, where the authored 4:3 frame measures 22) and stays centred in the wheel. The
render suite gains three cases — a fade that must not tear, a map whose markers must follow it, and a
panel model that must keep its width — and passes 113/113 (5,124 assertions).

## Patch 045: a translucent strip sorts by its mean depth (2026-11-16)

"The grating beneath the minotaur shows through his model." The arena floor is one large translucent
strip (`z` 0.147-0.277 across its vertices) and the minotaur's skirt is translucent too (0.25-0.30).
The translucent pass sorted strips back to front by the *nearest* vertex, which for a floor is its
near rim: 0.269, a hair in front of one skirt strip's 0.2678. The floor was drawn after that strip
and its bars were blended over the skirt.

The key is now the mean of the strip's vertices — 0.21 for that floor — which is behind every skirt
pixel that overlaps it. Nothing else about the pass changes: the same back-to-front order, depth test
and no-depth-write. Across the death, map and arena captures the change moves 900-1,100 pixels and
no more, and the grate's bars no longer cross the character. It does not make intersecting
translucency correct — that remains the documented per-strip limitation — but a large surface under
a character is the common case and the mean decides it.

Carried by `patches/0009-widescreen-overlay-depth.patch` (entries 044-045), which touches
`render/src/display_list.cpp`, `render/include/dream/render/display_list.h`,
`render/src/vk/renderer.cpp` and `render/tests/test_display_list.cpp`, and applies after 0008.

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
