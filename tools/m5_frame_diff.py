"""Per-checkpoint frame diff: our render against Flycast's, same guest frame.

  python tools/m5_frame_diff.py --our work/m5/our --flycast work/m5/flycast \
      --frames 900,2400,3000,3600,5400,5600,6000,6200,6600,6800 --threshold 16

Both sides must be the same size. The metric is the mean absolute RGB difference
(0-255). Threshold 16 is calibrated here: a correct pair measures 1.5-14.6, while a
pair from two different screens measures 27-38. Side-by-side composites and a diff
heatmap can be written for review.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--our", required=True)
    ap.add_argument("--flycast", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--threshold", type=float, default=16.0)
    ap.add_argument("--sbs", default="", help="write side-by-side and diff images here")
    args = ap.parse_args()

    frames = [int(f) for f in args.frames.split(",") if f.strip()]
    if args.sbs:
        os.makedirs(args.sbs, exist_ok=True)

    failed = []
    print(f"{'frame':>6}  {'MAE':>6}  {'RMSE':>6}  {'>32':>6}  {'p95':>4}  result")
    for f in frames:
        a_path = os.path.join(args.our, f"f{f:04d}.png")
        b_path = os.path.join(args.flycast, f"f{f:04d}.png")
        if not os.path.exists(a_path) or not os.path.exists(b_path):
            print(f"{f:6d}  missing image: {a_path if not os.path.exists(a_path) else b_path}")
            failed.append(f)
            continue
        a, b = load(a_path), load(b_path)
        if a.shape != b.shape:
            print(f"{f:6d}  size mismatch: {a.shape[1]}x{a.shape[0]} vs {b.shape[1]}x{b.shape[0]}")
            failed.append(f)
            continue
        d = np.abs(a - b)
        mae = float(d.mean())
        rmse = float(np.sqrt(((a - b) ** 2).mean()))
        over32 = float((d.max(2) > 32).mean() * 100.0)
        p95 = float(np.percentile(d.max(2), 95))
        ok = mae <= args.threshold
        if not ok:
            failed.append(f)
        print(
            f"{f:6d}  {mae:6.2f}  {rmse:6.2f}  {over32:5.2f}%  {p95:4.0f}  "
            f"{'ok' if ok else 'FAIL'}"
        )
        if args.sbs:
            im_a = Image.open(a_path).convert("RGB")
            im_b = Image.open(b_path).convert("RGB")
            sbs = Image.new("RGB", (im_a.width * 2 + 8, im_a.height), (0, 0, 0))
            sbs.paste(im_a, (0, 0))
            sbs.paste(im_b, (im_a.width + 8, 0))
            ImageDraw.Draw(sbs).text((4, 4), f"{f}: ours | flycast", fill=(255, 255, 0))
            sbs.save(os.path.join(args.sbs, f"sbs-{f}.png"))
            heat = np.clip(d.max(2) * 4, 0, 255).astype(np.uint8)
            Image.fromarray(heat).save(os.path.join(args.sbs, f"diff-{f}.png"))

    print()
    if failed:
        print(f"FRAME DIFF FAILED at {len(failed)} checkpoint(s): {failed}")
        return 1
    print(f"FRAME DIFF OK: {len(frames)} checkpoint(s) at or below MAE {args.threshold:g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
