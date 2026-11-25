# 19 — Debugging the character LOD, step by step

This is a hands-on guide for the next person who picks up the character LOD. It assumes
Windows, PowerShell, and this repository. Every command below is meant to be pasted as-is.
Each step says what you should see; if you do not see it, the step says what to check.

The bug: a character drawn near the camera uses its full mesh; beyond a few world units the
game submits far fewer vertices (measured: 30 → 10 for the same part), the remaining triangles
degenerate, and the character looks shattered.

**What is already known**, so you do not repeat it:

* The LOD is a **vertex count**, passed down the draw chain and spent by the transform
  `fn_0c174b04` (loads XMTRX, `ftrv`, loops `r5` vertices).
* These have been tested and **disproved** — do not start here: a second coarse mesh; a
  per-wedge size cull; the `0.01` vertex/clip test at `0x0C163348`; the `3 → 2` word at
  `0x0C29A950`; the transform setup at `0x8C28A484`; the clamp at `0x0C160D24`; the object
  list at `0x8C28ADD8`; the radius/factor array; the part record at `0x8CC6CB40`.
* The remaining unknown is **who computes the count** and passes it as the stack argument to
  `fn_0c160c3c`.

---

## Step 0 — Reproduce the bug deterministically

From the repository root:

```powershell
cd 'G:\Spel\ROMS\Dreamcast\Draconus'
$exe = '.\engine\build-render\games\draconus\draconus_boot.exe'
$a = @('--config','engine\games\draconus\draconus.toml','--vmu','work\lod\card.vmu',
       '--replay-input','work\cross.rec','--rtc-seed','1000000','--max-frames','6540')
& $exe @a
```

`work\cross.rec` is a recorded run to the keep hall with a synthetic back-away appended. The
player is next to a guard around frame 6190 and backs away until about frame 6400. The run is
deterministic: same frames, same behaviour, every time.

Check the bug is present with the texture counter:

```powershell
$env:DREAM_TRACE_TEXTURE='c80d39d0'
& $exe @a 2>$null | Select-String '^tex frame'
Remove-Item Env:\DREAM_TRACE_TEXTURE
```

You should see the guard's body polygon count **fall from about 280 to about 140** as the
player backs away, then climb again on the way in. That is the bug.

---

## Step 1 — Set a breakpoint in the guest

The engine has a breakpoint built in: `DREAM_DEBUG_PC` makes the *interpreter* stop at a guest
address and dump the CPU state. It only works with `--interpret` (the translated build uses
`DREAM_TRACE_INSNS` instead, which needs a regenerated translation).

```powershell
$env:DREAM_DEBUG_PC='0x0c174b04:3'
$env:DREAM_DEBUG_FROM='20200000000'
& $exe --config engine\games\draconus\draconus.toml --vmu work\lod\card.vmu --replay-input work\cross.rec --rtc-seed 1000000 --interpret --max-frames 6230 2> work\lod\try1.err
Remove-Item Env:\DREAM_DEBUG_PC, Env:\DREAM_DEBUG_FROM
Get-Content work\lod\try1.err | Select-String 'debug pc' | Select-Object -First 3
```

**Expected** (abridged):

```
debug pc 8c174b04 cycles 20203548848 ... r5=0000001e ... r13=8c385620 ...
```

`r5 = 0x1E` is the vertex count — 30 vertices. Note `cycles 20203548848`; the interpreter takes
about ten minutes to get there.

**If nothing is printed**, `DREAM_DEBUG_FROM` was later than the run got. Lower it (e.g.
`20100000000`) or raise `--max-frames`.

**If the address is wrong**, note that the guest runs in the P1 mirror (`8c174b04`), which the
hook already handles; keep writing the `0x0c...` form.

---

## Step 2 — See the count change

Same command, far frame:

```powershell
$env:DREAM_DEBUG_PC='0x0c174b04:3'
$env:DREAM_DEBUG_FROM='20750000000'
& $exe --config engine\games\draconus\draconus.toml --vmu work\lod\card.vmu --replay-input work\cross.rec --rtc-seed 1000000 --interpret --max-frames 6385 2> work\lod\try2.err
Remove-Item Env:\DREAM_DEBUG_PC, Env:\DREAM_DEBUG_FROM
Get-Content work\lod\try2.err | Select-String 'debug pc' | Select-Object -First 3
```

**Expected**: `r5=0000000a` — 10 vertices for the same part (`r4`/`r10` = `8cc6cb40`).

That contrast is the whole phenomenon: 30 vertices near, 10 far, same part.

---

## Step 3 — Watch the state that changes

`DREAM_WATCH_WRITE` logs every guest store into a memory range, with the writing PC and the
frame. It works in the fast translated build, so use it without `--interpret`.

```powershell
$env:DREAM_WATCH_WRITE='0x0C28ADD8:16'
& $exe @a 2> work\lod\watch1.err | Out-Null
Remove-Item Env:\DREAM_WATCH_WRITE
(Get-Content work\lod\watch1.err | Select-String '^watch' | Measure-Object).Count
Get-Content work\lod\watch1.err | Select-String '^watch' | Select-Object -First 5
```

**Expected**: many lines like

```
watch: write32 0x8c28add8 = 0x8c59e4c0 at pc 0x0c164812 pr 0x0c164816 r15 0x8c482d5c frame 443
```

The `pc` is the instruction that wrote it. Disassemble around that PC (Step 6) and read what it
computes.

This works for **fixed** addresses. For an address that moves (a stack slot, a heap node), the
watcher cannot help — that is what Step 5 is for.

---

## Step 4 — Break where the count is handed over

The count is an argument to `fn_0c160c3c`, called from `0x0c164ae2` and `0x0c164b5e`, and the
draw function pushes it at `0x0c164ad8`.

```powershell
$env:DREAM_DEBUG_PC='0x0c164ad8:4'
$env:DREAM_DEBUG_FROM='20200000000'
& $exe --config engine\games\draconus\draconus.toml --vmu work\lod\card.vmu --replay-input work\cross.rec --rtc-seed 1000000 --interpret --max-frames 6230 2> work\lod\try3.err
Remove-Item Env:\DREAM_DEBUG_PC, Env:\DREAM_DEBUG_FROM
Get-Content work\lod\try3.err | Select-String 'debug pc|stack:' | Select-Object -First 8
```

The dump prints `r0..r15`, `pr`, `sr`, `fr0..fr15`, the `xf` bank (the `ftrm`/XMTRX matrix),
and the top twelve stack words. `r8` at this PC is the limit about to be pushed.

Use `DREAM_DEBUG_FROM` to land on the frame you want. The cycle clock is roughly
`frame × 3.29e9`; add or subtract `3.29e9` to move a thousand frames.

---

## Step 5 — For an address that moves, use cdb

`cdb.exe` is here:

```
C:\Program Files\WindowsApps\Microsoft.WinDbg_1.2610.1001.0_x64__8wekyb3d8bbwe\amd64\cdb.exe
```

It is a real debugger with hardware watchpoints (`ba w4 <addr>`) and a command interface:

```powershell
cd 'G:\Spel\ROMS\Dreamcast\Draconus'
$cdb = 'C:\Program Files\WindowsApps\Microsoft.WinDbg_1.2610.1001.0_x64__8wekyb3d8bbwe\amd64\cdb.exe'
$exe = '.\engine\build-render\games\draconus\draconus_boot.exe'
& $cdb -g -G $exe --config engine\games\draconus\draconus.toml --vmu work\lod\card.vmu --replay-input work\cross.rec --rtc-seed 1000000 --max-frames 6540
```

At the `0:000>` prompt:

```
ba w4 0x<host-address>
g
```

**The catch, and how to handle it.** The game does not run SH-4 code natively: guest code is
either translated C++ or the interpreter loop. So a guest address is not a host address, and
`bp 0c164ad8` will not work. Two ways around it:

1. **Guest addresses live inside the guest RAM buffer.** Find that buffer once (it is a 16 MB
   host allocation containing the boot image at guest `0x0C010000`), then
   `host = ram_base + (guest & 0x0FFFFFFF)`. An easy anchor is the ASCII string
   `Audio64 Ver 9.0.b.3`, which sits at guest `0x0C0A8229` in this title:

   ```
   s -a 0 L?0x7fffffff "Audio64 Ver"
   ```

   cdb prints the host address where it found the string. Then:

   ```
   ? <found> - 0xa8229
   ```

   is the host base of guest RAM, and a guest address `0x0C28ADD8` becomes
   `<base> + 0x28add8`. Set a watchpoint on that with `ba w4 <base>+0x28add8`.

2. **Use the engine hook instead** (Steps 1–4). For guest-level work it is the better tool: it
   stops at guest addresses, prints guest registers, and is deterministic under the replay. cdb
   only earns its keep when you need a watchpoint on an address that changes per hit.

---

## Step 6 — Read the code around a hit

Quick and dirty (capstone; it mangles FP opcodes, so trust it only for non-FP code):

```powershell
python work\sh4dis_ram.py work\lod\cross6200.txt 0x0c164a80 0x0c164b00
```

Accurate (Ghidra, handles FP correctly). The image has been extracted to
`work\lod\image.bin`; if it is missing, rebuild it from a RAM dump with `--dump`:

```powershell
$gh = 'C:\Users\Lawe\Desktop\ghidra_12.2_PUBLIC\support\analyzeHeadless.bat'
& $gh work\ghidra_proj Draconus -process image.bin -noanalysis `
      -scriptPath work\ghidra_scripts -postScript DumpRange2.java 0x0c160e7c 0x0c160fa4
```

Read `fn_0c160c3c` (per-part draw), `fn_0c164660` (parts loop), `fn_0c174b04` (transform) and
`fn_0c17c400` (divide by 12) — the chain is documented in `docs/18-CHARACTER-LOD-INVESTIGATION.md`.

---

## Step 7 — Try a patch and verify it

Poke a guest word at boot with `--patch` (applies in both translated and interpreter builds):

```powershell
$env:DREAM_TRACE_TEXTURE='c80d39d0'
& $exe @a --patch '0x0C160D30=0x0009' 2>$null | Select-String '^tex frame'
Remove-Item Env:\DREAM_TRACE_TEXTURE
```

Read the counts at frames 6190 (near) and 6360 (far). **If the patch is right**, the far count
stays high (≈280 instead of ≈140) and the picture is correct. If the counts are unchanged, the
patch did nothing — that is what happened with `0x0C160D30`, and it is why it is not in the
game.

**Verification checklist before you believe a patch:**

1. The far frame count at 6360 is close to the near frame count.
2. The image looks right: run windowed, walk up to a guard, back off, return.
3. Other characters and the player model are unaffected.
4. No crashes in `work\lod\*.err` or on stderr.

Once it works, wire it as a boot patch next to the existing widescreen patch instead of passing
`--patch` by hand.

---

## Rebuilding the engine

After editing anything under `engine\runtime\` (for example the debug hook in
`engine/runtime/src/devinterp/interpreter.cpp`):

```powershell
cmd /c '"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1 && cmake --build engine\build-render --target draconus_boot --parallel'
```

The Visual Studio environment is required; without it the build fails with
`fatal error C1083: Cannot open include file: 'cstdint'`.

---

## The one sentence that matters

The count is pushed at `0x0c164ad8`; find the instruction that last wrote `r8` before that, and
you have the LOD.
