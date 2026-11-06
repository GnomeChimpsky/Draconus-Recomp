"""Tests for draconus-disc.

Everything here is synthetic (no game data): a tiny ISO9660 image is built in
memory, plus a fake GDI descriptor on disk for the track-map tests. The real-dump
test runs only when DRACONUS_DISC points at a .gdi.
"""

from __future__ import annotations

import os
import random
import shutil
import uuid
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dracdisc.gdi import GdiError, GdiImage  # noqa: E402
from dracdisc.iso import Entry, Iso9660, IsoError  # noqa: E402

SECTOR = 2048

# Keep scratch data inside the workspace: some sandboxes deny access to the
# system temp directory, which would turn cleanup into a spurious failure.
TEST_TMP = Path(__file__).resolve().parents[1] / "scratch"
TEST_TMP.mkdir(exist_ok=True)


def _both32(value: int) -> bytes:
    return struct.pack("<I", value) + struct.pack(">I", value)


def _record(name: bytes, lba: int, size: int, flags: int = 0) -> bytes:
    header = bytes([0, 0]) + _both32(lba) + _both32(size)
    header += bytes(7) + bytes([flags, 0, 0])
    header += struct.pack("<H", 1) + struct.pack(">H", 1)  # volume sequence number
    body = bytes([len(name)]) + name
    if len(name) % 2 == 0:
        body += b"\x00"
    record = header + body
    total = len(record)
    if total % 2:
        record += b"\x00"
        total += 1
    return bytes([total]) + record[1:]


def _named_dir(name: bytes, lba: int, size: int) -> bytes:
    return _record(name, lba, size, flags=0x02)


def _dir_bytes(records: list[bytes], sectors: int = 1) -> bytes:
    out = b"".join(records)
    out += b"\x00" * (sectors * SECTOR - len(out))
    return out


def _pvd(root_lba: int, root_size: int, volume_id: str = "TESTDISC") -> bytes:
    data = bytearray(SECTOR)
    data[0] = 1
    data[1:6] = b"CD001"
    data[6] = 1
    data[40:72] = volume_id.encode().ljust(32, b" ")
    data[80:88] = _both32(1000)
    data[128:132] = struct.pack("<H", SECTOR) + struct.pack(">H", SECTOR)
    data[132:136] = struct.pack("<I", 10)  # path table size
    data[140:144] = struct.pack("<I", 18)  # L path table
    data[156:190] = _record(b"\x00", root_lba, root_size, flags=0x02)
    return bytes(data)


class FakeImage:
    """Minimal stand-in for GdiImage: a bytes blob addressed in LBAs."""

    first_data_lba = 0
    last_data_lba = 10000

    def __init__(self, sectors: dict[int, bytes]):
        self.sectors = sectors
        self.data_tracks = [type("T", (), {"lba": 0})()]

    def read(self, lba: int, count: int = 1, unit: int = SECTOR) -> bytes:
        out = bytearray()
        for n in range(count):
            out += self.sectors.get(lba + n, bytes(SECTOR))
        return bytes(out)


def build_image(tmp: Path) -> Path:
    """A small but valid ISO9660 image behind a one-track GDI."""
    root = _dir_bytes([
        _record(b"\x00", 20, SECTOR, flags=0x02),
        _record(b"\x01", 20, SECTOR, flags=0x02),
        _record(b"README.TXT;1", 22, 11),
        _named_dir(b"DATA", 21, SECTOR),
    ])
    data = _dir_bytes([
        _record(b"\x00", 21, SECTOR, flags=0x02),
        _record(b"\x01", 20, SECTOR, flags=0x02),
        _record(b"ASSET.PVR;1", 23, 4),
    ])
    sectors = {
        0: bytes(SECTOR),              # boot area
        16: _pvd(20, SECTOR),
        17: bytes([255]) + b"CD001" + bytes(SECTOR - 6),
        20: root,
        21: data,
        22: b"hello world" + bytes(SECTOR - 11),
        23: b"PVR\x00" + bytes(SECTOR - 4),
    }

    track = tmp / "track01.bin"
    with open(track, "wb") as handle:
        for lba in range(30):
            handle.write(sectors.get(lba, bytes(SECTOR)))
    gdi = tmp / "test.gdi"
    gdi.write_text("1\n1 0 4 2048 track01.bin 0\n", encoding="ascii")
    return gdi


class GdiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TEST_TMP / f't{uuid.uuid4().hex}'
        self.tmp.mkdir(parents=False)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_disc(self, types: list[tuple[int, int, int]]) -> Path:
        lines = [str(len(types))]
        for index, (lba, typ, sectors) in enumerate(types, start=1):
            name = f"track{index:02d}.bin"
            (self.tmp / name).write_bytes(bytes(sectors * 2048))
            lines.append(f"{index} {lba} {typ} 2048 {name} 0")
        gdi = self.tmp / "disc.gdi"
        gdi.write_text("\n".join(lines) + "\n", encoding="ascii")
        return gdi

    def test_track_map_and_read(self) -> None:
        gdi = self._write_disc([(0, 4, 2), (10, 0, 2), (20, 4, 2)])
        image = GdiImage(gdi)
        self.assertEqual([t.number for t in image.tracks], [1, 2, 3])
        self.assertEqual(image.first_data_lba, 0)
        self.assertEqual(len(image.read(0, 2)), 4096)

    def test_audio_read_is_refused(self) -> None:
        gdi = self._write_disc([(0, 4, 2), (10, 0, 2)])
        image = GdiImage(gdi)
        with self.assertRaises(GdiError):
            image.read(10, 1)

    def test_gap_is_refused(self) -> None:
        gdi = self._write_disc([(0, 4, 2), (10, 4, 2)])
        image = GdiImage(gdi)
        with self.assertRaises(GdiError):
            image.read(5, 1)

    def test_track_count_mismatch(self) -> None:
        gdi = self.tmp / "bad.gdi"
        gdi.write_text("3\n1 0 4 2048 track01.bin 0\n", encoding="ascii")
        (self.tmp / "track01.bin").write_bytes(bytes(2048))
        with self.assertRaises(GdiError):
            GdiImage(gdi)

    def test_overlapping_tracks_rejected(self) -> None:
        gdi = self._write_disc([(0, 4, 4), (2, 4, 2)])
        with self.assertRaises(GdiError):
            GdiImage(gdi)

    def test_multi_sector_raw_read_strides_over_headers(self) -> None:
        # Regression: a multi-sector read from a 2352-byte track must return each
        # sector's user data, not a contiguous block of raw bytes (which shifts
        # every sector after the first by 304 bytes and still looks like code).
        track = self.tmp / "track01.bin"
        payload = bytearray()
        for sector in range(4):
            header = bytes([0x00]) + b"\xff" * 10 + bytes([0x00]) + bytes([sector, 0x46, 0x57, 0x01])
            user = bytes([sector]) * 2048
            ecc = bytes([0xEE]) * (2352 - 16 - 2048)
            payload += header + user + ecc
        track.write_bytes(payload)
        gdi = self.tmp / "raw.gdi"
        gdi.write_text("1\n1 0 4 2352 track01.bin 0\n", encoding="ascii")
        image = GdiImage(gdi)
        data = image.read(0, 4)
        self.assertEqual(len(data), 4 * 2048)
        for sector in range(4):
            chunk = data[sector * 2048:(sector + 1) * 2048]
            self.assertEqual(chunk, bytes([sector]) * 2048, f"sector {sector}")


class IsoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TEST_TMP / f't{uuid.uuid4().hex}'
        self.tmp.mkdir(parents=False)
        self.gdi = build_image(self.tmp)
        self.iso = Iso9660(GdiImage(self.gdi))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_walk_finds_files_and_dirs(self) -> None:
        entries = self.iso.walk()
        paths = {e.path for e in entries}
        self.assertIn("README.TXT", paths)
        self.assertIn("DATA/ASSET.PVR", paths)
        self.assertTrue(all(not e.is_dir for e in entries if e.path.endswith(".PVR")))
        self.assertEqual(self.iso.resync_events, [])

    def test_read_entry(self) -> None:
        target = next(e for e in self.iso.walk() if e.path == "README.TXT")
        self.assertEqual(self.iso.read_entry(target), b"hello world")

    def test_terminator_mid_sector(self) -> None:
        # Padding after the last record must not be read as a record, and the
        # walk must end cleanly with no resync.
        image = FakeImage({
            16: _pvd(20, SECTOR),
            20: _dir_bytes([_record(b"\x00", 20, SECTOR, flags=0x02),
                            _record(b"\x01", 20, SECTOR, flags=0x02),
                            _record(b"A.TXT;1", 21, 3)]),
            21: b"abc" + bytes(SECTOR - 3),
        })
        iso = Iso9660(image, base_lba=0)
        names = {e.name for e in iso.walk()}
        self.assertEqual(names, {"A.TXT"})
        self.assertEqual(iso.resync_events, [])

    def test_directory_continues_after_padding_sector(self) -> None:
        first = _dir_bytes([_record(b"\x00", 20, 4096, flags=0x02),
                            _record(b"\x01", 20, 4096, flags=0x02)], sectors=1)
        second = _dir_bytes([_record(b"B.TXT;1", 21, 3)], sectors=1)
        image = FakeImage({
            16: _pvd(20, 4096),
            20: first,
            21: second,
        })
        # A two-sector directory: the zero padding in sector 0 must not end it.
        image.sectors[20] = first + second
        iso = Iso9660(image, base_lba=0)
        names = {e.name for e in iso.walk()}
        self.assertIn("B.TXT", names)
        self.assertEqual(iso.resync_events, [])

    def test_record_crossing_sector_is_reported_not_crashed(self) -> None:
        # Fill a sector with valid records, then place one that would run past
        # the sector boundary; the reader must report it and stop, not desync.
        records = b"".join(_record(b"F%02d.TXT;1" % i, 21, 3) for i in range(48))
        self.assertEqual(len(records), 2016)
        blob = records + bytes([100]) + bytes(SECTOR - 2017)
        image = FakeImage({16: _pvd(20, SECTOR), 20: blob})
        iso = Iso9660(image, base_lba=0)
        iso.walk()
        self.assertGreaterEqual(len(iso.resync_events), 1)
        self.assertIn("crosses sector", iso.resync_events[0].reason)

    def test_oversized_directory_extent_is_a_truncation_not_a_resync(self) -> None:
        # Mirrors this disc: the directory claims 3 sectors but only the first
        # holds records; the rest is unrelated data. That is a truncation.
        content = _dir_bytes([_record(b"\x00", 20, 6144, flags=0x02),
                              _record(b"\x01", 20, 6144, flags=0x02),
                              _record(b"A.TXT;1", 21, 3)])
        garbage = bytes(random.Random(7).randrange(256) for _ in range(SECTOR * 2))
        image = FakeImage({16: _pvd(20, 6144), 20: content + garbage, 21: b"abc" + bytes(SECTOR - 3)})
        iso = Iso9660(image, base_lba=0)
        names = {e.name for e in iso.walk()}
        self.assertIn("A.TXT", names)
        self.assertEqual(iso.resync_events, [])
        self.assertEqual(len(iso.truncations), 1)
        self.assertEqual(iso.truncations[0].offset, SECTOR)

    def test_fuzz_never_desyncs_silently(self) -> None:
        rng = random.Random(1234)
        for trial in range(1000):
            blob = bytes(rng.randrange(256) for _ in range(SECTOR))
            image = FakeImage({16: _pvd(20, SECTOR), 20: blob})
            iso = Iso9660(image, base_lba=0)
            try:
                entries = iso.walk()
            except Exception as exc:  # noqa: BLE001 - the point of the test
                self.fail(f"trial {trial}: walk raised {exc!r}")
            # Either it parsed nothing, or every accepted record is in range.
            first, last = image.first_data_lba, image.last_data_lba
            for entry in entries:
                self.assertTrue(entry.name)
                self.assertGreaterEqual(entry.extent_lba, first)
                self.assertLess(entry.extent_lba, last)
                self.assertLessEqual(entry.size, (last - entry.extent_lba) * SECTOR)

    def test_missing_volume_raises(self) -> None:
        image = FakeImage({})
        with self.assertRaises(IsoError):
            Iso9660(image, base_lba=0)


@unittest.skipUnless(os.environ.get("DRACONUS_DISC"), "DRACONUS_DISC not set")
class RealDumpTests(unittest.TestCase):
    def test_verify(self) -> None:
        from dracdisc.cli import cmd_verify
        import argparse

        rc = cmd_verify(argparse.Namespace(disc=os.environ["DRACONUS_DISC"]))
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
