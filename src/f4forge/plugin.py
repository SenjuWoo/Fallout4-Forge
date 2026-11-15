"""Plugin files (.esm/.esp/.esl): TES4 header, masters, flags, record/GRUP walker, EDIDs, FormID stats.

Record header (24 bytes): type, u32 data size, u32 flags, u32 FormID, u32 version-control,
u16 form version, u16 unknown. GRUP header (24 bytes): "GRUP", u32 group size (header included),
4-byte label, i32 group type, u16 stamp, u16 vc, u32 unknown. Subrecord: type, u16 size, data;
an XXXX subrecord carries a u32 size for the next subrecord. Flag 0x00040000 = compressed:
u32 decompressed size + zlib stream. TES4 flags: 0x1 master, 0x80 localized, 0x200 light.
The light-plugin FormID range is data (knowledge/plugins.json, fact plugin.light_range).
"""
from __future__ import annotations

import mmap
import struct
import zlib
from collections import Counter
from pathlib import Path

from .util import KNOWLEDGE_DIR, ForgeError, load_json

FLAG_ESM = 0x1
FLAG_LOCALIZED = 0x80
FLAG_ESL = 0x200
FLAG_COMPRESSED = 0x00040000
FLAG_DELETED = 0x20
REC = struct.Struct("<4sIIIIHH")
SUB = struct.Struct("<4sH")


def rules() -> dict:
    return load_json(KNOWLEDGE_DIR / "plugins.json")


def read_header(path: Path, max_bytes: int = 1 << 16) -> dict:
    path = Path(path)
    with open(path, "rb") as f:
        head = f.read(24)
        if len(head) < 24 or head[:4] != b"TES4":
            raise ForgeError(f"{path.name}: not a plugin (no TES4 record)", "check the file is a Fallout 4 plugin")
        _, size, flags, _, _, form_version, _ = REC.unpack(head)
        data = f.read(min(size, max_bytes))
    out = {"flags": flags, "esm": bool(flags & FLAG_ESM), "esl": bool(flags & FLAG_ESL),
           "localized": bool(flags & FLAG_LOCALIZED), "form_version": form_version, "header_size": 24 + size,
           "hedr_version": None, "records": None, "next_object_id": None, "masters": [], "author": None,
           "description": None}
    for sig, body in subrecords(data):
        if sig == b"HEDR" and len(body) >= 12:
            v, recs, nxt = struct.unpack_from("<fiI", body)
            out.update(hedr_version=round(v, 2), records=recs, next_object_id=nxt)
        elif sig == b"MAST":
            out["masters"].append(zstring(body))
        elif sig == b"CNAM":
            out["author"] = zstring(body)
        elif sig == b"SNAM":
            out["description"] = zstring(body)
    return out


def zstring(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("cp1252", "replace")


def subrecords(data: bytes):
    i, big = 0, None
    n = len(data)
    while i + 6 <= n:
        sig, size = SUB.unpack_from(data, i)
        i += 6
        if big is not None:
            size, big = big, None
        if sig == b"XXXX" and size == 4:
            big = struct.unpack_from("<I", data, i)[0]
            i += 4
            continue
        yield sig, data[i:i + size]
        i += size


def is_light(path: Path, header: dict) -> bool:
    return Path(path).suffix.lower() == ".esl" or header["esl"]


class Walker:
    """Walk every record. Holds the file in a memory map; call close() or use as a context manager."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.f = open(self.path, "rb")
        self.size = self.path.stat().st_size
        self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ) if self.size else b""
        self.header = read_header(self.path)

    def close(self):
        if self.size:
            self.m.close()
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def records(self, want_data: bool = False):
        """Yield (type, formid, flags, offset, data_size, data-or-None). Groups are entered, not yielded."""
        m, end = self.m, self.size
        pos = self.header["header_size"]
        while pos + 24 <= end:
            sig = m[pos:pos + 4]
            if sig == b"GRUP":
                pos += 24  # enter the group: its contents follow its header
                continue
            _, size, flags, fid, _, _, _ = REC.unpack_from(m, pos)
            data = None
            if want_data:
                raw = m[pos + 24:pos + 24 + size]
                if flags & FLAG_COMPRESSED:
                    try:
                        data = zlib.decompress(raw[4:])
                    except zlib.error as e:
                        raise ForgeError(f"{self.path.name}: record {fid:08X} does not inflate: {e}", "the plugin is damaged")
                else:
                    data = raw
            yield sig.decode("ascii", "replace"), fid, flags, pos, size, data
            pos += 24 + size

    def groups(self) -> int:
        m, end, n = self.m, self.size, 0
        pos = self.header["header_size"]
        while pos + 24 <= end:
            if m[pos:pos + 4] == b"GRUP":
                n += 1
                pos += 24
            else:
                pos += 24 + struct.unpack_from("<I", m, pos + 4)[0]
        return n


def light_floor(header: dict) -> int:
    """Lowest object ID a new record may use (xEdit rule, fact plugin.light_range)."""
    r = rules()["object_id_floor"]
    v = header.get("hedr_version") or 0
    if v >= r["hardcoded_range_min_hedr"] and (len(header["masters"]) > 0 or not r["requires_master"]):
        return r["hardcoded_floor"]
    return r["default_floor"]


def inspect(path: Path, edids: bool = False, limit: int = 50) -> dict:
    path = Path(path)
    with Walker(path) as w:
        h = w.header
        own = len(h["masters"])
        types, overrides = Counter(), Counter()
        new_ids, compressed, deleted, total = [], 0, 0, 0
        edid_map, dup = {}, []
        for sig, fid, flags, _, _, data in w.records(want_data=edids):
            total += 1
            types[sig] += 1
            idx = fid >> 24
            if idx < own:
                overrides[h["masters"][idx]] += 1
            else:
                new_ids.append(fid & 0xFFFFFF)
            compressed += bool(flags & FLAG_COMPRESSED)
            deleted += bool(flags & FLAG_DELETED)
            if edids and data:
                for s, body in subrecords(data):
                    if s == b"EDID":
                        e = zstring(body)
                        if e in edid_map:
                            dup.append(e)
                        edid_map[e] = f"{fid:08X}"
                    break
        groups = w.groups()
    out = {"file": str(path), "hedr_version": h["hedr_version"], "form_version": h["form_version"],
           "hedr_records": h["records"], "next_object_id": h["next_object_id"], "records_walked": total,
           "groups": groups, "flags": {"esm": h["esm"], "esl": h["esl"], "localized": h["localized"]},
           "light": is_light(path, h), "masters": h["masters"], "author": h["author"],
           "types": dict(types.most_common(limit)), "type_count": len(types),
           "formids": {"new": len(new_ids), "overrides": sum(overrides.values()),
                       "overrides_by_master": dict(overrides.most_common()),
                       "new_min": f"{min(new_ids):06X}" if new_ids else None,
                       "new_max": f"{max(new_ids):06X}" if new_ids else None},
           "compressed_records": compressed, "deleted_records": deleted}
    if edids:
        out["edids"] = len(edid_map)
        out["duplicate_edids"] = sorted(set(dup))[:limit]
        out["edid_sample"] = dict(list(edid_map.items())[:min(limit, 20)])
    return out


def esl_check(path: Path) -> dict:
    """Can this plugin be (or is it valid as) a light plugin? New object IDs must sit in [floor, max]."""
    path = Path(path)
    r = rules()
    with Walker(path) as w:
        h = w.header
        own = len(h["masters"])
        ids = sorted({fid & 0xFFFFFF for _, fid, _, _, _, _ in w.records() if fid >> 24 >= own})
    floor, top = light_floor(h), r["light_max_object_id"]
    errors, warnings = [], []
    below = [i for i in ids if i < floor]
    above = [i for i in ids if i > top]
    if below:
        errors.append({"code": "LIGHT-BELOW-FLOOR", "message": f"{len(below)} new object ID(s) below {floor:03X}",
                       "examples": [f"{i:06X}" for i in below[:5]],
                       "fix": "renumber the new records into the light range (or raise HEDR to 1.0 with a master)"})
    if above:
        errors.append({"code": "LIGHT-ABOVE-MAX", "message": f"{len(above)} new object ID(s) above {top:03X}",
                       "examples": [f"{i:06X}" for i in above[:5]], "fix": "compact the FormIDs (xEdit: Compact FormIDs for ESL)"})
    if len(ids) > top - floor + 1:
        errors.append({"code": "LIGHT-TOO-MANY", "message": f"{len(ids)} new records; a light plugin holds {top - floor + 1}",
                       "fix": "split the plugin or keep it a full plugin"})
    if path.suffix.lower() == ".esp" and not h["esl"] and not errors:
        warnings.append({"code": "LIGHT-ELIGIBLE", "message": "eligible to be ESL-flagged", "fix": "set the ESL flag if you want it light"})
    return {"file": str(path), "light": is_light(path, h), "hedr_version": h["hedr_version"], "masters": len(h["masters"]),
            "new_records": len(ids), "allowed_range": [f"{floor:03X}", f"{top:03X}"], "ok": not errors,
            "errors": errors, "warnings": warnings, "fact": r["fact"]}
