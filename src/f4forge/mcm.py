"""MCM (Mod Configuration Menu) validator: config.json, settings.ini, keybinds.json, cross-checked.

Rules come from knowledge/mcm.json (fact mcm.schema: control types, value sources and actions as used by
every installed MCM config, plus the installed MCM.psc API). An unknown key or type is a warning that names
its tier; a broken reference (missing ini key, hotkey without a keybind, bad sourceForm) is an error.
"""
from __future__ import annotations

import configparser
import json
import re
from pathlib import Path

from .util import KNOWLEDGE_DIR, ForgeError, load_json


def rules() -> dict:
    return load_json(KNOWLEDGE_DIR / "mcm.json")


def _ini_keys(path: Path) -> set[str] | None:
    if not path.is_file():
        return None
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # keep case for reporting; comparisons lower-case below
    try:
        cp.read_string(path.read_text(encoding="utf-8-sig", errors="replace"))
    except configparser.Error as e:
        raise ForgeError(f"settings.ini does not parse: {e}", "fix the INI syntax")
    return {f"{k}:{s}".lower() for s in cp.sections() for k in cp.options(s)}


def validate(folder: Path, load_order: set[str] | None = None) -> dict:
    """Validate one MCM/Config/<Mod> folder."""
    r = rules()
    folder = Path(folder)
    errors, warnings = [], []

    def err(code, msg, fix=""):
        errors.append({"code": code, "message": msg, "fix": fix})

    def warn(code, msg, fix=""):
        warnings.append({"code": code, "message": msg, "fix": fix, "tier": "installed corpus (fact mcm.schema)"})

    cfg = folder / "config.json"
    if not cfg.is_file():
        err("MCM-NO-CONFIG", "config.json missing", "add MCM/Config/<Mod>/config.json")
        return {"folder": str(folder), "ok": False, "errors": errors, "warnings": warnings}
    try:
        doc = json.loads(cfg.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as e:
        err("MCM-JSON", f"config.json is not valid JSON: {e}", "fix the JSON (MCM does not accept comments)")
        return {"folder": str(folder), "ok": False, "errors": errors, "warnings": warnings}
    for k in r["top_level"]["required"]:
        if not doc.get(k):
            err("MCM-TOP-MISSING", f"top-level '{k}' missing", f"add \"{k}\"")
    for k in doc:
        if k not in r["top_level"]["known"]:
            warn("MCM-TOP-UNKNOWN", f"unknown top-level key '{k}'")
    if doc.get("modName") and doc["modName"] != folder.name:
        warn("MCM-MODNAME-FOLDER", f"modName '{doc['modName']}' differs from the folder '{folder.name}'",
             "MCM finds settings and keybinds by modName; keep them equal")
    if not doc.get("content") and not doc.get("pages"):
        err("MCM-NO-CONTENT", "neither 'content' nor 'pages'", "add a content list or pages")
    ini = _ini_keys(folder / "settings.ini")
    kb_ids = set()
    kb = folder / "keybinds.json"
    if kb.is_file():
        try:
            kdoc = json.loads(kb.read_text(encoding="utf-8-sig"))
            kb_ids = {str(k.get("id", "")).lower() for k in kdoc.get("keybinds", [])}
            if kdoc.get("modName") and doc.get("modName") and kdoc["modName"] != doc["modName"]:
                err("MCM-KB-MODNAME", f"keybinds.json modName '{kdoc['modName']}' differs from config.json", "use the same modName")
            for k in kdoc.get("keybinds", []):
                act = (k.get("action") or {}).get("type")
                if not k.get("id"):
                    err("MCM-KB-NO-ID", "a keybind has no id", "give every keybind an id")
                if act and act not in r["action_types"]:
                    warn("MCM-KB-ACTION", f"keybind {k.get('id')}: unknown action type {act}")
        except ValueError as e:
            err("MCM-KB-JSON", f"keybinds.json is not valid JSON: {e}", "fix the JSON")
    sf_rx = re.compile(r["source_form_pattern"])
    id_rx = re.compile(r["mod_setting_id_pattern"])
    controls = list(doc.get("content") or [])
    for pg in doc.get("pages") or []:
        if not pg.get("pageDisplayName"):
            warn("MCM-PAGE-NAME", "a page has no pageDisplayName")
        controls += pg.get("content") or []
    used_ini = set()
    for i, c in enumerate(controls):
        t = c.get("type")
        where = f"control {i + 1} ({t or 'no type'}{', ' + str(c['id']) if c.get('id') else ''})"
        if not t:
            err("MCM-NO-TYPE", f"{where}: no type", "set a control type")
            continue
        if t not in r["control_types"]:
            warn("MCM-TYPE-UNKNOWN", f"{where}: unknown control type")
        vo = c.get("valueOptions") or {}
        if t in r["value_controls"]:
            st = vo.get("sourceType")
            if not st:
                err("MCM-NO-SOURCE", f"{where}: valueOptions.sourceType missing", "add a sourceType")
            elif st not in r["source_types"]:
                warn("MCM-SOURCE-UNKNOWN", f"{where}: unknown sourceType {st}")
            else:
                spec = r["source_types"][st]
                for need in spec["needs"]:
                    if not (c.get(need) or vo.get(need)):
                        if need == "id" and "groupControl" in c:
                            # An id-less group switcher only shows/hides other controls; nothing is stored.
                            warn("MCM-GROUP-TOGGLE", f"{where}: group switcher without id (value not saved)")
                        else:
                            err("MCM-SOURCE-FIELD", f"{where}: {st} needs '{need}'", f"add \"{need}\"")
                if "sourceForm" in spec["needs"]:
                    sf = vo.get("sourceForm") or c.get("sourceForm")
                    if sf and not sf_rx.match(sf):
                        err("MCM-SOURCE-FORM", f"{where}: sourceForm '{sf}' is not Plugin.esp|FormID", "use e.g. MyMod.esp|800")
                    elif sf and load_order is not None and sf.split("|")[0].lower() not in load_order:
                        warn("MCM-SOURCE-PLUGIN", f"{where}: {sf.split('|')[0]} is not in the load order")
                if spec.get("ini") and c.get("id"):
                    if not id_rx.match(str(c["id"])):
                        err("MCM-ID-FORMAT", f"{where}: id must be name:Section", "e.g. bEnabled:Main")
                    elif ini is None:
                        err("MCM-NO-INI", f"{where}: uses a ModSetting but settings.ini is missing", "add settings.ini with defaults")
                    elif str(c["id"]).lower() not in ini:
                        err("MCM-INI-KEY", f"{where}: {c['id']} has no default in settings.ini", "add the key to settings.ini")
                    used_ini.add(str(c["id"]).lower())
        if t == "hotkey":
            if not c.get("id"):
                err("MCM-HOTKEY-ID", f"{where}: hotkey has no id", "add an id that keybinds.json defines")
            elif str(c["id"]).lower() not in kb_ids:
                err("MCM-HOTKEY-KB", f"{where}: hotkey {c['id']} is not in keybinds.json", "add it to keybinds.json")
        act = (c.get("action") or {}).get("type")
        if act and act not in r["action_types"]:
            warn("MCM-ACTION", f"{where}: unknown action type {act}")
    for p in doc.get("pluginRequirements") or []:
        if load_order is not None and p.lower() not in load_order:
            warn("MCM-PLUGIN-REQ", f"required plugin {p} is not in the load order")
    if ini:
        unused = sorted(ini - used_ini)
        if unused and len(unused) < 50:
            warnings.append({"code": "MCM-INI-UNUSED", "message": f"settings.ini keys not bound to a control: {', '.join(unused[:8])}",
                             "fix": "fine for script-only settings", "tier": "advice"})
    return {"folder": str(folder), "mod": doc.get("modName"), "controls": len(controls), "ok": not errors,
            "errors": errors, "warnings": warnings, "fact": r["fact"]}


def validate_installed(game_root: Path, load_order: set[str] | None = None) -> dict:
    from .util import ci_path
    base = ci_path(game_root, "Data/MCM/Config")
    rows = [validate(d, load_order) for d in sorted(base.iterdir()) if d.is_dir() and (d / "config.json").is_file()] if base else []
    return {"configs": len(rows), "ok": sum(1 for r in rows if r["ok"]),
            "with_errors": [{"mod": r["folder"].split("\\")[-1].split("/")[-1], "errors": r["errors"][:5]} for r in rows if not r["ok"]],
            "warnings": sum(len(r["warnings"]) for r in rows), "results": rows}
