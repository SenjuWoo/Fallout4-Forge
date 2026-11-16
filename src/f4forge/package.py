"""Packaging: a deterministic release zip from data/ (sorted entries, fixed timestamps), optional BA2 packing
(<Plugin> - Main.ba2 and <Plugin> - Textures.ba2), a private-path and secret scan, a build receipt naming every
input, and `validate` for any mod zip. FOMOD lives in fomod.py.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from . import __version__ as FORGE_VERSION
from .util import ForgeError, iter_files, save_json, sha256_file

FIXED_TIME = (2026, 1, 1, 0, 0, 0)
DEV_SUFFIXES = (".blend", ".blend1", ".psd", ".xcf", ".kra", ".spp", ".bak", ".tmp", ".log", ".pdb", ".lib", ".exp",
                ".obj", ".ilk", ".pyc")
PAPERWORK_NAMES = {"plan.md", "state.md", "changelog.md", "workspace_ownership.md", "f4forge.json", "validation.md",
                   "decisions.md", "agents.md", "claude.md", "local.md", "field-reports.md", "workspace.md"}
LOOSE_PREFIXES = ("f4se/", "mcm/", "tools/", "scripts/source/", "interface/translations/")
SECRET_PATTERNS = [
    ("SECRET-GITHUB", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("SECRET-AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("SECRET-OPENAI", re.compile(r"\bsk-[A-Za-z0-9_\-]{30,}")),
    ("SECRET-ANTHROPIC", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("SECRET-PRIVATE-KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
# Separators may be doubled when the path sits inside a JSON or escaped string.
PATH_PATTERN = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]{1,2}(?:Users|Documents and Settings|home)[\\/]{1,2}[^\\/\s\"']+", re.I)


def scan_text(text: str) -> list[dict]:
    hits = []
    for code, rx in SECRET_PATTERNS:
        m = rx.search(text)
        if m:
            hits.append({"code": code, "message": f"looks like a secret ({m.group(0)[:6]}…)", "fix": "remove it and rotate the key"})
    m = PATH_PATTERN.search(text)
    if m:
        hits.append({"code": "PRIVATE-PATH", "message": f"absolute user path {m.group(0)[:40]}", "fix": "use a Data-relative path"})
    return hits


def payload_files(root: Path) -> list[tuple[str, Path]]:
    data = root / "data"
    if not data.is_dir():
        raise ForgeError("no data/ folder", "f4forge build fills data/")
    out = []
    for p in iter_files(data):
        rel = p.relative_to(data).as_posix()
        low = rel.lower()
        if p.name.lower() in PAPERWORK_NAMES or low.endswith(DEV_SUFFIXES) or p.name.startswith(".") or "__pycache__" in low:
            continue
        out.append((rel, p))
    return out


def _zip(entries: list[tuple[str, bytes]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, data in sorted(entries, key=lambda e: e[0].lower()):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 0
            zf.writestr(info, data)
    tmp.replace(out)


def build(root: Path, out_dir: Path | None = None, archives: bool | None = None, ba2_version: int | None = None,
          with_fomod: bool | None = None) -> dict:
    from .project import load_manifest
    m = load_manifest(root)
    pk = m.get("package", {})
    archives = pk.get("archives", False) if archives is None else archives
    ba2_version = ba2_version or pk.get("ba2_version", 1)
    with_fomod = pk.get("fomod", False) if with_fomod is None else with_fomod
    files = payload_files(root)
    if not files:
        raise ForgeError("data/ holds nothing to package", "f4forge build, or add files to data/")
    entries: list[tuple[str, bytes]] = []
    packed = {}
    if archives:
        plugin = (m.get("plugin") or {}).get("name")
        if not plugin:
            raise ForgeError("BA2 packing needs a plugin (the game loads archives named after a plugin)", "add --kind plugin or drop --archives")
        stem = Path(plugin).stem
        tex = [(r, p) for r, p in files if r.lower().startswith("textures/") and r.lower().endswith(".dds")]
        main = [(r, p) for r, p in files if (r, p) not in tex and not r.lower().startswith(LOOSE_PREFIXES)
                and "/" in r and not r.lower().endswith((".esp", ".esm", ".esl", ".ini"))]
        loose = [(r, p) for r, p in files if (r, p) not in tex and (r, p) not in main]
        from . import ba2
        tmp = Path(tempfile.mkdtemp(prefix="f4f-pack-"))
        try:
            if main:
                a = tmp / f"{stem} - Main.ba2"
                ba2.write_gnrl([(r.replace("/", "\\"), p) for r, p in main], a, ba2_version)
                entries.append((a.name, a.read_bytes()))
                packed["main"] = {"archive": a.name, "files": len(main)}
            if tex:
                a = tmp / f"{stem} - Textures.ba2"
                ba2.write_dx10([(r.replace("/", "\\"), p) for r, p in tex], a, ba2_version)
                entries.append((a.name, a.read_bytes()))
                packed["textures"] = {"archive": a.name, "files": len(tex), "load": "NOT RUN"}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        files = loose
    for rel, p in files:
        entries.append((rel, p.read_bytes()))
    if with_fomod:
        from .fomod import generate
        # Main files go under Data/ (required); data/Options/<Name>/ folders become optional FOMOD choices.
        entries = [(n if n.lower().startswith("options/") else "Data/" + n, d) for n, d in entries]
        for n, d in generate(m, [n for n, _ in entries]).items():
            entries.append((n, d))
    out_dir = out_dir or root / "dist"
    zpath = out_dir / f"{m['id']}-{m['version']}.zip"
    _zip(entries, zpath)
    receipt = {"project": m["name"], "id": m["id"], "version": m["version"], "forge_version": FORGE_VERSION,
               "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "zip": zpath.name, "zip_sha256": sha256_file(zpath),
               "archives": packed, "fomod": bool(with_fomod),
               "inputs": [{"file": n, "sha256": hashlib.sha256(d).hexdigest()} for n, d in sorted(entries, key=lambda e: e[0].lower())]}
    save_json(out_dir / f"{m['id']}-{m['version']}.receipt.json", receipt)
    v = validate(zpath, m)
    return {"zip": str(zpath), "sha256": receipt["zip_sha256"], "entries": len(entries), "archives": packed,
            "fomod": bool(with_fomod), "receipt": str(out_dir / f"{m['id']}-{m['version']}.receipt.json"), "validation": v}


def validate(zpath: Path, manifest: dict | None = None) -> dict:
    errors, warnings = [], []
    names = []
    try:
        zf = zipfile.ZipFile(zpath)
    except (zipfile.BadZipFile, OSError) as e:
        return {"zip": str(zpath), "ok": False, "errors": [{"code": "ZIP", "message": str(e), "fix": "rebuild it"}], "warnings": []}
    with zf:
        lower_seen = {}
        has_fomod = any(n.lower().startswith("fomod/") for n in zf.namelist())
        for info in zf.infolist():
            n = info.filename
            if n.endswith("/"):
                continue
            names.append(n)
            low = n.lower()
            rel = low[5:] if has_fomod and low.startswith("data/") else low
            if n.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", n) or ".." in n.replace("\\", "/").split("/"):
                errors.append({"code": "ZIP-PATH", "message": f"unsafe entry path {n}", "fix": "entries must be relative"})
            if low in lower_seen:
                errors.append({"code": "ZIP-CASE", "message": f"{n} and {lower_seen[low]} differ only in case", "fix": "rename one"})
            lower_seen[low] = n
            base = low.rsplit("/", 1)[-1]
            if base in PAPERWORK_NAMES:
                errors.append({"code": "ZIP-PAPERWORK", "message": f"{n} is project paperwork", "fix": "keep it out of the payload"})
            if low.endswith(DEV_SUFFIXES):
                errors.append({"code": "ZIP-DEVFILE", "message": f"{n} is a development file", "fix": "remove it from data/"})
            if low.endswith(".psc") and not rel.startswith("scripts/source/"):
                errors.append({"code": "ZIP-PSC", "message": f"{n} is a script source outside Scripts/Source", "fix": "move it or drop it"})
            if not has_fomod and "/" not in rel and not low.endswith((".esp", ".esm", ".esl", ".ba2", ".ini", ".txt", ".md")):
                warnings.append({"code": "ZIP-ROOT", "message": f"{n} sits at the Data root", "fix": "check the layout"})
            if info.file_size < 8 * 1024 * 1024 and low.endswith((".json", ".ini", ".txt", ".xml", ".psc", ".toml", ".yaml", ".md", ".cfg")):
                for hit in scan_text(zf.read(info).decode("utf-8", "replace")):
                    errors.append({**hit, "message": f"{n}: {hit['message']}"})
        if has_fomod:
            from .fomod import validate_xml
            for e in validate_xml(zf):
                errors.append(e)
    plugins = [n for n in names if n.lower().endswith((".esp", ".esm", ".esl"))]
    return {"zip": str(zpath), "entries": len(names), "plugins": plugins, "fomod": any(n.lower().startswith("fomod/") for n in names),
            "ok": not errors, "errors": errors, "warnings": warnings}
