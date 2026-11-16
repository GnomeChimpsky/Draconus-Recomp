"""CHD identity checks.

The tools deliberately do not decompress CHDs: libchdr is the engine's dependency, and the
verifier has to run from a plain Python install (and inside the frozen launcher). The CHD v5
header is enough to tell a supported image from any other file: chdman stores the SHA-1 of the
raw disc data there, computed from the decompressed data, so a correct CHD of this release
carries the same value however it was compressed.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from . import known

MAGIC = b"MComprHD"
# tag, header length, version, four compressors, logical bytes, map and metadata offsets,
# hunk and unit bytes, then the raw, combined and parent SHA-1s. 124 bytes in CHD v5.
HEADER = struct.Struct(">8sII16sQQQII20s20s20s")
FRAME_SIZE = 2448  # the GD-ROM frame chdman stores, subcode included


class ChdError(Exception):
    """The file is not a CHD this tool can identify."""


@dataclass(frozen=True)
class ChdHeader:
    version: int
    logical_bytes: int
    hunk_bytes: int
    unit_bytes: int
    raw_sha1: bytes
    sha1: bytes
    parent_sha1: bytes

    @property
    def has_parent(self) -> bool:
        return any(self.parent_sha1)


def read_header(path: str | Path) -> ChdHeader:
    try:
        with open(path, "rb") as f:
            raw = f.read(HEADER.size)
    except OSError as exc:
        raise ChdError(f"{path}: {exc}") from exc
    if len(raw) < HEADER.size or raw[:8] != MAGIC:
        raise ChdError(f"{path}: not a CHD image")
    (_magic, _length, version, _compressors, logical, _map_offset, _meta_offset,
     hunk_bytes, unit_bytes, raw_sha1, sha1, parent_sha1) = HEADER.unpack(raw)
    if version != 5:
        raise ChdError(f"{path}: CHD version {version} is not supported (only v5)")
    return ChdHeader(version, logical, hunk_bytes, unit_bytes, raw_sha1, sha1, parent_sha1)


def verify(path: str | Path) -> tuple[bool, list[str]]:
    """Whether this CHD is the supported disc. Returns (ok, failures)."""
    try:
        header = read_header(path)
    except ChdError as exc:
        return False, [str(exc)]
    failures: list[str] = []
    if header.unit_bytes != FRAME_SIZE:
        failures.append(f"frame size {header.unit_bytes} != {FRAME_SIZE}; not a GD-ROM CHD")
    if header.has_parent:
        failures.append("CHD needs a parent image; the game cannot open it alone")
    expected = bytes.fromhex(known.CHD_RAW_SHA1)
    if header.raw_sha1 != expected:
        failures.append(f"raw sha1 {header.raw_sha1.hex()} != {known.CHD_RAW_SHA1}")
    return not failures, failures
