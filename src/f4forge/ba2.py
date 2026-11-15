"""BA2 archives (BTDX). This module starts with the header; T11 adds list/extract/verify.

Header (24 bytes): magic "BTDX", u32 version, 4-char type ("GNRL" or "DX10"),
u32 file count, u64 name-table offset. Installed archives use versions 1, 7 and 8
(fact ba2.versions.installed).
"""
from __future__ import annotations

import struct
from pathlib import Path

from .util import ForgeError

HEADER = struct.Struct("<4sI4sIQ")


def read_header(path: Path) -> dict:
    with open(path, "rb") as f:
        raw = f.read(HEADER.size)
    if len(raw) < HEADER.size:
        raise ForgeError(f"{Path(path).name}: shorter than a BA2 header", "the file is truncated or not a BA2")
    magic, version, kind, count, names = HEADER.unpack(raw)
    if magic != b"BTDX":
        raise ForgeError(f"{Path(path).name}: not a BA2 (magic {magic!r})", "only Fallout 4 BTDX archives are read")
    return {"version": version, "type": kind.decode("ascii", "replace"), "files": count, "name_table_offset": names}
