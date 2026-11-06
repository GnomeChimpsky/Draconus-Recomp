"""ISO9660 reader with strict, *auditable* directory framing.

Dreamcast discs routinely contain directories that are less well-formed than the
standard promises, and one silent desync is enough to produce a plausible but
wrong file list. So every framing decision here is either standard-compliant or
recorded as a :class:`ResyncEvent` -- nothing is skipped quietly.

Rules implemented (ECMA-119 9.3 / 6.8.1):
  * a record may never cross a logical-sector boundary;
  * a record length of 0 pads out the rest of that sector, and the directory
    continues in the next sector;
  * a directory ends when its declared extent is exhausted or a sector starts
    with a 0 length (some masters omit the explicit terminator sector).

Multi-extent files (flag bit 0x80) are stitched in record order.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .gdi import GdiImage

SECTOR = 2048
FLAG_DIR = 0x02
FLAG_MULTI_EXTENT = 0x80

NAME_MAX = 222


class IsoError(RuntimeError):
    """Raised when no usable volume descriptor can be found."""


@dataclass
class ResyncEvent:
    directory: str
    offset: int
    reason: str


@dataclass
class TruncationEvent:
    """A directory whose declared extent runs past its real content.

    Not corruption: some mastering tools record the allocated directory size and
    leave the trailing sectors holding unrelated data (verified on this disc).
    """

    directory: str
    offset: int
    reason: str


@dataclass
class Entry:
    path: str
    name: str
    extent_lba: int
    size: int
    is_dir: bool
    flags: int
    extents: list[tuple[int, int]] = field(default_factory=list)

    @property
    def extension(self) -> str:
        base = self.name.rsplit(".", 1)
        return base[-1].upper() if len(base) == 2 and base[-1] else ""


class Iso9660:
    """Reads the ISO9660 volume that lives at the GD-ROM high-density area."""

    def __init__(self, image: GdiImage, base_lba: int | None = None):
        self.image = image
        self.resync_events: list[ResyncEvent] = []
        self.truncations: list[TruncationEvent] = []
        self.volume_id = ""
        self.path_table_lba = 0
        self.path_table_size = 0
        self.base_lba = base_lba if base_lba is not None else self._locate_volume()
        # Read the volume descriptor eagerly: a wrong disc should fail here, not
        # halfway through a walk.
        self._read_pvd()

    # ------------------------------------------------------------- discovery

    def _locate_volume(self) -> int:
        """Pick the *largest* ISO9660 volume among the data tracks.

        A Dreamcast GD-ROM carries two sessions. The low-density one is a tiny
        licence/readme volume; the game's filesystem is the high-density one.
        Choosing by declared volume size avoids depending on track order.
        """
        best: tuple[int, int] | None = None
        for track in self.image.data_tracks:
            try:
                sector = self.image.read(track.lba + 16, 1)
            except Exception:  # noqa: BLE001 - a probe, not a read path
                continue
            if sector[1:6] != b"CD001" or sector[0] != 1:
                continue
            blocks = struct.unpack("<I", sector[80:84])[0]
            if best is None or blocks > best[1]:
                best = (track.lba, blocks)
        if best is None:
            raise IsoError("no ISO9660 primary volume descriptor found in any data track")
        return best[0]

    def _read_pvd(self) -> None:
        pvd = self.image.read(self.base_lba + 16, 1)
        if pvd[1:6] != b"CD001":
            raise IsoError("primary volume descriptor signature missing")
        self.volume_id = pvd[40:72].decode("latin-1").strip()
        self.path_table_size = struct.unpack("<I", pvd[132:136])[0]
        self.path_table_lba = struct.unpack("<I", pvd[140:144])[0]
        # Root directory record lives at 156; its LE extent/size follow the
        # length and extended-attribute bytes.
        root = pvd[156:190]
        if root[0] != 34:
            raise IsoError(f"unexpected root directory record length {root[0]}")
        self.root_lba = struct.unpack("<I", root[2:6])[0]
        self.root_size = struct.unpack("<I", root[10:14])[0]

    # ------------------------------------------------------------------ walk

    def walk(self) -> list[Entry]:
        """Return every file and directory reachable from the root, depth first."""
        self._read_pvd()
        entries: list[Entry] = []
        seen: set[tuple[int, int]] = set()

        def visit(extent_lba: int, size: int, prefix: str, depth: int) -> None:
            key = (extent_lba, size)
            if key in seen or depth > 32:
                return
            seen.add(key)
            if not self._is_data_extent(extent_lba, size):
                self.resync_events.append(
                    ResyncEvent(prefix or "/", 0,
                                f"directory extent outside data area (lba={extent_lba}, size={size})")
                )
                return
            pending: dict[str, Entry] = {}
            try:
                records = list(self._records(extent_lba, size, prefix or "/"))
            except Exception as exc:  # noqa: BLE001 - report, never abort the walk
                self.resync_events.append(
                    ResyncEvent(prefix or "/", 0, f"unreadable directory extent: {exc}")
                )
                return
            for record in records:
                name = record.name
                if name in (".", ".."):
                    continue
                path = f"{prefix}{name}"
                is_dir = bool(record.flags & FLAG_DIR)
                if is_dir:
                    entries.append(
                        Entry(path + "/", name, record.extent_lba, record.size, True, record.flags)
                    )
                    visit(record.extent_lba, record.size, path + "/", depth + 1)
                    continue
                if record.flags & FLAG_MULTI_EXTENT:
                    existing = pending.get(name)
                    if existing is not None:
                        existing.extents.append((record.extent_lba, record.size))
                        existing.size += record.size
                        continue
                    entry = Entry(
                        path, name, record.extent_lba, record.size, False,
                        record.flags, [(record.extent_lba, record.size)],
                    )
                    pending[name] = entry
                    entries.append(entry)
                    continue
                entries.append(
                    Entry(path, name, record.extent_lba, record.size, False, record.flags,
                          [(record.extent_lba, record.size)])
                )
            # multi-extent files whose last record lacked the flag still need
            # their first extent registered
            for entry in pending.values():
                if not entry.extents:
                    entry.extents.append((entry.extent_lba, entry.size))

        visit(self.root_lba, self.root_size, "", 0)
        entries.sort(key=lambda e: e.path)
        return entries

    # --------------------------------------------------------------- records

    def _records(self, extent_lba: int, size: int, directory: str):
        sectors = max(1, (size + SECTOR - 1) // SECTOR)
        data = self.image.read(extent_lba, sectors)
        limit = min(size, len(data))
        cursor = 0
        while cursor < limit:
            sector_start = (cursor // SECTOR) * SECTOR
            if data[cursor] == 0:
                if cursor == sector_start:
                    # Explicit terminator at the start of a sector: over.
                    return
                nxt = sector_start + SECTOR
                if nxt >= limit:
                    return
                cursor = nxt
                continue
            record, reason = self._parse_record(data, cursor)
            if record is None:
                if cursor == sector_start:
                    # The declared extent runs past the real content. Mastering
                    # tools often write the *allocated* directory size, leaving
                    # trailing sectors holding unrelated data. Stop and report a
                    # truncation rather than pretending the data is a record.
                    self.truncations.append(TruncationEvent(directory, cursor, reason))
                    return
                self.resync_events.append(ResyncEvent(directory, cursor, reason))
                nxt = sector_start + SECTOR
                if nxt >= limit:
                    return
                cursor = nxt
                continue
            yield record
            cursor += record.length

    def _parse_record(self, data: bytes, cursor: int) -> tuple[_Record | None, str]:
        length = data[cursor]
        sector_start = (cursor // SECTOR) * SECTOR
        if length < 34:
            return None, f"invalid record length {length}"
        if cursor - sector_start + length > SECTOR:
            return None, f"record crosses sector boundary (length {length})"
        raw = data[cursor:cursor + length]
        if len(raw) < length:
            return None, "truncated record"
        name_len = raw[32]
        if name_len == 0 or name_len > NAME_MAX or 33 + name_len > length:
            return None, f"invalid name length {name_len}"
        name = _clean_name(raw[33:33 + name_len])
        if not name or any(not (32 <= ord(ch) < 127) for ch in name):
            return None, "non-printable file identifier"
        extent_lba = struct.unpack("<I", raw[2:6])[0]
        size = struct.unpack("<I", raw[10:14])[0]
        if not self._is_data_extent(extent_lba, size):
            return None, f"extent out of range (lba={extent_lba}, size={size})"
        return _Record(name, extent_lba, size, raw[25], length), ""

    # ------------------------------------------------------------------ read

    def _is_data_extent(self, lba: int, size: int) -> bool:
        """True when [lba, lba+size) sits wholly inside the disc's data area."""
        checker = getattr(self.image, "is_data_lba", None)
        if checker is not None:
            if not checker(lba):
                return False
            if size == 0:
                return True
            return bool(checker(lba + (size - 1) // SECTOR))
        first = getattr(self.image, "first_data_lba", 0)
        last = getattr(self.image, "last_data_lba", lba + size // SECTOR + 2)
        if not (first <= lba < last):
            return False
        return size == 0 or lba + (size - 1) // SECTOR < last

    def read_entry(self, entry: Entry) -> bytes:
        extents = entry.extents or [(entry.extent_lba, entry.size)]
        out = bytearray()
        for lba, size in extents:
            if size == 0:
                continue
            out += self.image.read(lba, (size + SECTOR - 1) // SECTOR)
        return bytes(out[: entry.size])

    def find(self, path: str) -> Entry | None:
        target = path.lstrip("/")
        for entry in self.walk():
            if entry.path.rstrip("/").lstrip("/").lower() == target.lower():
                return entry
        return None

    # ---------------------------------------------------------------- report

    def summary(self) -> str:
        entries = self.walk()
        files = [e for e in entries if not e.is_dir]
        dirs = [e for e in entries if e.is_dir]
        total = sum(e.size for e in files)
        return (
            f"ISO9660 volume {self.volume_id!r} at base LBA {self.base_lba}; "
            f"{len(files)} files in {len(dirs)} directories, {total / 1048576:.1f} MB; "
            f"{len(self.resync_events)} resync event(s), "
            f"{len(self.truncations)} declared-extent truncation(s)"
        )


@dataclass
class _Record:
    name: str
    extent_lba: int
    size: int
    flags: int
    length: int = 0


def _clean_name(raw: bytes) -> str:
    # The first two records of every directory are named 0x00 and 0x01 and mean
    # "." and ".."; they must not be mistaken for files.
    if raw == b"\x00":
        return "."
    if raw == b"\x01":
        return ".."
    text = raw.decode("latin-1")
    if ";" in text:
        text = text.split(";", 1)[0]
    if text.endswith("."):
        text = text[:-1]
    return text
