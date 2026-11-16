"""NIF files: header, block types, string table, texture sets and material references; Blender round trips.

Header layout from niftools nif.xml (primary, fact mesh.nif_header): "Gamebryo File Format, Version x\\n",
u32 version, u8 endian, u32 user version, u32 block count, BS stream header (u32 BS version, export strings
as u8-length strings: author, [u32 unknown if BSVER > 130], process script if BSVER < 131, export script,
max filepath if BSVER >= 103), u16 block-type count + u32-length strings, u16 type index per block,
u32 size per block, u32 string count, u32 max length, u32-length strings, u32 group count + sizes.
Fallout 4 meshes: version 20.2.0.7, user version 12, BS version 130.
"""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

from .util import ForgeError, run

TEXTURE_SET_TYPES = {"BSShaderTextureSet"}
MATERIAL_RX = re.compile(r"\.(bgsm|bgem)$", re.I)


class _R:
    def __init__(self, data: bytes):
        self.d, self.i = data, 0

    def take(self, fmt: str):
        v = struct.unpack_from("<" + fmt, self.d, self.i)
        self.i += struct.calcsize("<" + fmt)
        return v[0] if len(v) == 1 else v

    def short_string(self) -> str:
        n = self.d[self.i]
        s = self.d[self.i + 1:self.i + 1 + n].rstrip(b"\0").decode("cp1252", "replace")
        self.i += 1 + n
        return s

    def sized_string(self) -> str:
        n = self.take("I")
        s = self.d[self.i:self.i + n].decode("cp1252", "replace")
        self.i += n
        return s


def read(path: Path) -> dict:
    data = Path(path).read_bytes()
    nl = data.find(b"\n", 0, 128)
    if nl < 0 or not data.startswith((b"Gamebryo File Format", b"NetImmerse File Format")):
        raise ForgeError(f"{Path(path).name}: not a NIF file", "pass a .nif")
    r = _R(data)
    r.i = nl + 1
    header_text = data[:nl].decode("ascii", "replace")
    try:
        version = r.take("I")
        vtxt = ".".join(str((version >> s) & 0xFF) for s in (24, 16, 8, 0))
        if version < 0x14020007:
            raise ForgeError(f"NIF version {vtxt} is older than the Fallout 4 layout", "only 20.2.0.7 files are read")
        endian = r.take("B")
        user = r.take("I")
        nblocks = r.take("I")
        bsver = r.take("I")
        author = r.short_string()
        if bsver > 130:
            r.take("I")
        process = r.short_string() if bsver < 131 else ""
        export = r.short_string()
        maxpath = r.short_string() if bsver >= 103 else ""
        ntypes = r.take("H")
        types = [r.sized_string() for _ in range(ntypes)]
        type_idx = [r.take("H") for _ in range(nblocks)]
        sizes = [r.take("I") for _ in range(nblocks)]
        nstr = r.take("I")
        r.take("I")
        strings = [r.sized_string() for _ in range(nstr)]
        ngroups = r.take("I")
        r.i += 4 * ngroups
    except struct.error as e:
        raise ForgeError(f"{Path(path).name}: header truncated ({e})", "the NIF is damaged")
    blocks = []
    pos = r.i
    for ti, size in zip(type_idx, sizes):
        blocks.append({"type": types[ti & 0x7FFF], "offset": pos, "size": size})
        pos += size
    footer = None
    if pos + 4 <= len(data):
        nroots = struct.unpack_from("<I", data, pos)[0]
        if pos + 4 + 4 * nroots == len(data):
            footer = nroots
    out = {"file": str(path), "header": header_text, "version": vtxt, "endian": "little" if endian else "big",
           "user_version": user, "bs_version": bsver, "author": author, "process_script": process,
           "export_script": export, "max_filepath": maxpath, "blocks": len(blocks), "block_types": types,
           "strings": strings, "roots": footer, "size_ok": footer is not None, "_blocks": blocks, "_data": data}
    return out


def info(path: Path) -> dict:
    n = read(path)
    counts = {}
    for b in n["_blocks"]:
        counts[b["type"]] = counts.get(b["type"], 0) + 1
    return {k: v for k, v in n.items() if not k.startswith("_") and k != "strings"} | {
        "string_count": len(n["strings"]), "block_counts": counts}


def refs(path: Path) -> dict:
    n = read(path)
    data = n["_data"]
    textures = []
    for b in n["_blocks"]:
        if b["type"] in TEXTURE_SET_TYPES:
            r = _R(data)
            r.i = b["offset"]
            count = r.take("i")
            for _ in range(max(0, count)):
                t = r.sized_string()
                if t:
                    textures.append(t)
    materials = sorted({s for s in n["strings"] if MATERIAL_RX.search(s)})
    return {"file": str(path), "materials": materials, "textures": sorted(set(textures))}


def norm_asset(p: str, prefix: str) -> str:
    """Data-relative lowercase backslash path; texture paths in NIFs omit the 'textures\\' prefix sometimes."""
    q = p.replace("/", "\\").lower().lstrip("\\")
    if q.startswith("data\\"):
        q = q[5:]
    if not q.startswith(prefix + "\\"):
        q = prefix + "\\" + q
    return q


def check_refs(path: Path, project_data: Path | None, installed: set[str] | None) -> dict:
    r = refs(path)
    missing, found = [], 0
    local = set()
    if project_data and project_data.is_dir():
        local = {p.relative_to(project_data).as_posix().replace("/", "\\").lower() for p in project_data.rglob("*") if p.is_file()}
    for kind, prefix in (("materials", "materials"), ("textures", "textures")):
        for a in r[kind]:
            key = norm_asset(a, prefix)
            if key in local or (installed is not None and key in installed):
                found += 1
            else:
                missing.append({"kind": kind[:-1], "path": a, "resolved": key})
    return {**r, "resolved": found, "missing": missing,
            "installed_index": installed is not None, "ok": not missing}


# --- Blender + PyNifly (headless, add-on loaded by path, never installed into Blender) ------------

BLENDER_SCRIPT = Path(__file__).with_name("blender_nif.py")


def blender_exe() -> str:
    from .tools import find_exe
    p = find_exe("blender")
    if not p:
        raise ForgeError("Blender not found", "install Blender or put blender on PATH")
    return str(p)


def pynifly_dir() -> Path:
    from .tools import tool_path
    d = tool_path("pynifly")
    if not d:
        raise ForgeError("PyNifly is not installed", "f4forge tools sync --only pynifly --approve")
    return d


def blender_run(mode: str, src: Path, out: Path, timeout: int = 900) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = [blender_exe(), "-b", "--factory-startup", "--python", str(BLENDER_SCRIPT), "--",
            mode, str(pynifly_dir()), str(src), str(out)]
    r = run(argv, timeout=timeout)
    text = (r.get("stdout") or "") + (r.get("stderr") or "")
    result = None
    for ln in text.splitlines():
        if ln.startswith("F4FORGE_RESULT "):
            result = json.loads(ln[len("F4FORGE_RESULT "):])
    if not result or not result.get("ok") or not out.is_file():
        raise ForgeError(f"Blender {mode} failed: " + (result or {}).get("error", text[-600:]),
                         "read the Blender output above")
    return {"mode": mode, "input": str(src), "output": str(out), **{k: v for k, v in result.items() if k != "ok"}}
