#!/usr/bin/env python3
r"""DraconusRecomp launcher: graphics, audio and gameplay settings, then Play.

The window is a tabbed settings page on the right and a picture from the game on the left. Tabs and
controls are described by TAB spec dictionaries (see TABS), so a new option is one dict entry plus
its key in DEFAULTS -- no new layout code.

The non-UI half (command line, settings file) is separated out so it can be exercised without a
window:  python tools/launcher.py --selftest
         python tools/launcher.py --smoke      (builds the window, checks the controls, closes it)

Run with:  python tools/launcher.py      (or tools\launcher.bat)
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vmu  # noqa: E402  (the tool beside this script; only its per-user card path is used here)

# The launcher's emblem: "Draconus Recomped Emblem light.png", trimmed of the transparent margin
# its artwork leaves on the right and scaled to 320 px wide. The original canvas is 1000 px wide but
# the banner ends at x=801, so using it unmodified drew the logo noticeably left of the panel's
# centre; this file is the same artwork, centred in its own canvas.
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    # A windowed build has no stdout; --selftest/--smoke must not crash on print().
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))

    def _game_dir() -> str:
        """The folder holding DraconusRecomp.exe and draconus.toml.

        The release may keep the launcher beside the game or one folder below it; the TOML decides,
        so the packaging does not have to match a path baked into the build.
        """
        for candidate in (APP_DIR, os.path.dirname(APP_DIR)):
            if os.path.exists(os.path.join(candidate, "draconus.toml")):
                return candidate
        return APP_DIR

    ROOT = _game_dir()
    DISC_TOOL = ""  # unused when frozen: the verifier is a bundled module
    CONFIG = os.path.join(ROOT, "draconus.toml")
    BINARY = os.path.join(ROOT, "DraconusRecomp.exe")
    ART = os.path.join(getattr(sys, "_MEIPASS", APP_DIR), "launcher-emblem.png")
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DISC_TOOL = os.path.join(ROOT, "tools", "draconus-disc")
    CONFIG = os.path.join(ROOT, "engine", "games", "draconus", "draconus.toml")
    BINARY = os.path.join(ROOT, "engine", "build-render", "games", "draconus", "draconus_boot.exe")
    ART = os.path.join(ROOT, "tools", "launcher-emblem.png")
REPOSITORY = "https://github.com/GnomeChimpsky/Draconus-Recomp"
GAME_ID = "draconus"

# One per-user folder for everything this project writes: the launcher's settings, the
# controller bindings and the memory card all live under the engine's per-user root
# (%APPDATA%\dream-recomp on Windows). The old settings file lived in a second folder; it is still
# read when the new one does not exist, so an upgrade keeps the player's choices.
USER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(vmu.default_path(GAME_ID))))
SETTINGS = os.path.join(USER_DIR, "launcher.json")
LEGACY_SETTINGS = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "DraconusRecomp", "launcher.json"
)

IMAGE_RE = re.compile(r'^\s*image\s*=\s*"(.*)"', re.MULTILINE)

# The bottom bar's two folder buttons. The saves folder holds the card; the settings folder is the
# per-user root, so it shows launcher.json and bindings.txt beside the saves folder.
SETTINGS_DIR = USER_DIR
SAVES_DIR = os.path.dirname(vmu.default_path(GAME_ID))

# The output-device combo is built from what the engine reports at startup. The list object is
# mutated in place (AUDIO_DEVICES[:] = ...) so the TABS entry keeps pointing at it.
AUDIO_DEVICES = [("System default", "")]

# Everything the tabs can set. A new option is one entry here and one control in TABS.
DEFAULTS = {
    "scale": 1,
    "aspect": "off",
    "aspect_custom": "16:9",
    "fov": 90,
    "present_rate": 0,
    "frame_interpolation": False,
    "display_mode": "windowed",
    "vsync": True,
    "fps": False,
    "sh4_clock": 200,
    "audio": True,
    "audio_volume": 100,
    "audio_device": "",
    "audio_buffer": 0,
    "path": "translated",
    "controls": "classic",
    "look_invert": False,
}


# ----------------------------------------------------------------------------- non-UI logic

def read_image_path(config: str = CONFIG) -> str:
    with open(config, encoding="utf-8") as f:
        m = IMAGE_RE.search(f.read())
    return m.group(1) if m else ""


def write_image_path(image: str, config: str = CONFIG) -> None:
    """Point the title config at a dump. Only the image line changes."""
    with open(config, encoding="utf-8") as f:
        text = f.read()
    if not IMAGE_RE.search(text):
        raise RuntimeError("no image line in " + config)
    text = IMAGE_RE.sub('image = "%s"' % image.replace("\\", "/"), text, count=1)
    with open(config, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def verify_disc(image: str) -> tuple[bool, str]:
    """Run the project's own verifier. Returns (ok, human-readable report).

    Frozen builds carry dracdisc as a module: there is no interpreter to start, so it runs
    in-process and its output is captured from stdout.
    """
    if FROZEN:
        import contextlib
        import io
        from dracdisc import cli as _cli

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = _cli.main(["verify", image])
        report = buf.getvalue()
    else:
        result = subprocess.run(
            [sys.executable, "-m", "dracdisc", "verify", image],
            cwd=DISC_TOOL, capture_output=True, text=True,
        )
        rc = result.returncode
        report = (result.stdout or "") + (result.stderr or "")
    return rc == 0 and "VERIFY OK" in report, report.strip()


def describe_disc(report: str) -> str:
    """Pull the useful lines out of the verifier's output for the status bar."""
    keep = []
    for line in report.splitlines():
        line = line.strip()
        if line.startswith(("VERIFY OK", "Draconus:", "boot ", "ISO9660:")):
            keep.append(line)
    return "\n".join(keep) if keep else report.strip()


def load_settings() -> dict:
    s = dict(DEFAULTS)
    # The new per-user root first; the old DraconusRecomp file is the fallback for an upgrade, and
    # the next save writes it to the new place.
    for path in (SETTINGS, LEGACY_SETTINGS):
        try:
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            continue
        for k in DEFAULTS:
            if k in saved and isinstance(saved[k], type(DEFAULTS[k])):
                s[k] = saved[k]
        # Older settings had a fullscreen checkbox. A saved `true` is what borderless means now;
        # a saved `false` was the windowed default, which the new key already holds.
        if "display_mode" not in saved and saved.get("fullscreen") is True:
            s["display_mode"] = "borderless"
        if s.get("display_mode") not in ("windowed", "borderless", "exclusive"):
            s["display_mode"] = "windowed"
        break
    return s


def save_settings(s: dict) -> None:
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump({k: s[k] for k in DEFAULTS}, f, indent=2)
    except OSError:
        pass  # a read-only machine still gets to play with this run's settings


def list_audio_devices() -> list[str]:
    """The playback devices the engine reports, or [] if the build is missing or has no SDL3."""
    if not os.path.isfile(BINARY):
        return []
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [BINARY, "--list-audio-devices"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    names: list[str] = []
    for line in proc.stdout.splitlines():
        name = line.strip()
        if name and name not in names:
            names.append(name)
    return names


def audio_device_choices(saved: str = "") -> list[tuple[str, str]]:
    """Rows for the output-device combo. A saved device that is gone stays selectable (and the
    engine falls back to the default with a message), rather than silently resetting the setting."""
    names = list_audio_devices()
    choices = [("System default", "")]
    choices += [(name, name) for name in names]
    if saved and saved not in names:
        choices.append(("%s (not found)" % saved, saved))
    return choices


# --- the display's rates -------------------------------------------------------------------
#
# A present rate only looks smooth when the display can hold every picture for the same number of
# refreshes, so the list of rates to offer comes from the display rather than from a fixed table: a
# 165 Hz panel holds 120 pictures a second for one refresh and then two, which judders, while 165 is
# held for one every time. `docs/ENGINE-CHANGES.md` (patch 039) has the measurements.


class DEVMODEW(ctypes.Structure):
    """DEVMODEW, laid out so that dmDisplayFrequency lands at its real offset (184).

    The union of printing and display fields is written as its printing variant: both variants are
    16 bytes, which is all the offsets after it depend on.
    """

    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.c_ushort),
        ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort),
        ("dmDriverExtra", ctypes.c_ushort),
        ("dmFields", ctypes.c_ulong),
        ("dmOrientation", ctypes.c_short),
        ("dmPaperSize", ctypes.c_short),
        ("dmPaperLength", ctypes.c_short),
        ("dmPaperWidth", ctypes.c_short),
        ("dmScale", ctypes.c_short),
        ("dmCopies", ctypes.c_short),
        ("dmDefaultSource", ctypes.c_short),
        ("dmPrintQuality", ctypes.c_short),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", ctypes.c_ulong),
        ("dmPelsWidth", ctypes.c_ulong),
        ("dmPelsHeight", ctypes.c_ulong),
        ("dmDisplayFlags", ctypes.c_ulong),
        ("dmDisplayFrequency", ctypes.c_ulong),
        ("dmICMMethod", ctypes.c_ulong),
        ("dmICMIntent", ctypes.c_ulong),
        ("dmMediaType", ctypes.c_ulong),
        ("dmDitherType", ctypes.c_ulong),
        ("dmReserved1", ctypes.c_ulong),
        ("dmReserved2", ctypes.c_ulong),
        ("dmPanningWidth", ctypes.c_ulong),
        ("dmPanningHeight", ctypes.c_ulong),
    ]


def _devmode() -> "DEVMODEW":
    devmode = DEVMODEW()
    devmode.dmSize = ctypes.sizeof(DEVMODEW)
    return devmode


class DISPLAY_DEVICEW(ctypes.Structure):
    """DISPLAY_DEVICEW, used to ask every attached display for its modes."""

    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("DeviceName", ctypes.c_wchar * 32),
        ("DeviceString", ctypes.c_wchar * 128),
        ("StateFlags", ctypes.c_ulong),
        ("DeviceID", ctypes.c_wchar * 128),
        ("DeviceKey", ctypes.c_wchar * 128),
    ]


DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x1
DISPLAY_DEVICE_MIRRORING_DRIVER = 0x8
ENUM_CURRENT_SETTINGS = 0xFFFFFFFF


def _display_device_names(user32) -> list[str]:
    names: list[str] = []
    index = 0
    while index < 32:
        device = DISPLAY_DEVICEW()
        device.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not user32.EnumDisplayDevicesW(None, index, ctypes.byref(device), 0):
            break
        index += 1
        if not (device.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP):
            continue
        if device.StateFlags & DISPLAY_DEVICE_MIRRORING_DRIVER:
            continue
        if device.DeviceName and device.DeviceName not in names:
            names.append(device.DeviceName)
    return names


def display_refresh_rates() -> list[int]:
    """Refresh rates of every attached display, from its current mode and fullscreen modes.

    Only the current desktop mode and the modes at the desktop resolution count: a 75 Hz mode that
    exists only at 640x480 is not something a windowed 165 Hz panel can use. The game window opens
    on the primary display, but a player can move it, so all attached displays contribute.
    [] when the display cannot be asked (non-Windows or no driver).
    """
    if sys.platform != "win32":
        return []
    try:
        user32 = ctypes.windll.user32
    except (AttributeError, OSError):
        return []
    names = _display_device_names(user32)
    rates: set[int] = set()
    for name in names or [None]:
        current = _devmode()
        if not user32.EnumDisplaySettingsW(name, ENUM_CURRENT_SETTINGS,
                                          ctypes.byref(current)):
            continue
        width, height = int(current.dmPelsWidth), int(current.dmPelsHeight)
        hz = int(current.dmDisplayFrequency)
        if hz > 1:
            rates.add(hz)
        # Fullscreen modes at the desktop size are the ones an exclusive-mode present rate can
        # actually use. Enumerating every mode would add rates that belong to 640x480/800x600.
        index = 0
        while user32.EnumDisplaySettingsW(name, index, ctypes.byref(current)):
            index += 1
            if (int(current.dmPelsWidth) == width and int(current.dmPelsHeight) == height):
                hz = int(current.dmDisplayFrequency)
                if hz > 1:
                    rates.add(hz)
            if index > 512:  # a driver that never says stop must not hang the launcher
                break
    return sorted(rates)


def present_rate_choices(modes: list[int] | None = None) -> list[tuple[str, int]]:
    """Rows for the present-rate combo: rates this display can hold evenly.

    A rate only looks smooth when the panel can hold every picture for the same number of
    refreshes. Each current/fullscreen rate is offered, as is every divisor of it that is still at
    least 60 Hz (144 offers 72, 240 offers 120 and 80); a 60 Hz display therefore offers no rate
    it cannot show. With no modes at all the launcher falls back to the common targets so the
    dropdown is not empty; the engine still caps a rate the display cannot show.
    """
    modes = sorted({hz for hz in (modes or []) if hz > 1})
    if not modes:
        return [("Match the game (60 Hz)", 0), ("120 Hz", 120), ("144 Hz", 144),
                ("180 Hz", 180), ("240 Hz", 240)]

    candidates: set[int] = set()
    for hz in modes:
        if hz > 60:
            candidates.add(hz)
        for divisor in (2, 3, 4):
            if hz % divisor == 0 and hz // divisor > 60:
                candidates.add(hz // divisor)
    rows: list[tuple[str, int]] = [("Match the game (60 Hz)", 0)]
    for rate in sorted(candidates):
        rows.append(("%d Hz" % rate, rate))
    return rows


DISPLAY_REFRESH_RATES = display_refresh_rates()
PRESENT_RATE_CHOICES = present_rate_choices(DISPLAY_REFRESH_RATES)
INTERPOLATION_RATES = [rate for _, rate in PRESENT_RATE_CHOICES if rate > 60]


def aspect_ratio(aspect: str, custom: str = "16:9") -> float:
    """The width/height ratio a Widescreen setting names; 4:3 for off or an unreadable value."""
    text = str(custom if aspect == "custom" else aspect).strip()
    if text in ("", "off"):
        return 4.0 / 3.0
    try:
        if ":" in text:
            width, height = text.split(":", 1)
            ratio = float(width) / float(height)
        else:
            ratio = float(text)
    except (ValueError, ZeroDivisionError):
        return 4.0 / 3.0
    return ratio if ratio > 0 else 4.0 / 3.0


def resolution_choices(aspect: str = "off", custom: str = "16:9") -> list[tuple[str, int]]:
    """Rows for the resolution combo: the window each --scale opens at this aspect.

    The engine draws at 640x480 times the scale and opens a window whose width follows the aspect,
    with a 720-line floor (render/window_size.cpp). So 4x at 16:9 is a 2560x1440 window, not the
    4:3 render's 2560x1920, and 1x at 16:9 is a 1280x720 window showing the native render upscaled.
    """
    ratio = aspect_ratio(aspect, custom)
    rows: list[tuple[str, int]] = []
    for scale in (1, 2, 3, 4):
        # Same rounding as the engine's std::lround, including the 720-line minimum.
        height = max(int(640 * scale / ratio + 0.5), 720)
        width = int(height * ratio + 0.5)
        label = "%dx - %d x %d" % (scale, width, height)
        if scale == 1:
            label += " (native render)"
        rows.append((label, scale))
    return rows


def window_geometry(screen_w: int, screen_h: int, margin_w: int = 80,
                    margin_h: int = 140) -> tuple[int, int, int, int]:
    """The main window size and its minimum, clamped so both fit the given area.

    The window wants 1240x780, but a laptop may be 1024x600: the height floor used to be 620 and
    overrode the screen clamp, and the width ignored the screen entirely, so the launcher opened
    with its bottom or right edge off-screen. A screen too small for the preferred size wins, and
    the minimum follows the clamped window rather than the preferred one.
    """
    width = min(1240, max(320, screen_w - margin_w))
    height = min(780, max(360, screen_h - margin_h))
    return width, height, min(900, width), min(580, height)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def screen_work_area(root: "tk.Misc") -> tuple[int, int, int, int]:
    """The desktop area a window can use: the screen without the taskbar on Windows.

    `winfo_screenheight()` is the whole display, including the strip the taskbar covers. Sizing the
    window from that put its bottom buttons under the taskbar on a low-resolution laptop, where
    every pixel matters. The work area is the rectangle Windows itself uses for maximized windows.
    """
    if sys.platform == "win32":
        try:
            rect = RECT()
            # SPI_GETWORKAREA = 0x0030
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                width = int(rect.right - rect.left)
                height = int(rect.bottom - rect.top)
                if width > 0 and height > 0:
                    return int(rect.left), int(rect.top), width, height
        except (AttributeError, OSError):
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def window_placement(work: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Window width/height and top-left corner, centred in the work area.

    Centring is part of the fix: a window that is merely clamped can still be placed with its
    bottom edge against the taskbar, which is where the buttons live.
    """
    left, top, work_w, work_h = work
    width, height, _, _ = window_geometry(work_w, work_h, margin_w=40, margin_h=80)
    x = left + max(0, (work_w - width) // 2)
    y = top + max(0, (work_h - height) // 2)
    return width, height, x, y


def build_command(image: str, s: dict, extra: list[str] | None = None) -> list[str]:
    """The boot command line a settings dict describes. Pure, so --selftest can check it."""
    cmd = [BINARY, "--config", CONFIG]
    # The image is passed explicitly rather than relying on the config: a release can be
    # installed read-only, and the engine's --disc override is what makes that playable.
    if image:
        cmd += ["--disc", image]
    cmd += ["--window"]
    if int(s.get("scale", 1)) != 1:
        cmd += ["--scale", str(int(s["scale"]))]
    aspect = s.get("aspect", "off")
    if aspect == "16:9" or aspect == "21:9":
        cmd += ["--aspect", aspect]
    elif aspect == "custom" and str(s.get("aspect_custom", "")).strip():
        cmd += ["--aspect", str(s["aspect_custom"]).strip()]
    # 90 is the game's own vertical FOV, so passing it would only add a line to every command line
    # and to every settings file ever written. `or 90` rather than a defaulted get(): a stale
    # settings file without the key must not crash here.
    fov = int(s.get("fov") or 90)
    if fov != 90:
        cmd += ["--fov", str(fov)]
    if int(s.get("present_rate", 0)):
        cmd += ["--present-rate", str(int(s["present_rate"]))]
    if s.get("frame_interpolation") and int(s.get("present_rate", 0)) > 60:
        cmd += ["--frame-interpolation"]
    display_mode = str(s.get("display_mode", "windowed"))
    if display_mode != "windowed":
        cmd += ["--display", display_mode]
    if not s.get("vsync", True):
        cmd += ["--present-mode", "immediate"]
    if s.get("fps"):
        cmd += ["--fps"]
    # 200 is the console, and passing it would only add a line to every command line and to every
    # settings file ever written, so it is left to the default. `or 200` rather than a defaulted
    # get(): collect() yields None for a key that is not in DEFAULTS, and a stale settings file
    # should produce a plain 200 here rather than a crash.
    if int(s.get("sh4_clock") or 200) != 200:
        cmd += ["--sh4-clock", str(int(s["sh4_clock"]))]
    if s.get("path", "translated") == "interpreter":
        cmd += ["--interpret"]
    if s.get("controls", "classic") == "modern":
        cmd += ["--controls", "modern"]
    if s.get("look_invert"):
        cmd += ["--look-invert"]
    if not s.get("audio", True):
        cmd += ["--no-audio"]
    else:
        volume = max(0, min(100, int(s.get("audio_volume") or 100)))
        if volume != 100:
            cmd += ["--audio-volume", str(volume)]
        device = str(s.get("audio_device") or "")
        if device:
            cmd += ["--audio-device", device]
        buffer_ms = int(s.get("audio_buffer") or 0)
        if buffer_ms > 0:
            cmd += ["--audio-buffer", str(buffer_ms)]
    return cmd + (extra or [])


# ----------------------------------------------------------------------------- the tabs
#
# Each control: kind, key, label, optional help text, and kind-specific fields.
#   combo   values: [(label, value)], width (characters, default 26)
#   check   (a checkbox)                      radio  values: [(label, value)]
#   slider  min, max, suffix                  note   (a grey line of text)
#   disc    (the disc row, handled specially)

TABS = [
    ("Graphics", [
        {"kind": "note", "warn": True,
         "text": "FOV above 90\u00b0 can cull models at the screen edges; they may pop in when you "
                 "turn."},
        {"kind": "combo", "key": "sh4_clock", "label": "CPU clock",
         "values": [("200 MHz (default)", 200), ("250 MHz", 250), ("300 MHz (1.5x)", 300),
                    ("400 MHz (2x)", 400)],
         "help": "Overclocking increases the frame budget and can help raise performance when "
                 "playing at high resolutions. Be advised: overclocks might affect game speed and "
                 "audio on some machines, use with caution."},
        {"kind": "combo", "key": "scale", "label": "Resolution",
         # Replaced in the window for the aspect the player has saved; 4:3 is the build-time list.
         "values": resolution_choices(),
         "help": "Renders at a multiple of 640 x 480; the window opens at the size shown for the "
                 "selected aspect."},
        {"kind": "combo", "key": "aspect", "label": "Widescreen",
         "values": [("Off - 4:3", "off"), ("16:9 - hor+", "16:9"),
                    ("21:9 - hor+", "21:9"), ("Custom ratio - hor+", "custom")],
         "help": "Hor+ widens the field of view instead of stretching it. The HUD keeps its shape "
                 "and moves outward with the frame."},
        {"kind": "entry", "key": "aspect_custom", "label": "Custom ratio",
         "depends": ("aspect", "custom"), "width": 10,
         "help": "Two numbers, for example 32:9."},
        {"kind": "slider", "key": "fov", "label": "Field of view", "min": 60, "max": 120,
         "suffix": "\u00b0",
         "help": "The vertical field of view. A wider angle shows more of the world above and "
                 "below, and everything looks smaller; narrower zooms in. It composes with "
                 "Widescreen: the aspect and the FOV are separate parts of the projection. The "
                 "HUD and menus keep their size."},
        {"kind": "combo", "key": "present_rate", "label": "Present rate",
         "values": PRESENT_RATE_CHOICES,
         "help": "Presents up to this rate while the game logic stays at 60 Hz. The list is built "
                 "from this display's current refresh and fullscreen modes at the desktop size, "
                 "plus rates that divide them, so every picture is held for the same time. 0 "
                 "matches the game. Exclusive fullscreen can switch to a listed mode; the engine "
                 "caps a rate the display cannot show and says so."},
        {"kind": "check", "key": "frame_interpolation",
         "label": "Interpolation",
         "depends": ("present_rate", INTERPOLATION_RATES),
         "help": "Draws the frame between two guest frames instead of repeating one, so the extra "
                 "presents carry real motion. Each extra picture is a full extra render, so it "
                 "cannot raise the rate -- it fills the rate the display can already hold."},
        {"kind": "check", "key": "vsync", "label": "VSync",
         "help": "On, the picture is presented in step with the display. Off, it is presented "
                 "immediately, which tears but removes the display's pacing."},
        {"kind": "combo", "key": "display_mode", "label": "Display mode",
         "values": [("Windowed", "windowed"),
                    ("Borderless fullscreen", "borderless"),
                    ("Exclusive fullscreen", "exclusive")]},
        {"kind": "check", "key": "fps", "label": "Show the frame counter",
         "help": "Starts with the overlay on. F10 toggles it in game. It is drawn by the GPU over "
                 "the finished frame, so it costs nothing at any present rate."},
    ]),
    ("Audio", [
        {"kind": "check", "key": "audio", "label": "Enable sound",
         "help": "Off runs the game silently and skips the audio device entirely."},
        {"kind": "slider", "key": "audio_volume", "label": "Volume", "min": 0, "max": 100,
         "suffix": "%",
         "help": "Playback volume."},
        {"kind": "combo", "key": "audio_device", "label": "Output device",
         "values": AUDIO_DEVICES,
         "help": "The SDL playback devices this machine reports. A device that is unplugged is "
                 "kept in the list as '(not found)'; playing then falls back to the system default "
                 "and the engine says which device it used. The list refreshes when the dropdown "
                 "opens."},
        {"kind": "combo", "key": "audio_buffer", "label": "Audio buffer",
         "values": [("Low latency - 93 ms", 93),
                    ("Balanced - 186 ms (default)", 0),
                    ("Safe - 372 ms", 372)],
         "help": "How much audio the output queue may hold before samples are dropped. Lower keeps "
                 "sound closer to the picture; higher rides out longer frame stalls on a busy "
                 "machine. Changes take effect on the next launch."},
    ]),
    ("Game", [
        {"kind": "disc", "label": "Game disc",
         "help": "Your own dump of the USA V1.000 release. GDI and CHD images are "
                 "accepted; the launcher checks the disc before Play, so a wrong dump fails "
                 "here instead of inside the game."},
        {"kind": "combo", "key": "controls", "label": "Controls", "width": 46,
         "values": [("Classic - Dreamcast pad", "classic"),
                    ("Modern - twin-stick, LT block, RT attack", "modern")],
         "help": "Modern enables twin stick controls: left stick moves and strafes, right stick "
                 "turns. Left trigger blocks, right trigger attacks. In this mode you use d-pad "
                 "instead of left stick to navigate menus."},
        {"kind": "check", "key": "look_invert", "label": "Invert right-stick look",
         "help": "The right stick's vertical axis looks up and down and eases back to centre. "
                 "Turn this on if up feels down."},
        {"kind": "radio", "key": "path", "label": "Engine path",
         "values": [("Translated - fast", "translated"),
                    ("Interpreter - reference, slow", "interpreter")],
         "help": "The translated path is the real thing. The interpreter is the reference the "
                 "translation is checked against."},
    ]),
]

# The Game tab is first: the disc and the engine path are what a player acts on before playing.
TABS.sort(key=lambda tab: ("Game", "Graphics", "Audio").index(tab[0]))


# ----------------------------------------------------------------------------- UI

class Launcher(tk.Tk):
    BG = "#141013"
    FG = "#e8dcc8"
    DIM = "#a08c78"
    OK = "#7fc97f"    # a disc that verified
    BAD = "#e06c6c"   # no disc, or one that was rejected
    WARN = "#e0b04a"  # selected but not checked yet

    def __init__(self) -> None:
        super().__init__()
        self.title("Draconus: Cult of the Wyrm - Launcher")
        self.configure(bg=self.BG)
        try:
            # The native Windows theme draws its own backgrounds, which fight the launcher's dark
            # palette; claim a flat one for the comboboxes, checkboxes and buttons.
            ttk.Style(self).theme_use("clam")
        except tk.TclError:
            pass
        # Fit the window to the desktop's work area (above the taskbar) and centre it, so the
        # bottom bar is never flush against, or under, the taskbar on a low-resolution laptop.
        width, height, x, y = window_placement(screen_work_area(self))
        self.geometry("%dx%d+%d+%d" % (width, height, x, y))
        self.minsize(min(900, width), min(580, height))
        self.settings = load_settings()
        # Enumerate once before the tabs are built; the device combo reads this list object.
        AUDIO_DEVICES[:] = audio_device_choices(self.settings.get("audio_device", ""))
        self.image_path = self._initial_image()
        self.disc_ok = False
        self.status = tk.StringVar(value="Ready.")
        self.vars: dict[str, tk.Variable] = {}
        self.combos: dict[str, ttk.Combobox] = {}
        self._dependent: list[tuple[str, str, tk.Widget]] = []
        # The saved aspect decides the pixel counts the resolution rows show.
        self._refresh_resolution()
        self._build()
        self._sync_depends()
        self._update_disc_state()
        self.protocol("WM_DELETE_WINDOW", self._close)
        # Check the saved disc once the window is up, so a returning player sees "Disc OK".
        self.after(150, self._auto_check_disc)

    def _initial_image(self) -> str:
        try:
            path = read_image_path()
        except Exception:
            return ""
        # The shipped config carries a CHANGE-ME placeholder; that is "no disc", not a bad path.
        if not path or path.upper().startswith("CHANGE-ME"):
            return ""
        return path

    # -- layout ---------------------------------------------------------------------------
    def _build(self) -> None:
        outer = tk.Frame(self, bg=self.BG)
        outer.pack(fill="both", expand=True)

        left = tk.Frame(outer, bg=self.BG, width=360)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._build_left(left)

        right = tk.Frame(outer, bg=self.BG)
        right.pack(side="left", fill="both", expand=True, padx=(0, 16), pady=16)
        self._build_right(right)

    def _build_left(self, parent: tk.Frame) -> None:
        tk.Frame(parent, bg=self.BG, height=24).pack()
        try:
            self._art = tk.PhotoImage(file=ART)
            # Integer subsample only; the emblem is already sized for the panel (320 px wide in a
            # 360 px column), so this only shrinks it if a larger file is dropped in.
            factor = max(1, round(self._art.width() / 300))
            if factor > 1:
                self._art = self._art.subsample(factor)
            tk.Label(parent, image=self._art, bg=self.BG, bd=0).pack(pady=(10, 0))
        except tk.TclError:
            tk.Label(parent, text="(art missing)", bg=self.BG, fg=self.DIM).pack()
        tk.Label(parent, text="DRACONUS", bg=self.BG, fg=self.FG,
                 font=("Georgia", 22, "bold")).pack(pady=(18, 0))
        tk.Label(parent, text="Cult of the Wyrm", bg=self.BG, fg=self.DIM,
                 font=("Georgia", 11, "italic")).pack()
        tk.Label(parent, text="static recompilation", bg=self.BG, fg=self.DIM,
                 font=("Segoe UI", 8)).pack(pady=(6, 0))
        tk.Label(parent, text="by GnomeChimpsky", bg=self.BG, fg=self.DIM,
                 font=("Georgia", 10, "italic")).pack(pady=(28, 0))
        link = tk.Label(parent, text="Github repository", bg=self.BG, fg=self.FG,
                        font=("Segoe UI", 10, "underline"), cursor="hand2")
        link.pack(pady=(6, 0))
        link.bind("<Button-1>", lambda _e: self.open_repository())
        link.bind("<Enter>", lambda _e: link.configure(fg="#f0c674"))
        link.bind("<Leave>", lambda _e: link.configure(fg=self.FG))

    def _build_right(self, parent: tk.Frame) -> None:
        head = tk.Frame(parent, bg=self.BG)
        head.pack(fill="x")
        tk.Label(head, text="Settings", bg=self.BG, fg=self.FG,
                 font=("Segoe UI", 16, "bold")).pack(side="left")

        # The status line and the action bar are packed from the bottom before the notebook fills
        # the rest. With the old order a short window squeezed the later-packed widgets, so the
        # buttons a player presses first were the ones that fell off the bottom edge; now the
        # settings page is what gets clipped when there is not enough height.
        self.status_label = tk.Label(parent, textvariable=self.status, bg=self.BG, fg=self.DIM,
                                     anchor="w", justify="left", wraplength=560)
        self.status_label.pack(side="bottom", fill="x", pady=(8, 12))

        bar = tk.Frame(parent, bg=self.BG)
        bar.pack(side="bottom", fill="x", pady=(12, 0))
        self.action_bar = bar
        # The folders hold the things a player may want to look at outside the launcher: the card
        # the game saves to, and this window's own settings file.
        ttk.Button(bar, text="Open saves folder",
                   command=lambda: self.open_folder(SAVES_DIR)).pack(side="left")
        ttk.Button(bar, text="Open settings folder",
                   command=lambda: self.open_folder(SETTINGS_DIR)).pack(side="left", padx=(8, 0))
        self.play_button = ttk.Button(bar, text="Play", command=self.play)
        self.play_button.pack(side="right")
        ttk.Button(bar, text="Reset", command=self.reset).pack(side="right", padx=8)
        ttk.Button(bar, text="Quit", command=self._close).pack(side="right")

        nb = ttk.Notebook(parent)
        self.notebook = nb
        for name, controls in TABS:
            tab = tk.Frame(nb, bg=self.BG)
            nb.add(tab, text=name)
            self._build_tab(tab, controls)
        nb.pack(fill="both", expand=True, pady=(10, 0))

    def _build_tab(self, tab: tk.Frame, controls: list[dict]) -> None:
        tab.configure(padx=18, pady=14)
        row = 0
        for c in controls:
            kind = c["kind"]
            if kind == "note":
                fg = "#e0a030" if c.get("warn") else self.DIM
                tk.Label(tab, text=c["text"], bg=self.BG, fg=fg, anchor="w",
                         justify="left", wraplength=700).grid(
                    row=row, column=0, columnspan=2, sticky="w", pady=(8, 0))
                row += 1
                continue

            tk.Label(tab, text=c.get("label", ""), bg=self.BG, fg=self.FG, anchor="w").grid(
                row=row, column=0, sticky="w", pady=(10, 0))
            widget = self._control(tab, c)
            if widget is not None:
                widget.grid(row=row, column=1, sticky="w", padx=(18, 0), pady=(10, 0))
            row += 1
            # The explanation sits under its row rather than in a third column: a long radio label
            # or a wide combo pushed a third column off the edge of the window.
            if c.get("help"):
                tk.Label(tab, text=c["help"], bg=self.BG, fg=self.DIM, anchor="w",
                         justify="left", wraplength=720, font=("Segoe UI", 8)).grid(
                    row=row, column=0, columnspan=2, sticky="w", pady=(2, 0))
                row += 1
        tab.columnconfigure(0, minsize=190)
        tab.columnconfigure(1, weight=1)

    def _control(self, tab: tk.Frame, c: dict) -> tk.Widget | None:
        kind, key = c["kind"], c.get("key")
        if kind == "combo":
            # The StringVar is the widget's textvariable, not a label beside it: _value_for reads
            # the var, so it must be what the combobox holds. Without the binding the var stays
            # empty and every selection silently falls back to the saved setting.
            # A saved rate this display no longer reports stays selectable rather than showing a
            # blank box: the engine still honours it, and a panel whose modes changed must not
            # silently rewrite the player's setting.
            if key == "present_rate":
                saved = int(self.settings.get(key, 0) or 0)
                if saved and all(value != saved for _, value in c["values"]):
                    c["values"] = list(c["values"]) + [("%d Hz (not a mode here)" % saved, saved)]
            var = tk.StringVar(value=self._label_for(key))
            self.vars[key] = var
            labels = [label for label, _ in c["values"]]
            box = ttk.Combobox(tab, values=labels, state="readonly",
                               width=int(c.get("width", 26)), textvariable=var)
            self.combos[key] = box
            box.bind("<<ComboboxSelected>>", lambda _e: self._combo_changed(key))
            if key == "audio_device":
                box.configure(postcommand=self._refresh_audio_devices)
            return box
        if kind == "slider":
            var = tk.IntVar(value=int(self.settings.get(key, c.get("min", 0))))
            self.vars[key] = var
            frame = tk.Frame(tab, bg=self.BG)
            readout = tk.StringVar()

            def show(value, suffix=c.get("suffix", ""), target=readout):
                target.set("%d%s" % (int(float(value)), suffix))

            scale = tk.Scale(frame, from_=c.get("min", 0), to=c.get("max", 100),
                             orient="horizontal", variable=var, showvalue=False,
                             resolution=1, length=260, width=12,
                             bg=self.BG, fg=self.FG, troughcolor="#3a2f35",
                             activebackground="#c9a227", highlightthickness=0, bd=0,
                             command=show)
            scale.pack(side="left")
            tk.Label(frame, textvariable=readout, bg=self.BG, fg=self.FG, width=5,
                     anchor="w").pack(side="left", padx=(8, 0))
            show(var.get())
            return frame
        if kind == "entry":
            var = tk.StringVar(value=str(self.settings.get(key, "")))
            self.vars[key] = var
            ent = ttk.Entry(tab, textvariable=var, width=c.get("width", 18))
            if c.get("depends"):
                self._dependent.append((c["depends"][0], c["depends"][1], ent))
            if key == "aspect_custom":
                # The resolution labels follow this text, so type "32:9" and see the pixels.
                var.trace_add("write", lambda *_a: self._custom_aspect_changed())
            return ent
        if kind == "check":
            var = tk.BooleanVar(value=bool(self.settings.get(key, False)))
            self.vars[key] = var
            box = ttk.Checkbutton(tab, variable=var)
            if c.get("depends"):
                self._dependent.append((c["depends"][0], c["depends"][1], box))
            return box
        if kind == "radio":
            var = tk.StringVar(value=str(self.settings.get(key, "")))
            self.vars[key] = var
            frame = tk.Frame(tab, bg=self.BG)
            for label, value in c["values"]:
                ttk.Radiobutton(frame, text=label, value=value, variable=var).pack(
                    anchor="w")
            return frame
        if kind == "disc":
            frame = tk.Frame(tab, bg=self.BG)
            top = tk.Frame(frame, bg=self.BG)
            top.pack(anchor="w")
            self.disc_label = tk.Label(top, text=self._disc_text(), bg=self.BG, fg=self.FG,
                                       anchor="w")
            self.disc_label.pack(side="left", padx=(0, 10))
            ttk.Button(top, text="Browse...", command=self.browse_disc).pack(side="left")
            ttk.Button(top, text="Check disc", command=self.check_disc).pack(
                side="left", padx=(8, 0))
            self.disc_status = tk.Label(frame, text="", bg=self.BG, anchor="w",
                                        font=("Segoe UI", 9, "bold"))
            self.disc_status.pack(anchor="w", pady=(6, 0))
            return frame
        return None

    # -- settings plumbing ----------------------------------------------------------------
    def _label_for(self, key: str) -> str:
        for _, controls in TABS:
            for c in controls:
                if c.get("key") == key and c["kind"] == "combo":
                    for label, value in c["values"]:
                        if value == self.settings.get(key):
                            return label
        return ""

    def _value_for(self, key: str):
        for _, controls in TABS:
            for c in controls:
                if c.get("key") == key and c["kind"] == "combo":
                    label = self.vars[key].get()
                    for text, value in c["values"]:
                        if text == label:
                            return value
        return self.settings.get(key)

    def _sync_depends(self) -> None:
        for dep_key, dep_value, widget in self._dependent:
            current = self.settings.get(dep_key)
            if isinstance(dep_value, (list, tuple, set)):
                enabled = current in dep_value
            else:
                enabled = current == dep_value
            widget.configure(state="normal" if enabled else "disabled")

    def _combo_changed(self, key: str) -> None:
        self.settings[key] = self._value_for(key)
        if key == "aspect":
            self._refresh_resolution()
        self._sync_depends()

    def _refresh_resolution(self) -> None:
        """Re-label the resolution rows for the aspect now selected, keeping the scale value.

        The labels were build-time 4:3, so a player at 16:9 read "4x - 2560 x 1920" for a window
        that opens at 2560x1440. The value is the same --scale either way; only the numbers change.
        """
        control = None
        for _, controls in TABS:
            for c in controls:
                if c.get("key") == "scale":
                    control = c
                    break
        if control is None:
            return
        control["values"] = resolution_choices(self.settings.get("aspect", "off"),
                                               self.settings.get("aspect_custom", "16:9"))
        box = self.combos.get("scale")
        if box is not None:
            box.configure(values=[label for label, _ in control["values"]])
            self.vars["scale"].set(self._label_for("scale"))

    def _custom_aspect_changed(self) -> None:
        self.settings["aspect_custom"] = self.vars["aspect_custom"].get()
        if self.settings.get("aspect") == "custom":
            self._refresh_resolution()

    def _refresh_audio_devices(self) -> None:
        """Re-enumerate when the device dropdown opens, so a headset plugged in after the launcher
        started is selectable without restarting it."""
        AUDIO_DEVICES[:] = audio_device_choices(self.settings.get("audio_device", ""))
        box = self.combos.get("audio_device")
        if box is not None:
            box.configure(values=[label for label, _ in AUDIO_DEVICES])

    def collect(self) -> dict:
        for _, controls in TABS:
            for c in controls:
                if c["kind"] == "combo":
                    self.settings[c["key"]] = self._value_for(c["key"])
                elif c["kind"] == "slider":
                    self.settings[c["key"]] = int(self.vars[c["key"]].get())
                elif c["kind"] == "entry":
                    self.settings[c["key"]] = self.vars[c["key"]].get()
                elif c["kind"] in ("check", "radio"):
                    self.settings[c["key"]] = self.vars[c["key"]].get()
        return dict(self.settings)

    def reset(self) -> None:
        self.settings = dict(DEFAULTS)
        # Rebuild the window with the defaults, including the 4:3 resolution labels.
        self._refresh_resolution()
        for child in list(self.children.values()):
            child.destroy()
        self.vars.clear()
        self.combos.clear()
        self._dependent.clear()
        self._build()
        self._sync_depends()

    # -- actions --------------------------------------------------------------------------
    def open_repository(self) -> None:
        """Open the project's GitHub page in the default browser."""
        if not webbrowser.open(REPOSITORY):
            self.status.set("No browser could be opened; the repository is " + REPOSITORY)

    def open_folder(self, path: str) -> None:
        """Show a folder in the desktop's file manager, creating it if it does not exist yet.

        The saves folder is created by the engine on the first card write and the settings folder
        by the first Play; opening either before that should still work rather than fail on a path
        that is not there.
        """
        try:
            os.makedirs(path, exist_ok=True)
            if hasattr(os, "startfile"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError as exc:
            messagebox.showerror("Folder", "Cannot open %s:\n%s" % (path, exc))
        else:
            self.status.set("Opened " + path)

    def _disc_text(self) -> str:
        # The state line underneath says what is missing; this is only the file name.
        return os.path.basename(self.image_path) if self.image_path else ""

    def _set_disc_state(self, ok: bool, text: str, colour: str) -> None:
        """The one place that decides whether Play is allowed and what the disc line says."""
        self.disc_ok = ok
        if hasattr(self, "disc_status"):
            self.disc_status.configure(text=text, fg=colour)
        if hasattr(self, "play_button"):
            self.play_button.state(["!disabled"] if ok else ["disabled"])

    def _update_disc_state(self) -> None:
        if not self.image_path:
            self._set_disc_state(False, "No disc selected", self.BAD)
        elif not os.path.exists(self.image_path):
            self._set_disc_state(False, "Disc file not found", self.BAD)
        elif self.disc_ok:
            self._set_disc_state(True, "Disc OK", self.OK)
        else:
            self._set_disc_state(False, "Not checked - press Check disc", self.WARN)

    def _auto_check_disc(self) -> None:
        if self.image_path and os.path.exists(self.image_path):
            self.check_disc()
        else:
            self._update_disc_state()

    def check_disc(self) -> bool:
        """Verify the selected image; Play is only enabled for the supported disc."""
        path = self.image_path
        if not path:
            self._set_disc_state(False, "No disc selected", self.BAD)
            return False
        if not os.path.exists(path):
            self._set_disc_state(False, "Disc file not found", self.BAD)
            return False
        self.disc_status.configure(text="Checking...", fg=self.WARN)
        self.status.set("Checking " + os.path.basename(path))
        self.update_idletasks()
        ok, report = verify_disc(path)
        summary = describe_disc(report)
        if ok:
            try:
                write_image_path(path)
            except (OSError, RuntimeError) as exc:
                # A read-only release folder is a supported layout: the engine takes the image
                # with --disc, so verification is enough to play this session. Only persistence
                # is lost, and the player is told so.
                self._set_disc_state(True, "Disc OK (not saved)", self.OK)
                self.status.set(
                    "Disc OK - %s; the path could not be saved (%s). "
                    "Play will use this disc for this session." % (os.path.basename(path), exc))
                return True
            self._set_disc_state(True, "Disc OK", self.OK)
            self.status.set("Disc OK - " + os.path.basename(path))
        else:
            first = summary.splitlines()[0] if summary else "Disc rejected"
            self._set_disc_state(False, first, self.BAD)
            self.status.set("REJECTED\n" + summary)
        return ok

    def browse_disc(self) -> None:
        path = filedialog.askopenfilename(
            title="Select your Draconus disc image",
            filetypes=[("Dreamcast disc images", "*.gdi *.chd"),
                       ("GDI dump", "*.gdi"),
                       ("CHD image", "*.chd"),
                       ("All files", "*.*")],
        )
        if not path:
            return
        self.image_path = path
        self.disc_label.configure(text=self._disc_text())
        self._set_disc_state(False, "Checking...", self.WARN)
        self.status.set("Selected " + os.path.basename(path))
        self.after(50, self.check_disc)

    def play(self) -> None:
        if not self.disc_ok:
            messagebox.showerror(
                "Disc",
                "No verified disc selected.\n\nPick your own dump and press Check disc first.")
            return
        if not os.path.exists(BINARY):
            messagebox.showerror("Build", "The recompiled build is missing:\n" + BINARY)
            return
        if not self.image_path or not os.path.exists(self.image_path):
            messagebox.showerror("Disc", "The configured disc image is missing:\n" +
                                 (self.image_path or "(none)"))
            return
        s = self.collect()
        save_settings(s)
        cmd = build_command(self.image_path, s)
        self.status.set("Launching...")
        self.update_idletasks()
        try:
            subprocess.Popen(cmd, cwd=ROOT)
        except OSError as exc:
            messagebox.showerror("Launch", str(exc))
            return
        bits = []
        if int(s["scale"]) != 1:
            bits.append("%dx resolution" % int(s["scale"]))
        if s["aspect"] != "off":
            bits.append(("custom " + s["aspect_custom"]) if s["aspect"] == "custom"
                        else s["aspect"] + " hor+")
        if int(s["present_rate"]):
            bits.append("%d Hz present" % int(s["present_rate"]))
        if s.get("frame_interpolation"):
            bits.append("interpolated")
        display_mode = str(s.get("display_mode", "windowed"))
        if display_mode != "windowed":
            bits.append(display_mode)
        if s["path"] == "interpreter":
            bits.append("interpreter")
        self.status.set("Running" + ((" - " + ", ".join(bits)) if bits else "") + ".")

    def _close(self) -> None:
        try:
            save_settings(self.collect())
        finally:
            self.destroy()


# ----------------------------------------------------------------------------- tests

def selftest() -> int:
    failures = []

    def expect(name, cmd, flags):
        for f in flags:
            if f not in cmd:
                failures.append("%s: missing %s" % (name, f))

    base = {"scale": 1, "aspect": "off", "aspect_custom": "16:9", "present_rate": 0,
            "frame_interpolation": False, "display_mode": "windowed",
            "vsync": True, "fps": False, "sh4_clock": 200, "audio": True,
            "audio_volume": 100, "audio_device": "", "audio_buffer": 0,
            "path": "translated", "controls": "classic"}
    image = "C:/fixtures/draconus.gdi"

    cmd = build_command(image, base)
    if "--scale" in cmd or "--aspect" in cmd or "--interpret" in cmd:
        failures.append("defaults: unexpected flags")
    # The image must reach the engine as --disc, not only through the writable TOML: a read-only
    # release folder has to remain playable.
    expect("disc", cmd, ["--disc", image])
    cmd = build_command("", base)
    if "--disc" in cmd:
        failures.append("empty image still passed --disc")
    # The Saves tab is gone and the audio recording setting with it: the launcher must not attach a
    # card, schedule a load, or name a WAV file. The game's own VMU screens save and load, and a
    # windowed run gets the engine's per-user card with no flags.
    for stale in ("--vmu", "--press", "--wav", "--unthrottled"):
        if stale in cmd:
            failures.append("removed option still passed: %s" % stale)

    cmd = build_command(image, dict(base, scale=2, aspect="16:9", present_rate=120))
    expect("graphics", cmd, ["--scale", "2", "--aspect", "16:9", "--present-rate", "120"])

    cmd = build_command(image, dict(base, present_rate=120, frame_interpolation=True))
    expect("interpolation", cmd, ["--present-rate", "120", "--frame-interpolation"])

    cmd = build_command(image, dict(base, present_rate=60, frame_interpolation=True))
    if "--frame-interpolation" in cmd:
        failures.append("interpolation at 60 Hz: --frame-interpolation still passed")

    cmd = build_command(image, dict(base, display_mode="borderless"))
    expect("borderless", cmd, ["--display", "borderless"])

    cmd = build_command(image, dict(base, display_mode="exclusive"))
    expect("exclusive", cmd, ["--display", "exclusive"])

    cmd = build_command(image, dict(base, aspect="custom", aspect_custom="32:9"))
    expect("custom aspect", cmd, ["--aspect", "32:9"])

    cmd = build_command(image, dict(base, vsync=False, fps=True))
    expect("toggles", cmd, ["--present-mode", "immediate", "--fps"])

    cmd = build_command(image, dict(base, audio=False))
    expect("audio", cmd, ["--no-audio"])
    for flag in ("--audio-volume", "--audio-device", "--audio-buffer"):
        if flag in cmd:
            failures.append("sound off still passed %s" % flag)

    # The present-rate list comes from the display's own rates, and the labels are just the rate. A
    # 165 Hz panel that also reports 120 and 144 offers those and their even divisors (72 from 144);
    # it does not invent 180/240 modes it cannot show.
    rows = [value for _, value in present_rate_choices([60, 120, 144, 165])]
    if rows != [0, 72, 120, 144, 165]:
        failures.append("rates: 165 Hz panel produced %r" % (rows,))
    if [label for label, _ in present_rate_choices([60, 120, 144, 165])][-1] != "165 Hz":
        failures.append("rates: labels should be the rate alone")
    # A 240 Hz panel reports 240 and 120, and 240 offers 80 as its third.
    rows = [value for _, value in present_rate_choices([60, 120, 240])]
    if rows != [0, 80, 120, 240]:
        failures.append("rates: 240 Hz panel produced %r" % (rows,))
    # A 60 Hz panel must not be offered rates it cannot show.
    rows = [value for _, value in present_rate_choices([60])]
    if rows != [0]:
        failures.append("rates: 60 Hz panel produced %r" % (rows,))
    # No display to ask: the common targets, so the dropdown is never empty.
    fallback = [value for _, value in present_rate_choices([])]
    if fallback != [0, 120, 144, 180, 240]:
        failures.append("rates: fallback list changed: %r" % (fallback,))
    if DEVMODEW.dmDisplayFrequency.offset != 184 or ctypes.sizeof(DEVMODEW) != 220:
        failures.append("rates: DEVMODEW layout is %d bytes with the rate at %d" %
                        (ctypes.sizeof(DEVMODEW), DEVMODEW.dmDisplayFrequency.offset))

    # The resolution rows follow the selected aspect: 4x at 16:9 is 2560x1440, not 4:3's 2560x1920.
    # The engine's 720-line window floor applies too, so 1x wide is a 1280x720 window showing the
    # native render upscaled rather than a 640x360 window.
    labels = {scale: label for label, scale in resolution_choices("off", "16:9")}
    if labels[4] != "4x - 2560 x 1920" or labels[1] != "1x - 960 x 720 (native render)":
        failures.append("resolution 4:3: %r" % (labels,))
    labels = {scale: label for label, scale in resolution_choices("16:9", "16:9")}
    if (labels[4] != "4x - 2560 x 1440" or labels[2] != "2x - 1280 x 720"
            or labels[1] != "1x - 1280 x 720 (native render)"):
        failures.append("resolution 16:9: %r" % (labels,))
    labels = {scale: label for label, scale in resolution_choices("21:9", "16:9")}
    if labels[4] != "4x - 2560 x 1097":
        failures.append("resolution 21:9: %r" % (labels[4],))
    labels = {scale: label for label, scale in resolution_choices("custom", "32:9")}
    if labels[4] != "4x - 2560 x 720":
        failures.append("resolution 32:9: %r" % (labels[4],))
    labels = {scale: label for label, scale in resolution_choices("custom", "nonsense")}
    if labels[4] != "4x - 2560 x 1920":
        failures.append("unreadable custom ratio should fall back to 4:3: %r" % (labels[4],))

    # The window and its minimum fit the screen, including a 1024x600 laptop where the old 620 px
    # floor made the window taller than the display.
    if window_geometry(1024, 600) != (944, 460, 900, 460):
        failures.append("geometry 1024x600: %r" % (window_geometry(1024, 600),))
    if window_geometry(1920, 1080) != (1240, 780, 900, 580):
        failures.append("geometry 1920x1080: %r" % (window_geometry(1920, 1080),))

    # It is also centred inside the work area (screen minus taskbar), not just clamped: a typical
    # 768-line laptop leaves 728 pixels above the taskbar.
    if window_placement((0, 0, 1366, 728)) != (1240, 648, 63, 40):
        failures.append("placement 1366x728: %r" % (window_placement((0, 0, 1366, 728)),))
    if window_placement((1920, 0, 1920, 1040)) != (1240, 780, 2260, 130):
        failures.append("placement 1920x1040: %r" % (window_placement((1920, 0, 1920, 1040)),))

    cmd = build_command(image, dict(base, audio_volume=35, audio_device="Speakers (USB Audio)",
                                    audio_buffer=93))
    expect("audio options", cmd,
           ["--audio-volume", "35", "--audio-device", "Speakers (USB Audio)",
            "--audio-buffer", "93"])

    cmd = build_command(image, dict(base))
    for flag in ("--audio-volume", "--audio-device", "--audio-buffer"):
        if flag in cmd:
            failures.append("audio default still passed %s" % flag)

    if ("System default", "") not in audio_device_choices():
        failures.append("audio device choices lack the system default")

    cmd = build_command(image, dict(base, path="interpreter"))
    expect("path", cmd, ["--interpret"])

    cmd = build_command(image, dict(base, controls="modern"))
    expect("controls", cmd, ["--controls", "modern"])
    cmd = build_command(image, dict(base, controls="classic"))
    if "--controls" in cmd:
        failures.append("classic controls still passed --controls")

    cmd = build_command(image, dict(base, fov=75))
    expect("field of view", cmd, ["--fov", "75"])
    cmd = build_command(image, dict(base))
    if "--fov" in cmd:
        failures.append("default field of view still passed --fov")

    cmd = build_command(image, dict(base, look_invert=True))
    expect("invert look", cmd, ["--look-invert"])
    cmd = build_command(image, dict(base))
    if "--look-invert" in cmd:
        failures.append("default look direction passed --look-invert")

    # The tab spec must cover every default, or a control would be silently unset.
    keys = set()
    for _, controls in TABS:
        for c in controls:
            if "key" in c:
                keys.add(c["key"])
    missing = set(DEFAULTS) - keys
    if missing:
        failures.append("defaults with no control: " + ", ".join(sorted(missing)))

    print("FAILED:" if failures else "SELFTEST OK")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


def check_ui(app: Launcher) -> list[str]:
    """What the controls *do*, not just what they display.

    A combobox that keeps its choice to itself shows the new label and quietly builds the old
    command line; --selftest cannot see that, because it never touches a widget. Select the two
    values a widescreen player selects and check the command line, then put them back.
    """
    failures = []

    def pick(key: str, label: str) -> None:
        box = app.combos[key]
        box.set(label)
        box.event_generate("<<ComboboxSelected>>")
        app.update()

    def pick_value(key: str, value) -> None:
        """Select a combo row by its value: the labels change with the aspect."""
        for _, controls in TABS:
            for c in controls:
                if c.get("key") == key and c["kind"] == "combo":
                    for label, candidate in c["values"]:
                        if candidate == value:
                            pick(key, label)
                            return
        failures.append("no %s=%r row" % (key, value))

    pick_value("scale", 4)
    pick("aspect", "16:9 - hor+")
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    for flag in ("--scale", "4", "--aspect", "16:9"):
        if flag not in cmd:
            failures.append("4x + 16:9 lost %r: %s" % (flag, " ".join(cmd)))
    if app.vars["scale"].get() != "4x - 2560 x 1440":
        failures.append("resolution label at 16:9: %r" % (app.vars["scale"].get(),))

    pick("aspect", "Off - 4:3")
    if app.vars["scale"].get() != "4x - 2560 x 1920":
        failures.append("resolution label at 4:3: %r" % (app.vars["scale"].get(),))
    pick_value("scale", 1)
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    for flag in ("--scale", "--aspect"):
        if flag in cmd:
            failures.append("defaults kept %r: %s" % (flag, " ".join(cmd)))

    # A custom ratio names its own height; the labels follow it as it is typed.
    pick("aspect", "Custom ratio - hor+")
    app.vars["aspect_custom"].set("32:9")
    app.update()
    if app.vars["scale"].get() != "1x - 2560 x 720 (native render)":
        failures.append("resolution label at 32:9: %r" % (app.vars["scale"].get(),))
    app.vars["aspect_custom"].set("16:9")
    pick("aspect", "Off - 4:3")

    # Every dropdown must show a label for the value it holds. A combo whose key is missing from
    # DEFAULTS renders as an empty box and silently keeps the engine's default: the CPU clock did
    # exactly that, and neither --selftest nor a command-line check could see it, because a blank
    # box still collects the right value. This catches the whole class, not just that one row.
    for _, controls in TABS:
        for c in controls:
            if c["kind"] != "combo":
                continue
            shown = app.vars[c["key"]].get()
            if not shown:
                failures.append("dropdown %r came up blank (is %r in DEFAULTS?)" % (c["key"], c["key"]))
            elif shown not in [label for label, _ in c["values"]]:
                failures.append("dropdown %r shows %r, which is not one of its values"
                                % (c["key"], shown))

    # And the CPU clock reaches the command line when it is set, and does not when it is not.
    pick("sh4_clock", "300 MHz (1.5x)")
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    if "--sh4-clock" not in cmd or "300" not in cmd:
        failures.append("300 MHz lost --sh4-clock: %s" % " ".join(cmd))
    pick("sh4_clock", "200 MHz (default)")
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    if "--sh4-clock" in cmd:
        failures.append("200 MHz kept --sh4-clock: %s" % " ".join(cmd))

    pick("controls", "Modern - twin-stick, LT block, RT attack")
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    if "--controls" not in cmd or "modern" not in cmd:
        failures.append("modern controls lost --controls modern: %s" % " ".join(cmd))
    pick("controls", "Classic - Dreamcast pad")
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    if "--controls" in cmd:
        failures.append("classic controls kept --controls: %s" % " ".join(cmd))

    # The FOV slider must reach the command line, and its 90-degree default must not.
    app.vars["fov"].set(75)
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    if "--fov" not in cmd or "75" not in cmd:
        failures.append("field-of-view slider lost --fov: %s" % " ".join(cmd))
    app.vars["fov"].set(90)
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    if "--fov" in cmd:
        failures.append("90-degree field of view kept --fov: %s" % " ".join(cmd))

    app.vars["look_invert"].set(True)
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    if "--look-invert" not in cmd:
        failures.append("invert-look checkbox lost --look-invert: %s" % " ".join(cmd))
    app.vars["look_invert"].set(False)

    # The volume slider must reach the command line; a Scale that only moves its own handle is
    # the same defect as a combo that only changes its text.
    app.vars["audio_volume"].set(40)
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    if "--audio-volume" not in cmd or "40" not in cmd:
        failures.append("volume slider lost --audio-volume: %s" % " ".join(cmd))
    app.vars["audio_volume"].set(100)
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    if "--audio-volume" in cmd:
        failures.append("100%% volume kept --audio-volume: %s" % " ".join(cmd))

    # The tabs that remain, and their order: Game first, because the disc comes before settings.
    names = [app.notebook.tab(i, "text") for i in range(len(app.notebook.tabs()))]
    if names != ["Game", "Graphics", "Audio"]:
        failures.append("tabs: %r" % names)

    # Clamping and centring are unit-tested; this is the real window, so a regression in the
    # wiring still shows. The window must fit the work area (the screen above the taskbar).
    work = screen_work_area(app)
    if (app.winfo_width() > work[2] or app.winfo_height() > work[3]
            or app.winfo_x() < work[0] or app.winfo_y() < work[1]):
        failures.append("window %dx%d+%d+%d does not fit the work area %r" % (
            app.winfo_width(), app.winfo_height(), app.winfo_x(), app.winfo_y(), work))

    # A low-resolution laptop gets a window too short for the settings page. The buttons must stay
    # reachable: shrink below the instance minimum and check the action bar is still on screen.
    saved_geometry, saved_min = app.geometry(), app.minsize()
    app.minsize(600, 360)
    app.geometry("900x420")
    app.update()
    bar = app.action_bar
    if not bar.winfo_ismapped():
        failures.append("action bar disappeared in a short window")
    elif bar.winfo_rooty() + bar.winfo_height() > app.winfo_rooty() + app.winfo_height():
        failures.append("action bar bottom is outside the short window")
    app.minsize(*saved_min)
    app.geometry(saved_geometry)
    app.update()

    # The disc row gates Play. Nothing selected must mean no Play, whatever the saved settings say.
    saved_image, saved_ok = app.image_path, app.disc_ok
    app.image_path = ""
    app._update_disc_state()
    if "disabled" not in app.play_button.state():
        failures.append("Play is enabled with no disc selected")
    if app.disc_status.cget("text") != "No disc selected":
        failures.append("disc state with no disc: %r" % app.disc_status.cget("text"))
    # Put the real disc back so the window the screenshot shows is the one a player gets.
    app.image_path, app.disc_ok = saved_image, saved_ok
    app.disc_label.configure(text=app._disc_text())
    app._update_disc_state()

    # The bottom bar's folder buttons are what is left of the old Saves tab: saving and loading are
    # the game's own now, but the card and the settings file still need to be findable.
    def texts(widget: tk.Widget) -> list[str]:
        found = []
        for child in widget.winfo_children():
            try:
                found.append(str(child.cget("text")))
            except tk.TclError:
                pass
            found += texts(child)
        return found

    labels = texts(app)
    for label in ("Open saves folder", "Open settings folder"):
        if label not in labels:
            failures.append("bottom bar: %r button missing" % label)
    for label in ("by GnomeChimpsky", "Github repository"):
        if label not in labels:
            failures.append("left panel: %r missing" % label)

    # The repository link must open the project's page and nothing else.
    opened: list[str] = []
    real_open = webbrowser.open
    webbrowser.open = lambda url: opened.append(url) or True  # type: ignore[assignment]
    try:
        app.open_repository()
    finally:
        webbrowser.open = real_open  # type: ignore[assignment]
    if opened != [REPOSITORY]:
        failures.append("repository link opened %r, expected %r" % (opened, REPOSITORY))
    return failures


def smoke(shot: str | None = None) -> int:
    app = Launcher()
    app.update_idletasks()
    app.update()
    # Verify whatever disc is configured before the screenshot: the window a player sees should
    # show the real state, and a disc that no longer verifies is a failure, not a pretty picture.
    disc_ok = None
    if app.image_path and os.path.exists(app.image_path):
        disc_ok = app.check_disc()
    failures = check_ui(app)
    if disc_ok is False:
        failures.append("the configured disc did not verify")
    if shot:
        # For checking the layout without a human: raise the window and grab every tab.
        try:
            from PIL import ImageGrab
            app.lift()
            app.attributes("-topmost", True)
            app.update()
            notebook = app.notebook
            for i in range(len(notebook.tabs())):
                notebook.select(i)
                app.update()
                x, y = app.winfo_rootx(), app.winfo_rooty()
                w, h = app.winfo_width(), app.winfo_height()
                out = shot if len(notebook.tabs()) == 1 else "%s-%d.png" % (shot[:-4], i)
                ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(out)
                print("wrote", out)
        except Exception as exc:  # no Pillow, or no interactive desktop
            print("screenshot failed:", exc)
    app.destroy()
    for f in failures:
        print("  -", f)
    print("SMOKE OK" if not failures else "SMOKE FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--shot", default=None)
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    if args.smoke:
        sys.exit(smoke(args.shot))
    Launcher().mainloop()
