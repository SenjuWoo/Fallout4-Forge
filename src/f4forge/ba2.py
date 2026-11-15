"""BA2 archives (BTDX): read, list, extract, verify, and write GNRL and DX10.

Header (24 bytes): magic "BTDX", u32 version, 4-char type "GNRL" | "DX10", u32 file count,
u64 name-table offset. Fallout 4 archives use versions 1, 7 and 8 with the same layout
(fact ba2.header, confirmed by the installed sweep).

GNRL record (36 bytes): u32 name hash, char[4] extension, u32 directory hash, u32 flags,
u64 data offset, u32 packed size (0 = stored), u32 unpacked size, u32 0xBAADF00D.
DX10 record: u32 name hash, char[4] ext, u32 dir hash, u8 unknown, u8 chunk count,
u16 chunk-header size (24), u16 height, u16 width, u8 mip count, u8 DXGI format,
u16 flags (low byte 1 = cubemap, high byte = tile mode 8), then per chunk: u64 offset,
u32 packed size, u32 unpacked size, u16 first mip, u16 last mip, u32 0xBAADF00D.
Name table: per file u16 length + bytes (no terminator). Compression: zlib.
"""
from __future__ import annotations

import fnmatch
import os
import struct
import time
import zlib
from pathlib import Path

from . import dds
from .util import KNOWLEDGE_DIR, ForgeError, iter_files, load_json

HEADER = struct.Struct("<4sI4sIQ")
GNRL_REC = struct.Struct("<I4sIIQIII")
DX10_REC = struct.Struct("<I4sIBBHHHBBH")
DX10_CHUNK = struct.Struct("<QIIHHI")
ALIGN = 0xBAADF00D


def read_header(path: Path) -> dict:
    with open(path, "rb") as f:
        raw = f.read(HEADER.size)
    if len(raw) < HEADER.size:
        raise ForgeError(f"{Path(path).name}: shorter than a BA2 header", "the file is truncated or not a BA2")
    magic, version, kind, count, names = HEADER.unpack(raw)
    if magic != b"BTDX":
        raise ForgeError(f"{Path(path).name}: not a BA2 (magic {magic!r})", "only Fallout 4 BTDX archives are read")
    return {"version": version, "type": kind.decode("ascii", "replace"), "files": count, "name_table_offset": names}


class Archive:
    """A parsed BA2. Entries carry name, ext and data locations; payload is read lazily."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.size = self.path.stat().st_size
        h = read_header(self.path)
        self.version, self.type, self.count, self.names_at = h["version"], h["type"], h["files"], h["name_table_offset"]
        if self.type not in ("GNRL", "DX10"):
            raise ForgeError(f"{self.path.name}: unknown BA2 type {self.type}", "only GNRL and DX10 are known")
        if self.version not in (1, 7, 8):
            raise ForgeError(f"{self.path.name}: BA2 version {self.version} is not a Fallout 4 layout",
                             "versions 1, 7 and 8 are read (fact ba2.header)")
        self.entries: list[dict] = []
        with open(self.path, "rb") as f:
            f.seek(HEADER.size)
            if self.type == "GNRL":
                raw = f.read(GNRL_REC.size * self.count)
                if len(raw) != GNRL_REC.size * self.count:
                    raise ForgeError(f"{self.path.name}: file table truncated", "the archive is damaged")
                for i in range(self.count):
                    nh, ext, dh, flags, off, packed, size, align = GNRL_REC.unpack_from(raw, i * GNRL_REC.size)
                    self.entries.append({"name_hash": nh, "ext": ext.rstrip(b"\0").decode("ascii", "replace"),
                                         "dir_hash": dh, "flags": flags, "offset": off, "packed": packed,
                                         "size": size, "align": align})
            else:
                for _ in range(self.count):
                    raw = f.read(DX10_REC.size)
                    if len(raw) != DX10_REC.size:
                        raise ForgeError(f"{self.path.name}: texture table truncated", "the archive is damaged")
                    nh, ext, dh, unk, nchunks, chsize, height, width, mips, fmt, flags = DX10_REC.unpack(raw)
                    chunks = []
                    for _c in range(nchunks):
                        off, packed, size, m0, m1, align = DX10_CHUNK.unpack(f.read(DX10_CHUNK.size))
                        chunks.append({"offset": off, "packed": packed, "size": size, "mip_first": m0, "mip_last": m1,
                                       "align": align})
                    self.entries.append({"name_hash": nh, "ext": ext.rstrip(b"\0").decode("ascii", "replace"),
                                         "dir_hash": dh, "unknown": unk, "chunk_header_size": chsize,
                                         "height": height, "width": width, "mips": mips, "format": fmt,
                                         "flags": flags, "chunks": chunks})
            if self.names_at:
                if self.names_at > self.size:
                    raise ForgeError(f"{self.path.name}: name table offset past the end", "the archive is damaged")
                f.seek(self.names_at)
                blob = f.read()
                pos = 0
                for e in self.entries:
                    if pos + 2 > len(blob):
                        raise ForgeError(f"{self.path.name}: name table truncated", "the archive is damaged")
                    n = struct.unpack_from("<H", blob, pos)[0]
                    e["name"] = blob[pos + 2:pos + 2 + n].decode("cp1252", "replace")
                    pos += 2 + n
            else:
                for i, e in enumerate(self.entries):
                    e["name"] = f"{e['name_hash']:08x}.{e['ext']}"

    def summary(self) -> dict:
        out = {"file": str(self.path), "version": self.version, "type": self.type, "files": self.count,
               "bytes": self.size}
        if self.type == "GNRL":
            out["compressed"] = sum(1 for e in self.entries if e["packed"])
        else:
            out["chunks"] = sum(len(e["chunks"]) for e in self.entries)
        return out

    def _read(self, f, off: int, packed: int, size: int) -> bytes:
        f.seek(off)
        if packed:
            data = zlib.decompress(f.read(packed))
        else:
            data = f.read(size)
        if len(data) != size:
            raise ForgeError(f"{self.path.name}: entry inflated to {len(data)} bytes, expected {size}", "the archive is damaged")
        return data

    def read(self, e: dict, f=None) -> bytes:
        """The file as it is on disk once extracted (DX10 entries get a rebuilt DDS header)."""
        own = f is None
        f = f or open(self.path, "rb")
        try:
            if self.type == "GNRL":
                return self._read(f, e["offset"], e["packed"], e["size"])
            payload = b"".join(self._read(f, c["offset"], c["packed"], c["size"]) for c in e["chunks"])
            return dds.build_header(e["width"], e["height"], e["mips"], e["format"], bool(e["flags"] & 1)) + payload
        finally:
            if own:
                f.close()

    def payload(self, e: dict, f=None) -> bytes:
        """Raw payload: GNRL file bytes, or DX10 pixel data without a DDS header."""
        data = self.read(e, f)
        return data if self.type == "GNRL" else data[dds.header_size(data):]

    def find(self, name: str) -> dict | None:
        low = norm(name)
        return next((e for e in self.entries if norm(e["name"]) == low), None)


def norm(name: str) -> str:
    return name.replace("/", "\\").lower().lstrip("\\")


def _safe_target(out: Path, name: str) -> Path:
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".", "..")]
    target = out.joinpath(*parts)
    if out.resolve() not in target.resolve().parents:
        raise ForgeError(f"entry escapes the output folder: {name}", "the archive is unsafe")
    return target


def guard_out(out: Path, game_root: Path | None) -> None:
    if game_root and (out.resolve() == game_root.resolve() or game_root.resolve() in out.resolve().parents):
        raise ForgeError("refusing to extract into the game folder (read-only input)", "choose an --out folder outside the game")


def list_entries(arc: Archive, pattern: str | None = None, limit: int | None = None) -> list[dict]:
    rows = []
    for e in arc.entries:
        if pattern and not fnmatch.fnmatch(e["name"].lower(), pattern.lower()):
            continue
        if arc.type == "GNRL":
            rows.append({"name": e["name"], "size": e["size"], "packed": e["packed"]})
        else:
            rows.append({"name": e["name"], "width": e["width"], "height": e["height"], "mips": e["mips"],
                         "format": dds.format_name(e["format"]), "chunks": len(e["chunks"]),
                         "cubemap": bool(e["flags"] & 1)})
        if limit and len(rows) >= limit:
            break
    return rows


def extract(arc: Archive, out: Path, pattern: str | None = None) -> dict:
    n, total = 0, 0
    with open(arc.path, "rb") as f:
        for e in arc.entries:
            if pattern and not fnmatch.fnmatch(e["name"].lower(), pattern.lower()):
                continue
            target = _safe_target(out, e["name"])
            target.parent.mkdir(parents=True, exist_ok=True)
            data = arc.read(e, f)
            target.write_bytes(data)
            n += 1
            total += len(data)
    return {"archive": str(arc.path), "out": str(out), "files": n, "bytes": total}


def verify(path: Path, sample: str = "middle") -> dict:
    """Parse the whole table and name table, then inflate one sampled entry (and check its size)."""
    t = time.time()
    try:
        arc = Archive(path)
        row = arc.summary()
        if arc.entries:
            idx = {"first": 0, "middle": len(arc.entries) // 2, "last": len(arc.entries) - 1}[sample]
            e = arc.entries[idx]
            data = arc.read(e)
            row["sample"] = {"name": e["name"], "bytes": len(data)}
            if arc.type == "DX10":
                info = dds.parse(data)
                row["sample"]["format"] = info["format_name"]
        row["ok"] = True
    except (ForgeError, OSError, zlib.error, struct.error) as ex:
        row = {"file": str(path), "ok": False, "error": str(ex)}
    row["seconds"] = round(time.time() - t, 3)
    return row


# --- writer -----------------------------------------------------------------------------------

def rules() -> dict:
    return load_json(KNOWLEDGE_DIR / "ba2.json")


def crc32_lower(text: str) -> int:
    """BA2 hash: CRC-32 (reflected 0xEDB88320) with initial value 0 and no final XOR, over lowercase cp1252
    bytes (fact ba2.hashes). zlib.crc32 pre/post-inverts, so start it at 0xFFFFFFFF and invert the result."""
    return zlib.crc32(text.lower().encode("cp1252", "replace"), 0xFFFFFFFF) ^ 0xFFFFFFFF


def name_hashes(name: str) -> tuple[int, bytes, int]:
    """(name hash, ext bytes, dir hash) for an archive path. Rule in knowledge/ba2.json (fact ba2.hashes)."""
    p = norm(name)
    d, _, f = p.rpartition("\\")
    stem, dot, ext = f.rpartition(".")
    if not dot:
        stem, ext = f, ""
    return crc32_lower(stem), ext.encode("ascii", "replace")[:4].ljust(4, b"\0"), crc32_lower(d)


def collect(root: Path, include: list[str] | None = None) -> list[tuple[str, Path]]:
    """(archive name, source path) for every file under root, Data-relative names with backslashes."""
    out = []
    for p in iter_files(root):
        rel = p.relative_to(root).as_posix()
        if include and not any(fnmatch.fnmatch(rel.lower(), pat.lower()) for pat in include):
            continue
        out.append((rel.replace("/", "\\"), p))
    out.sort(key=lambda x: x[0].lower())
    return out


def write_gnrl(files: list[tuple[str, Path | bytes]], out: Path, version: int = 1, level: int = 6) -> dict:
    if version not in (1, 7, 8):
        raise ForgeError(f"BA2 version {version} is not written", "use 1 (default, every runtime) or 8")
    stored = tuple(rules()["gnrl_stored_extensions"])
    blobs, records = [], []
    for name, src in files:
        data = src if isinstance(src, bytes) else Path(src).read_bytes()
        nh, ext, dh = name_hashes(name)
        packed = b""
        if not name.lower().endswith(stored) and data:
            c = zlib.compress(data, level)
            if len(c) < len(data):
                packed = c
        blobs.append(packed or data)
        records.append([nh, ext, dh, 0x00100100, 0, len(packed), len(data), ALIGN])
    off = HEADER.size + GNRL_REC.size * len(records)
    for r, b in zip(records, blobs):
        r[4] = off
        off += len(b)
    names = b"".join(struct.pack("<H", len(n.encode("cp1252"))) + n.encode("cp1252") for n, _ in files)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(HEADER.pack(b"BTDX", version, b"GNRL", len(records), off))
        for r in records:
            f.write(GNRL_REC.pack(*r))
        for b in blobs:
            f.write(b)
        f.write(names)
    os.replace(tmp, out)
    return {"archive": str(out), "type": "GNRL", "version": version, "files": len(records),
            "compressed": sum(1 for r in records if r[5]), "bytes": out.stat().st_size}


def chunk_plan(width: int, height: int, mips: int, fmt: int, cube: bool) -> list[tuple[int, int]]:
    """Mip ranges per chunk, from the rule taken from vanilla archives (knowledge/ba2.json, fact ba2.dx10_chunks):
    a mip gets its own chunk while it has at least min_pixels pixels, up to max_chunks - 1 chunks;
    the remaining mips share the last chunk. Cubemaps are one chunk."""
    r = rules()["dx10_chunks"]
    if cube or mips <= 1:
        return [(0, max(0, mips - 1))]
    plan, m = [], 0
    while m < mips:
        w, h = max(1, width >> m), max(1, height >> m)
        if len(plan) < r["max_chunks"] - 1 and w * h >= r["min_pixels"] and m < mips - 1:
            plan.append((m, m))
            m += 1
        else:
            plan.append((m, mips - 1))
            break
    return plan


def write_dx10(files: list[tuple[str, Path | bytes]], out: Path, version: int = 1, level: int = 6) -> dict:
    if version not in (1, 7, 8):
        raise ForgeError(f"BA2 version {version} is not written", "use 1 (default) or 8")
    recs, blobs_per = [], []
    for name, src in files:
        data = src if isinstance(src, bytes) else Path(src).read_bytes()
        info = dds.parse(data)
        if info["dxgi"] is None:
            raise ForgeError(f"{name}: DDS format {info['format_name']} has no DXGI code", "convert it with f4forge tex convert")
        body = data[info["header_size"]:]
        cube = info["cubemap"]
        plan = chunk_plan(info["width"], info["height"], info["mips"], info["dxgi"], cube)
        faces = 6 if cube else 1
        offsets = []
        pos = 0
        for m0, m1 in plan:
            n = sum(dds.mip_size(max(1, info["width"] >> m), max(1, info["height"] >> m), info["dxgi"])
                    for m in range(m0, m1 + 1)) * faces
            offsets.append((m0, m1, body[pos:pos + n]))
            pos += n
        if pos != len(body):
            raise ForgeError(f"{name}: DDS payload is {len(body)} bytes, expected {pos} for its mips", "re-export the texture")
        chunks = []
        for m0, m1, raw in offsets:
            c = zlib.compress(raw, level)
            packed = c if len(c) < len(raw) else b""
            chunks.append([0, len(packed), len(raw), m0, m1, ALIGN, packed or raw])
        nh, ext, dh = name_hashes(name)
        recs.append([nh, ext, dh, 0, len(chunks), DX10_CHUNK.size, info["height"], info["width"], info["mips"],
                     info["dxgi"], 0x800 | (1 if cube else 0)])
        blobs_per.append(chunks)
    off = HEADER.size + sum(DX10_REC.size + DX10_CHUNK.size * len(c) for c in blobs_per)
    for chunks in blobs_per:
        for c in chunks:
            c[0] = off
            off += len(c[6])
    names = b"".join(struct.pack("<H", len(n.encode("cp1252"))) + n.encode("cp1252") for n, _ in files)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(HEADER.pack(b"BTDX", version, b"DX10", len(recs), off))
        for r, chunks in zip(recs, blobs_per):
            f.write(DX10_REC.pack(*r))
            for c in chunks:
                f.write(DX10_CHUNK.pack(*c[:6]))
        for chunks in blobs_per:
            for c in chunks:
                f.write(c[6])
        f.write(names)
    os.replace(tmp, out)
    return {"archive": str(out), "type": "DX10", "version": version, "files": len(recs),
            "chunks": sum(len(c) for c in blobs_per), "bytes": out.stat().st_size, "load": "NOT RUN"}


def pack(src: Path, out: Path, kind: str = "auto", version: int = 1, include: list[str] | None = None) -> dict:
    files = collect(src, include)
    if not files:
        raise ForgeError(f"nothing to pack under {src}", "point at a Data-relative folder")
    if kind == "auto":
        kind = "DX10" if all(n.lower().endswith(".dds") for n, _ in files) else "GNRL"
    return write_dx10(files, out, version) if kind.upper() == "DX10" else write_gnrl(files, out, version)
