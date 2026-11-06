"""GDI descriptor parsing and multi-track user-data reads.

A Dreamcast GD-ROM dump is a ``.gdi`` text descriptor plus one file per track::

    <track count>
    <number> <start LBA> <type> <sector size> <file> <offset>

``type`` is 4 for a data track and 0 for CD-DA audio. A track's file may use
either 2352-byte raw sectors (Mode 1: user data at +16) or 2048-byte cooked
sectors.

Draconus keeps parts of one ISO9660 filesystem in *two* data tracks (03 and 05),
so a reader that treats one file as "the disc" silently truncates the image.
This module exists to make that impossible: every read is resolved through the
track map, and audio tracks refuse user-data reads.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

USER_DATA_OFFSET = 16  # Mode 1 raw sector header


class GdiError(RuntimeError):
    """Raised for malformed descriptors or reads outside the data area."""


@dataclass(frozen=True)
class Track:
    number: int
    lba: int  # first sector of this track, in disc LBAs
    type: int  # 4 = data, 0 = audio
    sector_size: int  # 2048 or 2352
    path: Path

    @property
    def is_data(self) -> bool:
        return self.type == 4

    def __post_init__(self) -> None:
        if self.sector_size not in (2048, 2352):
            raise GdiError(f"track {self.number}: unsupported sector size {self.sector_size}")
        try:
            size = os.path.getsize(self.path)
        except OSError as exc:
            raise GdiError(f"track {self.number}: cannot stat {self.path}: {exc}") from exc
        if size % self.sector_size:
            raise GdiError(
                f"track {self.number}: {self.path.name} size {size} is not a multiple "
                f"of its {self.sector_size}-byte sector size"
            )
        object.__setattr__(self, "sectors", size // self.sector_size)

    sectors: int = 0

    @property
    def end_lba(self) -> int:
        return self.lba + self.sectors


class GdiImage:
    """A disc image backed by a ``.gdi`` descriptor and its track files."""

    def __init__(self, gdi_path: str | os.PathLike[str]):
        self.path = Path(gdi_path)
        if not self.path.exists():
            raise GdiError(f"no such descriptor: {self.path}")
        self.tracks = self._parse(self.path)
        self.data_tracks = [t for t in self.tracks if t.is_data]
        if not self.data_tracks:
            raise GdiError("descriptor declares no data tracks")

    @staticmethod
    def _parse(gdi_path: Path) -> list[Track]:
        raw_lines = [
            ln.strip()
            for ln in gdi_path.read_text(encoding="ascii", errors="replace").splitlines()
        ]
        raw_lines = [ln for ln in raw_lines if ln]
        if not raw_lines:
            raise GdiError("empty descriptor")
        try:
            declared = int(raw_lines[0])
        except ValueError as exc:
            raise GdiError(f"first line is not a track count: {raw_lines[0]!r}") from exc
        body = raw_lines[1:]
        if len(body) != declared:
            raise GdiError(f"descriptor declares {declared} tracks but lists {len(body)}")

        tracks: list[Track] = []
        for line in body:
            parts = line.split()
            if len(parts) != 6:
                raise GdiError(f"malformed track line: {line!r}")
            number, lba, typ, sector_size, filename, _offset = parts
            track = Track(
                number=int(number),
                lba=int(lba),
                type=int(typ),
                sector_size=int(sector_size),
                path=(gdi_path.parent / filename).resolve(),
            )
            tracks.append(track)

        tracks.sort(key=lambda t: t.lba)
        for prev, nxt in zip(tracks, tracks[1:]):
            if prev.end_lba > nxt.lba:
                raise GdiError(
                    f"tracks {prev.number} and {nxt.number} overlap "
                    f"({prev.end_lba} > {nxt.lba})"
                )
        return tracks

    # ------------------------------------------------------------------ reads

    def track_for(self, lba: int) -> Track:
        for track in self.tracks:
            if track.lba <= lba < track.end_lba:
                return track
        raise GdiError(f"LBA {lba} is outside every track")

    def is_data_lba(self, lba: int) -> bool:
        """True when ``lba`` belongs to a data track (not audio, not a gap)."""
        try:
            return self.track_for(lba).is_data
        except GdiError:
            return False

    def read(self, lba: int, count: int = 1, unit: int = 2048) -> bytes:
        """Read ``count`` sectors of user data starting at disc LBA ``lba``.

        Spans track boundaries as long as every sector belongs to a data track.
        Raises :class:`GdiError` for audio sectors, gaps and short files.

        Raw 2352-byte sectors carry a 16-byte header plus 288 bytes of ECC after
        the user data, so a multi-sector read must stride over each sector rather
        than copy a contiguous block. Getting this wrong yields a file whose first
        sector is right and every later sector is shifted -- which looks like code
        and is not.
        """
        if count <= 0:
            return b""
        if unit > 2048 and unit > unit:
            raise GdiError("unit must be 2048 or the track's sector size")
        out = bytearray()
        remaining = count
        cursor = lba
        while remaining:
            track = self.track_for(cursor)
            if not track.is_data:
                raise GdiError(
                    f"LBA {cursor} belongs to audio track {track.number}: refusing a user-data read"
                )
            take = min(remaining, track.end_lba - cursor)
            header = USER_DATA_OFFSET if (track.sector_size == 2352 and unit == 2048) else 0
            offset = (cursor - track.lba) * track.sector_size + header
            with open(track.path, "rb") as handle:
                handle.seek(offset)
                raw = handle.read(take * track.sector_size)
            for index in range(take):
                start = index * track.sector_size
                piece = raw[start:start + unit]
                if len(piece) < unit:
                    # Truncated image: return what exists rather than padding.
                    out += piece
                    return bytes(out)
                out += piece
            cursor += take
            remaining -= take
        return bytes(out)

    # --------------------------------------------------------------- helpers

    @property
    def first_data_lba(self) -> int:
        return self.data_tracks[0].lba

    @property
    def last_data_lba(self) -> int:
        return max(t.end_lba for t in self.data_tracks)

    def describe(self) -> str:
        lines = [f"GDI {self.path.name}  ({len(self.tracks)} tracks)"]
        for track in self.tracks:
            kind = "data" if track.is_data else "audio"
            lines.append(
                f"  {track.number}: LBA {track.lba:7d}-{track.end_lba - 1:7d} "
                f"{kind:5s} {track.sector_size:4d} B/sector  {track.path.name}"
            )
        return "\n".join(lines)
