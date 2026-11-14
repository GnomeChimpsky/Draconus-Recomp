# M6 audio — baseline and result

Measured 2026-11-06 (baseline) and 2026-11-14 (result) on the retail disc, with the translated
runtime and `--rtc-seed 1000000`.

## What M6 requires

> 10 s of music spectra matched vs Flycast; 10 min without dropouts; WAV capture diff.

All three are now measured. Flycast's SDL2 audio backend can write through SDL's disk driver, which
gives a digital reference without a loopback device. The captures, the spectral comparison and the
dropout run are below; `tools\m6-check.ps1` repeats the gate.

## Result (2026-11-14)

| clause | measurement | verdict |
|---|---|---|
| 10 s spectra | 10.00 s of menu music after START: sample correlation **1.0000**, spectral correlation median **1.0000** (min 0.9999), octave bands within **0.00 dB**, **12/12** dominant peaks, centroid 286.0 Hz both | pass |
| WAV diff | **99.55 %** of samples differ, RMS **1.1 LSB**, worst **5 LSB** after alignment; the same waveform with a ~1 LSB rounding difference | pass |
| 10 min dropouts | 600.000 s ours, 7 silent runs; each has a matching silent run in the 600.723 s Flycast capture; the long ones are the game's **DEMO PLAY** attract screen | pass |
| title screen | silent in Flycast too (15.55-33.5 s); ours is silent 12.8-25.6 s because START is scripted earlier | correct behaviour |

The music match is not "close". After the offset, the two captures have the same dominant
frequencies, the same per-octave balance and the same spectral centroid, and nearly every sample is
within a couple of 16-bit LSB.

## How the Flycast reference was captured

`flycast.exe` has no "record audio" menu item, but its SDL2 backend can use SDL's disk audio driver:

```powershell
$env:SDL_AUDIODRIVER = "disk"
$env:SDL_DISKAUDIOFILE = "work\m6\flycast_10min.raw"
flycast.exe -config audio:backend=sdl2 -config config:LuaFileName=draconus_m6_capture.lua "<retail .gdi>"
```

The file is raw s16le stereo 44.1 kHz; `tools\audio-check.py raw2wav` converts it without touching the
samples. `tools\flycast-m6.ps1` wraps this, including the Lua script that presses START on guest frame
1800 and A on frame 2100 (held 30 frames each) and exits on frame 36000. It prefers the retail
v1.000 GDI by name and refuses when several discs are present, because comparing the prototype's
audio would answer the wrong question.

The recompiled run uses the documented schedule, `--press "start@1150,a@1400"`, and the same
`--rtc-seed`. The captures are:

```
work\m6\flycast_90s.wav     Flycast, 5,400 frames   (90.117 s)
work\m6\ours_90s.wav        ours,    5,400 frames
work\m6\flycast_10min.wav   Flycast, 36,000 frames  (600.723 s)
work\m6\ours_10min.wav      ours,    36,000 frames  (600.000 s, --wav's cap)
```

Ours reaches the menu music about eight seconds before Flycast; the scripts press START at 19.2 s
and 30 s, so the offset is a schedule difference, not late music. `audio-check.py compare` finds
that offset from the loudness envelopes and refines it to the sample (-7.882 s for the 90 s pair).

## The title screen is silent in Flycast too

The baseline's open question was whether our silent title screen missed a cue. It does not:

| capture | intro | title silence | menu music |
|---|---|---|---|
| Flycast, 90 s | 7.55-15.55 s | **15.55-33.50 s** | from 33.50 s |
| ours, 90 s | 4.85-12.80 s | **12.80-25.60 s** | from 25.60 s |

Both are silent between the logo/intro burst and the first START. The title's silent period is
shorter in our capture because START is scripted 10.8 s earlier; the screen itself is the same
silent title screen. The memory card is not the cause: attaching a VMU did not change our capture
(`docs/14-M3-M6-FLYCAST-REFERENCE.md`).

## 10 s of music spectra

The comparison window is 34.00 s in Flycast and 26.12 s in ours, ten seconds starting 0.5 s after
the menu music begins:

```
sample correlation      1.0000
sample diff             99.55 % of samples differ, rms 1.1 LSB, worst 5 LSB
spectral correlation    mean 1.0000  median 1.0000  min 0.9999
spectral cosine         median 1.0000
octave band difference  worst 0.00 dB
dominant peaks          12 of 12 matched
centroid                286.0 Hz vs 286.0 Hz
rms                     3344 vs 3345
```

The dominant peaks are the same set of harmonically related partials, not merely a similar centroid;
the full per-band table is `0.00 dB` from 40 Hz to 16 kHz. That is the M6 spectra clause.

A capture-to-capture caution: two Flycast runs are not sample-identical after the intro (the VMU and
attract state are not reset between runs), so the 90 s pair is the one used for the sample-level WAV
diff. The 600 s pair still matches spectrally (median 1.0000, bands 0.00 dB, 12/12 peaks) but has an
RMS sample difference of 228.7 LSB because of that state difference; it is used for the dropout
timing, where sample phase does not matter.

## 10 minutes without dropouts

The 600 s captures produce the same seven silent runs in the same order. The four music/attract
runs differ in length by at most 0.7 s; boot and title differ because the scripts press START at
different times. `audio-check.py gaps` matches each run locally rather than through one global
offset, because the two captures drift a second or two apart over ten minutes.

| ours (s) | length | Flycast (s) | length | reading |
|---|---|---|---|---|
| 0.00 | 4.85 | 0.00 | 7.60 | boot, before the first sound |
| 12.80 | 12.80 | 15.55 | 18.00 | title screen |
| 68.00 | 2.50 | 76.20 | 2.65 | music cue boundary |
| 91.00 | 2.30 | 99.45 | 2.50 | music cue boundary |
| 183.65 | 54.45 | 192.50 | 54.90 | **DEMO PLAY** attract screen |
| 328.50 | 54.45 | 337.95 | 55.15 | **DEMO PLAY** attract screen |
| 473.35 | 54.50 | 483.65 | 54.85 | **DEMO PLAY** attract screen |

The three long gaps repeat about every 145 s. They are not dropouts: Flycast has the same gaps at
the same points in its attract loop, and a screenshot at 474 s, just before the third long gap,
shows the game's **"DEMO PLAY / PRESS START BUTTON"** screen over a gameplay demo. The game stops
its music while that attract loop is idle and starts it again when the loop advances. Ours
reproduces the same schedule. No gap in ours is sounding in Flycast, so the dropout clause passes.

Counters from the 600 s run: 36,000 frames, 600.377 s guest time, 26,477,495 AICA samples,
1,842,313,686 ARM instructions, 18,267,849 samples non-zero (69.0 %), 1,870 key-ons, 6 channels
active, 0 faults. The first 90 s of this run are byte-identical to the separate 90 s run, so the
audio path is deterministic run to run.

## Remaining M6 questions, answered

1. **Is the title meant to have music?** No. Flycast is silent there too; the first music is the menu
   after START.
2. **Is `2 channels active` too low?** That was a menu snapshot. The 600 s run reaches 6 active
   channels and 1,870 key-ons through the attract loop and the demo, so the mixer is not starving.
3. **Are the long gaps dropouts?** No. They are the DEMO PLAY attract loop, and Flycast has them at
   the same points.

## Reproducing the gate

```powershell
tools\m6-check.ps1            # captures what is missing and runs both clauses
tools\m6-check.ps1 -Skip10min # only the 10 s spectral clause
```

Flycast is only needed to make the reference. Its path and the retail GDI are auto-detected; pass
`-Flycast` and `-Disc` to override. The captures live in `work\m6` and are not committed, because
the reference contains the game's own audio and is made from the owner's disc.

---

# Baseline (2026-11-06)

The rest of this file is the original baseline measurement. It remains the record of what played,
what did not, and why, before the Flycast audio reference existed.

## Capture

```powershell
draconus_boot --config games/draconus/draconus.toml --interpret \
    --max-frames 1800 --rtc-seed 1000000 --wav work/audio_baseline.wav
```

`--wav` writes 16-bit stereo 44.1 kHz, capped at ten minutes.

## Result — 29.86 s captured

```
silent (<-48 dBFS) 73.9 %
peak               32765   (full scale)
rms                3771
```

Per-second RMS shows one contiguous burst and nothing after it:

```
 t(s)   rms   peak
   0      0      0
   ...
   4    564   4690  #
   5   5665  20121  ##################
   6   5951  19365  ###################
   7   6043  16782  ####################
   8  11061  26233  ####################################
   9   6118  23562  ####################
  10  10892  32765  ####################################
  11   6378  30130  #####################
  12   1072   5355  ###
  13+     0      0
```

So the intro/logo sequence has audio, and the title screen after it is silent.

## Counters from the same run

```
AICA: arm7 running at pc 0x00004b08, 1,316,739 samples, 93,171,728 ARM instructions,
      0 FIQs, 0 SWIs, 3,360 timer irqs, 5 SH-4 irq raises, 200 channel writes,
      4,931 dsp writes; mixer: 3 key-ons, 0 channels active, 351,353 of 1,316,739
      samples non-zero, dsp running; SCPU sh4->arm 0, arm->sh4 5
syscalls: flashrom=22 gdrom=615,356 sysinfo=9
```

Two facts matter:

1. **`SCPU sh4->arm 0`** — the SH-4 never writes the SCPU register, i.e. it never issues a
   command to the ARM7 sound driver. The ARM7 runs, but nothing is asking it to play.
2. **No `gdrom.cdda` count at all** — the title never issues CD-audio commands, so the two
   CDDA tracks on the disc (`track02.raw` ~7 s, `track04.raw` ~6 s) are not the title music.
   CD-audio playback is indeed unimplemented (`runtime/src/hle/bios.cpp:415`,
   `runtime/src/aica/mixer.cpp:1037`), but implementing it would not change this title's
   silence.

## In-game audio works — the title is what is silent

The same capture run with scripted input (`--press "start@1150,a@1400"`, 3000 frames = 49.9 s)
shows the real picture:

```
  0-3 s   silence            (boot)
  4-12 s  intro/logo burst
 13-24 s  silence            (title screen)
 25-49 s  sustained audio    (after Start and A: menus and the game)
```

RMS in the in-game section stays between 1,200 and 5,500 with peaks to ~24,600, i.e. continuous
sound for 24 s. Counters for that run: **2 channels active, 1,420,937 of 2,199,574 samples
non-zero (64.6 %)**, 5 key-ons.

A spectrum of 30-36 s (6 s window, Hanning) confirms it is music rather than noise:

```
dominant frequencies  41.0, 41.2, 82.5, 123.5, 123.7, 330.0, 330.2, 392.5 Hz
                      (E1/E2, B2, E4, G4 — harmonically related)
centroid              1554 Hz
zero-crossing rate    0.020   (tonal, not noisy)
top-8 share           2.2 %    (many partials, i.e. a mix, not one tone)
```

## What the counters mean, revised

* `SCPU sh4->arm 0` is **not** blocking sound: 24 s of music plays with that counter at zero.
  The driver is evidently driven another way (register writes: 1,565 SH-4 vs 130,078 ARM in
  the longer run), so SCPU is not this title's command channel.
* `gdrom.cdda` is absent even in play, so the disc's two CDDA tracks are unused by this title.
  CD-audio playback stays unimplemented without loss here.

## 100-second dropout measurement

`--max-frames 6000 --press "start@1150,a@1400" --wav` (99.9 s, 488 s of host time on the
interpreter path):

```
samples          4,406,658
non-zero         3,410,599  (77.4 %)
key-ons         9
channels active 2
```

Gap analysis (50 ms windows, threshold < -72 dBFS, counting runs of 0.25 s or more):

| at | length | reading |
|---|---|---|
| 4.00 s | 0.85 s | start of the intro burst |
| 12.80 s | 12.80 s | the title screen, silent as above |
| 67.70 s | 2.80 s | after the music starts |
| 91.00 s | 2.30 s | after the music starts |

Mean RMS after the music starts is 4,616. The two later gaps are cue boundaries, which the
Flycast reference later confirmed.
