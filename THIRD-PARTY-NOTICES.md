# Third-party notices

The Draconus-Recomp release bundle contains or links the components below. This file records
what they are and where their licences are published; it is not a substitute for the full licence
texts, which ship with the upstream projects and are available at the links.

## The game executable

| Component | Licence | Notes |
|---|---|---|
| `dream-recomp` engine | GPL-2.0 | <https://github.com/phobos665/dream-recomp> |
| Draconus-Recomp patches and title config | GPL-2.0 | This repository; see `LICENSE` |
| libchdr | BSD-3-Clause | <https://github.com/rtissera/libchdr>; bundled in the engine build |
| zstd 1.5.7 | BSD-3-Clause | Bundled by libchdr |
| miniz 3.1.2 | MIT | Bundled by libchdr |
| LZMA SDK 26.02 | Public domain | Bundled by libchdr |
| toml++ | MIT | <https://github.com/marzer/tomlplusplus> |
| SDL3 | zlib | <https://github.com/libsdl-org/SDL>; `SDL3.dll` ships beside the game |
| Vulkan loader | Apache-2.0 / MIT | Supplied by the player's GPU driver as `vulkan-1.dll`; not bundled |

## The frozen launcher

| Component | Licence | Notes |
|---|---|---|
| Python 3.11 | PSF License 2.0 | <https://www.python.org/>; embedded by PyInstaller |
| PyInstaller 6.22.3 | GPL-2.0-or-later with the bootloader exception | <https://pyinstaller.org/> |
| PyInstaller hooks-contrib 2026.10 | GPL-2.0-or-later | <https://github.com/pyinstaller/pyinstaller-hooks-contrib> |
| Tcl/Tk 8.6 | BSD-style | <https://www.tcl.tk/software/tcltk/license.html> |
| OpenSSL 1.1.1 (`libcrypto-1_1.dll`) | OpenSSL License and SSLeay License | <https://www.openssl.org/source/license.html> |
| Microsoft Visual C++ runtime (`MSVCP140.dll`, `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll`) | Microsoft Visual C++ Redistributable terms | Redistributed with the application under Microsoft's terms |

## Artwork

`tools/launcher-emblem.png` and `Draconus Recomped Emblem light.png` are fan-made title
treatments that incorporate the *Draconus* wordmark. They are not disc data; the wordmark and
the game remain the property of their owners. See `docs/LEGAL.md`.

## Redistribution

If you redistribute a release bundle, keep this file, `LICENSE`, and `docs/LEGAL.md` with it,
and do not add a disc image, extracted files, saves, screenshots, or generated C++ to it.
