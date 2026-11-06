# 10 — First coding task, and what comes next

## The first task (implemented: M1)

**`tools/draconus-disc` — a dump validator and extractor.**

It was chosen because it is needed by everything downstream, has a binary pass/fail,
and repairs the exact defects found during reconnaissance.

### What it does

* Parses the `.gdi`, builds a track map, and resolves every read through the correct
  track (the filesystem spans tracks 3 and 5; audio reads are refused).
* Finds the *largest* ISO9660 volume among the data tracks — the low-density session is
  a licence volume with no executable.
* Walks ISO9660 with strict, auditable framing:
  * records may not cross a sector boundary;
  * zero-length records pad the rest of a sector;
  * a directory that declares more space than it uses stops at the first invalid
    sector and is reported as a **truncation** (normal on this disc), while a genuine
    mid-sector anomaly is reported as a **resync** (never silent).
* Scans `DIRENT.DIR` — the engine's own index — with structural validation and
  de-duplication, and reports the extension histogram.
* `verify` fails closed unless the boot program has the expected size and SHA-256.
* `extract` writes the boot program (and optionally the ISO tree) only after the hash
  check passes.
* `manifest` emits the full inventory as JSON for later diffing.

### Acceptance tests (all passing)

| Test | Result |
|---|---|
| Boot program extracted with `a59ff87c…` | pass (`dracdisc verify`) |
| Extraction byte-identical to the engine's `dcdisc` | pass |
| Multi-sector raw reads stride over sector headers | pass (regression test) |
| ISO walk: 0 resync events on the retail dump | pass |
| `1,000`-case malformed-record fuzz never crashes or desyncs | pass |
| Audio-track user-data read rejected | pass |
| Overlapping/mismatched track maps rejected | pass |
| Synthetic multi-sector directory with padding still parses | pass |

Run: `python -m unittest discover -s tests` → `OK (15 tests, 1 skipped)`.
The skipped test is the real-dump check; set `DRACONUS_DISC` to run it.

### Measured output

```
ISO9660 volume 'DRACONUS1' at base LBA 45000; 3690 files in 60 directories,
936.6 MB; 0 resync event(s), 0 declared-extent truncation(s)
boot: 1ST_READ.BIN LBA 547857 size 2339580 sha256 a59ff87c…4567da
DIRENT.DIR @LBA 547529: 3713 records (3653 files, 946.1 MB)
```

## The next task (M2)

**Prove the engine can translate this game, or find out early that it cannot.**

1. Add `games/draconus/draconus.toml` with the verified addresses
   (`load 0x8C010000`, `link 0x0C010000`, `entry 0x8C010000`).
2. Run the translator on the hash-verified boot program; record the coverage line
   verbatim.
3. Build with the development interpreter and run headless to the first gap; record the
   address.
4. Run `--suggest-config`, fold the seeds back in, rebuild, and measure again.
5. Write the numbers into `docs/07-ROADMAP.md` under M2 and decide go/no-go.

**Exit criteria:** coverage reported, first gap identified, one seeding round done,
second run reproducible, and a written go/no-go against ADR-0001.

## What not to do next

* Do not start asset decoding (`.IMG`, `.PFE`) before the game runs; there is no way to
  validate a guessed format yet.
* Do not start the launcher before M4; the input binding layer needs real game input to
  design against.
* Do not "fix" engine files in place — patches only, recorded in the ledger.
