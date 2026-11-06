# 01 — Disc forensics

All numbers below were produced by `tools/draconus-disc` against
`Draconus - Cult of the Wyrm v1.000 (2000)(Crave)(US)`, not copied from a database.

## GDI track map

| # | LBAs | Type | Sector | File | Note |
|---|---|---|---|---|---|
| 1 | 0 – 605 | data | 2352 | `track01.bin` | low-density licence volume, `DRACONUS1` |
| 2 | 756 – 1281 | audio | 2352 | `track02.raw` | CD-DA |
| 3 | 45,000 – 67,137 | data | 2352 | `track03.bin` | high-density session start |
| 4 | 67,288 – 67,738 | audio | 2352 | `track04.raw` | CD-DA |
| 5 | 67,889 – 549,149 | data | 2352 | `track05.bin` | ~985.6 MB user data, holds the boot file |

Consequences that shape the tooling:

* **The filesystem spans tracks 3 and 5.** A reader that opens one file truncates
  the image; extents cross LBA 67,137 → 67,889.
* Audio tracks must never be read as user data. `GdiImage.read` refuses.
* Track files are raw 2352-byte Mode 1; user data starts at +16.

## Sessions

**Low-density (`track01`)** — a licence volume, volume id `DRACONUS1`. It contains
only `ABSTRACT.TXT`, `BIBLIOGR.TXT`, `COPYRIGH.TXT`, `WARNING.DA`. **No executable.**

**High-density (`track03` + `track05`)** — the game's volume, also `DRACONUS1`:

* IP.BIN at LBA 45,000: `SEGA SEGAKATANA`, maker `SEGA ENTERPRISES`,
  product `F888 GD-ROM1/1`, dev code `T40203N`, version `V1.000`, date `20000519`,
  region `U`, boot file `1ST_READ.BIN`, company `SEGA LC-T-402`,
  title `DRACONUS CULT OF THE WYRM`.
* Primary volume descriptor at LBA 45,016; L-path table at 45,018; root directory
  at 45,020.

## The boot program

| Property | Value |
|---|---|
| Path in ISO | `1ST_READ.BIN` (root) |
| LBA | 547,857 |
| Size | 2,339,580 bytes |
| SHA-256 | `a59ff87c15b7cff926fc77089ae315cf30905586e34504a18b426d634f4567da` |
| Load address | `0x8C010000` (Katana convention; link view `0x0C010000`) |
| First instructions | `nop` sled → `mov.l @(disp,PC)` → `and`/`or` → `jmp @r2` — a CRT stub, i.e. code at offset 0 |
| Shape | ~1,169,790 16-bit instructions; 7,000 `rts`; 12,909 `bsr`; FPU-class opcodes ≈10.5 % |

`dracdisc verify` fails closed unless this hash matches.

**The file is stored plain, not scrambled.** That matters because a blind
"descramble" pass is a common reflex for Dreamcast boot binaries, and it corrupts
this one: the engine's own `dcdisc` module documents that the BIOS only scrambles
`1ST_READ.BIN` when booting from a CD-R (MIL-CD), and that a GD-ROM stores it in plain
form. Verified here too — descrambling changes ~the whole file and the result faults
immediately, while the plain bytes decode to a coherent CRT stub. The SHA-256 above is
therefore the canonical identity of the supported build.

## Two file inventories, and why

### ISO9660 (authoritative for reachable files)

`3690 files in 60 directories, 936.6 MB, 0 resync events, 0 truncations`

The tree is complete and well-formed. Two reader behaviours are still implemented
because a disc can exercise them, but neither triggers on this dump:

1. **Declared extent larger than content** — if a directory's first record in a sector
   fails validation, the walker stops and records a *truncation* rather than treating
   unrelated bytes as records.
2. **Broken sector chain** — a record that fails mid-sector is reported as a *resync*
   and the walker skips to the next sector. Never silent.

### `DIRENT.DIR` (the engine's own index)

`3713 records / 3653 files, 946.1 MB` — close to the disc capacity, and consistent
with the ISO tree (the difference is duplicates and the index's own copy).

The file is a **memory image** of the engine's directory structure: it embeds live
`0x8C3Dxxxx` pointers and per-directory blocks, so it cannot be walked with a fixed
stride from offset 0. Records are 44 bytes:

```
+0   u8[6]   flags/parent (zero on this disc — used as a scan guard)
+6   u32 LE  first-sector LBA
+10  u32 LE  size in bytes
+14  u8      type (0 = file, 2 = directory)
+15  u8      tag (name checksum; purpose unconfirmed)
+16  char[28] NUL-padded name
```

The reader scans every offset, requires the six zero bytes, a plausible LBA/size, a
legal type and a sane NUL-terminated name, then de-duplicates. This is a heuristic
and is labelled as one; it is why the count is reported with its method.

Extension histogram of the engine index:

| ext | count | ext | count |
|---|---|---|---|
| `.PVR` | 1429 | `.ANM` | 23 |
| `.STR` | 1128 | `.RAW` | 15 |
| `.APM` | 354 | `.IFL` | 10 |
| `.ENT` | 328 | `.TXT` | 8 |
| `.TBB` | 157 | `.ENX` | 5 |
| `.IMG` | 86 | `.FON` | 5 |
| `.TPM` | 74 | `.PFE` | 5 |

## Post-mortem: the multi-sector read bug (fixed 2026-11-05)

The first version of `GdiImage.read` copied `count * 2048` contiguous bytes from a
2352-byte track. Sector 0 was correct; every later sector was the raw stream
(ECC + the next sector's header), so extracted files had their first sector right and
the rest shifted by 304 bytes. Symptoms:

* directory extents appeared "larger than their content" (34 false truncations),
* the ISO tree looked truncated (1,079 files instead of 3,690),
* the boot executable's hash was `86fc4486…` instead of `a59ff87c…`, and it crashed
  the recompiled build after 23 guest cycles while the same dump booted in Flycast.

The fix strides over each sector. It is covered by a regression test, and the
extraction is now byte-identical to the engine's own `dcdisc` output. The lesson is
recorded because the failure mode is unusually deceptive: a file that is 98 % correct
still looks like code to every heuristic.

Remaining small counts: `.DIR`, `.TAM`, `.BIN`, `.DA`, `.DRV`, `.LST`, `.OLD`,
`.SA`, `.SX`, `.WAV`.

## Reproducing

```
python -m dracdisc verify   "<retail .gdi>"
python -m dracdisc inspect  "<retail .gdi>"
python -m dracdisc manifest "<retail .gdi>" -o work/manifest.json
```

`work/manifest.json` records the track map, every ISO entry with LBA/size and SHA-256
(for files ≤ 4 MB), and every `DIRENT.DIR` record. It is generated per dump and is
not part of the source tree.
