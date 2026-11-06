# 04 — Reference repositories: what is verified, what is claimed

All repositories are recent and several are explicitly AI-assisted. Their READMEs are
the *claim*; this table records what inspection actually established. Nothing here was
built or executed (no `git` on this machine at survey time).

| Repository | Licence | Verified by inspection | Still a claim |
|---|---|---|---|
| **DCRecomp/BlueStingerRecomp** | MIT | C++20; own recompiler `bs-recomp`; `config/*.toml`; Vulkan *and* software backends on one IR; SDL3 app; CMake presets; 423 KB `STATUS.md`; `.recomp.json`; PT-BR docs | "~82 % of roadmap"; bit-exact Vulkan vs software; audio parity |
| **enrique363/voldorium** | custom, "personal non-commercial" | Python SH-4→C translator; C runtime (HLE BIOS, maple, TA→OpenGL, AICA, GGPO); releases to 1.1.3; changelog documents real bugs (interrupt polling in tight loops, ADPCM loop state, alpha test); oracle capture via patched Flycast; reproducible builds | Netplay quality; 16:9 HUD fidelity |
| **theurbanninja1993-sketch/army-men-sarges-heroes-recomp** | GPL-2.0 | a *port repo* vendoring the dreamcomp framework under `dreamcomp/`; findings docs on mouse camera, high-refresh blinking, widescreen gaps | Game completeness |
| **cherryduck/dreamcomp** | GPL-2.0 | **identical blob SHAs** to the subtree above — a framework layer over `phobos665/dream-recomp`, plus audit scripts and AI workflow skills | Port status table |
| **sp00nznet/dcrecomp** | GPL-2.0 (MIT until 2026-10-20) | `static_recompile.py` (74 KB), `sh4_disasm.py` (28 KB), partial PVR2/AICA/Maple HAL, no conformance harness, self-declared gaps | "Crazy Taxi links", "Mushiking runs" |
| **flyinghead/flycast** | GPL-2.0 | since 2018, 2,635 ★, 401 forks; the de-facto hardware reference and the oracle every other project validates against | — |
| **phobos665/dream-recomp** | GPL-2.0 | title-per-directory TOML; dev interpreter; `--suggest-config`; `--write-hash`; F11 capture bundles; differential harness; `dcdisc` for `.gdi`/`.chd`; 5 titles booting | "Crazy Taxi plays" |
| **sonicfreak1337/SARecomp** (KatanaRecomp) | **none** — no `LICENSE` in the tree, `license: null`; KatanaRecomp is not a separately published repo | **technically the most complete** Dreamcast recompilation (see below) | Per-issue completeness |

## SARecomp / KatanaRecomp — reference-only

**Classification: legally blocked for code reuse pending explicit permission from the
author; technically the strongest benchmark available.**

Verified from its tree, it has already solved problems this project will hit:

| Our need | Where it is solved (study only) |
|---|---|
| Frame-rate decoupling / "SIM FPS" vs display | `src/sonic_execution_clock.hpp`, `sonic_frame_completion_contract.hpp`, `sonic_host_resume.hpp` |
| Rendering: model pipeline, hierarchy, palettes, D3D11 + Vulkan | `src/sonic_model_pipeline.*`, `sonic_render_hierarchy*`, `sonic_palette_batch*`, `cmake/SonicVulkan.cmake` |
| Texture/sound catalogues and overrides | `src/sonic_native_texture_catalog.*`, `sonic_native_sound_catalog.*` |
| Input bindings, prompt sets, SDL mappings, mouse camera | `src/sonic_input.*`, `sonic_input_bindings.hpp`, `sonic_native_input_policy.hpp`, `sonic_camera_orbit.hpp` |
| In-game options menu, config language | `src/sonic_menu*`, `docs/configuration-language.md` |
| Launcher, installer, disc import | `cmake/setup/`, `assets/setup/`, `docs/INSTALLATION.md` |
| Widescreen HUD policy | `src/sonic_big_hud.hpp` |
| AOT engineering (FPU regions, register cache, dispatch, PGO, hot-code order) | the `cmake/Linux*.cmake` / `cmake/Sonic*.cmake` family, `cmake/hot-code-order.txt`, `cmake/LinuxPgo.cmake` |
| Validation baselines | `baseline/*.json` (~830 KB bundles) |
| Audio device loss / recovery | `src/sonic_audio_*`, `docs/audio-device-recovery.md` |

### Boundary rules (enforced in review)

1. Read for *architecture, algorithms and engineering judgement*.
   **Never copy, paste, port line-by-line, or vendor** a file.
2. Nothing from it enters our tree. Our licensed base is `dream-recomp`.
3. Log every study session in `docs/refs/sarecomp-notes.md`, naming the file and the
   idea — never code.
4. Send the permission request in `docs/refs/permission-request-draft.md` early.
   If a grant arrives, re-evaluate reuse for the **port layer only**.
5. This is an engineering classification, not legal advice. Before any real reuse,
   obtain a written grant.

## Why the licensed base is dream-recomp

* Designed for adding a title (`games/<id>/` + TOML), not forking a game.
* HLE BIOS and GD-ROM: **no BIOS image required**, which matters both practically
  and legally.
* A development interpreter lets work continue before translation is complete —
  essential for a ~7,000-function game.
* The differential harness against Flycast is the method this project intends to use.
* Its disc tooling already accepts `.gdi` and `.chd`.
* GPL-2.0 is compatible with Flycast, the oracle.

Rejected as bases: **SARecomp** (licence), **voldorium** (licence; methodology only),
**dcrecomp** (hardware too incomplete), **BlueStingerRecomp** (permissive but
game-specific; kept as an optional MIT donor and fallback), **dreamcomp** (a wrapper;
borrow its audit discipline, not its code).
