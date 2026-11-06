# Engine changes ledger

Engine source lives in `engine/` (a pinned copy of `phobos665/dream-recomp`, GPL-2.0).
It is **not hand-edited**: every change is a minimal patch recorded here, so it can be
offered upstream and so an engine update can be re-applied deliberately.

| # | Date | Version | File(s) | Why | Upstreamable |
|---|---|---|---|---|---|
| 001 | 2026-11-05 | dream-recomp 0.1.0 (`main` @ 2026-10-29) | `runtime/boot/boot_main.cpp` | `--present-mode` referenced `dream::render::vk::Window::PresentMode` outside `#ifdef DREAM_WITH_RENDERER`, so **any** renderer-free build of a title's launcher failed to compile (`C3083`/`C2039`). Guarded the option; a renderer-free build now prints an error instead. | yes — bug fix |
| 002 | 2026-11-06 | same | `runtime/src/sh4/abi_bare.cpp` (`call_indirect`), `runtime/src/system.cpp` (`on_rte`), `runtime/src/devinterp/interpreter.cpp` | Diagnostic only: `DREAM_TRACE_HOOK=1` logs every dispatch into the hook page and every `rte` with `spc`/`frame_pc`/`r15`/`frame_sp`/`sr`/`ssr`. Off unless the variable is set; no behaviour change. | no — local aid |
| 003 | 2026-11-06 | same | `runtime/src/devinterp/interpreter.cpp` (fetch loop), `runtime/src/system.cpp` (`on_untranslated`) | **Fixes the `0x8C001006` fault.** A hook marker has no guest code, but the interpreter only dispatched hooks on call/jump transfers, so control arriving *on* a marker (a task resumed on the GD-ROM vector after a scheduler switch) fetched `0xFF` as an instruction. The fetch loop now dispatches an exact entry inside `[native_lo, native_hi)`; `on_untranslated` declares the BIOS hook page as that range. | yes — bug fix |

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

## How to update the engine

1. Re-download the pinned commit into a scratch directory.
2. Diff against `engine/` and re-apply the entries above.
3. Record any new local changes here before building.
4. Re-run the M1/M2 acceptance checks.
