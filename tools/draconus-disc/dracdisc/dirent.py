"""Reader for the engine's own file index (``DIRENT.DIR``).

Draconus does not rely on ISO9660 alone. Its engine keeps a packed copy of the
whole directory tree in ``DIRENT.DIR`` (two copies exist on the disc), using a
fixed 44-byte record::

    +0   u8[6]   flags/parent (zero on this disc)
    +6   u32 LE  first-sector LBA
    +10  u32 LE  size in bytes
    +14  u8      type  (0 = file, 2 = directory)
    +15  u8      tag   (name checksum, purpose unconfirmed)
    +16  char[28] NUL-padded file name

The blob is a *memory image*, not a serialised table: it also embeds 0x8Cxxxxxx
run-time pointers and per-directory blocks, so records are not uniformly
reachable by stepping 44 bytes from the start. We therefore scan every offset
and keep records that validate, then de-duplicate.

This is deliberately a heuristic: it is reported as such, with counts, so that a
future strict parser can be compared against it.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass

RECORD_SIZE = 44
HEADER = 6
NAME_OFFSET = HEADER + 10
NAME_SIZE = 28
MAX_PLAUSIBLE_SIZE = 13_000_000

_NAME_STRIP = re.compile(rb"^[A-Za-z0-9_.\-]{1,27}$")


@dataclass(frozen=True)
class DirentEntry:
    name: str
    lba: int
    size: int
    kind: int  # 0 = file, 2 = directory
    offset: int

    @property
    def extension(self) -> str:
        parts = self.name.rsplit(".", 1)
        return parts[-1].upper() if len(parts) == 2 else ""


class DirentIndex:
    """A validated, de-duplicated view of a DIRENT.DIR blob."""

    def __init__(self, blob: bytes, first_lba: int, last_lba: int, source_lba: int = 0):
        self.blob = blob
        self.source_lba = source_lba
        self.first_lba = first_lba
        self.last_lba = last_lba
        self.entries: list[DirentEntry] = []
        self.rejected = 0
        self._scan()

    # ------------------------------------------------------------------ scan

    def _scan(self) -> None:
        found: dict[tuple[str, int, int], DirentEntry] = {}
        limit = len(self.blob) - RECORD_SIZE
        for offset in range(0, max(0, limit)):
            entry = self._try_record(offset)
            if entry is None:
                continue
            key = (entry.name, entry.lba, entry.size)
            found.setdefault(key, entry)
        self.entries = sorted(found.values(), key=lambda e: (e.lba, e.name))

    def _try_record(self, offset: int) -> DirentEntry | None:
        # The six bytes before the LBA are zero in every genuine record; using
        # them as a guard removes the false positives a bare scan would collect
        # from high-entropy file data.
        if self.blob[offset:offset + HEADER] != b"\x00" * HEADER:
            return None
        head = self.blob[offset + 6: offset + 14]
        if len(head) < 8:
            return None
        lba, size = struct.unpack("<II", head)
        if lba < self.first_lba or lba >= self.last_lba:
            return None
        if size == 0 or size > MAX_PLAUSIBLE_SIZE:
            return None
        kind = self.blob[offset + 14]
        if kind not in (0, 2):
            return None
        raw = self.blob[offset + 16: offset + 16 + NAME_SIZE]
        if len(raw) < NAME_SIZE:
            return None
        zero = raw.find(b"\x00")
        if zero <= 0:
            return None
        name = raw[:zero]
        if not _NAME_STRIP.match(name) or name.startswith(b"."):
            return None
        return DirentEntry(name.decode("ascii"), lba, size, kind, offset)

    # --------------------------------------------------------------- reports

    @property
    def files(self) -> list[DirentEntry]:
        return [e for e in self.entries if e.kind != 2]

    @property
    def total_bytes(self) -> int:
        return sum(e.size for e in self.files)

    def extension_histogram(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.files:
            key = entry.extension or "<none>"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    def summary(self) -> str:
        hist = self.extension_histogram()
        top = ", ".join(f"{k}={v}" for k, v in list(hist.items())[:8])
        return (
            f"DIRENT.DIR @LBA {self.source_lba}: {len(self.entries)} records "
            f"({len(self.files)} files, {self.total_bytes / 1048576:.1f} MB); top: {top}"
        )
