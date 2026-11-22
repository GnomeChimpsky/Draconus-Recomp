# RenHDrum (bundled binary)

`renhdrum.dll` is the haptics engine behind the launcher's **Controller** tab: a DualSense's
voice-coil actuators, its two adaptive triggers and its speaker; a Switch Pro Controller's HD Rumble;
an Xbox pad's four motors. Nothing in this project would otherwise be able to reach those.

| | |
|---|---|
| Upstream | <https://github.com/trzz1214/RenHDrum> |
| Tag | `v0.5.0` (commit `e778da6e169640e225a7f898b77cbb40af97c60f`) |
| License | **MIT**, elected from the upstream `MIT OR Apache-2.0` dual license — see below |
| File | `renhdrum.dll`, Windows x64, 825,344 bytes |
| SHA-256 | `827B5DB99B13339F63B7BDA08D59C3244A82D2FFCC42DCE669B49FFFE637A8C5` |
| Built with | `cargo build --release`, Rust 1.100.0, MSVC 14.44, `+crt-static` from the repository's own `.cargo/config.toml` |

## Why MIT, and not Apache-2.0

Upstream offers the core library under either license. This project is **GPL-2.0-only**, and
Apache-2.0 is not compatible with GPL-2.0 while MIT is, so the MIT option is the one taken. The full
text is in [`LICENSE-MIT`](LICENSE-MIT); the upstream attribution notice, which credits Ryujinx, the
HD Rumble reverse-engineering community, libopus and the DualSense work, is in [`NOTICE`](NOTICE).

Both files ship inside every release bundle under `licenses/`, which is what the MIT terms ask for
("the above copyright notice and this permission notice shall be included in all copies").

## Why a binary is checked in

The engine the game builds from (`engine/`) is fetched by `setup.ps1` and carries our changes as
patches; it is not part of this repository. `renhdrum.dll` is loaded at run time from beside the
game's executable, so a release cannot be assembled without it. Building it needs a Rust toolchain
that nothing else in this project uses, and a release should not depend on that being installed.

So the pinned, reproducible artefact lives here, and a release copies it beside the game. Override
the copy by rebuilding it:

```powershell
tools\build-renhdrum.ps1            # clones the pinned tag, builds, verifies, installs here
tools\build-renhdrum.ps1 -Check     # verifies the checked-in file against the hash above
```

`DREAM_RENHDRUM=0` in the environment disables the whole path at run time without deleting the file,
and `DREAM_RENHDRUM_TRACE=1` prints which pad was claimed.

## What it is not

It contains no game code and no Nintendo, Sony or Microsoft data. The upstream project ships no
emulator binaries, games or keys, and neither does this one.
