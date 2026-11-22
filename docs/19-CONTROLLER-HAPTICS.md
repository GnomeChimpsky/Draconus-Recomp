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

The game's effect is turned into that sample like this: the pack's seven power steps become amplitude;
its 4–30 Hz motor rate sets the low band between 60 and 120 Hz, so a slow heavy effect stays a thump
and a fast one rises; and a short effect (160 ms or less) gets a stronger, higher component at 340 Hz
so a hit reads as sharp rather than soft. A one-shot ends after the duration the game asked for, and a
continuous one 250 ms after the game last repeated it, so a lost stop can never leave a motor running.

## The options

| Launcher row | Engine flag | What it does |
|---|---|---|
| **HD rumble (RenHDrum)** | `--haptics` | The above instead of two motors. The master switch: nothing else here loads the DLL without it. |
| **Trigger feedback on hits** | `--trigger-feedback` | A pulse in the trigger that made an impact. Left for a block that took a hit, right for a swing that landed. |
| **Trigger resistance while blocking** | `--trigger-resistance` | Light resistance in the left trigger for as long as the block is held, and the block-hit pulse buzzes through it. |
| **Controller speaker taps** | `--haptics-speaker` | Audible taps from the DualSense's own speaker, synthesised by RenHDrum from the rumble. Off by default: it is a taste, and the pack's signal is coarse. |
| **Haptic strength** | `--haptics-strength N` | How hard the actuators are driven, 10–100 %. The trigger effects keep their own strengths. |

The trigger options are DualSense-only and need it **wired**: the adaptive triggers are addressed by an
11-byte effect inside a 47-byte HID output report, which this engine sends only over USB.

## How a block and a hit become trigger feedback

The title is the only source of "something was hit": its Puru Puru effects fire when a block connects
and when an attack lands (measured on hardware). Nothing else about the fight is visible to the host,
so the plan is the one a player would describe:

* **Block held** — the left trigger carries a light resistance (`feedback` from zone 1 at strength 2),
  so the guard has weight before anything happens.
* **An effect while blocking** — the left trigger buzzes for 110 ms: the block took a hit, and then the
  resistance comes back.
* **Attack pressed** — a faint 55 ms buzz in the right trigger for the swing itself, and a 400 ms
  window opens.
* **An effect inside that window** — a harder 90 ms buzz in the right trigger, and the window closes,
  so the burst behind a landed blow is not read as a second hit.

Effects below 20 % power are the game's ambience, not a hit, and never reach a trigger. Each side has
a 70 ms minimum gap between pulses so a long rumble cannot machine-gun a trigger.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Nothing changed at all | Is **HD rumble** on? Is `renhdrum.dll` beside the game's executable? The release folder has it; a source tree copies it from `third_party\renhdrum\`. |
| The game says `haptics: renhdrum.dll not found beside the game` | The file is missing or in the wrong folder. It is loaded only from the executable's own directory. |
| `haptics: on, no supported pad yet` | The pad is not one RenHDrum claims, or a DualSense is on Bluetooth. Wired is required for a DualSense. |
| Rumble works, triggers do nothing | Triggers need the wired DualSense and one of the two trigger options. A wireless pad never gets them. |
| Triggers feel wrong on a specific pad | Move the strength slider; the trigger effects are the same ones a PS5 game uses, but every pad's springs age differently. |

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
