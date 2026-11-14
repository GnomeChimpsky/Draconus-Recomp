# Virtual VMUs: saving, loading, and booting into a save

The Dreamcast's memory card is a *visual memory unit*: 128 KB of flash in 256 blocks of 512 bytes,
with the file allocation table in block 254 and the directory chain in blocks 241–253. This packet
speaks that format, so a card made here opens in Flycast (and vice versa) and the game cannot tell
the difference.

| Piece | Where |
|---|---|
| The card device (Maple expansion slot 1, block read/write, write-back) | `engine/runtime/src/maple/maple.cpp` |
| The default per-user card for a windowed run | `engine/runtime/boot/boot_main.cpp` (`default_vmu_path`) |
| Card reader, blank-card writer, save listing | `tools/vmu.py` |
| Launcher tab, save selection, boot-into-save | `tools/launcher.py` |

## Where the card lives

A windowed run with no `--vmu` uses

```
Windows   %APPDATA%\dream-recomp\saves\draconus\vmu_a1.bin
macOS     ~/Library/Application Support/dream-recomp/saves/draconus/vmu_a1.bin
Linux     $XDG_DATA_HOME/dream-recomp/saves/draconus/vmu_a1.bin
          (or ~/.local/share/dream-recomp/saves/draconus/vmu_a1.bin)
```

and creates it, blank and formatted, the first time. `a1` is the hardware address the card answers
on: controller port A, expansion slot 1. `--vmu FILE` (play script: `-Vmu FILE`) still attaches a
specific image; the launcher always passes one explicitly so it can read the saves off exactly the
file it hands the game.

**Headless runs stay card-less unless `--vmu` is passed.** A card answers Maple frames and changes
the write stream, which would invalidate every golden trace; this is the same rule the M2/M3 runs
were measured under.

A file that is not exactly 131,072 bytes is refused and never adopted, because the device rewrites
the whole image after each block write — a mistyped path must not be truncated. A missing path is
created; an existing path that is not a card is an error.

## Inspecting and making cards

```powershell
python tools\vmu.py C:\path\to\card.vmu          # what is on it
python tools\vmu.py --new C:\path\to\card.vmu    # a blank, formatted card
```

The lister reads the directory entries and reports each save's name, block count, size and BCD
timestamp. That is all a Dreamcast tool can know without understanding the title's own save format;
Draconus's files are named `DRACONUS.001` … `DRACONUS.008`. Only data files (type `0x33`) are
listed: a VMU mini-game (`0xCC`) is not a save, and leaving it out keeps the launcher's indices
lined up with the game's own Load Game list.

The blank image is byte-identical to the engine's `MemoryCard::format()`. The launcher's self-test
checks that equality path indirectly (both write the same image) and parses a fabricated entry back.

## In the launcher

**Saves** tab:

* **Attach a memory card** — off boots with an empty slot, which is how a console with no card in it
  behaves (the title then says "No VMU Found").
* **Card file** — the image, with `...` to pick one and **New...** to write a formatted blank card.
* **Saves on this card** — file name, save date, and block count. A card that does not exist yet
  says so instead of failing.
* **Launch straight into a save** — with a save selected, Play passes a `--press` schedule that
  walks the game's own frontend to its Load Game list, picks the file, and lets the game load it.
  Nothing is faked: the save is loaded by the game's normal path. The game's list has eight slots,
  so the launcher refuses a ninth rather than pressing past the end.

## How the boot-into-save schedule was found

The guest clock is deterministic (fixed 1/60 s frames), so the frontend can be driven by frame
number. Measured on this title, with a card attached:

| guest frame | press | result |
|---|---|---|
| 1600 | Start | title → intro cinematic |
| 2300 | Start | skip the cinematic → main menu |
| 3300 | Down | New Game → Load Game |
| 3550 | A | → "Load Game / Choose VMU" |
| 4700 | A | → "Load Game / Choose Savegame Slot" (only when the card has a save file) |
| 5200 + 120·n | Down × n | walk the list; it has two columns of four but Down walks reading order |
| 5200 + 120·(n+1) | A | load entry `n` and let the game take over |

The file list is ordered exactly as the card's directory is, and the launcher lists entries in that
same order, so entry *n* in the launcher is entry *n* on screen. Verified with a card carrying eight
synthetic entries: two Downs highlighted `DRACONUS.003`, five highlighted `DRACONUS.006`, and the
launcher's exact schedule for slot 5 (`…,down@5680,a@5800`) ended on the game's own `LOAD ERROR!`
page — the game read the right directory entry and tried to load the synthetic data.

The launcher's `LOAD_SCHEDULE` + `load_presses()` implement exactly this; `--selftest` pins the
command line it produces, including the number of Downs for a chosen slot.

## What saves, and what does not

Draconus's in-game pause menu is **Map / Set Mark / Restore Mark / Options / Quit Game**. "Set
Mark" is a checkpoint, not a card write: a scripted run that accepts it reports **0 block writes**
on the card and returns to the game, which is why it cannot be used to produce a VMU save. The
VMU file flow (`VMSSavePage` → `SavePage` → `SavedOKPage`) is reached from the game's own
save points/level transitions, which are part of the title's design; the engine implements the card
and the guest decides when to write. This is unchanged from a real console.

What was verified end to end here:

* A blank card made by `tools/vmu.py` is byte-identical to the engine's.
* Draconus reads a formatted card (16 block reads at the title: root + FAT + 13 directory blocks +
  one), and draws no "No VMU Found" notice.
* A directory entry named `DRACONUS.001` appears on the game's Load Game list, and loading it
  reaches the game's `LOAD ERROR!` path (expected: the data is synthetic).
* The engine writes every block write back to the image file and refuses to write to a file that is
  not a card (its unit test covers the refusal).
* The Crazy Taxi evidence in `engine/docs/vmu-creation-study.md`: a blank card made the same way is
  accepted and a real `CRAZYTAXI_DC` save is written through the same device.

## Sharing with an emulator

Flycast keeps a card per title as `<product-id>_vmu_save_A1.bin` (for Draconus, look for
`T40203N_vmu_save_A1.bin` or the name from your own Flycast data directory). Point the launcher's
**Card file** at it (or run `play-draconus.ps1 -Vmu <file>`), and the same bytes the emulator wrote
are what the game reads. Saves made here can be copied back the same way.

## Risks and limits

* **Torn writes.** `MemoryCard::save()` rewrites the whole 128 KB after every block write, so a
  kill in the middle of a save can leave a half-updated image. Write to a copy if a save matters.
* **One card.** The bus can address five expansion slots on each of four ports; the boot attaches
  one card on port A slot 1, which is what the title's own slot picker offers by default.
* **No format of existing files.** A 128 KB file without the format marker is refused, not
  reformatted. Make a blank card next to it instead and import saves as needed.
* **Save data format.** The launcher lists files but does not decode the title's save contents; that
  would need the game's own structures and is not needed to pick one.
* **Headless determinism.** Passing `--vmu` to a headless run changes its Maple traffic and write
  hash. Use a copy of the card per run when comparing traces.
