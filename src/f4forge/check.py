"""Project check: runs every validator that applies to the project's files and reports errors, warnings, gaps,
what was checked, and the evidence tier reached (static, compile, package; load and gameplay are never claimed).
"""
from __future__ import annotations

import re
from pathlib import Path

from . import project as P
from .util import ForgeError, iter_files

TEXT_SUFFIXES = (".json", ".ini", ".txt", ".xml", ".psc", ".md", ".toml", ".yaml", ".yml", ".cfg")


def _wrap(results: list[dict], name: str, rows: list[dict]):
    for r in rows:
        for e in r.get("errors", []):
            results["errors"].append({"check": name, "file": r.get("file") or r.get("folder"), **e})
        for w in r.get("warnings", []):
            results["warnings"].append({"check": name, "file": r.get("file") or r.get("folder"), **w})
    results["checked"].append({"check": name, "items": len(rows)})


def check_project(root: Path, game_arg: str | None = None, compile_scripts: bool = False) -> dict:
    m = P.load_manifest(root)
    res = {"project": str(root), "id": m.get("id"), "version": m.get("version"), "errors": [], "warnings": [],
           "gaps": [], "checked": []}
    data = root / "data"
    game_root = None
    load_order = None
    installed = None
    try:
        from .game import find_game
        game_root = find_game(game_arg)[0]
        from .loadorder import load_order as lo
        load_order = {o["plugin"].lower() for o in lo(game_root)["order"]}
        from .index import assets
        installed = assets(game_root)
        if installed is None:
            res["gaps"].append({"gap": "no asset index: material/texture/mesh references are checked against the project only",
                                "fix": "f4forge index"})
    except ForgeError as e:
        res["gaps"].append({"gap": f"game not found ({e}); installed references and masters are not checked", "fix": e.fix})

    # manifest
    if not P.SEMVER.match(str(m.get("version", ""))):
        res["errors"].append({"check": "manifest", "code": "VERSION", "message": f"version {m.get('version')} is not X.Y.Z", "fix": "f4forge bump X.Y.Z"})
    res["checked"].append({"check": "manifest", "items": 1})

    # plugin
    if m.get("plugin"):
        from . import plugin as PL
        name = m["plugin"]["name"]
        built = P.plugin_build_path(root, m)
        shipped = data / name
        target = shipped if shipped.is_file() else built if built.is_file() else None
        if target is None:
            res["errors"].append({"check": "plugin", "code": "PLUGIN-MISSING", "message": f"{name} not built", "fix": "f4forge build"})
        else:
            h = PL.read_header(target)
            if m["plugin"].get("light") or target.suffix.lower() == ".esl":
                _wrap(res, "plugin-light", [PL.esl_check(target)])
            if not shipped.is_file():
                res["warnings"].append({"check": "plugin", "code": "PLUGIN-NOT-IN-DATA",
                                        "message": f"{name} is built but not in data/ (f4forge build copies it)", "fix": "f4forge build"})
            yaml = root / "plugin"
            if yaml.is_dir() and any(yaml.rglob("*.yaml")):
                newest = max(p.stat().st_mtime for p in yaml.rglob("*.yaml"))
                if newest > target.stat().st_mtime + 1:
                    res["warnings"].append({"check": "plugin", "code": "PLUGIN-STALE",
                                            "message": "the YAML tree is newer than the plugin", "fix": "f4forge build"})
            for mast in h["masters"]:
                if load_order is not None and mast.lower() not in load_order and not (data / mast).is_file():
                    res["errors"].append({"check": "plugin", "code": "MISSING-MASTER", "message": f"master {mast} is not installed",
                                          "fix": "install it, or remove the dependency"})
            info = PL.inspect(target, edids=False)
            if info["types"].get("CELL") and info["formids"]["overrides"]:
                res["warnings"].append({"check": "previs", "code": "PREVIS-CELL-EDIT",
                                        "message": "the plugin overrides CELL records; edited cells with precombined geometry "
                                                   "need precombines and previs regenerated",
                                        "fix": "f4forge ck precombine/previs --plugin " + name + " (knowledge previs)"})
            res["checked"].append({"check": "plugin", "items": 1, "records": info["records_walked"]})

    # scripts
    src = root / "source" / "Scripts"
    pscs = list(src.rglob("*.psc")) if src.is_dir() else []
    if pscs:
        missing = [p.stem for p in pscs if not list((data / "Scripts").rglob(p.stem + ".pex"))]
        if missing:
            res["warnings"].append({"check": "scripts", "code": "PEX-MISSING", "message": f"not compiled: {', '.join(missing[:8])}",
                                    "fix": "f4forge build (or f4forge papyrus compile)"})
        if compile_scripts:
            from . import papyrus as PY
            try:
                r = PY.compile_scripts([src], root / "build" / "check-scripts", "auto", PY.import_dirs(root), game_root)
                for d in r["diagnostics"]:
                    (res["errors"] if d["severity"] == "error" else res["warnings"]).append(
                        {"check": "compile", "code": "PAPYRUS", "file": d["file"], "message": f"({d['line']},{d['column']}) {d['message']}", "fix": ""})
                res["compiled"] = r["ok"]
            except ForgeError as e:
                res["gaps"].append({"gap": f"compile not run: {e}", "fix": e.fix})
        res["checked"].append({"check": "scripts", "items": len(pscs)})
    for p in iter_files(data, (".psc",)):
        rel = p.relative_to(data).as_posix().lower()
        if not rel.startswith("scripts/source/"):
            res["errors"].append({"check": "scripts", "code": "PSC-OUTSIDE-SOURCE", "file": str(p),
                                  "message": "script source outside Scripts/Source would ship in the wrong place",
                                  "fix": "keep sources in source/Scripts"})

    # framework configs and data kinds
    from . import datakinds as D
    from . import frameworks_cfg as F
    from . import mcm
    mcm_dirs = [d for d in (data / "MCM" / "Config").iterdir() if d.is_dir()] if (data / "MCM" / "Config").is_dir() else []
    if mcm_dirs:
        _wrap(res, "mcm", [mcm.validate(d, load_order | {m["plugin"]["name"].lower()} if load_order and m.get("plugin") else load_order) for d in mcm_dirs])
    robco = [p for p in iter_files(data / "F4SE" / "Plugins" / "RobCo_Patcher", (".ini",))]
    if robco:
        lo2 = (load_order or set()) | ({m["plugin"]["name"].lower()} if m.get("plugin") else set())
        _wrap(res, "robco", [F.robco_validate(p, None, lo2 if load_order is not None else None) for p in robco])
    swaps = [p for p in data.glob("*") if p.name.lower().endswith("_swap.ini")] if data.is_dir() else []
    if swaps:
        _wrap(res, "bos", [F.bos_validate(p) for p in swaps])
    lm = list(iter_files(data / "F4SE" / "Plugins" / "F4EE" / "Presets", (".json",)))
    if lm:
        _wrap(res, "looksmenu", [D.looksmenu_validate(p) for p in lm])
    bsp = list(iter_files(data / "Tools" / "BodySlide" / "SliderPresets", (".xml",)))
    bsg = list(iter_files(data / "Tools" / "BodySlide" / "SliderGroups", (".xml",)))
    if bsp or bsg:
        _wrap(res, "bodyslide", [D.bodyslide_preset_validate(p) for p in bsp] + [D.slider_group_validate(p) for p in bsg])
    inis = [p for p in data.glob("*.ini") if not p.name.lower().endswith("_swap.ini")] if data.is_dir() else []
    if inis:
        _wrap(res, "ini", [D.ini_validate(p) for p in inis])

    # assets
    local = {p.relative_to(data).as_posix().replace("/", "\\").lower() for p in iter_files(data)} if data.is_dir() else set()
    known = local | (installed or set())
    mats = list(iter_files(data / "Materials", (".bgsm", ".bgem")))
    if mats:
        from . import bgsm
        rows = []
        for p in mats:
            row = {"file": str(p), "errors": [], "warnings": []}
            try:
                doc = bgsm.parse(p.read_bytes())
                for field, tex in bgsm.textures(doc).items():
                    key = "textures\\" + tex.replace("/", "\\").lower().lstrip("\\")
                    key = key.replace("textures\\textures\\", "textures\\")
                    if key not in known:
                        row["warnings"].append({"code": "MAT-TEXTURE", "message": f"{field} {tex} not found in the project"
                                                + (" or installed archives" if installed is not None else ""), "fix": "add the texture or fix the path"})
            except ForgeError as e:
                row["errors"].append({"code": "MAT-PARSE", "message": str(e), "fix": e.fix})
            rows.append(row)
        _wrap(res, "materials", rows)
    dds_files = list(iter_files(data / "Textures", (".dds",)))
    if dds_files:
        from . import textures as TX
        _wrap(res, "textures", [TX.inspect(p) for p in dds_files])
    nifs = list(iter_files(data / "Meshes", (".nif",)))
    if nifs:
        from . import nif
        rows = []
        for p in nifs:
            try:
                r = nif.check_refs(p, data, installed)
                rows.append({"file": str(p), "errors": [], "warnings": [
                    {"code": "NIF-REF", "message": f"{x['kind']} {x['path']} not found", "fix": "ship it or fix the path"} for x in r["missing"]]})
            except ForgeError as e:
                rows.append({"file": str(p), "errors": [{"code": "NIF-PARSE", "message": str(e), "fix": e.fix}], "warnings": []})
        _wrap(res, "meshes", rows)
    fuz = list(iter_files(data / "Sound" / "Voice", (".fuz",)))
    if fuz:
        from . import audio
        rows = []
        rx = re.compile(r"^sound/voice/[^/]+\.es[mpl]/[^/]+/[0-9a-f]{8}_\d+\.fuz$", re.I)
        for p in fuz:
            row = {"file": str(p), "errors": [], "warnings": []}
            try:
                audio.fuz_unpack(p.read_bytes())
            except ForgeError as e:
                row["errors"].append({"code": "FUZ", "message": str(e), "fix": e.fix})
            if not rx.match(p.relative_to(data).as_posix()):
                row["errors"].append({"code": "VOICE-PATH", "message": "voice file is not at Sound/Voice/<Plugin>/<VoiceType>/<INFO>_<n>.fuz",
                                      "fix": "f4forge audio voice writes the right path"})
            rows.append(row)
        _wrap(res, "voice", rows)
    if installed is not None and data.is_dir():
        from .datakinds import replacer_report
        rep = replacer_report(data, installed)
        if rep["replaces_installed"]:
            res["warnings"].append({"check": "replacers", "code": "REPLACES-INSTALLED",
                                    "message": f"{len(rep['replaces_installed'])} file(s) replace installed assets "
                                               f"(e.g. {rep['replaces_installed'][0]})", "fix": "intended for a replacer; otherwise rename"})
        res["checked"].append({"check": "replacers", "items": rep["new_files"] + len(rep["replaces_installed"])})

    # private paths and secrets (the package validator repeats this on the zip)
    from .package import scan_text
    for p in iter_files(data):
        if p.suffix.lower() in TEXT_SUFFIXES:
            for hit in scan_text(p.read_text(encoding="utf-8", errors="replace")):
                res["errors"].append({"check": "privacy", "file": str(p), **hit})

    # gaps from the kinds
    if "audio" in m.get("kinds", []) and game_root:
        from .game import creation_kit
        if creation_kit(game_root)["tier"] != "creation-kit":
            res["gaps"].append({"gap": "voice generation needs the Creation Kit (xwmaencode, LipGenerator)", "fix": "install the Creation Kit"})
    res["ok"] = not res["errors"]
    tiers = {"static": "PASS" if res["ok"] else "FAIL"}
    if pscs:
        tiers["compile"] = ("PASS" if res.get("compiled") else "FAIL") if compile_scripts else "NOT RUN"
    dist = root / "dist"
    zips = sorted(dist.glob(f"{m.get('id')}-{m.get('version')}*.zip")) if dist.is_dir() else []
    tiers["package"] = "BUILT" if zips else "NOT RUN"
    tiers["load"] = "NOT RUN"
    tiers["gameplay"] = "NOT RUN"
    res["evidence"] = tiers
    return res
