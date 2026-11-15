"""Plugin <-> YAML tree through the pinned Spriggit CLI. The YAML tree in a project's plugin/ folder is
the source of truth for its records (D4); the binary plugin in build/ is generated from it.

Serialization package: Spriggit.Yaml.Fallout4 at the version recorded in the project manifest
(default: the pinned Spriggit release). Spriggit fetches that NuGet package on first use.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .util import ForgeError, run

PACKAGE = "Spriggit.Yaml.Fallout4"


def exe() -> Path:
    from .tools import find_exe, load_lock
    p = find_exe("spriggit")
    if not p:
        raise ForgeError("Spriggit is not installed", "f4forge tools sync --only spriggit --approve")
    return p


def default_version() -> str:
    from .tools import entry, load_lock
    return entry(load_lock(), "spriggit")["tag"]


def _project(project: str | None):
    from .project import find_project, load_manifest
    root = find_project(project)
    return root, load_manifest(root)


def _package(manifest: dict | None) -> tuple[str, str]:
    sp = (manifest or {}).get("plugin", {}).get("spriggit", {})
    return sp.get("package", PACKAGE), sp.get("version", default_version())


def _guard(out: Path) -> None:
    try:
        from .game import find_game
        g = find_game()[0].resolve()
        o = out.resolve()
        if o == g or g in o.parents:
            raise ForgeError("refusing to write into the game folder (read-only input)", "choose a project folder")
    except ForgeError as e:
        if "refusing" in str(e):
            raise


def export(plugin_path: Path, out: Path | None = None, project: str | None = None) -> dict:
    manifest = None
    if out is None:
        root, manifest = _project(project)
        out = root / "plugin"
    elif project:
        _, manifest = _project(project)
    _guard(out)
    pkg, ver = _package(manifest)
    t = time.time()
    r = run([str(exe()), "serialize", "-i", str(plugin_path), "-o", str(out), "-g", "Fallout4", "-p", pkg, "-v", ver],
            timeout=3600)
    text = (r.get("stdout") or "") + (r.get("stderr") or "")
    if not r["ok"] or "Finished serializing" not in text:
        raise ForgeError("Spriggit serialize failed: " + text[-800:], "read the Spriggit output above")
    files = [p for p in out.rglob("*.yaml")]
    return {"plugin": str(plugin_path), "yaml": str(out), "yaml_files": len(files), "package": f"{pkg} {ver}",
            "seconds": round(time.time() - t, 1)}


def build(yaml_dir: Path | None = None, out: Path | None = None, project: str | None = None) -> dict:
    manifest = None
    if yaml_dir is None or out is None:
        from .project import plugin_build_path
        root, manifest = _project(project)
        yaml_dir = yaml_dir or root / "plugin"
        out = out or plugin_build_path(root, manifest)
    if not (Path(yaml_dir) / "spriggit-meta.json").is_file():
        raise ForgeError(f"{yaml_dir} is not a Spriggit tree (no spriggit-meta.json)",
                         "create records first (f4forge records new) or export a plugin (f4forge plugin export)")
    _guard(out)
    pkg, ver = _package(manifest)
    out.parent.mkdir(parents=True, exist_ok=True)
    t = time.time()
    r = run([str(exe()), "deserialize", "-i", str(yaml_dir), "-o", str(out), "-p", pkg, "-v", ver], timeout=3600)
    text = (r.get("stdout") or "") + (r.get("stderr") or "")
    if not r["ok"] or not out.is_file():
        raise ForgeError("Spriggit deserialize failed: " + text[-800:], "fix the YAML the message names")
    from .plugin import inspect
    info = inspect(out, edids=True, limit=20)
    return {"ok": True, "yaml": str(yaml_dir), "plugin": str(out), "records": info["records_walked"],
            "edids": info.get("edids"), "light": info["light"], "masters": info["masters"], "package": f"{pkg} {ver}",
            "seconds": round(time.time() - t, 1)}


def record_index(plugin_path: Path) -> dict:
    """{FormID hex: (type, EditorID)} from the pure-Python walker; used to prove round trips."""
    from .plugin import Walker, subrecords, zstring
    out = {}
    with Walker(plugin_path) as w:
        for sig, fid, _, _, _, data in w.records(want_data=True):
            edid = None
            for s, body in subrecords(data or b""):
                if s == b"EDID":
                    edid = zstring(body)
                break
            out[f"{fid:08X}"] = (sig, edid)
    return out


def roundtrip(plugin_path: Path, work: Path) -> dict:
    yaml_dir = work / "yaml"
    rebuilt = work / "rebuilt" / Path(plugin_path).name
    e = export(Path(plugin_path), yaml_dir)
    b = build(yaml_dir, rebuilt)
    a, c = record_index(Path(plugin_path)), record_index(rebuilt)
    return {"plugin": str(plugin_path), "records": len(a), "record_equal": a == c,
            "byte_equal": Path(plugin_path).read_bytes() == rebuilt.read_bytes(), "yaml_files": e["yaml_files"],
            "only_in_source": sorted(set(a) - set(c))[:5], "only_in_rebuilt": sorted(set(c) - set(a))[:5],
            "package": b["package"], "meta": json.loads((yaml_dir / "spriggit-meta.json").read_text(encoding="utf-8"))}
