"""Plugin files (.esm/.esp/.esl). This module starts with the TES4 header; T13 adds the walker.

Record header (24 bytes): type, u32 data size, u32 flags, u32 FormID, u32 version-control,
u16 form version, u16 unknown. TES4 subrecords: type, u16 size, data. HEDR = f32 version,
i32 record count, u32 next object id. Flags: 0x1 master (ESM), 0x80 localized, 0x200 light (ESL).
"""
from __future__ import annotations

import struct
from pathlib import Path

from .util import ForgeError

FLAG_ESM = 0x1
FLAG_LOCALIZED = 0x80
FLAG_ESL = 0x200


def read_header(path: Path, max_bytes: int = 1 << 16) -> dict:
    path = Path(path)
    with open(path, "rb") as f:
        head = f.read(24)
        if len(head) < 24 or head[:4] != b"TES4":
            raise ForgeError(f"{path.name}: not a plugin (no TES4 record)", "check the file is a Fallout 4 plugin")
        _, size, flags, _, _, form_version, _ = struct.unpack("<4sIIIIHH", head)
        data = f.read(min(size, max_bytes))
    out = {"flags": flags, "esm": bool(flags & FLAG_ESM), "esl": bool(flags & FLAG_ESL),
           "localized": bool(flags & FLAG_LOCALIZED), "form_version": form_version,
           "hedr_version": None, "records": None, "next_object_id": None, "masters": []}
    i = 0
    while i + 6 <= len(data):
        sig, n = struct.unpack_from("<4sH", data, i)
        body = data[i + 6:i + 6 + n]
        if sig == b"HEDR" and n >= 12:
            v, recs, nxt = struct.unpack_from("<fiI", body)
            out.update(hedr_version=round(v, 2), records=recs, next_object_id=nxt)
        elif sig == b"MAST":
            out["masters"].append(body.rstrip(b"\0").decode("cp1252", "replace"))
        i += 6 + n
    return out
