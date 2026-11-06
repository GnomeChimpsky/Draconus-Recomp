"""draconus-disc: Dreamcast GD-ROM (GDI/ISO9660) inspection and extraction.

Built for Draconus: Cult of the Wyrm (USA, T-40203N, V1.000), whose filesystem
spans two data tracks and whose engine keeps a second, internal file index
(DIRENT.DIR) that the ISO9660 tree only partially mirrors.

Public API:
    GdiImage     -- multi-track GDI track map + user-data reads
    Iso9660      -- ISO9660 volume reader (strict directory framing)
    DirentIndex  -- heuristic reader for the engine's DIRENT.DIR index
    known        -- hashes and identifiers of the supported dump
"""

from .gdi import GdiImage, Track, GdiError
from .iso import Iso9660, IsoError, Entry
from .dirent import DirentIndex, DirentEntry
from . import known

__version__ = "0.1.0"

__all__ = [
    "GdiImage",
    "Track",
    "GdiError",
    "Iso9660",
    "IsoError",
    "Entry",
    "DirentIndex",
    "DirentEntry",
    "known",
    "__version__",
]
