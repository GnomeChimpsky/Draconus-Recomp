# 18 — Character LOD: what it is, and what has been ruled out

The game draws non-player characters at reduced geometric detail at short range: beyond
roughly six world units the body, cloak and armour break into a scatter of stretched
triangles, and walking up to the character restores the full mesh. The same behaviour is
present on the retail disc in Flycast, and the recomp reproduces it faithfully — replaying
an `F11` bundle through `dream_render_view` gives the captured frame back.

This document records what was measured, what was tested and rejected, and where the
remaining work would start. It is deliberately pessimistic: five mechanisms were proposed
and each was falsified by a test, so the summary is a list of things that are *not* the
cause.

## What the captures show

Three `F11` captures taken at increasing distance, plus a pair taken either side of the
"it looks right now" point:

| capture | guard distance | triangles | appearance |
|---|---|---|---|
| `capture-000` (00:13) | ~7.5 units | 95–104 | broken |
| `capture-001` (00:13) | ~4.8 units | ~480 | correct |
| `capture-000` (01:03) | ~7.5 units | 95 | broken |
| `capture-001` (01:04) | ~3.5 units | 657 | correct |

Depth-shading only the far guard's triangles (`work/lod_shape.py`) shows a coherent figure —
hood, shoulders, cloak, sword — rather than degenerate geometry. The "corruption" is the
character's textures stretched over far fewer triangles; the fine armour and weapon layers
are simply not present in what is submitted.

Triangle areas in guest pixels, for the same character far and near:

| | triangles | median area | under 0.5 px² | under 1 px² |
|---|---|---|---|---|
| far (~7.5 units) | 104 | 4.57 | 30 (29%) | 34 |
| near (~3.5 units) | 657 | 3.67 | 62 (9%) | 112 |

There is no size floor, so nothing is being culled by projected area. The far model is
proportionally much richer in degenerate slivers, which is what a collapsing vertex set
looks like: triangles shrink to nothing and the hardware drops them, leaving the large ones
as shards.

## The assets

The level bundles are zlib-chunked containers whose contents are partly plain text. Model
data is text with one token per line:

```
vert <x> <y> <z>
wedge <index>
txtcoord <u> <v>
normal <x> <y> <z>
color <r> <g> <b> <a>
detail <min> <max>
lodstart <int>
chunkend
```

Every `lodstart` on the disc is `INT_MAX` (9130 occurrences, 8914 exactly `2147483647`), so
the per-wedge LOD start is disabled in the shipped data. `detail` is `0 65535` for
essentially every wedge. The character attributes are class-level and include
`LOD_DISTANCE_MODIFIER`, `LOD_EXTENT_MODIFIER`, `VISIBLE_DISTANCE` and `ACTIVE_DISTANCE`;
character templates (`.att`) live inside the level bundles (`KRUJEN.att`, `MINO.att`, …).
`tools/dracdisc` and `work/unimg2.py` are enough to unpack a bundle; `work/dump_chunk.py`
prints a chunk as text.

## What was ruled out

1. **A second, coarse mesh selected by distance.** The per-texture triangle counts step
   together (body, cloak, armour) at the same frames, but the counts *climb back gradually*
   after every drop (61 → 168 → 170 → 178 …), which is a character leaving and re-entering
   view, not a mesh swap. A real swap steps and holds; nothing in the recordings steps and
   holds. Both vertex-setup callers (`fn_0c1630e4`, `fn_0c187b1c`) show identical calls and
   arguments across the candidate frames.
2. **Per-wedge size culling.** The far model still contains 30 sub-half-pixel triangles, so
   no size threshold is dropping them.
3. **The `0.01` wedge/vertex test.** `fn_0c1630e4` skips geometry when a per-vertex float is
   below the constant at `0x0C163348` (0.01). Patching that constant to `-1.0` with
   `--patch`, so the test can never fire, leaves the per-frame triangle counts
   **byte-identical**. The tested float is written by the 4×4 transform in `fn_0c174b04`,
   i.e. it is a clip/w coordinate: the test is near-plane vertex rejection.
4. **The `3 → 2` counter.** `DREAM_WATCH_WRITE=0x0C29A950:4` showed the word is a buffer
   rebuilt every frame by a loop at `0x0c01a686` (values 0, 1, 2, 3 …), not a state flag.
5. **The transform setup as the selector.** The 296-byte block at `0x8C28A484` is filled by
   a `memcpy` (`fn_0c175920`) from `0x0c164a38`; it is per-part scratch rebuilt from the
   model each frame.

Also noted and not pursued: a float compare against `100.0` in `fn_0c187b1c`'s neighbourhood
(a visibility cutoff) and a `6.0` clamp in `fn_0c0b1f22` (a lerp/clamp, not a distance test).

## Tools built or found for this

| tool | what it does |
|---|---|
| `DREAM_TRACE_TEXTURE=<tcw>` | one line per render with the polygon count for that texture — the per-frame detail signal. Added to `engine/runtime/boot/boot_main.cpp`, env-gated, no effect unless set. |
| `DREAM_WATCH_WRITE=addr[:len]` | already in the engine: logs every guest store into a range with the writing PC, PR, r15 and frame. |
| `DREAM_TRACE_INSNS=lo:hi:FILE` | the interpreter single-step tracer; with `DREAM_TRACE_FROM/TO` (cycles) it records registers for a narrow window. Translated code only carries the call if generated with `--trace-insns`. |
| `--patch ADDR=VALUE` | guest-memory poke, applied at boot (and each vblank in a windowed run). |
| `--replay-input FILE` | deterministic replay of a recorded pad stream. |

Scripts in `work/lod/`: `lod_inspect.py`, `lod_clusters.py`, `lod_pertex.py`, `lod_areas.py`,
`lod_shape.py`, and the trace/dump parsers (`lod_steps.py`, `lod_sweep.py`, `insn_args.py`,
`callers.py`, `lod_rdiff.py`). The analysis notes in this file are reproducible from those.

## Replays

* `work/keep.rec` — a recorded run to the keep hall. The guards in it stay at fixed
  distances (one ~2–3 units, one ~7–8 units), so it contains **no LOD transition**.
* `work/cross.rec` — `keep.rec` with a synthesised back-away-and-return appended
  (frames 6190–6500). Backing away moves the guard from ~3 to ~8 units and the triangle
  count falls smoothly 292 → 137 with no step.

## The debugger, and what it found (2026-11-23)

There is no interactive debugger on this machine, but the development interpreter decodes every
instruction itself, so a breakpoint can live inside it. `DREAM_DEBUG_PC=0xADDR[:N]` (with
`DREAM_DEBUG_FROM` to ignore hits before a guest cycle) prints `r0..r15`, `pr`, `sr`, `fr0..fr15`
and the XF bank — the bank `ftrv` multiplies by, so a skinning matrix is readable — when that
guest instruction is about to run. Addresses are masked to the P0 alias.

The first thing it settled: **the LOD is a vertex count, and the count is distance-dependent.**

| breakpoint | near (~frame 6120) | far (~frame 6290) |
|---|---|---|
| `0x0c174b04` (transform entry), part `8CC6CB40` | `r5 = 0x1E` (30 vertices) | `r5 = 0x0A` (10 vertices) |
| `0x0c174b04`, part `8CC526A0` | `r5 = 0x0B` (11) | `r5 = 0x04` (4) |
| `0x0c163262` (draw loop), `r13` | `0x11` (17) | `0x07` (7) |
| `0x0c160e1a` (chunk loop), `r11` | `0x200` (512) | `0x16F`, `0x126`, `0x34`, `0x0A` |

So the same part is transformed with a third of its vertices when the character is far away.
The count is passed down the draw chain: `fn_0c164660` (parts loop) → `fn_0c160c3c` (per-part
draw, takes the part, the vertex source, a matrix and a flag word, plus stack arguments) →
`fn_0c174b04` (XMTRX + `ftrv`, loops `r5` vertices). The count is a stack argument to
`fn_0c160c3c` and arrives in `r5` at the transform.

Inside `fn_0c160c3c` the count is a **byte length**: at `0x0c160d34` it computes
`r11 = r12 - r10` (end pointer minus start), then scales it with `shad` (shift by `-5`).

Measured at `0x0c160d36`, start/end for the same part:

| frame | start | end | length |
|---|---|---|---|
| near (~6120) | `8CDF6060` | `8CDFA060` | **0x4000** (16384 B) |
| far (~6290) | `8CE180E0` | `8CE1AEC0` | 0x2DE0 (11744 B) |
| far | `8CCC2340` | `8CCC29C0` | 0x0680 (1664 B) |
| far | `8CC8A620` | `8CC8A760` | **0x0140** (320 B) |

So the LOD walks a **prefix of the part's vertex data**, and the prefix shrinks with distance:
16 KB at 3–4 units against 320 bytes beyond the threshold. That is the whole effect — a range
end pointer, not a blend and not a second mesh.

This reframes the fix: it is not a blend factor to disable but a **data-length clamp**, so the
candidate patch is wherever that end pointer (or the shift that scales it) is chosen from the
distance — a comparison, not a scale.

The clamp itself is five instructions at `0x0c160d24`:

```
0x0c160d24: r0  = 0x4000        ; chunk size, 16 KB
0x0c160d26: r12 = r10           ; end = start
0x0c160d28: r2  = *(r14+4)      ; r2 = the part's data end (stack argument)
0x0c160d2a: r12 += 0x4000       ; end = start + chunk
0x0c160d2c: cmp/hi r2, r12      ; if end > limit ...
0x0c160d2e: bf 0xc160d32        ;   keep it
0x0c160d30: r12 = r2            ; else end = limit
0x0c160d32: r11 = r12 - r10     ; length = end - start
0x0c160d3e: r11 = shad(r11, -5) ; count = length scaled
```

So the per-part walk is `min(start + 0x4000, limit)`, and the distance changes the **`limit`**
stack argument: it is the part's data end. Near it lies at least a full 16 KB chunk ahead of the
start; far it is only 320 bytes ahead. That argument is built by the caller `fn_0c164660`, which
is the remaining hop — the clamp is known, the producer of `limit` is not.

Measured at `0x0c160d28`, where the limit is loaded (`stack[1]`, with `r14 == r15`):

| | start (`r10`) | limit | limit − start |
|---|---|---|---|
| near (~6120) | `8CDF6060` | `8CE0F5E0` | 0x19580 — 103,808 B (the full part) |
| far (~6290) | `8CE180E0` | `8CE1AEC0` | 0x02DE0 — 11,744 B (11% of it) |

So the LOD is a **fraction of the part's vertex data**: the whole model up close, about an
eighth of it beyond the threshold. The two call sites that push the limit are `0x0c164ae2` and
`0x0c164b5e` in `fn_0c164660`; the value is not in any register sampled at those sites, so it is
read through one of the pushed pointers rather than computed in a register there.

## Where the remaining work starts

The evidence points at a per-vertex collapse: vertices blend toward a point as distance
grows, triangles degenerate, and the hardware drops them. The draw path consumes the result,
which is why every test in the draw and clip paths came back negative.

The next probe is on the **source** side of the vertex build: find where a model-space
vertex is blended toward the collapse point before the matrix transform. The transform setup
is `fn_0c174b04` (loads XMTRX and does `ftrv`), called from `fn_0c160c3c`; the input vertex
stream and the bone matrices it multiplies are the places to watch. A real debugger session
with hardware breakpoints on the vertex buffer (x64dbg against `draconus_boot.exe`, using
the symbols in `draconus_boot.map`, where `fn_0c1630e4` resolves to `0x140622a90`) would be
the direct route.

A cheap alternative has not been tried: patch the *distance* the engine uses for the
character (not found), or the model's `.att` `LOD_DISTANCE_MODIFIER` if the loader can be
made to read a larger value.
