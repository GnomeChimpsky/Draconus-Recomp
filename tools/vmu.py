#!/usr/bin/env python3
"""Virtual memory units: what is saved on a card, and how to make a blank one.

A VMU image is the standard 128 KB Dreamcast card: 256 blocks of 512 bytes, with the file
allocation table in block 254 and the directory chain in blocks 241..253. The layout is the one
the console's formatter writes and every Dreamcast emulator reads, so a card made here can be
carried to Flycast and back. There are no checksums in the filesystem.

This module is the launcher's half of the feature: it lists the save files on a card so one can be
picked, and it writes a formatted blank card (the engine writes the same image when ``--vmu`` names
a path that does not exist yet).

Run it directly to inspect a card::

    python tools/vmu.py <card.vmu>
    python tools/vmu.py --new <card.vmu>      # create a blank, formatted card
"""

from __future__ import annotations

import datetime
import os
import struct
import sys
from dataclasses import dataclass

BLOCK_SIZE = 512
BLOCK_COUNT = 256
IMAGE_SIZE = BLOCK_SIZE * BLOCK_COUNT          # 131,072
FAT_BLOCK = 254
ROOT_BLOCK = 255
DIRECTORY_HEAD = 253                           # where the first entry lives
DIRECTORY_TAIL = 241                           # end of the chain
ENTRY_SIZE = 32

# File types in a directory entry. 0x33 is a data file (a save), 0xCC an executable (a VMU
# mini-game). The lister shows data files only: they are what a game's load screen offers, and the
# launcher's index has to line up with that screen. Mini-games are skipped, not treated as saves.
_TYPE_DATA = 0x33
_TYPE_GAME = 0xCC

# FAT values: an allocated last block of a chain, and a free block.
_FAT_END = 0xFFFA
_FAT_FREE = 0xFFFC


class VmuError(Exception):
    """The file is not a memory card image, or cannot be read."""


@dataclass(frozen=True)
class SaveFile:
    """One directory entry on a card, as the game and every VMU tool see it."""

    name: str
    kind: int
    protected: bool
    first_block: int
    blocks: int
    header_offset: int
    timestamp: datetime.datetime | None
    index: int

    @property
    def size_bytes(self) -> int:
        return self.blocks * BLOCK_SIZE

    @property
    def is_game(self) -> bool:
        return self.kind == _TYPE_GAME

    def timestamp_text(self) -> str:
        if self.timestamp is None:
            return "(no timestamp)"
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _bcd(value: int) -> int | None:
    hi, lo = value >> 4, value & 0x0F
    if hi > 9 or lo > 9:
        return None
    return hi * 10 + lo


def _timestamp(raw: bytes) -> datetime.datetime | None:
    """century, year, month, day, hour, minute, second, weekday, all BCD."""
    if len(raw) != 8:
        return None
    parts = [_bcd(b) for b in raw[:7]]
    if any(p is None for p in parts):
        return None
    century, year, month, day, hour, minute, second = parts
    try:
        return datetime.datetime(century * 100 + year, month, day, hour, minute, second)
    except ValueError:  # a card with a nonsense stamp is still a card
        return None


def _fat(data: bytes) -> list[int]:
    return list(struct.unpack_from("<256H", data, FAT_BLOCK * BLOCK_SIZE))


def _directory_blocks(data: bytes) -> list[int]:
    """The directory chain in link order, following the FAT.

    A card the engine or the console formatted chains 253 -> 252 -> ... -> 241. A card with a
    damaged FAT still has the blocks in the same place, so the fallback reads them downwards
    rather than answering "no saves" for a card that plainly has some.
    """
    try:
        fat = _fat(data)
    except struct.error:
        return list(range(DIRECTORY_HEAD, DIRECTORY_TAIL - 1, -1))
    chain: list[int] = []
    block = DIRECTORY_HEAD
    for _ in range(BLOCK_COUNT):
        if block < DIRECTORY_TAIL or block > DIRECTORY_HEAD or block in chain:
            break
        chain.append(block)
        nxt = fat[block]
        if nxt in (_FAT_END, _FAT_FREE) or nxt >= BLOCK_COUNT:
            break
        block = nxt
    if not chain:
        chain = list(range(DIRECTORY_HEAD, DIRECTORY_TAIL - 1, -1))
    return chain


def read_saves(path: str) -> list[SaveFile]:
    """Every save file on the card, in the order the directory stores them.

    The order matters: Draconus lists a card's files in this order, so the index here is what a
    launcher has to send to pick a particular save.
    """
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:
        raise VmuError(f"cannot read {path}: {exc}") from exc
    if len(data) != IMAGE_SIZE:
        raise VmuError(
            f"{path} is {len(data)} bytes; a memory card is exactly {IMAGE_SIZE}"
        )
    return read_saves_from_image(data)


def read_saves_from_image(data: bytes) -> list[SaveFile]:
    if len(data) != IMAGE_SIZE:
        raise VmuError(f"image is {len(data)} bytes; a memory card is exactly {IMAGE_SIZE}")
    saves: list[SaveFile] = []
    for block in _directory_blocks(data):
        base = block * BLOCK_SIZE
        for offset in range(0, BLOCK_SIZE, ENTRY_SIZE):
            raw = data[base + offset: base + offset + ENTRY_SIZE]
            if len(raw) < ENTRY_SIZE or raw[0] != _TYPE_DATA:
                continue
            name = raw[4:16].split(b"\x00", 1)[0].decode("ascii", "replace").strip()
            first = struct.unpack_from("<H", raw, 2)[0]
            blocks = struct.unpack_from("<H", raw, 0x18)[0]
            header = struct.unpack_from("<H", raw, 0x1A)[0]
            saves.append(
                SaveFile(
                    name=name or "(unnamed)",
                    kind=raw[0],
                    protected=raw[1] == 0xFF,
                    first_block=first,
                    blocks=blocks,
                    header_offset=header,
                    timestamp=_timestamp(raw[0x10:0x18]),
                    index=len(saves),
                )
            )
    return saves


def formatted(data: bytes) -> bool:
    """The card carries the system block's format marker."""
    if len(data) != IMAGE_SIZE:
        return False
    root = ROOT_BLOCK * BLOCK_SIZE
    return data[root:root + 16] == b"\x55" * 16


def blank_image() -> bytes:
    """A blank, formatted card, byte for byte what the engine's ``MemoryCard::format`` writes.

    The values are the ones two real cards and Flycast's default image agree on; the creation
    stamp is the fixed 1998-11-27 both references carry, not the host clock, so the bytes are
    reproducible.
    """
    image = bytearray(IMAGE_SIZE)
    root = ROOT_BLOCK * BLOCK_SIZE
    image[root:root + 16] = b"\x55" * 16          # format marker
    image[root + 0x10] = 0x01                     # a custom volume colour follows
    image[root + 0x11:root + 0x14] = b"\xFF\xFF\xFF"  # blue, green, red
    image[root + 0x14] = 0x64                     # alpha 100
    image[root + 0x30:root + 0x38] = bytes(
        (0x19, 0x98, 0x11, 0x27, 0x00, 0x00, 0x59, 0x04)
    )

    def put16(offset: int, value: int) -> None:
        struct.pack_into("<H", image, offset, value)

    put16(root + 0x40, 255)   # last block
    put16(root + 0x42, 0)     # partition
    put16(root + 0x44, 255)   # system area block
    put16(root + 0x46, 254)   # FAT block
    put16(root + 0x48, 1)     # FAT blocks
    put16(root + 0x4A, 253)   # directory block
    put16(root + 0x4C, 13)    # directory blocks
    image[root + 0x4E] = 5    # volume icon
    put16(root + 0x50, 200)   # first block of the executable/save area
    put16(root + 0x52, 31)    # blocks in it
    image[root + 0x56] = 0x80

    fat = FAT_BLOCK * BLOCK_SIZE
    for block in range(BLOCK_COUNT):
        put16(fat + block * 2, _FAT_FREE)
    put16(fat + 241 * 2, _FAT_END)   # directory tail
    for block in range(242, DIRECTORY_HEAD + 1):
        put16(fat + block * 2, block - 1)  # 253 -> 252 -> ... -> 241
    put16(fat + FAT_BLOCK * 2, _FAT_END)
    put16(fat + ROOT_BLOCK * 2, _FAT_END)
    return bytes(image)


def write_blank(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as f:
        f.write(blank_image())


def default_path(game_id: str = "draconus") -> str:
    """The per-user card the engine attaches when a windowed run names no ``--vmu``.

    The same rule as ``boot_main.cpp``: ``%APPDATA%`` on Windows, ``Application Support`` on
    macOS, the XDG data directory on Linux. The launcher passes the path explicitly so it can
    read the saves off it; the engine's own default covers the other launch paths.
    """
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        root = os.path.join(base, "dream-recomp")
    elif sys.platform == "darwin":
        root = os.path.expanduser("~/Library/Application Support/dream-recomp")
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        root = os.path.join(root, "dream-recomp")
    return os.path.join(root, "saves", game_id, "vmu_a1.bin")


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--new":
        write_blank(argv[1])
        print(f"wrote a blank formatted card to {argv[1]}")
        return 0
    if len(argv) != 1:
        print("usage: python tools/vmu.py CARD.vmu | --new CARD.vmu", file=sys.stderr)
        return 2
    path = argv[0]
    try:
        saves = read_saves(path)
    except VmuError as exc:
        print(exc, file=sys.stderr)
        return 1
    with open(path, "rb") as f:
        card = f.read()
    print(f"{path}: {'formatted' if formatted(card) else 'not formatted'}, "
          f"{len(saves)} save file(s)")
    for save in saves:
        print(f"  [{save.index}] {save.name:<12} {save.blocks:3d} blocks  "
              f"{save.timestamp_text()}  first block {save.first_block}"
              f"{'  (protected)' if save.protected else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
