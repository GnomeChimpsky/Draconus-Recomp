"""Command line interface for draconus-disc."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import __version__, known
from .dirent import DirentIndex
from .gdi import GdiImage
from .iso import Iso9660, IsoError

DIRENT_NAME = "DIRENT.DIR"


# --------------------------------------------------------------------- helpers


def load(gdi_path: str) -> tuple[GdiImage, Iso9660]:
    image = GdiImage(gdi_path)
    iso = Iso9660(image)
    return image, iso


def read_ipbin(image: GdiImage) -> dict[str, str]:
    sector = image.read(image.first_data_lba, 1)
    if not sector.startswith(known.IPBIN_MAGIC):
        raise IsoError("IP.BIN magic not found at the start of the high-density area")
    dev_and_version = sector[0x40:0x50].decode("latin-1").split()
    return {
        "hardware": sector[0x00:0x10].decode("latin-1").strip(),
        "maker": sector[0x10:0x20].decode("latin-1").strip(),
        "product": sector[0x20:0x2F].decode("latin-1").strip(),
        "region": sector[0x30:0x3F].decode("latin-1").strip(),
        "devcode": dev_and_version[0] if dev_and_version else "",
        "version": dev_and_version[-1] if len(dev_and_version) > 1 else "",
        "date": sector[0x50:0x58].decode("latin-1").strip(),
        "boot": sector[0x60:0x70].decode("latin-1").strip(),
        "maker2": sector[0x70:0x80].decode("latin-1").strip(),
        "title": sector[0x80:0x100].decode("latin-1").strip(),
    }


def find_boot(iso: Iso9660, entries=None):
    entries = entries if entries is not None else iso.walk()
    for entry in entries:
        if entry.name.upper() == known.BOOT_FILE:
            return entry
    raise IsoError(f"{known.BOOT_FILE} not present in the ISO9660 tree")


def dirent_index(image: GdiImage, iso: Iso9660, entries=None) -> DirentIndex | None:
    entries = entries if entries is not None else iso.walk()
    candidates = [e for e in entries if e.name.upper() == DIRENT_NAME]
    if not candidates:
        return None
    # The root copy is the authoritative one (the DATA copy is a duplicate).
    entry = min(candidates, key=lambda e: len(e.path))
    blob = iso.read_entry(entry)
    return DirentIndex(blob, image.first_data_lba, image.last_data_lba, entry.extent_lba)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -------------------------------------------------------------------- commands


def cmd_inspect(args: argparse.Namespace) -> int:
    image, iso = load(args.disc)
    print(image.describe())
    ip = read_ipbin(image)
    print(f"\nIP.BIN: {ip['title']!r}")
    print(f"  product={ip['product']} version={ip['version']} date={ip['date']} "
          f"region={ip['region']} boot={ip['boot']}")
    entries = iso.walk()
    print(f"\n{iso.summary()}")
    for path in sorted({e.path.split('/')[0] + '/' for e in entries if e.is_dir}):
        print(f"  dir {path}")
    boot = find_boot(iso, entries)
    print(f"\nboot: {boot.path} LBA {boot.extent_lba} size {boot.size} "
          f"sha256 {sha256(iso.read_entry(boot))}")
    index = dirent_index(image, iso, entries)
    if index:
        print(f"\n{index.summary()}")
        print("  extensions: " + ", ".join(f"{k}={v}" for k, v in index.extension_histogram().items()))
    else:
        print("\nno DIRENT.DIR present (ISO-only image)")
    if iso.truncations:
        print(f"\n{len(iso.truncations)} directory extent(s) declared larger than their content "
              f"(trailing sectors are not directory data):")
        for event in iso.truncations[:6]:
            print(f"   {event.directory or '/'} +0x{event.offset:x}: {event.reason}")
    if iso.resync_events:
        print(f"\n!! {len(iso.resync_events)} resync event(s)")
        for event in iso.resync_events[:10]:
            print(f"   {event.directory} +0x{event.offset:x}: {event.reason}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    image, iso = load(args.disc)
    failures: list[str] = []

    ip = read_ipbin(image)
    if ip["product"].split()[0] != known.PRODUCT:
        failures.append(f"product {ip['product']!r} != {known.PRODUCT!r}")
    if known.LICENCE not in ip["maker2"]:
        failures.append(f"licence {known.LICENCE!r} not in {ip['maker2']!r}")
    if ip["version"] != known.VERSION:
        failures.append(f"version {ip['version']!r} != {known.VERSION!r}")

    entries = iso.walk()
    try:
        boot = find_boot(iso, entries)
    except IsoError as exc:
        failures.append(str(exc))
        boot = None
    if boot is not None:
        if boot.size != known.BOOT_SIZE:
            failures.append(f"boot size {boot.size} != {known.BOOT_SIZE}")
        digest = sha256(iso.read_entry(boot))
        if digest != known.BOOT_SHA256:
            failures.append(f"boot sha256 {digest} != {known.BOOT_SHA256}")

    if iso.resync_events:
        failures.append(f"{len(iso.resync_events)} ISO9660 resync event(s)")

    if failures:
        print("VERIFY FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("VERIFY OK")
    print(f"  {known.DISC_TITLE} {known.VERSION} ({known.PRODUCT}, {known.LICENCE})")
    print(f"  boot {known.BOOT_FILE}: {known.BOOT_SIZE} bytes, sha256 {known.BOOT_SHA256}")
    print(f"  ISO9660: {len([e for e in entries if not e.is_dir])} files, "
          f"0 resync events")
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    image, iso = load(args.disc)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    entries = iso.walk()
    boot = find_boot(iso, entries)
    data = iso.read_entry(boot)
    digest = sha256(data)
    if not args.force:
        if len(data) != known.BOOT_SIZE:
            print(f"refusing to write: boot size {len(data)} != {known.BOOT_SIZE}",
                  file=sys.stderr)
            return 1
        if digest != known.BOOT_SHA256:
            print(f"refusing to write: sha256 {digest} != {known.BOOT_SHA256}\n"
                  f"pass --force to extract an unsupported build", file=sys.stderr)
            return 1
    target = out / known.BOOT_FILE
    target.write_bytes(data)
    print(f"wrote {target} ({len(data)} bytes, sha256 {digest})")

    if args.all:
        count = 0
        for entry in entries:
            if entry.is_dir:
                continue
            rel = entry.path.lstrip("/")
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(iso.read_entry(entry))
            count += 1
        print(f"wrote {count} ISO files under {out}")
    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    image, iso = load(args.disc)
    entries = iso.walk()
    ip = read_ipbin(image)
    boot = find_boot(iso, entries)
    boot_data = iso.read_entry(boot)
    index = dirent_index(image, iso, entries)

    iso_files = [e for e in entries if not e.is_dir]
    manifest = {
        "tool": "draconus-disc",
        "tool_version": __version__,
        "disc": {
            "title": ip["title"],
            "product": ip["product"],
            "version": ip["version"],
            "date": ip["date"],
            "region": ip["region"],
            "gdi": image.path.name,
            "tracks": [
                {
                    "number": t.number,
                    "lba": t.lba,
                    "end_lba": t.end_lba,
                    "sectors": t.sectors,
                    "type": "data" if t.is_data else "audio",
                    "sector_size": t.sector_size,
                    "file": t.path.name,
                }
                for t in image.tracks
            ],
        },
        "iso9660": {
            "volume_id": iso.volume_id,
            "base_lba": iso.base_lba,
            "file_count": len(iso_files),
            "dir_count": len([e for e in entries if e.is_dir]),
            "total_bytes": sum(e.size for e in iso_files),
            "resync_events": [
                {"directory": e.directory, "offset": e.offset, "reason": e.reason}
                for e in iso.resync_events
            ],
            "entries": [
                {"path": e.path, "lba": e.extent_lba, "size": e.size,
                 "dir": e.is_dir, "sha256": sha256(iso.read_entry(e)) if not e.is_dir and e.size <= 4_000_000 else None}
                for e in entries
            ],
        },
        "boot": {
            "path": boot.path,
            "lba": boot.extent_lba,
            "size": boot.size,
            "sha256": sha256(boot_data),
            "matches_known_dump": sha256(boot_data) == known.BOOT_SHA256,
        },
        "dirent": None,
    }
    if index is not None:
        manifest["dirent"] = {
            "source_lba": index.source_lba,
            "blob_size": len(index.blob),
            "record_count": len(index.entries),
            "file_count": len(index.files),
            "total_bytes": index.total_bytes,
            "extensions": index.extension_histogram(),
            "entries": [
                {"name": e.name, "lba": e.lba, "size": e.size, "dir": e.kind == 2}
                for e in index.entries
            ],
        }
    text = json.dumps(manifest, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dracdisc",
        description="Inspect, verify, extract and index a Dreamcast GDI dump of "
                    "Draconus: Cult of the Wyrm.",
    )
    parser.add_argument("--version", action="version", version=f"draconus-disc {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("inspect", help="show track map, volume, tree summary and boot hash")
    p.add_argument("disc")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("verify", help="fail closed unless the dump is the supported build")
    p.add_argument("disc")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("extract", help="extract the boot executable (and optionally all ISO files)")
    p.add_argument("disc")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--all", action="store_true", help="also extract every ISO9660 file")
    p.add_argument("--force", action="store_true", help="extract even if the hash is unknown")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("manifest", help="write a JSON inventory of the disc")
    p.add_argument("disc")
    p.add_argument("-o", "--out")
    p.set_defaults(func=cmd_manifest)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (IsoError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
