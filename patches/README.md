# Engine patches

`setup.ps1` fetches `dream-recomp` at a pinned commit. This directory holds the project's delta
against that commit, so a fresh clone builds the same engine this project was developed on.

| Patch | What it carries |
|---|---|
| `0001-engine-local-changes.patch` | The sum of ledger entries 001–035 in `docs/ENGINE-CHANGES.md`: the diagnostics and instruction tracer, the hook-dispatch fix, the replay host-state skip, the SR-write rule, the exception-handler stop address (the translated-path fault), the flash side-effect marking, the inlined RAM fast path, cached host memory for the offscreen readback, hor+ widescreen, presentation decoupled from the 60 Hz logic, 4:3 pillarboxing for flat 2D screens (`frame_uses_depth`, plus the presenter's bar discard), the window following `--scale` with `--fullscreen` and a content aspect (`window_size`, `content_aspect`), `--present-rate` capped to the display's refresh (`present_rate`), geometry interpolation for the extra presents (`interpolate`), the per-user memory card a windowed run attaches when `--vmu` names none (`default_vmu_path`), windowed/borderless/exclusive display modes (`DisplayMode`), the screen-space HUD compression that keeps the HUD's 4:3 shape at 16:9 (`compress_screen_overlays`), the direct-present path that keeps a finished frame on the GPU for the presenter to sample (`Presenter::use_image`, `Offscreen::read_back`), the overlay's blend destination supplied separately as `under` so the frame counter and the binding screen stop reading the write-combined staging buffer (`fill_rect`, `draw_text`, `Presenter::upload`'s `decorate`, `InputMenu::draw`), exclusive fullscreen choosing a refresh that is a whole multiple of the picture rate so every picture is held for the same number of vertical blanks (`Window::set_content_hz`), a runtime SH-4 clock so a scene that misses its real budget can be given more cycles per blank (`--sh4-clock`, `sched::sh4_clock`), and the jump pack in the controller's second expansion slot whose effects drive ordinary gamepad rumble (`maple::JumpPack`, `Window::rumble`), with the frame-time, presentation-cadence, per-frame and host-profile diagnostics (`DREAM_TRACE_FRAME_HIST`, `DREAM_TRACE_PACING`, `DREAM_TRACE_FRAMES`, `DREAM_PROFILE`, `tools/profile-map.py`, `DREAM_MAPLE_TRACE`, `DREAM_RUMBLE_TRACE`), the HUD-panel pass that carries the item wheel's 3D models with the wheel and refuses a world-space particle billboard (`compress_screen_overlays` panel rule), `dream_render_view --aspect` for checking a capture at a widescreen aspect, and the launcher's audio device/volume/buffer controls (`--audio-device`, `--audio-volume`, `--audio-buffer`, `--list-audio-devices`). Touches `runtime/`, `translator/`, `render/`, `audio/` and `cmake/`. |
| `0002-modern-controls.patch` | Ledger entry 036: the optional `--controls modern` layer — `InputPreset`/`effective_bindings`, extra physical sources for A and X, `Window::set_input_preset`, and the XInput remap. The launcher **Controls** option, `-ModernControls` and the input tests accompany it in the repository. |
| `0003-m5-coverage.patch` | Ledger entries 037–038: pointer discovery scans far enough to reach Draconus's long static-constructor functions (200 → 1,024 instructions; 8,936 → 9,126 functions), and `resume_miss` retries the other functions containing an address before the interpreter. Together they take a 60 s scripted play from 101 untranslated calls to 0. |
| `0004-frame-interpolation-pairing.patch` | Ledger entry 039: the interpolation stops tearing the picture. The resynchronisation window goes from two candidates to sixteen, a strip whose list position changed is paired on its texture coordinates, and every corner is moved by *position* rather than by strip so two strips that share one cannot move it differently (the seams that opened and snapped shut). The presenter repeats the current picture for a still frame or one whose pairing mostly failed, presents the intermediate frame from the GPU instead of round-tripping it through the host, and F11 captures the picture that is actually on screen (with a `.interp` geometry dump when that is the intermediate frame). The on-screen counter is drawn on the GPU as solid rectangles from the same font geometry (`shaders/overlay.*`, `overlay::text_rects`), so it no longer reads the frame back on every present. Touches `render/{include,src,shaders,tests}` and `runtime/boot/boot_main.cpp`; adds `DREAM_INTERP_PAIR` and a frame list for `DREAM_INTERP_DUMP`. The launcher's present-rate list comes from the display's own modes, in the repository rather than in this patch. |

`setup.ps1` applies each patch after fetching the engine, and is safe to re-run: a tree that
already has the patch is detected with `git apply --reverse --check` and left alone.

## Refreshing the patch

When the ledger changes, regenerate the file from two trees with the same layout: `a/` a pristine
engine at the pinned commit, `b/` the working engine, both containing the changed source
directories (`audio/`, `cmake/`, `render/`, `runtime/`, `translator/`).

```powershell
# a/ = freshly fetched engine; b/ = the checkout with the changes applied
git diff --no-index --no-renames --no-color --src-prefix= --dst-prefix= a b > 0001-engine-local-changes.patch
```

`0002-modern-controls.patch` is generated the same way, with `a/` the pinned tree **plus 0001** and
`b/` the working engine; it therefore applies after 0001 in `setup.ps1`'s sorted order.

Apply a patch with `git apply -p1` from inside `engine/`. Verify before committing:

```powershell
cd engine; git apply --check <repo>\patches\0001-engine-local-changes.patch
```

The engine is GPL-2.0 and this repository is a derivative work (see `LICENSE`); the patch contains
only project-written changes, no game data.
