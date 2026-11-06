# draconus-disc

Dump validation, ISO9660 inspection and extraction for
**Draconus: Cult of the Wyrm** (Dreamcast, USA, `F888`, V1.000).

Python 3.9+, standard library only. It reads your own dump; it contains no game data.

## Why it exists

This disc is not a single-file ISO:

* the ISO9660 filesystem **spans two data tracks** (03 and 05);
* the low-density session is a small licence volume whose PVD would be found first by
  a naive reader, and it contains **no executable**;
* the engine keeps a second, private file index (`DIRENT.DIR`) that the HLE filesystem
  will eventually have to understand;
* raw 2352-byte sectors carry a 16-byte header and ECC, so **multi-sector reads must
  stride** — copying a contiguous block yields a file whose first sector is right and
  whose later sectors are garbage that still looks like code (this bug cost the
  project a day; see the regression test).

A reader that ignores any of these produces a plausible but wrong inventory. This tool
handles each explicitly and reports what it did.

## Commands

```powershell
python -m dracdisc verify   "<disc.gdi>"
python -m dracdisc inspect  "<disc.gdi>"
python -m dracdisc manifest "<disc.gdi>" -o manifest.json
python -m dracdisc extract  "<disc.gdi>" -o out [--all] [--force]
```

* `verify` — checks IP.BIN identifiers, the boot program's size and **SHA-256**
  (`a59ff87c15b7cff926fc77089ae315cf30905586e34504a18b426d634f4567da`, identical to the
  engine's own `dcdisc` extraction), and that the ISO walk produced no resync events.
  Exits non-zero on any mismatch.
* `inspect` — track map, IP.BIN fields, volume summary, boot hash, `DIRENT.DIR`
  statistics, truncation and resync reports.
* `manifest` — JSON inventory: tracks, every ISO entry with LBA/size (and SHA-256 for
  files ≤ 4 MB), and every `DIRENT.DIR` record.
* `extract` — writes `1ST_READ.BIN` only after the hash check; `--all` also extracts
  the ISO tree; `--force` overrides the hash gate for research on other builds.

## Design notes

### Track model (`gdi.py`)

Every read is resolved through the track map. Reads that fall in an audio track or in a
gap raise `GdiError`; nothing silently returns zeros. Track files may use 2048-byte
cooked or 2352-byte Mode 1 sectors (user data at +16).

### Directory framing (`iso.py`)

* A record may not cross a 2048-byte sector boundary.
* A zero-length record pads the rest of *that sector*; the directory continues in the
  next one.
* If a record is invalid **at a sector start**, the declared extent is larger than the
  content → the directory ends and a `TruncationEvent` is recorded.
* If a record is invalid **mid-sector**, the sector chain is broken → a `ResyncEvent`
  is recorded and the reader skips to the next sector. Resyncs are never silent.

The two event kinds are reported separately because they mean different things: on this
disc, truncations are expected mastering behaviour and resyncs would be a real problem.

### Engine index (`dirent.py`)

`DIRENT.DIR` is a memory image (it embeds `0x8C3Dxxxx` pointers), so it is scanned
rather than walked. A record is 44 bytes:

```
+0   u8[6]   zero guard
+6   u32 LE  LBA
+10  u32 LE  size
+14  u8      type (0 file, 2 directory)
+15  u8      tag
+16  char[28] name (NUL padded)
```

Records that fail validation are dropped, duplicates are collapsed by
`(name, lba, size)`. This is a heuristic and is documented as one; it is not used by
`verify`.

## Tests

```powershell
python -m unittest discover -s tests
```

14 tests, all synthetic (no game data): track maps, audio refusal, gaps, overlapping
tracks, ISO framing, mid-sector padding, sector-crossing records, declared-extent
truncation, a 1,000-case fuzz run that must never crash, and an optional real-dump
check enabled by setting `DRACONUS_DISC`.

## Limitations

* The `DIRENT.DIR` tag byte semantics are unknown; the scanner does not depend on them.
* `--force` bypasses both the size and the hash gate, which is how the prototype build
  (2,182,340 bytes) is extracted. The retail dump is still verified by default.
* `.chd` input is not supported directly (convert with `chdman`, or use the `.gdi`).
* Only the USA V1.000 build is recognised by `verify`; the prototype parses but is
  reported as unsupported.
