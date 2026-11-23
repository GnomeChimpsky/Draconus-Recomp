# Controller haptics

The jump pack gives a Dreamcast game exactly one thing to say to a pad: one motor, seven power steps,
4–30 Hz. A modern controller can do much more, and the launcher's **Controller** tab lets the game say
it there instead. This page is what each option does, what it needs, and what to check when a pad does
nothing.

Nothing here is required to play. Every option is off by default, and every failure — a missing
`renhdrum.dll`, a pad the engine does not know, a USB port that exposes no audio endpoint — leaves the
plain two-motor rumble in charge, which is what the game did before this feature existed.

## What is behind it

[RenHDrum](https://github.com/trzz1214/RenHDrum) (MIT, Three-Dola) is a haptics engine that takes a
two-band rumble sample — amplitude and frequency, low band and high band, per side — and rebuilds it
on whatever the pad actually has:

| Pad | How it is driven | What you feel |
|---|---|---|
| DualSense / Edge, wired | 4-channel 48 kHz audio on the pad's own USB audio endpoint, channels 2–3 | Voice-coil actuators: a real thump, not a phone buzzer |
| DualSense / Edge, Bluetooth | not claimed — see below | plain rumble |
| Switch Pro Controller | 10-byte HD Rumble sub-commands | HD Rumble packets |
| Xbox One / Series | four motors | grips plus, where the pad has them, trigger motors |

The game's effect is turned into that sample like this: the pack's seven power steps become amplitude,
scaled by how long the effect lasts (a real motor has inertia, so a 50 ms pulse gets a third of the
level and a 900 ms one all of it); its 4–30 Hz motor rate sets the low band between 60 and 120 Hz; and
a hit — half drive or more, with at least 80 ms behind it — also gets a small high band at 170–200 Hz
so it reads as sharp rather than soft. A one-shot ends after the duration the game asked for, and a
continuous one 250 ms after the game last repeated it, so a lost stop can never leave a motor running.

## The options

| Launcher row | Engine flag | What it does |
|---|---|---|
Every row below is only available with **Modern controls**, because that is the layout where the
triggers block and attack; in Classic the launcher greys the whole section out.

| Launcher row | Engine flag | What it does |
|---|---|---|
| **HD rumble (RenHDrum)** | `--haptics` | The above instead of two motors: the pad's actuators, driven through its own USB audio endpoint. |
| **HD rumble strength** | `--haptics-strength N` | How hard the actuators are driven, 10–100 %. |
| **Trigger feedback on blocks and hits** | `--trigger-feedback` | Every rumble becomes a short buzz in a trigger: left only while the block is held, both otherwise. Needs no HD rumble and no audio path. |
| **Trigger buzz strength** | `--trigger-strength N` | How hard that buzz is, 1–8. The default 3 is RenHDrum's own level. |
| **Trigger resistance (both triggers)** | `--trigger-resistance` | A constant weight under both triggers from launch, with the buzzes playing through it. |
| **Resistance: left / right** | `--resistance-left N` / `--resistance-right N` | The weight on each trigger, 1–8. Defaults 3 and 1. |
| **Resistance starts at** | `--resistance-zone N` | Where in the travel the weight begins, 0–9. Default 1. |
| **Controller speaker taps (experimental)** | `--haptics-speaker` | Audible taps from the DualSense's own speaker, synthesised by RenHDrum from the rumble. Off by default. |
| **Speaker level** | `--speaker-level N` | How loud those taps are, 0–100 %. Default 60. |

The trigger options are DualSense-only and need it **wired**: the adaptive triggers are addressed by an
11-byte effect inside a 47-byte HID output report, which this engine sends only over USB. They work
with **HD rumble** off, in which case the pad's audio endpoint is never opened at all.

## How the rumble reaches the triggers

The title's rumble is the only input; nothing is inferred from the audio, the animation or the other
buttons. Every effect at or above 45 % of the pack's drive becomes a short buzz — 100 ms, amplitude 3,
25 Hz, the level RenHDrum's own trigger effects use — and the block button decides where it lands:

* **Left trigger held** — the left trigger only. That is the block, so the hit it takes is felt there.
* **Any other rumble** — both triggers.

Effects below that level are the game's ambience — a footstep, a light idle — and never reach a
trigger. One trigger cannot start another pulse within 120 ms, and letting go of the block ends its
buzz with it.

**Resistance** is separate and optional: a constant weight sits under *both* triggers from the moment
the game starts (left strength 3, right strength 1, from zone 1), so a trigger feels the same in the
first second of a level as in the middle of a fight. A rumble buzz plays through it and the weight
comes back afterwards.

None of this uses audio. The trigger effects are HID output reports, the pad's 4-channel audio endpoint
is never opened for them, and **Trigger feedback** works with **HD rumble** switched off.

A vibration at amplitude 8 around 50 Hz is not a tap: the trigger's actuator renders it as a loud
mechanical rattle, which is what an early build of this did.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Nothing changed at all | For trigger feedback alone, neither **HD rumble** nor `renhdrum.dll` is needed on a Pro Controller, but a DualSense's triggers do need the DLL: is it beside the executable? The release folder has it; a source tree copies it from `third_party\renhdrum\`. |
| The game says `haptics: renhdrum.dll not found beside the game` | The file is missing or in the wrong folder. It is loaded only from the executable's own directory. |
| `haptics: on, no supported pad yet` | The pad is not one RenHDrum claims, or a DualSense is on Bluetooth. Wired is required for a DualSense. |
| Rumble works, triggers do nothing | Triggers need the wired DualSense and one of the two trigger options. A wireless pad never gets them. |
| Triggers feel wrong on a specific pad | Move the strength slider; the trigger effects are the same ones a PS5 game uses, but every pad's springs age differently. |
| A rattle or clicks from the pad | The trigger buzz is 100 ms at amplitude 3 / 25 Hz, and only a rumble at half drive or more starts one — so a footstep or a turn never reaches a trigger. The actuator path is quiet too: amplitude is scaled by duration and the high band needs 80 ms behind it. If something still sounds too loud, the **Haptic strength** slider is the lever. |

Two environment switches make a report actionable:

```text
DREAM_RENHDRUM_TRACE=1   prints the DLL version, each claim, the audio endpoint and the pad's name
DREAM_RENHDRUM=0         disables the whole path, for an A/B against the plain rumble
```

`dream_haptics_probe.exe` (built from `engine` sources with the renderer, not shipped) claims the first
pad and plays the whole sequence — block, block hit, release, swing, landing blow, rumble — printing
each step, so a pad can be checked without loading a game or playing to the first fight.

## Not supported

* **A DualSense over Bluetooth.** Windows does not expose the pad's 4-channel endpoint over Bluetooth,
  and the combined HID report that replaces it is not implemented in this host. The pad keeps SDL's
  rumble, which still works.
* **Game audio in the controller speaker.** RenHDrum's speaker plays its own synthesis of the rumble
  signal, not the game's mix. Sending the mix there would need the engine's audio path to grow a second
  stream and a way to choose which sound; see `docs/ENGINE-CHANGES.md`, patch 050.
* **Steam Controller grips.** The DLL supports them; this host does not claim that pad.
