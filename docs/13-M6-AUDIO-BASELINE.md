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

## Lead

The burst that does play came out of the ARM7/mixer without any SCPU command, which suggests
the sound driver is working and the SH-4 side is not talking to it. Next measurements:

1. Find the SH-4's sound-command path (SCPU at `0xA0800000` region) and check whether the
   game writes it at all after init — count the writes, not just the calls.
2. Check what the game reads from AICA during boot (version/status). If our AICA returns a
   value the driver rejects, the game may conclude there is no sound hardware and disable its
   audio path — which would explain a silent title with a working driver.
3. Only then look at CDDA, and only if a title needs it.

## Reproducing the gate once Flycast is available

`--wav` output is a normal WAV, so the M6 acceptance becomes: capture the same 10 s from
Flycast and ours, match spectra, then run ten minutes and check for dropouts (count samples
vs wall time, and listen for the mixer's `0 channels active` gaps).
