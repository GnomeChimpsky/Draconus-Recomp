# Diagnosis — why the game "is not playable"

Investigated 2026-11-06 on the interpreter path, `--rtc-seed 1000000`, screenshots taken with
`--window --screenshot-at N` (presented frames lag guest frames by ~87).

## What was tested

Two runs with identical seed and inputs, differing only in whether Right was held from frame
1500 to 2380:

```
A: start@1150, a@1400
B: start@1150, a@1400, right@1500,right@1520,...,right@2380
```

Frames compared at presented 2400 (guest 2487): **identical, 0.00 % of pixels changed.**

That is *not* evidence of broken input — frame 2400 is the intro cinematic, which is
non-interactive by design. Holding Right in a cutscene should do nothing.

## Where the game actually is

| presented frame | screen |
|---|---|
| 900 | title with the "No VMU Found" warning |
| 2400 | intro cinematic (red sky, creatures), advancing |
| 3000 | same cinematic, camera moved on (proves the scene animates) |
| 6000 | **"DEMO PLAY / PRESS START BUTTON"** over a castle scene |
| 6600 (after start@6000) | back at the **title screen** |

So the sequence runs: title → (Start) → intro cinematic → attract/demo → (Start) → title.

## Conclusion

1. **Input reaches the game.** Start at the title begins the intro; Start at the demo screen
   returns to the title; A was consumed earlier. The 2400-vs-3000 comparison proves the scene
   is advancing rather than frozen.
2. **The game is in attract mode at frame 6000, waiting for Start.** It is not hung.
3. **We have not yet reached the actual game.** Nothing we scripted produced a main menu or a
   playable level; the loop we observed is title ↔ attract.

So "not playable" is, so far, a *sequence* problem, not a broken-input problem: the scripted
presses drive the attract loop but never enter gameplay. Whether the main menu is reachable —
and whether it responds correctly when it is — is the next test.

## Next test

Press Start *during* the intro (the usual way to skip a movie into the menu), then screenshot:

```
--press "start@1150,start@2500,a@2600"  --screenshot-at 3000
```

If a menu appears, capture it; that is the first genuinely interactive screen and the real
start of playability testing. If nothing but the attract loop is reachable, the next suspect
is the title's menu state machine, and Flycast becomes the reference for what that screen
should look like and when it appears.

## Method note

Each 6000-frame capture costs ~10 minutes (interpreter at 0.22x), so this diagnosis is
built from a handful of long runs rather than continuous observation. Flycast would give the
reference flow at full speed, but its keyboard pad is disabled in `emu.cfg`
(`maple_sdl_keyboard = 0`) and `SendKeys` to its window did not register, so driving it
needs a different input path (e.g. `PostMessage`/a mapped pad) before it can serve as the
flow oracle.
