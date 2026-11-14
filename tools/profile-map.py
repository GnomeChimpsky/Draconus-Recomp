"""Resolve sampled addresses against the MSVC link map that /MAP writes.

The launcher's DREAM_PROFILE diagnostic prints module-relative offsets ('rva'); this turns them into
the function names the map carries, so a profile reads as `DcMemory::read32` and `fn_0c1582a0`
rather than as hex. Usage:

    python tools\\profile-map.py <draconus_boot.map> <profile.txt> [--top N]

<profile.txt> is a run's stdout; every "profile:   rva X  Y%  N" line in it is resolved and the rows
are re-printed with names, largest sample count first.
"""
import re
import sys

# 0001:0001efa0       ?fn_0c018380@gen@dream@@YAXAEAUCtx@sh4@2@AEAVMemory@2@@Z 000000014001ffa0 f ...
PUBLIC = re.compile(r"^\s+0001:[0-9a-fA-F]{8}\s+(\S+)\s+([0-9a-fA-F]{16})\s")
SAMPLE = re.compile(r"profile:\s+rva\s+([0-9a-fA-F]+)\s+([\d.]+)%\s+(\d+)")


def demangle(name: str) -> str:
    """Best-effort readable form of an MSVC decorated name (not a full demangler)."""
    if name.startswith("?"):
        name = name[1:]
    # ?fn_0c018380@gen@dream@@... -> fn_0c018380
    head = name.split("@")[0]
    if head.startswith("fn_"):
        return head
    # ?read32@DcMemory@mem@dream@@... -> DcMemory::read32
    parts = name.split("@@")[0].split("@")
    parts = [p for p in parts if p and not p.startswith("?")]
    return "::".join(reversed(parts))


def load_map(path: str):
    symbols = []
    with open(path, "r", errors="replace") as f:
        for line in f:
            m = PUBLIC.match(line)
            if m:
                symbols.append((int(m.group(2), 16), m.group(1)))
    symbols.sort()
    return symbols


def resolve(symbols, rva: int):
    # The map's addresses are absolute under the preferred base; the profile's are module-relative.
    target = PREFERRED_BASE + rva
    lo, hi = 0, len(symbols) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if symbols[mid][0] <= target:
            best = symbols[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        return "?"
    start, name = best
    if target - start > 0x8000:  # far past the symbol: a DLL or an un-annotated region
        return "?"
    return f"{demangle(name)}+0x{target - start:x}" if target != start else demangle(name)


PREFERRED_BASE = 0x140000000


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    symbols = load_map(sys.argv[1])
    rows = []
    with open(sys.argv[2], "r", errors="replace") as f:
        for line in f:
            m = SAMPLE.search(line)
            if m:
                rows.append((int(m.group(3)), int(m.group(1), 16), float(m.group(2))))
    if not rows:
        print("no 'profile: rva' lines found")
        return 1
    merged = {}
    for count, rva, pct in rows:
        name = resolve(symbols, rva)
        got = merged.setdefault(name, [0, 0.0])
        got[0] += count
        got[1] += pct
    for name, (count, pct) in sorted(merged.items(), key=lambda kv: -kv[1][0]):
        print(f"{pct:6.2f}%  {count:6d}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
