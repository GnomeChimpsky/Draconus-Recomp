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
import json
import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISC_TOOL = os.path.join(ROOT, "tools", "draconus-disc")
CONFIG = os.path.join(ROOT, "engine", "games", "draconus", "draconus.toml")
BINARY = os.path.join(ROOT, "engine", "build-render", "games", "draconus", "draconus_boot.exe")
ART = os.path.join(ROOT, "tools", "launcher-art.png")
SETTINGS = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "DraconusRecomp", "launcher.json"
)
BINDINGS = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "dream-recomp", "dream-recomp",
    "bindings.txt",
)

IMAGE_RE = re.compile(r'^\s*image\s*=\s*"(.*)"', re.MULTILINE)

# Everything the tabs can set. A new option is one entry here and one control in TABS.
DEFAULTS = {
    "scale": 1,
    "aspect": "off",
    "aspect_custom": "16:9",
    "present_rate": 0,
    "vsync": True,
    "fps": False,
    "audio": True,
    "wav": "",
    "wav_on": False,
    "unthrottled": False,
    "path": "translated",
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
    """Run the project's own verifier. Returns (ok, human-readable report)."""
    result = subprocess.run(
        [sys.executable, "-m", "dracdisc", "verify", image],
        cwd=DISC_TOOL, capture_output=True, text=True,
    )
    report = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0 and "VERIFY OK" in report, report.strip()


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
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            saved = json.load(f)
        for k in DEFAULTS:
            if k in saved and isinstance(saved[k], type(DEFAULTS[k])):
                s[k] = saved[k]
    except (OSError, ValueError):
        pass
    return s


def save_settings(s: dict) -> None:
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump({k: s[k] for k in DEFAULTS}, f, indent=2)
    except OSError:
        pass  # a read-only machine still gets to play with this run's settings


def build_command(image: str, s: dict, extra: list[str] | None = None) -> list[str]:
    """The boot command line a settings dict describes. Pure, so --selftest can check it."""
    cmd = [BINARY, "--config", CONFIG, "--window"]
    if int(s.get("scale", 1)) != 1:
        cmd += ["--scale", str(int(s["scale"]))]
    aspect = s.get("aspect", "off")
    if aspect == "16:9" or aspect == "21:9":
        cmd += ["--aspect", aspect]
    elif aspect == "custom" and str(s.get("aspect_custom", "")).strip():
        cmd += ["--aspect", str(s["aspect_custom"]).strip()]
    if int(s.get("present_rate", 0)):
        cmd += ["--present-rate", str(int(s["present_rate"]))]
    if not s.get("vsync", True):
        cmd += ["--present-mode", "immediate"]
    if s.get("fps"):
        cmd += ["--fps"]
    if s.get("unthrottled"):
        cmd += ["--unthrottled"]
    if s.get("path", "translated") == "interpreter":
        cmd += ["--interpret"]
    if not s.get("audio", True):
        cmd += ["--no-audio"]
    wav = str(s.get("wav", "")).strip()
    if s.get("wav_on") and wav:
        cmd += ["--wav", wav]
    return cmd + (extra or [])


# ----------------------------------------------------------------------------- the tabs
#
# Each control: kind, key, label, optional help text, and kind-specific fields.
#   combo   values: [(label, value)]           entry  depends: (key, value)
#   check   (a checkbox)                        radio  values: [(label, value)]
#   button  action: name                        note   (a grey line of text)
#   disc    (the disc row, handled specially)   wav    (checkbox + path + browse)

TABS = [
    ("Graphics", [
        {"kind": "combo", "key": "scale", "label": "Resolution",
         "values": [("1x - 640 x 480 (native)", 1), ("2x - 1280 x 960", 2),
                    ("3x - 1920 x 1440", 3), ("4x - 2560 x 1920", 4)],
         "help": "Draws the 3D at a multiple of the guest's resolution; the game still sees "
                 "640 x 480, so nothing about it changes."},
        {"kind": "combo", "key": "aspect", "label": "Widescreen",
         "values": [("Off - 4:3", "off"), ("16:9 - hor+", "16:9"),
                    ("21:9 - hor+", "21:9"), ("Custom ratio - hor+", "custom")],
         "help": "hor+ widens the field of view instead of stretching it: more world to the sides, "
                 "and the HUD keeps its shape and moves outward with the frame."},
        {"kind": "entry", "key": "aspect_custom", "label": "Custom ratio",
         "depends": ("aspect", "custom"), "width": 10,
         "help": "Two numbers, for example 32:9."},
        {"kind": "combo", "key": "present_rate", "label": "Present rate",
         "values": [("Match the game (60 Hz)", 0), ("120 Hz", 120), ("144 Hz", 144)],
         "help": "The display refreshes at this rate while the game logic stays at 60 Hz. Frames "
                 "are repeated, not interpolated."},
        {"kind": "check", "key": "vsync", "label": "VSync",
         "help": "On, the picture is presented in step with the display. Off, it is presented "
                 "immediately, which tears but removes the display's pacing."},
        {"kind": "check", "key": "fps", "label": "Show the frame counter",
         "help": "Starts with the overlay on. F10 toggles it in game."},
    ]),
    ("Audio", [
        {"kind": "check", "key": "audio", "label": "Enable sound",
         "help": "Off runs the game silently and skips the audio device entirely."},
        {"kind": "wav", "key": "wav", "label": "Record the audio to a WAV file",
         "help": "Writes 16-bit stereo 44.1 kHz beside whatever path you choose. Recording works "
                 "whether or not sound is enabled."},
        {"kind": "note", "text": "Volume and output device selection arrive with the audio "
                                 "milestone (M6)."},
    ]),
    ("Gameplay", [
        {"kind": "radio", "key": "path", "label": "Engine path",
         "values": [("Translated - fast", "translated"),
                    ("Interpreter - reference, slow", "interpreter")],
         "help": "The translated path is the real thing. The interpreter is the reference the "
                 "translation is checked against."},
        {"kind": "check", "key": "unthrottled", "label": "Unthrottled (benchmarking)",
         "help": "Runs as fast as the host can instead of at the game's own clock. Useful for "
                 "measuring; games play wrong at the wrong speed."},
        {"kind": "button", "action": "bindings", "label": "Controller bindings",
         "text": "Open bindings file...",
         "help": "Opens the per-user bindings file. In game, F1 (or the pad's select button) opens "
                 "the same screen."},
        {"kind": "disc", "label": "Game disc"},
    ]),
]


# ----------------------------------------------------------------------------- UI

class Launcher(tk.Tk):
    BG = "#141013"
    FG = "#e8dcc8"
    DIM = "#a08c78"

    def __init__(self) -> None:
        super().__init__()
        self.title("Draconus: Cult of the Wyrm - Launcher")
        self.configure(bg=self.BG)
        self.geometry("1240x660")
        self.minsize(900, 580)
        self.settings = load_settings()
        self.image_path = self._initial_image()
        self.status = tk.StringVar(value="Ready.")
        self.vars: dict[str, tk.Variable] = {}
        self.combos: dict[str, ttk.Combobox] = {}
        self._dependent: list[tuple[str, str, tk.Widget]] = []
        self._build()
        self._sync_depends()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _initial_image(self) -> str:
        try:
            return read_image_path()
        except Exception:
            return ""

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
            # Integer subsample only; the art is 560x720 and the panel wants about 280 wide.
            factor = max(1, round(self._art.width() / 280))
            if factor > 1:
                self._art = self._art.subsample(factor)
            tk.Label(parent, image=self._art, bg=self.BG, bd=0).pack()
        except tk.TclError:
            tk.Label(parent, text="(art missing)", bg=self.BG, fg=self.DIM).pack()
        tk.Label(parent, text="DRACONUS", bg=self.BG, fg=self.FG,
                 font=("Georgia", 22, "bold")).pack(pady=(18, 0))
        tk.Label(parent, text="Cult of the Wyrm", bg=self.BG, fg=self.DIM,
                 font=("Georgia", 11, "italic")).pack()
        tk.Label(parent, text="static recompilation", bg=self.BG, fg=self.DIM,
                 font=("Segoe UI", 8)).pack(pady=(6, 0))

    def _build_right(self, parent: tk.Frame) -> None:
        head = tk.Frame(parent, bg=self.BG)
        head.pack(fill="x")
        tk.Label(head, text="Settings", bg=self.BG, fg=self.FG,
                 font=("Segoe UI", 16, "bold")).pack(side="left")
        tk.Label(head, text="changes are saved when you play", bg=self.BG, fg=self.DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=12)

        nb = ttk.Notebook(parent)
        self.notebook = nb
        nb.pack(fill="both", expand=True, pady=(10, 12))
        for name, controls in TABS:
            tab = tk.Frame(nb, bg=self.BG)
            nb.add(tab, text=name)
            self._build_tab(tab, controls)

        bar = tk.Frame(parent, bg=self.BG)
        bar.pack(fill="x")
        ttk.Button(bar, text="Play", command=self.play).pack(side="right")
        ttk.Button(bar, text="Reset", command=self.reset).pack(side="right", padx=8)
        ttk.Button(bar, text="Quit", command=self._close).pack(side="right")
        tk.Label(parent, textvariable=self.status, bg=self.BG, fg=self.DIM, anchor="w",
                 justify="left", wraplength=560).pack(fill="x", pady=(10, 0))

    def _build_tab(self, tab: tk.Frame, controls: list[dict]) -> None:
        tab.configure(padx=18, pady=14)
        row = 0
        for c in controls:
            kind = c["kind"]
            if kind == "note":
                tk.Label(tab, text=c["text"], bg=self.BG, fg=self.DIM, anchor="w",
                         justify="left", wraplength=700).grid(
                    row=row, column=0, columnspan=2, sticky="w", pady=(18, 0))
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
            var = tk.StringVar(value=self._label_for(key))
            self.vars[key] = var
            labels = [label for label, _ in c["values"]]
            box = ttk.Combobox(tab, values=labels, state="readonly", width=26,
                               textvariable=var)
            self.combos[key] = box
            box.bind("<<ComboboxSelected>>", lambda _e: self._combo_changed(key))
            return box
        if kind == "entry":
            var = tk.StringVar(value=str(self.settings.get(key, "")))
            self.vars[key] = var
            ent = ttk.Entry(tab, textvariable=var, width=c.get("width", 18))
            if c.get("depends"):
                self._dependent.append((c["depends"][0], c["depends"][1], ent))
            return ent
        if kind == "check":
            var = tk.BooleanVar(value=bool(self.settings.get(key, False)))
            self.vars[key] = var
            return ttk.Checkbutton(tab, variable=var)
        if kind == "radio":
            var = tk.StringVar(value=str(self.settings.get(key, "")))
            self.vars[key] = var
            frame = tk.Frame(tab, bg=self.BG)
            for label, value in c["values"]:
                ttk.Radiobutton(frame, text=label, value=value, variable=var).pack(
                    anchor="w")
            return frame
        if kind == "button":
            return ttk.Button(tab, text=c.get("text", c.get("label", "")),
                              command=self._action(c["action"]))
        if kind == "wav":
            frame = tk.Frame(tab, bg=self.BG)
            var_on = tk.BooleanVar(value=bool(self.settings.get("wav_on", False)))
            self.vars["wav_on"] = var_on
            ttk.Checkbutton(frame, text="record", variable=var_on).pack(side="left")
            var = tk.StringVar(value=str(self.settings.get("wav", "")))
            self.vars["wav"] = var
            ent = ttk.Entry(frame, textvariable=var, width=22)
            ent.pack(side="left", padx=6)
            ttk.Button(frame, text="...", width=3,
                       command=lambda: self._pick_wav()).pack(side="left")
            return frame
        if kind == "disc":
            frame = tk.Frame(tab, bg=self.BG)
            self.disc_label = tk.Label(frame, text=self._disc_text(), bg=self.BG, fg=self.DIM,
                                       anchor="w")
            self.disc_label.pack(side="left", padx=(0, 8))
            ttk.Button(frame, text="Change disc...", command=self.browse_disc).pack(side="left")
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
            state = "normal" if self.settings.get(dep_key) == dep_value else "disabled"
            widget.configure(state=state)

    def _combo_changed(self, key: str) -> None:
        self.settings[key] = self._value_for(key)
        self._sync_depends()

    def _action(self, name: str):
        if name == "bindings":
            return self.open_bindings
        return lambda: None

    def collect(self) -> dict:
        for _, controls in TABS:
            for c in controls:
                if c["kind"] == "combo":
                    self.settings[c["key"]] = self._value_for(c["key"])
                elif c["kind"] == "entry":
                    self.settings[c["key"]] = self.vars[c["key"]].get()
                elif c["kind"] == "wav":
                    self.settings["wav"] = self.vars["wav"].get()
                    self.settings["wav_on"] = self.vars["wav_on"].get()
                elif c["kind"] in ("check", "radio"):
                    self.settings[c["key"]] = self.vars[c["key"]].get()
        return dict(self.settings)

    def reset(self) -> None:
        self.settings = dict(DEFAULTS)
        for _, controls in TABS:
            for c in controls:
                key, kind = c.get("key"), c["kind"]
                if kind == "combo" and key in self.vars:
                    pass
        # rebuild the window with the defaults
        for child in list(self.children.values()):
            child.destroy()
        self.vars.clear()
        self.combos.clear()
        self._dependent.clear()
        self._build()
        self._sync_depends()

    # -- actions --------------------------------------------------------------------------
    def open_bindings(self) -> None:
        if os.path.exists(BINDINGS):
            try:
                os.startfile(BINDINGS)  # type: ignore[attr-defined]
                self.status.set("Opened " + BINDINGS)
            except OSError as exc:
                messagebox.showerror("Bindings", str(exc))
        else:
            messagebox.showinfo(
                "Bindings",
                "No bindings file yet.\n\nStart the game and press F1 (or the pad's select\n"
                "button) to open the binding screen; it saves to\n" + BINDINGS,
            )

    def _pick_wav(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Record the audio to", defaultextension=".wav",
            filetypes=[("WAV files", "*.wav"), ("All files", "*.*")],
        )
        if path:
            self.settings["wav"] = path
            self.vars["wav"].set(path)

    def _disc_text(self) -> str:
        if not self.image_path:
            return "(no disc configured)"
        return os.path.basename(self.image_path)

    def browse_disc(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a Draconus .gdi dump",
            filetypes=[("GDI dumps", "*.gdi"), ("All files", "*.*")],
        )
        if not path:
            return
        self.status.set("Verifying...")
        self.update_idletasks()
        ok, report = verify_disc(path)
        if not ok:
            self.status.set("REJECTED\n" + describe_disc(report))
            messagebox.showerror("Disc", "That dump did not verify:\n\n" + describe_disc(report))
            return
        write_image_path(path)
        self.image_path = path
        self.disc_label.configure(text=self._disc_text())
        self.status.set("Disc verified and saved. " + describe_disc(report).splitlines()[0])

    def play(self) -> None:
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
            "vsync": True, "fps": False, "audio": True, "wav": "", "unthrottled": False,
            "path": "translated"}
    image = "G:/dumps/draconus.gdi"

    cmd = build_command(image, base)
    if "--scale" in cmd or "--aspect" in cmd or "--interpret" in cmd:
        failures.append("defaults: unexpected flags")

    cmd = build_command(image, dict(base, scale=2, aspect="16:9", present_rate=120))
    expect("graphics", cmd, ["--scale", "2", "--aspect", "16:9", "--present-rate", "120"])

    cmd = build_command(image, dict(base, aspect="custom", aspect_custom="32:9"))
    expect("custom aspect", cmd, ["--aspect", "32:9"])

    cmd = build_command(image, dict(base, vsync=False, fps=True, unthrottled=True))
    expect("toggles", cmd, ["--present-mode", "immediate", "--fps", "--unthrottled"])

    cmd = build_command(image, dict(base, audio=False, wav="C:/tmp/run.wav", wav_on=True))
    expect("audio", cmd, ["--no-audio", "--wav", "C:/tmp/run.wav"])

    cmd = build_command(image, dict(base, path="interpreter"))
    expect("path", cmd, ["--interpret"])

    # The tab spec must cover every default, or a control would be silently unset.
    keys = set()
    for _, controls in TABS:
        for c in controls:
            if "key" in c:
                keys.add(c["key"])
            if c["kind"] == "wav":
                keys.add("wav_on")
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

    pick("scale", "4x - 2560 x 1920")
    pick("aspect", "16:9 - hor+")
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    for flag in ("--scale", "4", "--aspect", "16:9"):
        if flag not in cmd:
            failures.append("4x + 16:9 lost %r: %s" % (flag, " ".join(cmd)))

    pick("scale", "1x - 640 x 480 (native)")
    pick("aspect", "Off - 4:3")
    cmd = build_command(app.image_path or "disc.gdi", app.collect())
    for flag in ("--scale", "--aspect"):
        if flag in cmd:
            failures.append("defaults kept %r: %s" % (flag, " ".join(cmd)))
    return failures


def smoke(shot: str | None = None) -> int:
    app = Launcher()
    app.update_idletasks()
    app.update()
    failures = check_ui(app)
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
