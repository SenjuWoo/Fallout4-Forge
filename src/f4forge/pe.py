"""Pure-Python PE reader: the version resource (VS_FIXEDFILEINFO). No ctypes, works on any OS.

Layout from the Microsoft PE/COFF specification (primary): DOS header e_lfanew at 0x3C,
"PE\0\0", COFF header (20 bytes), optional header (magic 0x10B PE32 / 0x20B PE32+),
data directory 2 = resource table, resource directory tree type -> name -> language,
RT_VERSION = 16, VS_FIXEDFILEINFO signature 0xFEEF04BD.
"""
from __future__ import annotations

import struct
from pathlib import Path

RT_VERSION = 16
FIXED_SIG = b"\xbd\x04\xef\xfe"


class PEError(ValueError):
    pass


class PE:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.f = open(self.path, "rb")
        try:
            self._parse()
        except Exception:
            self.f.close()
            raise

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _read(self, off: int, n: int) -> bytes:
        self.f.seek(off)
        b = self.f.read(n)
        if len(b) != n:
            raise PEError("truncated PE")
        return b

    def _parse(self):
        head = self._read(0, 64)
        if head[:2] != b"MZ":
            raise PEError("not a PE file (no MZ)")
        lfanew = struct.unpack_from("<I", head, 0x3C)[0]
        if self._read(lfanew, 4) != b"PE\0\0":
            raise PEError("not a PE file (no PE signature)")
        coff = self._read(lfanew + 4, 20)
        self.machine, nsec = struct.unpack_from("<HH", coff, 0)
        opt_size = struct.unpack_from("<H", coff, 16)[0]
        opt_off = lfanew + 24
        opt = self._read(opt_off, opt_size)
        magic = struct.unpack_from("<H", opt, 0)[0]
        if magic == 0x10B:
            nd_off, dd_off = 92, 96
        elif magic == 0x20B:
            nd_off, dd_off = 108, 112
        else:
            raise PEError(f"unknown optional header magic {magic:#x}")
        self.pe32plus = magic == 0x20B
        ndirs = struct.unpack_from("<I", opt, nd_off)[0]
        self.dirs = [struct.unpack_from("<II", opt, dd_off + 8 * i) for i in range(min(ndirs, 16))
                     if dd_off + 8 * i + 8 <= len(opt)]
        self.sections = []
        sec = self._read(opt_off + opt_size, 40 * nsec)
        for i in range(nsec):
            name, vsize, va, rsize, rptr = struct.unpack_from("<8sIIII", sec, 40 * i)
            self.sections.append((name.rstrip(b"\0").decode("ascii", "replace"), vsize, va, rsize, rptr))

    def rva_to_off(self, rva: int) -> int:
        for _, vsize, va, rsize, rptr in self.sections:
            if va <= rva < va + max(vsize, rsize):
                return rptr + rva - va
        raise PEError(f"RVA {rva:#x} is outside every section")

    def resource(self, rtype: int) -> bytes | None:
        """Raw bytes of the first resource of a type (first name, first language)."""
        if len(self.dirs) < 3 or not self.dirs[2][0]:
            return None
        base = self.rva_to_off(self.dirs[2][0])

        def entries(off):
            named, ids = struct.unpack_from("<HH", self._read(base + off + 12, 4))
            raw = self._read(base + off + 16, 8 * (named + ids))
            return [struct.unpack_from("<II", raw, 8 * i) for i in range(named + ids)]

        off = None
        for name, target in entries(0):
            if not name & 0x80000000 and name == rtype:
                off = target
                break
        if off is None:
            return None
        for _ in range(2):  # name level, then language level
            if not off & 0x80000000:
                break
            sub = entries(off & 0x7FFFFFFF)
            if not sub:
                return None
            off = sub[0][1]
        if off & 0x80000000:
            return None
        rva, size = struct.unpack_from("<II", self._read(base + off, 8))
        return self._read(self.rva_to_off(rva), size)


def fixed_versions(path: Path) -> dict | None:
    """{'file': 'a.b.c.d', 'product': 'a.b.c.d'} from VS_FIXEDFILEINFO, or None."""
    try:
        with PE(path) as pe:
            data = pe.resource(RT_VERSION)
    except (OSError, PEError, struct.error):
        return None
    if not data:
        return None
    i = data.find(FIXED_SIG)
    if i < 0 or i + 24 > len(data):
        return None
    fms, fls, pms, pls = struct.unpack_from("<IIII", data, i + 8)

    def fmt(ms, ls):
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"

    return {"file": fmt(fms, fls), "product": fmt(pms, pls)}


def file_version(path: Path) -> str | None:
    v = fixed_versions(path)
    return v["file"] if v and v["file"] != "0.0.0.0" else None
