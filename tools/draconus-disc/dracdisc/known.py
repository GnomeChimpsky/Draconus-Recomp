"""Identifiers of the dump this tool supports.

Values were measured from the retail USA dump (``F888``, ``T-402``, licence
``T-40203N``, release ``20000519``) and are asserted by ``dracdisc verify``.
Nothing here is derived from the game's code beyond its published hashes.
"""

from __future__ import annotations

DISC_TITLE = "Draconus: Cult of the Wyrm (USA)"
PRODUCT = "F888"
LICENCE = "T-402"
VERSION = "V1.000"
RELEASE_DATE = "20000519"
REGION = "U"

BOOT_FILE = "1ST_READ.BIN"
BOOT_SIZE = 2_339_580
# Corrected 2026-11-05. The earlier value (86fc4486...) was the hash of a file
# produced by a reader bug that shifted every sector after the first; this value is
# byte-identical to the extraction made by the engine's own dcdisc tool.
BOOT_SHA256 = "a59ff87c15b7cff926fc77089ae315cf30905586e34504a18b426d634f4567da"
BOOT_LOAD_ADDRESS = 0x8C010000

# The low-density session carries no executable; the boot file lives at the very
# end of the high-density area, immediately after the engine's own DIRENT.DIR.
BOOT_KNOWN_LBA = 547_857

IPBIN_MAGIC = b"SEGA SEGAKATANA"

# Second, much earlier build. Used only as a differential reference.
PROTO_VOLUME_ID = "DIE21"
