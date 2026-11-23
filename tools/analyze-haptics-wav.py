"""Report where a rendered 4-channel DualSense stream puts its energy.

`--render` writes what the pad's DAC is handed. A voice coil turns everything into sound as well as
motion, and the question "is this click audible or is it felt" is really "how much of it is above a few
hundred hertz". Prints per-band energy for the two actuator channels, plus the step statistics that
catch a discontinuity (a click) as opposed to a tone (a buzz).

    python work/analyze_wav.py FILE.wav [FILE2.wav ...]
"""
import struct
import sys

import numpy as np


def read_wav(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise SystemExit(f"{path}: not a RIFF/WAVE file")
    pos = 12
    fmt = None
    while pos + 8 <= len(data):
        tag = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if tag == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif tag == b"data":
            channels, rate = fmt[1], fmt[2]
            samples = np.frombuffer(body, dtype="<i2").astype(np.float64) / 32767.0
            return samples.reshape(-1, channels), rate
        pos += 8 + size + (size & 1)
    raise SystemExit(f"{path}: no data chunk")


def bands(x, rate):
    if len(x) < 1024:
        return {}
    window = np.hanning(len(x))
    spec = np.abs(np.fft.rfft(x * window)) ** 2
    freqs = np.fft.rfftfreq(len(x), 1.0 / rate)
    total = spec.sum() or 1.0
    edges = [(0, 40), (40, 150), (150, 400), (400, 2000), (2000, rate / 2)]
    return {f"{lo}-{hi} Hz": spec[(freqs >= lo) & (freqs < hi)].sum() / total
            for lo, hi in edges}


def report(path):
    data, rate = read_wav(path)
    print(f"{path}: {data.shape[0]} frames, {data.shape[1]} ch @ {rate} Hz")
    for ch in range(data.shape[1]):
        x = data[:, ch]
        peak = float(np.max(np.abs(x)))
        rms = float(np.sqrt(np.mean(x * x)))
        steps = np.abs(np.diff(x))
        step_max = float(steps.max()) if len(steps) else 0.0
        step_over = int((steps > 0.20).sum())
        label = ("speaker L", "speaker R", "actuator L", "actuator R")[ch]
        print(f"  ch{ch} {label:<11} peak {peak:.3f} rms {rms:.3f} "
              f"max step {step_max:.3f} steps>0.20 {step_over}")
        if ch >= 2 and rms > 1e-6:
            b = bands(x, rate)
            print("      energy: " + "  ".join(f"{k} {100 * v:.1f}%" for k, v in b.items()))
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for path in sys.argv[1:]:
        report(path)
