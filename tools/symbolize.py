#!/usr/bin/env python3
"""Turn a Draconus-Recomp crash log into function names.

The game's opt-in crash log (the launcher's **Crash log** setting) writes the host stack as
``module+offset`` addresses, because the release ships no PDB. The linker map from the same build
names them:

    python tools\\symbolize.py crash.log draconus_boot.map --out crash.symbolized.txt

The map is in the matching ``DraconusRecomp-<version>-symbols.zip``. Check that the log's
``exe sha1:`` line equals the ``exe sha1:`` in that bundle's ``BUILD-INFO.txt``; pass ``--exe`` to
have the tool check the executable itself. Only the main executable's frames are annotated; DLL
frames are left as they are.

Also runs with no arguments beyond ``--selftest`` to check the map and log parsers against a
synthetic pair, so it can be exercised without a crash or a build.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import os
import re
import sys

# " Preferred load address is 0000000140000000" in the map header.
LOAD_ADDRESS = re.compile(r"Preferred load address is\s+([0-9A-Fa-f]+)")
# " 0001:0002c300  ?fn_0c018360@...  000000014002d300 f   draconus.cpp.obj"
MAP_ENTRY = re.compile(
    r"^\s+[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}\s+(\S+)\s+([0-9A-Fa-f]{16})\b")
# "DraconusRecomp.exe+0x2d324" in a crash log.
SYMBOL_REF = re.compile(r"(?P<module>[A-Za-z0-9_.\-]+)\+0x(?P<offset>[0-9A-Fa-f]+)")
EXE_SHA1 = re.compile(r"^exe sha1:\s*([0-9a-fA-F]{40})\s*$", re.MULTILINE)
EXE_LINE = re.compile(r"^exe:\s+(.+?)\s*$", re.MULTILINE)


def pretty_name(symbol: str) -> str:
    """A readable name: emitted guest functions keep their address, C++ names lose the decoration.

    The map carries MSVC-decorated names. ``?fn_0c018360@gen@dream@@YAX...`` is the host function
    for guest ``0x0c018360``; the address is the only part a report needs. Other names are cut at
    the first ``@`` so a reader is not handed a 200-character mangling.
    """
    guest = re.search(r"fn_([0-9a-fA-F]{8})(__resume)?", symbol)
    if guest:
        return "fn_" + guest.group(1).lower() + (guest.group(2) or "")
    clean = symbol.lstrip("?")
    return clean.split("@")[0] or symbol


def parse_map_text(text: str) -> list[tuple[int, str]]:
    """(RVA, name) for every public symbol, sorted, with unwind/data helpers dropped."""
    base = None
    entries: list[tuple[int, str]] = []
    for line in text.splitlines():
        if base is None:
            address = LOAD_ADDRESS.search(line)
            if address:
                base = int(address.group(1), 16)
                continue
        match = MAP_ENTRY.match(line)
        if not match:
            continue
        name = match.group(1)
        if name.startswith("$") or "$unwind$" in name:
            continue
        rva = int(match.group(2), 16) - (base or 0x140000000)
        if rva < 0:
            continue
        entries.append((rva, pretty_name(name)))
    entries.sort()
    # The same RVA can appear twice (a function and its resume entry share a body start); the
    # first is the function, keep it.
    unique: list[tuple[int, str]] = []
    for rva, name in entries:
        if not unique or unique[-1][0] != rva:
            unique.append((rva, name))
    return unique


def parse_map(path: str) -> list[tuple[int, str]]:
    with open(path, encoding="utf-8", errors="replace") as source:
        return parse_map_text(source.read())


def detect_module(log_text: str) -> str:
    match = EXE_LINE.search(log_text)
    return os.path.basename(match.group(1)) if match else ""


def symbolize_text(log_text: str, entries: list[tuple[int, str]], module: str) -> tuple[str, int]:
    """Annotate ``module+0x...`` with the nearest symbol; return (text, references named)."""
    if not entries or not module:
        return log_text, 0
    rvas = [rva for rva, _ in entries]
    count = 0

    def annotate(match: re.Match) -> str:
        nonlocal count
        if match.group("module").lower() != module.lower():
            return match.group(0)
        offset = int(match.group("offset"), 16)
        index = bisect.bisect_right(rvas, offset) - 1
        if index < 0:
            return match.group(0)
        name = entries[index][1]
        count += 1
        return "%s+0x%X -> %s+0x%X" % (
            match.group("module"), offset, name, offset - rvas[index])

    lines = []
    for line in log_text.splitlines(keepends=True):
        # A line that already carries an annotation is left alone, so running the tool twice is
        # harmless rather than adding "->" behind "->".
        if "->" in line:
            lines.append(line)
            continue
        body = line.rstrip("\r\n")
        end = line[len(body):]
        lines.append(SYMBOL_REF.sub(annotate, body) + end)
    return "".join(lines), count


def file_sha1(path: str) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def selftest() -> int:
    map_text = (
        " Preferred load address is 0000000140000000\n"
        "\n"
        " 0001:0002c300  ?fn_0c018360@gen@dream@@YAXAEAUCtx@sh4@2@AEAVMemory@2@@Z"
        " 000000014002d300 f   draconus.cpp.obj\n"
        " 0001:0002d000  ?helper@gen@dream@@YAXXZ 000000014002e000 f   draconus.cpp.obj\n"
        " 0002:0009ef50  $unwind$?fn_0c018360 0000000142371f50     draconus.cpp.obj\n"
    )
    log_text = (
        "exe:      C:\\games\\DraconusRecomp.exe\n"
        "exe sha1: " + "a" * 40 + "\n"
        "\n"
        "=== crash ===\n"
        "exception: 0xc0000005 at DraconusRecomp.exe+0x2d300\n"
        "  00  DraconusRecomp.exe+0x2d324\n"
        "  01  KERNEL32.DLL+0x2dda7\n"
    )
    failures = []
    entries = parse_map_text(map_text)
    if not entries or entries[0] != (0x2d300, "fn_0c018360"):
        failures.append("map: %r" % (entries[:2],))
    if (0x2e000, "helper") not in entries:
        failures.append("map: helper absent: %r" % (entries,))
    out, count = symbolize_text(log_text, entries, "DraconusRecomp.exe")
    if "DraconusRecomp.exe+0x2D324 -> fn_0c018360+0x24" not in out:
        failures.append("symbol: %s" % out)
    if "KERNEL32.DLL+0x2dda7 ->" in out:
        failures.append("symbol: a DLL frame was annotated")
    if count != 2:
        failures.append("symbol: %d references named, expected 2" % count)
    first = symbolize_text(out, entries, "DraconusRecomp.exe")[0]
    if first != out:
        failures.append("symbol: a second pass changed the text")
    for failure in failures:
        print("  -", failure)
    print("SYMBOLIZE SELFTEST OK" if not failures else "SYMBOLIZE SELFTEST FAILED")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a Draconus-Recomp crash log's host stack with the build's map.")
    parser.add_argument("log", nargs="?", help="the crash log")
    parser.add_argument("map", nargs="?", help="draconus_boot.map from the matching build")
    parser.add_argument("--module", default="",
                        help="executable name to annotate (default: the log's exe: line)")
    parser.add_argument("--out", default="", help="write here instead of stdout")
    parser.add_argument("--exe", default="",
                        help="check this executable against the log's exe sha1: line")
    parser.add_argument("--selftest", action="store_true", help="check the parsers and exit")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.log or not args.map:
        parser.print_usage(sys.stderr)
        print("symbolize.py: a crash log and a map are required", file=sys.stderr)
        return 2
    try:
        with open(args.log, encoding="utf-8", errors="replace") as source:
            log_text = source.read()
        entries = parse_map(args.map)
    except OSError as exc:
        print("symbolize.py:", exc, file=sys.stderr)
        return 2
    module = args.module or detect_module(log_text)
    if not module:
        print("symbolize.py: no exe: line in the log; pass --module NAME", file=sys.stderr)
        return 2
    recorded = EXE_SHA1.search(log_text)
    if args.exe and recorded:
        try:
            actual = file_sha1(args.exe)
        except OSError as exc:
            print("symbolize.py:", exc, file=sys.stderr)
            return 2
        if actual != recorded.group(1).lower():
            print("symbolize.py: %s is not the build the log came from\n  log:  %s\n  file: %s"
                  % (args.exe, recorded.group(1).lower(), actual), file=sys.stderr)
            return 2
    text, count = symbolize_text(log_text, entries, module)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as target:
            target.write(text)
        print("symbolized %d reference(s) into %s" % (count, args.out))
    else:
        sys.stdout.write(text)
        print("symbolized %d reference(s)" % count, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
