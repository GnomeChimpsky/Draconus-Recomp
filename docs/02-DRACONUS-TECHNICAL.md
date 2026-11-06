# 02 — Technical profile of the game

Everything here comes from strings and structure inside the user's own
`1ST_READ.BIN` and disc, or from the file inventory. Where a claim is an inference,
it says so.

## Hardware the game actually uses

| Subsystem | Evidence | Recompilation consequence |
|---|---|---|
| SH-4 CPU + FPU | code shape, ≈10.5 % FPU opcodes | needs correct FPU modes and `FTRV`/`FSCA` |
| PowerVR2 (TA + VRAM) | `pvr` strings, `.PVR` textures | low-level TA→Vulkan path |
| AICA + ARM7 | `Audio64 Ver 9.0.b.3`, `AUDIO64.DRV` (20,824 B) on disc | the game ships its own ARM7 driver: the AICA must *run* it |
| GD-ROM | `gdFsOpen/Read/Seek/GetFileSize`, `GDROM_dirent_map_buffer` | custom file layer on top of Katana `gdFs*`; not plain ISO access |
| Maple | pad, VMU (`VMSSavePage`, `VMU_SMART_TEXT`), Purupuru (`vibrate_purupuru`) | pad + VMU + rumble HLE |
| RTC | `syRtc Ver 1.02` | deterministic clock for tests |
| Flash | Katana standard (inferred from SDK use, not directly observed) | standard HLE |

**Not present:** WinCE boot (`0WINCEOS.BIN` absent), CRI Sofdec/ADX (case-sensitive
scan = 0 hits), Naomi hardware, modem/BBA (no strings found).

## Sega Katana SDK surface

| Marker | Meaning |
|---|---|
| `KAMUI failure on line …` | KAMUI animation library linked |
| `Audio64 Ver 9.0.b.3 Build:Nov 01 1999` | ARM7 sound driver version |
| `acDigiPlay`, `acSystemInstallDriver`, `amSoundFetchSample`, `amBankLoad` … | Sega AICA sound middleware, used heavily |
| `syRtc Ver 1.02 Build:Mar 02 1999` | RTC helper |
| `gdFs*` | Katana GD-ROM file API |

The `ac*`/`am*` assertion strings are valuable: they name the exact middleware
entry points the game calls, which is a ready-made checklist for the audio HLE.

## The engine's own namespace

The game does not use Dreamcast-native paths. It uses Windows-style backslash paths
under an internal root named **`die2`**:

```
\die2\current.img          \die2\data\equipment.img
\die2\data\credits.img     \die2\data\dirent.dir
\die2\merger.txt           \die2\dump\scriptdump.txt
\die2\dump\onscreen_errors.txt    \die2\dump\frameinfo.txt
frontend\pages.pfe         frontend\vmu*.raw
interface\interface.sx     interface\frontendbg.tpm
textures\banana.pvr        dc_sounds\whoosh.wav
items\entities\magicshield.TPM
```

Two conclusions:

1. The engine was carried over from a PC codebase (Die by the Sword), and the
   Dreamcast port kept the PC virtual filesystem, mapping it onto the disc.
2. The `\die2\dump\*` and `\die2\merger.txt` paths are leftovers of the original
   content pipeline — a **script dump** and a **merge** step. They hint at how level
   and script data were produced, which will matter when reading `.IMG` files.

## Asset formats observed

| Format | Where | Reading |
|---|---|---|
| `.IMG` | level/character bundles, 86 in the index, 4–7 MB each | container: level geometry + entities + scripts |
| `.PVR` | 1429 files | PowerVR texture (standard Dreamcast) |
| `.STR` | 1128 files | streamed data (music/voice or cutscene streams) — **unconfirmed which** |
| `.APM` | 354 | animation/motion (inferred) |
| `.ENT` | 328 | entities |
| `.TBB` | 157 | table/bank (unconfirmed) |
| `.TPM` | 74 | 2D/tilemap-ish (`GRIDTICK.TPM`, `FRUSTUM.TPM`) |
| `.PFE` | 5 | frontend *page* definitions (`pages.pfe`) |
| `.SX`, `.ANM`, `.IFL`, `.FON`, `.RAW`, `.WAV` | small counts | interface, animation, include list, font, VMU icon, sound |

**No format has been decoded yet.** That is deliberate: asset work is scheduled after
the game runs, and the Die by the Sword PC data in this workspace (`.ATD`, `.DMV`) is
the intended Rosetta stone.

## Runtime structure hints

Strings describing a scripted, data-driven engine:

```
move script chunk name          script class: actor
AFFECTS_TERRAIN                 WDS terrain post process
Backdrop Invalid for Script     script object type … is not a member of script class
PFE_SCRIPT                      SCRIPT Unknown Entry
```

Implications for recompilation:

* Dispatch is **data-driven**: script opcodes and class names select behaviour at
  run time. Static call-graph discovery will miss handlers reached only through
  these tables — expect to seed many functions (see `docs/08-RISKS.md`, risk 1).
* Terrain has a post-process step and warnings about re-export: geometry and its
  metadata are separate data structures, not just a mesh dump.
* The frontend is page-based (`.PFE`), so menu backgrounds/text are data the HLE
  filesystem must serve faithfully.

## Determinism notes

* The game reads the RTC (`syRtc`) — tests must pin it.
* Disc reads are real work on hardware; the engine layer counts them
  (`GDROM_dirent_map_buffer`, `MyFileRead`). A fast-read HLE can change timing, so
  read pacing needs the same treatment other ports applied.
* Audio is an ARM7 program: if it is not run, the game may still boot but sound (and
  possibly sync that waits on sample completion) will differ.
