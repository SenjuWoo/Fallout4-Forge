"""Local index of the installed game, stored under the forge home (index/):
assets (every path in the archive name tables plus loose Data files), scripts (.pex names), and records
(EditorID and FormKey of installed plugins, through the worker). Rebuild after installing or removing mods.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .home import home_dir
from .util import ForgeError, ci_child, save_json

_ASSETS: dict[str, set] = {}


def index_dir() -> Path:
    return home_dir() / "index"


def build_assets(game_root: Path) -> dict:
    from . import ba2
    t = time.time()
    dd = ci_child(game_root, "Data")
    names: dict[str, str] = {}
    errors = []
    for p in sorted(dd.glob("*.ba2")):
        try:
            for e in ba2.Archive(p).entries:
                names.setdefault(ba2.norm(e["name"]), p.name)
        except ForgeError as ex:
            errors.append(f"{p.name}: {ex}")
    loose = 0
    for sub in ("Meshes", "Textures", "Materials", "Scripts", "Sound", "Interface", "Music"):
        d = ci_child(dd, sub)
        if not d:
            continue
        for f in d.rglob("*"):
            if f.is_file():
                names[f.relative_to(dd).as_posix().replace("/", "\\").lower()] = "loose"
                loose += 1
    out = {"built": time.strftime("%Y-%m-%dT%H:%M:%S"), "game_root": str(game_root), "assets": len(names),
           "loose": loose, "errors": errors, "seconds": round(time.time() - t, 1)}
    index_dir().mkdir(parents=True, exist_ok=True)
    with open(index_dir() / "assets.json", "w", encoding="utf-8") as f:
        json.dump({"meta": out, "assets": names}, f)
    _ASSETS.clear()
    return out


def assets(game_root: Path | None = None, required: bool = False) -> set | None:
    p = index_dir() / "assets.json"
    if not p.is_file():
        if required:
            raise ForgeError("no asset index yet", "f4forge index")
        return None
    key = str(p)
    if key not in _ASSETS:
        with open(p, encoding="utf-8") as f:
            _ASSETS[key] = set(json.load(f)["assets"])
    return _ASSETS[key]


def asset_source(path: str) -> str | None:
    p = index_dir() / "assets.json"
    if not p.is_file():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)["assets"].get(path.replace("/", "\\").lower())


def build_scripts(game_root: Path) -> dict:
    """Script names (.pex) from archives and loose files, from the asset index."""
    a = assets(game_root, required=True)
    names = sorted({x.rsplit("\\", 1)[-1][:-4] for x in a if x.endswith(".pex")})
    save_json(index_dir() / "scripts.json", {"scripts": names})
    return {"scripts": len(names)}


def build_records(game_root: Path) -> dict:
    """EditorID -> FormKey for every installed plugin, through the records worker (written as JSON lines)."""
    from . import records as R
    t = time.time()
    req = {"verb": "find", **R.base_request(game_root, None), "edid": "", "limit": 10_000_000}
    res = R.call(req, timeout=7200)
    rows = res.get("results", [])
    with open(index_dir() / "records.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps({"edid": r.get("editor_id"), "formkey": r["formkey"], "type": r["type"],
                                "winning": r.get("winning")}) + "\n")
    return {"records": len(rows), "plugins": res.get("plugins"), "seconds": round(time.time() - t, 1)}


def build(game_root: Path, records: bool = True) -> dict:
    out = {"assets": build_assets(game_root)}
    out["scripts"] = build_scripts(game_root)
    if records:
        try:
            out["records"] = build_records(game_root)
        except ForgeError as e:
            out["records"] = {"skipped": str(e), "fix": e.fix}
    save_json(index_dir() / "index.json", out)
    return out


def find_records(edid: str, limit: int = 50) -> list[dict]:
    p = index_dir() / "records.jsonl"
    if not p.is_file():
        raise ForgeError("no record index yet", "f4forge index")
    q = edid.lower()
    out = []
    with open(p, encoding="utf-8") as f:
        for ln in f:
            r = json.loads(ln)
            if q in (r.get("edid") or "").lower():
                out.append(r)
                if len(out) >= limit:
                    break
    return out
