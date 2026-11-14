#!/usr/bin/env python3
"""Audio measurements for the M6 gate.

M6 asks for three things:

  1. ten seconds of music spectra matched against Flycast;
  2. ten minutes without dropouts;
  3. a WAV capture diff.

This tool supplies the measurements behind all three. It reads ordinary RIFF/WAVE files, plus the
raw s16le PCM that Flycast's SDL disk driver writes (``raw2wav``). Everything is deterministic: the
same two files always give the same numbers.

  python tools/audio-check.py info work/ours.wav
  python tools/audio-check.py align work/flycast.wav work/ours.wav
  python tools/audio-check.py compare work/flycast.wav work/ours.wav --gate
  python tools/audio-check.py gaps work/ours_10min.wav --reference work/flycast_10min.wav
  python tools/audio-check.py raw2wav work/fc.raw work/fc.wav

``compare`` finds the offset between two captures from their loudness envelopes, then compares the
loudest ten-second window common to both. A capture pair that carries the same music scores high
even when one machine reaches the music seconds earlier, which is the normal case here: the
recompiled build reaches the title about eight seconds before Flycast does.

The gate thresholds are deliberately about the music, not about bit-exactness. Two honest AICA
implementations can differ in effect send, resampling and level; they cannot differ in the notes.
So the pass conditions are sample correlation, per-frame spectral correlation, octave-band level
agreement and dominant-peak agreement, and each one has to hold across the whole window.
"""

import argparse
import math
import sys
import wave

try:
    import numpy as np
    from scipy import signal
except ImportError as exc:  # pragma: no cover - a tooling error, not a code path
    raise SystemExit("audio-check needs numpy and scipy: %s" % exc)


# --- files ------------------------------------------------------------------------------------


def read_wav(path):
    """Return (mono float32, [left, right] float32 or None, rate)."""
    with wave.open(path, "rb") as w:
        channels = w.getnchannels()
        width = w.getsampwidth()
        rate = w.getframerate()
        count = w.getnframes()
        raw = w.readframes(count)
    if width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise SystemExit("%s: unsupported sample width %d" % (path, width))
    if channels == 1:
        left = right = None
        mono = data
    else:
        frames = data.reshape(-1, channels)
        left = frames[:, 0]
        right = frames[:, 1] if channels > 1 else frames[:, 0]
        mono = frames.mean(axis=1, dtype=np.float32)
    return mono, (left, right), rate


def write_wav(path, samples, rate, channels):
    """Write float32 interleaved samples clamped to 16-bit PCM."""
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = np.round(pcm * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def read_raw_s16le(path, channels):
    raw = open(path, "rb").read()
    if len(raw) % (2 * channels):
        raw = raw[: len(raw) - (len(raw) % (2 * channels))]
    return raw


def resample_to(x, rate, target):
    if rate == target:
        return x
    from math import gcd

    g = gcd(rate, target)
    return signal.resample_poly(x, target // g, rate // g).astype(np.float32)


# --- measurements -----------------------------------------------------------------------------


def db(x):
    return 20.0 * math.log10(max(float(x), 1e-12))


def rms(x):
    if len(x) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def envelope(x, rate, step=0.05):
    n = int(round(step * rate))
    if n <= 0:
        raise ValueError("bad envelope step")
    usable = len(x) // n * n
    if usable == 0:
        return np.zeros(0, dtype=np.float32)
    return np.sqrt(np.mean(np.square(x[:usable].reshape(-1, n), dtype=np.float64), axis=1)).astype(
        np.float32
    )


def best_envelope_lag(reference, candidate, rate, max_seconds=30.0):
    """Find the time offset between two captures.

    The returned offset follows ``candidate_time = reference_time + offset``: a positive value
    means the candidate reaches the same sound later than the reference. This is the convention
    the rest of the tool uses.
    """
    ea = envelope(reference, rate)
    eb = envelope(candidate, rate)
    if len(ea) == 0 or len(eb) == 0:
        return 0.0, 0.0
    ea = ea - ea.mean()
    eb = eb - eb.mean()
    denom = float(np.sqrt(np.dot(ea, ea) * np.dot(eb, eb))) or 1.0
    corr = signal.correlate(ea, eb, mode="full", method="fft") / denom
    lags = signal.correlation_lags(len(ea), len(eb), mode="full")
    limit = int(max_seconds / 0.05)
    mask = np.abs(lags) <= limit
    if not mask.any():
        return 0.0, 0.0
    # Mask first, then take the absolute value: taking abs of a -inf sentinel would make every
    # out-of-range lag an infinite maximum and the first index would always win.
    masked = np.where(mask, np.abs(corr), -1.0)
    idx = int(np.argmax(masked))
    # scipy correlates the reference first and the candidate second: a peak at lag k means
    # candidate[n] == reference[n + k], so candidate_time = reference_time - k.
    return -float(lags[idx]) * 0.05, float(corr[idx])


def refine_lag(reference, candidate, rate, coarse_seconds, search=0.25, window=10.0):
    """Refine an envelope lag to the nearest sample with FFT cross-correlation.

    Only one ten-second slice is used, around the loudest part of the candidate, so a ten-minute
    capture costs the same as a ten-second one. The slice is wide enough that a musical phrase
    gives an unambiguous peak.
    """
    cstart = loudest_window(candidate, rate, window)
    rstart = cstart - coarse_seconds
    pad = int(round(0.25 * rate))
    ca = max(0, int(round(cstart * rate)) - pad)
    cb = min(len(candidate), ca + int(round(window * rate)) + 2 * pad)
    ra = max(0, int(round(rstart * rate)) - pad)
    rb = min(len(reference), ra + int(round(window * rate)) + 2 * pad)
    a = reference[ra:rb].astype(np.float64)
    b = candidate[ca:cb].astype(np.float64)
    if len(a) < rate // 2 or len(b) < rate // 2:
        return coarse_seconds, 0.0
    corr = signal.correlate(a, b, mode="full", method="fft")
    lags = signal.correlation_lags(len(a), len(b), mode="full")
    # The candidate starts at ca, the reference slice at ra. scipy's full correlation has
    # corr[k] = sum a[n + lag] * b[n], so b[n] matches a[n + lag]: candidate time ca + n
    # matches reference time ra + n + lag, and the offset we report is
    # candidate - reference = ca - ra - lag.
    offset = (ca - ra) - lags
    # Search only around the lag the envelope gave us. Masking the absolute offset instead would
    # reject every candidate when the captures start far apart.
    expected_lag = (ca - ra) - coarse_seconds * rate
    limit = int(round(search * rate))
    mask = np.abs(lags - expected_lag) <= limit
    if not mask.any():
        return coarse_seconds, 0.0
    denom = math.sqrt(float(np.dot(a, a)) * float(np.dot(b, b))) or 1.0
    corr = corr / denom
    idx = int(np.argmax(np.where(mask, corr, -1.0)))
    return float(offset[idx]) / rate, float(corr[idx])


def stft_mag(x, rate, n_fft=4096, hop=1024):
    f, t, z = signal.stft(
        x, fs=rate, nperseg=n_fft, noverlap=n_fft - hop, nfft=n_fft, boundary=None, padded=False
    )
    return f, t, np.abs(z)


def spectral_metrics(reference, candidate, rate, window_seconds=10.0):
    """Compare one window of each signal. Both signals must already be time-aligned."""
    n = min(len(reference), len(candidate), int(round(window_seconds * rate)))
    if n < rate:
        raise SystemExit("not enough aligned audio for a one-second comparison")
    a = reference[:n].astype(np.float64)
    b = candidate[:n].astype(np.float64)

    # Sample-level agreement, after a local alignment search of +/- 50 ms.
    search = int(0.05 * rate)
    best = (0, -2.0)
    for lag in range(-search, search + 1, 8):
        ca = max(0, lag)
        cb = min(len(a), len(b) + lag)
        x = a[ca:cb]
        y = b[ca - lag : cb - lag]
        n2 = min(len(x), len(y))
        if n2 < rate // 2:
            continue
        x = x[:n2]
        y = y[:n2]
        d = math.sqrt(float(np.dot(x, x)) * float(np.dot(y, y))) or 1.0
        score = float(np.dot(x, y)) / d
        if score > best[1]:
            best = (lag, score)
    lag = best[0]
    # Refine to the sample.
    for l in range(lag - 8, lag + 9):
        ca = max(0, l)
        cb = min(len(a), len(b) + l)
        x = a[ca:cb]
        y = b[ca - l : cb - l]
        n2 = min(len(x), len(y))
        if n2 < rate // 2:
            continue
        x = x[:n2]
        y = y[:n2]
        d = math.sqrt(float(np.dot(x, x)) * float(np.dot(y, y))) or 1.0
        score = float(np.dot(x, y)) / d
        if score > best[1]:
            best = (l, score)
    lag, sample_corr = best
    if lag:
        ca = max(0, lag)
        cb = min(len(a), len(b) + lag)
        a = a[ca:cb]
        b = b[ca - lag : cb - lag]
        n = min(len(a), len(b))
        a = a[:n]
        b = b[:n]

    fa, ta, za = stft_mag(a, rate)
    fb, tb, zb = stft_mag(b, rate)
    frames = min(za.shape[1], zb.shape[1])
    za = za[:, :frames]
    zb = zb[:, :frames]
    # Log magnitude, with the very top of the band removed: it is mostly codec/antialias noise.
    band = (fa >= 40.0) & (fa <= 16000.0)
    la = np.log10(za[band] + 1e-7)
    lb = np.log10(zb[band] + 1e-7)

    frame_corr = []
    frame_cos = []
    for i in range(frames):
        x = la[:, i]
        y = lb[:, i]
        if x.std() < 1e-9 or y.std() < 1e-9:
            continue  # a silent STFT frame has no spectrum to compare
        frame_corr.append(float(np.corrcoef(x, y)[0, 1]))
        xc = x - x.mean()
        yc = y - y.mean()
        denom = float(np.linalg.norm(xc) * np.linalg.norm(yc)) or 1.0
        frame_cos.append(float(np.dot(xc, yc) / denom))
    if not frame_corr:
        raise SystemExit("no non-silent frames in the comparison window")
    frame_corr = np.asarray(frame_corr)
    frame_cos = np.asarray(frame_cos)

    # Octave bands. Level is reported relative to the whole signal, so a gain difference does not
    # masquerade as a spectral difference.
    edges = [40, 80, 160, 320, 640, 1280, 2560, 5120, 10240, 16000]
    fa2, pa = signal.welch(a, fs=rate, nperseg=8192, noverlap=4096)
    fb2, pb = signal.welch(b, fs=rate, nperseg=8192, noverlap=4096)
    band_db = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (fa2 >= lo) & (fa2 < hi)
        if not m.any():
            continue
        # Normalize each side by its own total power, so a plain gain difference cancels and this
        # measures the shape of the spectrum rather than its absolute level.
        ea = float(np.sum(pa[m]) / (np.sum(pa) + 1e-15))
        eb = float(np.sum(pb[m]) / (np.sum(pb) + 1e-15))
        band_db.append(10.0 * math.log10((ea + 1e-15) / (eb + 1e-15)))
    band_db = np.asarray(band_db)

    def peaks(x):
        f, p = signal.welch(x, fs=rate, nperseg=8192, noverlap=4096)
        idx = signal.find_peaks(10.0 * np.log10(p + 1e-15), distance=5)[0]
        idx = idx[np.argsort(p[idx])[-12:]]
        return np.sort(f[idx])

    peaks_a = peaks(a)
    peaks_b = peaks(b)
    matched = 0
    for f in peaks_a:
        if np.any(np.abs(peaks_b - f) <= max(1.5, 0.01 * f)):
            matched += 1

    def centroid(x):
        f, p = signal.welch(x, fs=rate, nperseg=8192, noverlap=4096)
        return float(np.sum(f * p) / (np.sum(p) + 1e-15))

    difference = np.abs(a - b)
    return {
        "seconds": n / rate,
        "lag_ms": lag * 1000.0 / rate,
        "sample_corr": float(sample_corr),
        "samples": n,
        "sample_diff_fraction": float(np.count_nonzero(difference) / max(1, n)),
        "sample_diff_max": float(difference.max()) if n else 0.0,
        "sample_diff_rms": float(np.sqrt(np.mean(np.square(difference)))) if n else 0.0,
        "frame_corr_mean": float(frame_corr.mean()),
        "frame_corr_median": float(np.median(frame_corr)),
        "frame_corr_min": float(frame_corr.min()),
        "frame_cos_median": float(np.median(frame_cos)),
        "band_db_max_abs": float(np.max(np.abs(band_db))),
        "band_db": band_db,
        "peaks_a": peaks_a,
        "peaks_b": peaks_b,
        "peaks_matched": matched,
        "centroid_a": centroid(a),
        "centroid_b": centroid(b),
        "rms_a": rms(a),
        "rms_b": rms(b),
    }


def loudest_window(x, rate, seconds=10.0):
    """Start time of the loudest `seconds`-long window, measured in 100 ms blocks."""
    step = max(1, int(0.1 * rate))
    n = int(round(seconds * rate))
    count = (len(x) - n) // step + 1
    if count <= 0:
        return 0.0
    squares = np.square(x, dtype=np.float64)
    cumulative = np.concatenate(([0.0], np.cumsum(squares)))
    starts = np.arange(count, dtype=np.int64) * step
    energies = cumulative[starts + n] - cumulative[starts]
    return float(np.argmax(energies) * step) / rate


def gaps(x, rate, threshold_db=-72.0, min_seconds=0.25, step=0.05):
    """Return runs of near-silence as (start_seconds, length_seconds, mean_rms)."""
    e = envelope(x, rate, step)
    if len(e) == 0:
        return []
    level = np.where(e > 0, 20.0 * np.log10(np.maximum(e, 1e-12)), -120.0)
    silent = level < threshold_db
    runs = []
    i = 0
    while i < len(silent):
        if not silent[i]:
            i += 1
            continue
        j = i
        while j < len(silent) and silent[j]:
            j += 1
        seconds = (j - i) * step
        if seconds >= min_seconds:
            runs.append((i * step, seconds, float(np.mean(e[i:j]))))
        i = j
    return runs


# --- commands ---------------------------------------------------------------------------------


def cmd_info(args):
    mono, (left, right), rate = read_wav(args.file)
    seconds = len(mono) / rate
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    nonzero = float(np.count_nonzero(mono)) / max(1, len(mono))
    print("file       %s" % args.file)
    print("format     %d Hz, %s, %.3f s" % (rate, "stereo" if left is not None else "mono", seconds))
    print("peak       %d  (%.1f dBFS)" % (round(peak * 32767), db(peak)))
    print("rms        %d  (%.1f dBFS)" % (round(rms(mono) * 32767), db(rms(mono))))
    print("non-zero   %.1f %%" % (100.0 * nonzero))
    if left is not None:
        side = float(np.corrcoef(left, right)[0, 1]) if len(left) > 1 else 0.0
        print("L/R corr   %.3f" % side)
    e = envelope(mono, rate)
    print("silent     %.1f %% of 50 ms windows below %.0f dBFS" % (
        100.0 * float(np.mean(e < 10 ** (args.threshold / 20.0))) if len(e) else 0.0, args.threshold))
    if seconds <= 120:
        sec = int(math.ceil(seconds))
        print("")
        print(" t(s)      rms     peak  ")
        for i in range(sec):
            seg = mono[i * rate : (i + 1) * rate]
            if len(seg) == 0:
                break
            r = rms(seg)
            p = float(np.max(np.abs(seg)))
            print(
                "%4d  %8d  %6d  %s"
                % (i, round(r * 32767), round(p * 32767), "#" * min(50, int(r * 32767 / 80)))
            )


def cmd_align(args):
    ref, _, rr = read_wav(args.reference)
    cand, _, cr = read_wav(args.candidate)
    if rr != cr:
        cand = resample_to(cand, cr, rr)
    lag, corr = best_envelope_lag(ref, cand, rr, args.max_offset)
    fine, fine_corr = refine_lag(ref, cand, rr, lag, search=0.25)
    print("envelope lag   %+.2f s (corr %.3f)" % (lag, corr))
    print("refined lag    %+.3f s (sample corr %.4f over the overlap)" % (fine, fine_corr))
    print("reading        candidate time = reference time %+.3f s; %s" % (
        fine, "candidate is earlier" if fine < 0 else "candidate is later"))


def cmd_compare(args):
    ref, _, rr = read_wav(args.reference)
    cand, _, cr = read_wav(args.candidate)
    if rr != cr:
        cand = resample_to(cand, cr, rr)
        cr = rr

    if args.offset is not None:
        offset = args.offset
        offset_corr = 1.0
    else:
        offset, _ = best_envelope_lag(ref, cand, cr, args.max_offset)
        offset, offset_corr = refine_lag(ref, cand, cr, offset, search=0.25)

    # The comparison window. Explicit starts win; otherwise use the loudest ten seconds of the
    # candidate and take the matching moment in the reference.
    if args.candidate_start is not None:
        cstart = args.candidate_start
        rstart = args.reference_start if args.reference_start is not None else cstart - offset
    elif args.reference_start is not None:
        rstart = args.reference_start
        cstart = rstart + offset
    else:
        cstart = loudest_window(cand, cr, args.window)
        rstart = cstart - offset

    # Keep both windows inside their captures.
    if rstart < 0:
        cstart -= rstart
        rstart = 0.0
    if cstart < 0:
        rstart -= cstart
        cstart = 0.0
    end = min(len(ref) / rr - rstart, len(cand) / cr - cstart)
    if end < 1.0:
        raise SystemExit("the captures overlap by less than a second at this offset")
    window = min(args.window, end)

    a = ref[int(round(rstart * rr)) : int(round((rstart + window) * rr))]
    b = cand[int(round(cstart * cr)) : int(round((cstart + window) * cr))]
    m = spectral_metrics(a, b, rr, window)

    print("reference  %s" % args.reference)
    print("candidate  %s" % args.candidate)
    print("offset     %+.3f s (candidate time = reference time + offset, corr %.4f)" % (
        offset, offset_corr))
    print("window     reference %.2f s / candidate %.2f s, %.2f s long" % (rstart, cstart, window))
    print("")
    print("sample correlation      %.4f" % m["sample_corr"])
    print("sample diff             %.2f %% of samples differ, rms %.1f LSB, worst %.0f LSB" % (
        100.0 * m["sample_diff_fraction"], m["sample_diff_rms"] * 32767.0,
        m["sample_diff_max"] * 32767.0))
    print("spectral correlation    mean %.4f  median %.4f  min %.4f" % (
        m["frame_corr_mean"], m["frame_corr_median"], m["frame_corr_min"]))
    print("spectral cosine         median %.4f" % m["frame_cos_median"])
    print("octave band difference  worst %.2f dB" % m["band_db_max_abs"])
    print("dominant peaks          %d of %d matched" % (m["peaks_matched"], len(m["peaks_a"])))
    print("centroid                %.1f Hz vs %.1f Hz" % (m["centroid_a"], m["centroid_b"]))
    print("rms                     %d vs %d" % (round(m["rms_a"] * 32767), round(m["rms_b"] * 32767)))
    print("")
    print("  band (Hz)    ref-cand")
    edges = ["40-80", "80-160", "160-320", "320-640", "640-1k3", "1k3-2k6", "2k6-5k1", "5k1-10k", "10k-16k"]
    for label, d in zip(edges, m["band_db"]):
        print("  %-9s   %+6.2f dB" % (label, d))

    if args.gate:
        problems = []
        if m["sample_corr"] < args.min_sample_corr:
            problems.append("sample corr %.3f < %.2f" % (m["sample_corr"], args.min_sample_corr))
        if m["frame_corr_median"] < args.min_spectral_corr:
            problems.append(
                "spectral corr %.3f < %.2f" % (m["frame_corr_median"], args.min_spectral_corr)
            )
        if m["band_db_max_abs"] > args.max_band_db:
            problems.append("band diff %.2f dB > %.2f" % (m["band_db_max_abs"], args.max_band_db))
        if m["peaks_matched"] < args.min_peaks:
            problems.append("peaks %d < %d" % (m["peaks_matched"], args.min_peaks))
        if m["sample_diff_rms"] * 32767.0 > args.max_diff_rms:
            problems.append(
                "sample diff rms %.0f LSB > %.0f"
                % (m["sample_diff_rms"] * 32767.0, args.max_diff_rms)
            )
        if m["sample_diff_max"] * 32767.0 > args.max_lsb:
            problems.append(
                "sample diff %.0f LSB > %.0f" % (m["sample_diff_max"] * 32767.0, args.max_lsb)
            )
        print("")
        if problems:
            print("SPECTRA FAIL: " + "; ".join(problems))
            return 1
        print("SPECTRA OK")
    return 0


def cmd_gaps(args):
    mono, _, rate = read_wav(args.file)
    runs = gaps(mono, rate, args.threshold, args.min_silence, args.step)
    total = len(mono) / rate
    covered = sum(r[1] for r in runs)
    print("file       %s" % args.file)
    print("length     %.3f s" % total)
    print("threshold  %.0f dBFS, %.2f s minimum, %.0f ms windows" % (
        args.threshold, args.min_silence, args.step * 1000))
    print("gaps       %d, %.3f s total (%.1f %% of the capture)" % (
        len(runs), covered, 100.0 * covered / total if total else 0.0))
    if not runs:
        if args.gate and args.reference:
            print("")
            print("DROP-OUTS OK: the capture has no gaps at all")
        return 0
    if runs:
        print("")
        print("  start      length   mean rms   reading")
        ref = None
        silent_ref = None
        offset = None
        first_sound = None
        if args.reference:
            ref, _, rr = read_wav(args.reference)
            if rr != rate:
                ref = resample_to(ref, rr, rate)
                rr = rate
            offset, corr = best_envelope_lag(ref, mono, rate, args.max_offset)
            offset, corr = refine_lag(ref, mono, rate, offset, search=0.25)
            ref_env = envelope(ref, rate, args.step)
            silent_ref = ref_env < 10 ** (args.threshold / 20.0)
            ref_runs = gaps(ref, rate, args.threshold, args.min_silence, args.step)
            cand_env = envelope(mono, rate, args.step)
            non_silent = np.flatnonzero(cand_env >= 10 ** (args.threshold / 20.0))
            first_sound = float(non_silent[0]) * args.step if len(non_silent) else None
            print("  reference %s, candidate offset %+.3f s" % (args.reference, offset))
            print("")
        for start, length, mean in runs:
            reading = "silence"
            if ref is not None:
                # Candidate time t corresponds to reference time t - offset.
                rs = (start - offset) / args.step
                re = (start + length - offset) / args.step
                lo = max(0, int(round(rs)))
                hi = min(len(silent_ref), int(round(re)))
                if hi <= lo:
                    reading = "outside the reference"
                else:
                    fraction = float(np.mean(silent_ref[lo:hi]))
                    mapped = start - offset
                    # Match the whole run, not a fixed window: the two captures drift apart by a
                    # fraction of a second over ten minutes, and a 54 s gap is still the same gap
                    # when its edges move by one second.
                    matched_run = None
                    for ref_start, ref_length, _ in ref_runs:
                        if (abs(ref_start - mapped) <= max(1.5, 0.15 * length + 1.0)
                                and abs(ref_length - length) <= max(1.0, 0.3 * length)):
                            matched_run = (ref_start, ref_length)
                            break
                    if first_sound is not None and start < first_sound:
                        reading = "pre-roll (before the candidate's first sound)"
                    elif matched_run is not None:
                        reading = "same gap in reference at %.2f s (%.2f s)" % matched_run
                    elif fraction >= 0.5:
                        reading = "also silent in reference (%.0f%% of the window)" % (
                            100.0 * fraction
                        )
                    else:
                        reading = "DROPOUT: reference is sounding here (%.0f%% silent)" % (
                            100.0 * fraction
                        )
            print("  %8.2f  %7.2f  %8d   %s" % (start, length, round(mean * 32767), reading))
        if ref is not None:
            unexpected = 0
            outside = 0
            for start, length, mean in runs:
                if first_sound is not None and start < first_sound:
                    continue
                rs = (start - offset) / args.step
                re = (start + length - offset) / args.step
                lo = max(0, int(round(rs)))
                hi = min(len(silent_ref), int(round(re)))
                if hi <= lo:
                    outside += 1
                    continue
                mapped = start - offset
                matched = any(
                    abs(ref_start - mapped) <= max(1.5, 0.15 * length + 1.0)
                    and abs(ref_length - length) <= max(1.0, 0.3 * length)
                    for ref_start, ref_length, _ in ref_runs
                )
                if not matched and float(np.mean(silent_ref[lo:hi])) < 0.5:
                    unexpected += 1
            print("")
            if unexpected:
                print("DROPOUTS: %d gap(s) are sounding in the reference" % unexpected)
                return 1
            if outside:
                print("UNVERIFIED: %d gap(s) fall outside the reference; capture the full "
                      "ten minutes before calling this gate" % outside)
                return 1
            print("DROP-OUTS OK: every gap is silent in the reference too")
    if args.gate:
        # Without a reference, the gate is only "these are the gaps"; that is a weaker claim and
        # is stated as such.
        if runs and ref is None:
            longest = max(r[1] for r in runs)
            print("")
            print("note: without --reference this reports gaps, not whether they are intended")
            print("longest gap %.2f s" % longest)
    return 0


def cmd_raw2wav(args):
    # Copy the samples byte for byte. Going through float would turn -32768 into -32767 and put a
    # one-LSB dent in the reference the WAV diff is supposed to measure.
    raw = read_raw_s16le(args.raw, args.channels)
    with wave.open(args.wav, "wb") as w:
        w.setnchannels(args.channels)
        w.setsampwidth(2)
        w.setframerate(args.rate)
        w.writeframes(raw)
    print("wrote %s: %.3f s, %d Hz, %d channel(s)" % (
        args.wav, len(raw) / (2.0 * args.rate * args.channels), args.rate, args.channels))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("info", help="format, level and a per-second RMS table for short captures")
    pi.add_argument("file")
    pi.add_argument("--threshold", type=float, default=-72.0)
    pi.set_defaults(func=cmd_info)

    pa = sub.add_parser("align", help="find the time offset between two captures")
    pa.add_argument("reference")
    pa.add_argument("candidate")
    pa.add_argument("--max-offset", type=float, default=30.0)
    pa.set_defaults(func=cmd_align)

    pc = sub.add_parser("compare", help="compare ten seconds of spectra")
    pc.add_argument("reference")
    pc.add_argument("candidate")
    pc.add_argument("--window", type=float, default=10.0)
    pc.add_argument("--offset", type=float, default=None,
                    help="candidate time = reference time + offset (default: align automatically)")
    pc.add_argument("--reference-start", type=float, default=None)
    pc.add_argument("--candidate-start", type=float, default=None)
    pc.add_argument("--max-offset", type=float, default=30.0)
    pc.add_argument("--gate", action="store_true")
    pc.add_argument("--min-sample-corr", type=float, default=0.95)
    pc.add_argument("--min-spectral-corr", type=float, default=0.85)
    pc.add_argument("--max-band-db", type=float, default=3.0)
    pc.add_argument("--min-peaks", type=int, default=8)
    pc.add_argument("--max-diff-rms", type=float, default=512.0,
                    help="largest allowed RMS sample difference after alignment, in 16-bit LSB")
    pc.add_argument("--max-lsb", type=float, default=8192.0,
                    help="largest allowed single-sample difference after alignment, in 16-bit LSB")
    pc.set_defaults(func=cmd_compare)

    pg = sub.add_parser("gaps", help="find silent runs, optionally against a reference")
    pg.add_argument("file")
    pg.add_argument("--reference", default=None)
    pg.add_argument("--threshold", type=float, default=-72.0)
    pg.add_argument("--min-silence", type=float, default=0.25)
    pg.add_argument("--step", type=float, default=0.05)
    pg.add_argument("--max-offset", type=float, default=30.0)
    pg.add_argument("--gate", action="store_true")
    pg.set_defaults(func=cmd_gaps)

    pr = sub.add_parser("raw2wav", help="convert Flycast's SDL disk-driver raw PCM to WAV")
    pr.add_argument("raw")
    pr.add_argument("wav")
    pr.add_argument("--rate", type=int, default=44100)
    pr.add_argument("--channels", type=int, default=2)
    pr.set_defaults(func=cmd_raw2wav)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
