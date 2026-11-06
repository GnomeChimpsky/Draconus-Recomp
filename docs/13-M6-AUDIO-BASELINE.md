# M6 audio — baseline

Measured 2026-11-06 on the retail disc, interpreter path, `--rtc-seed 1000000`.

## What M6 requires

> 10 s of music spectra matched vs Flycast; 10 min without dropouts; WAV capture diff.

Flycast is not installed on this machine, so the *comparison* half of that gate cannot be run
here. What can be measured is our own output: how much audio exists, where, and which voices
produce it.

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

So the AICA/ARM7 path produces tonal in-game audio today. What is missing is the *title
screen* (13-24 s), which may be correct behaviour for this build or may be a cue that never
fires — that needs a reference.

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

Mean RMS after the music starts is 4,616. The two later gaps are either cue boundaries (a
track ending before the next starts) or real dropouts; a reference capture is needed to tell
them apart. Everything else from 25 s to 100 s is continuous.

The ten-minute gate is one longer run of the same command (`--max-frames 36000`), but at
~490 s of host time per 100 s of guest audio on the interpreter path it is a ~50 minute run,
so it is a scheduled job rather than something to do while iterating.

## Remaining M6 questions

1. Is the title screen meant to have music? Needs a Flycast capture (not installed here) or a
   reference recording. Everything else in the sequence has audio.
2. `2 channels active` is low for a game with music and effects; the AICA has 64. Either the
   mix really is sparse at this point in the game (menu) or voices are being keyed off early.
   A longer in-game capture with combat would settle it.
3. Dropouts: the 49.9 s capture has no gaps after 25 s, but M6 asks for ten minutes. `--wav`
   caps at ten minutes, so the run is straightforward once the title question is answered.

## Reproducing the gate once Flycast is available

`--wav` output is a normal WAV, so the M6 acceptance becomes: capture the same 10 s from
Flycast and ours, match spectra, then run ten minutes and check for dropouts (count samples
vs wall time, and listen for the mixer's `0 channels active` gaps).
