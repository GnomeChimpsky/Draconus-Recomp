#!/usr/bin/env python3
r"""DraconusRecomp launcher: pick a dump, verify it, choose options, play.

The non-UI half (verification, config rewrite, command line) is separated into functions so it
can be exercised without a window:  python tools/launcher.py --selftest

Run with:  python tools/launcher.py      (or tools\launcher.bat)
"""

from __future__ import annotations

import argparse
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

IMAGE_RE = re.compile(r'^\s*image\s*=\s*"(.*)"', re.MULTILINE)


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


def build_command(image: str, scale: int, translated: bool, extra: list[str]) -> list[str]:
    cmd = [BINARY, "--config", CONFIG, "--window"]
    if scale != 1:
        cmd += ["--scale", str(scale)]
    if not translated:
        cmd += ["--interpret"]
    return cmd + extra


# ----------------------------------------------------------------------------- UI

class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("DraconusRecomp - Draconus: Cult of the Wyrm")
        self.minsize(640, 380)
        self.image = tk.StringVar(value=self._initial_image())
        self.scale = tk.IntVar(value=1)
        self.translated = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Pick a .gdi dump, or use the one already configured.")
        self._build()

    def _initial_image(self) -> str:
        try:
            return read_image_path()
        except Exception:
            return ""

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Disc image (.gdi)").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.image).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse...", command=self.browse).grid(row=0, column=2, **pad)
        ttk.Button(frm, text="Verify", command=self.verify).grid(row=0, column=3, **pad)

        box = ttk.LabelFrame(frm, text="Options", padding=8)
        box.grid(row=1, column=0, columnspan=4, sticky="ew", **pad)
        ttk.Label(box, text="Window scale").pack(side="left")
        ttk.Spinbox(box, from_=1, to=4, width=3, textvariable=self.scale).pack(side="left", padx=6)
        ttk.Radiobutton(box, text="Interpreter (faster today)", variable=self.translated,
                        value=False).pack(side="left", padx=8)
        ttk.Radiobutton(box, text="Translated (slower, correct)", variable=self.translated,
                        value=True).pack(side="left")

        ttk.Button(frm, text="Play", command=self.play).grid(row=2, column=0, columnspan=4,
                                                             sticky="ew", **pad)
        info = ttk.Label(frm, textvariable=self.status, justify="left", anchor="w")
        info.grid(row=3, column=0, columnspan=4, sticky="new", **pad)
        frm.rowconfigure(3, weight=1)

    def browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a Draconus .gdi dump",
            filetypes=[("GDI dumps", "*.gdi"), ("All files", "*.*")],
        )
        if path:
            self.image.set(path)
            self.status.set("Selected. Press Verify, then Play.")

    def verify(self) -> None:
        image = self.image.get()
        if not image or not os.path.exists(image):
            messagebox.showerror("Disc", "That file does not exist.")
            return
        self.status.set("Verifying...")
        self.update_idletasks()
        ok, report = verify_disc(image)
        self.status.set(describe_disc(report) if ok else "REJECTED\n" + describe_disc(report))
        if ok:
            write_image_path(image)

    def play(self) -> None:
        image = self.image.get()
        if not os.path.exists(BINARY):
            messagebox.showerror("Build", "The recompiled build is missing:\n" + BINARY)
            return
        cmd = build_command(image, self.scale.get(), self.translated.get(), [])
        self.status.set("Launching...")
        self.update_idletasks()
        try:
            subprocess.Popen(cmd, cwd=ROOT)
        except OSError as exc:
            messagebox.showerror("Launch", str(exc))
            return
        self.status.set(
            "Running.\n" + ("Translated path: correct but slower until more of the game is "
                            "translated (docs/ENGINE-CHANGES.md)." if self.translated.get() else
                            "Interpreter path: the faster configuration today."))


def selftest() -> int:
    failures = []
    image = read_image_path()
    print("config image:", image or "<none>")
    if not image:
        failures.append("no image path in the config")
    ok_cmd = build_command(image, 1, False, ["--max-frames", "1"])
    if "--interpret" not in ok_cmd:
        failures.append("interpreter path missing from the command")
    trans = build_command(image, 2, True, [])
    if "--interpret" in trans or "--scale" not in trans:
        failures.append("translated/scale options wrong")
    if image and os.path.exists(image):
        ok, report = verify_disc(image)
        print("verify:", "OK" if ok else "REJECTED")
        print(describe_disc(report)[:300])
        if not ok:
            failures.append("the configured dump did not verify")
    else:
        print("configured dump missing; skipping verification")
    print("FAILED:" if failures else "SELFTEST OK")
    for f in failures:
        print("  -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    Launcher().mainloop()
