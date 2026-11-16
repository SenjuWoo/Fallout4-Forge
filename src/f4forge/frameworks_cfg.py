"""Validators for framework config files: RobCo Patcher INIs and Base Object Swapper *_SWAP.ini.

Syntax registries live in knowledge/robco.json (keys per folder, from the author's examples and every installed
patch) and knowledge/bos.json (the author's own description). An unknown key is a warning naming its tier; a
broken form reference or a malformed line is an error.
"""
from __future__ import annotations

import re
from pathlib import Path

from .util import KNOWLEDGE_DIR, load_json, read_text

FORM_ID_RX = re.compile(r"^(0x)?0*[0-9A-Fa-f]{1,8}$")  # leading zeros allowed (the author writes 0x000140d99)


def _issue(code, msg, line=None, fix="", tier=None):
    d = {"code": code, "message": msg, "fix": fix}
    if line is not None:
        d["line"] = line
    if tier:
        d["tier"] = tier
    return d


# --- RobCo Patcher -------------------------------------------------------------------------------------

def robco_rules() -> dict:
    return load_json(KNOWLEDGE_DIR / "robco.json")


def robco_validate(path: Path, folder: str | None = None, load_order: set[str] | None = None) -> dict:
    r = robco_rules()
    path = Path(path)
    if folder is None:
        parts = [p for p in path.parts]
        low = [p.lower() for p in parts]
        folder = parts[low.index("robco_patcher") + 1] if "robco_patcher" in low and low.index("robco_patcher") + 1 < len(parts) - 1 else None
    known = {k.lower(): k for k in r["folders"].get(folder, [])} if folder in r["folders"] else None
    form_rx = re.compile(r["form_pattern"], re.I)
    errors, warnings, patches = [], [], 0
    if folder not in r["folders"]:
        warnings.append(_issue("ROBCO-FOLDER", f"folder '{folder}' is not a RobCo Patcher record folder",
                               fix="put the INI under RobCo_Patcher/<" + "|".join(r["folders"]) + ">/", tier="installed corpus"))
    for n, ln in enumerate(read_text(path).splitlines(), 1):
        s = ln.strip().lstrip("﻿")
        if not s or s.startswith("//") or s.startswith(";") or s.startswith("#"):
            continue
        if "=" not in s:
            # RobCo Patcher only reads key=value lines; bare text (banners, titles) is skipped by it.
            warnings.append(_issue("ROBCO-TEXT", f"line without key=value is ignored: '{s[:40]}'", n,
                                   "comment it with //", "installed corpus"))
            continue
        patches += 1
        segs = [x for x in s.split(":")]
        has_filter = False
        for seg in segs:
            if "=" not in seg:
                errors.append(_issue("ROBCO-SEGMENT", f"segment '{seg.strip()[:40]}' has no '='", n, "write key=value"))
                continue
            key, value = seg.split("=", 1)
            key = key.strip()
            if key.lower().startswith("filterby"):
                has_filter = True
            if known is not None and key.lower() not in known:
                warnings.append(_issue("ROBCO-KEY", f"unknown key '{key}' for {folder}", n,
                                       "check the RobCo Patcher articles", "installed corpus (fact robco.syntax)"))
            if key in r.get("deprecated", {}):
                warnings.append(_issue("ROBCO-DEPRECATED", f"{key}: {r['deprecated'][key]}", n, tier="author example"))
            for item in value.split(","):
                item = item.strip()
                if "|" in item and not item.lower().startswith("none"):
                    head = item.split("=", 1)[0]
                    if not form_rx.match(head):
                        errors.append(_issue("ROBCO-FORM", f"'{head[:60]}' is not Plugin.ext|FormID", n,
                                             "use e.g. Fallout4.esm|00004822"))
                    elif load_order is not None:
                        plug = head.split("|", 1)[0].strip().lower()
                        if plug not in load_order:
                            warnings.append(_issue("ROBCO-PLUGIN", f"{head.split('|')[0].strip()} is not in the load order", n,
                                                   tier="this install"))
        if not has_filter and folder not in ("misc",):
            warnings.append(_issue("ROBCO-NO-FILTER", "patch line has no filterBy... key (applies to every record?)", n,
                                   tier="author examples"))
    return {"file": str(path), "folder": folder, "patches": patches, "ok": not errors, "errors": errors,
            "warnings": warnings, "fact": r["fact"]}


# --- Base Object Swapper ---------------------------------------------------------------------------------

def bos_rules() -> dict:
    return load_json(KNOWLEDGE_DIR / "bos.json")


def _bos_id(token: str) -> str | None:
    t = token.strip()
    if not t:
        return "empty ID"
    if "~" in t:
        fid, plugin = t.split("~", 1)
        if not FORM_ID_RX.match(fid.strip()):
            return f"'{fid}' is not a hex FormID"
        if not re.search(r"\.(esm|esp|esl)$", plugin.strip(), re.I):
            return f"'{plugin}' is not a plugin file name"
        return None
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", t):
        return f"'{t}' is neither FormID~Plugin nor an EditorID"
    return None


TRANSFORM_RX = re.compile(r"^(posR|posA|pos|rotR|rotA|rot|scaleA|scale|flagsC|flags)\((.*)\)$", re.I)
CHANCE_RX = re.compile(r"^chance[SLR]?\((\d+(?:\.\d+)?)\)$", re.I)


def bos_validate(path: Path) -> dict:
    r = bos_rules()
    path = Path(path)
    errors, warnings, rules_n = [], [], 0
    if not path.name.lower().endswith("_swap.ini"):
        errors.append(_issue("BOS-NAME", "file name must end with _SWAP.ini", fix="rename to <Mod>_SWAP.ini"))
    section = None
    for n, ln in enumerate(read_text(path).splitlines(), 1):
        s = ln.strip().lstrip("﻿")
        if not s or s.startswith(";") or s.startswith("#"):
            continue
        if s.startswith("["):
            name = s.strip("[]").split("|", 1)[0].strip()
            if name not in r["sections"]:
                errors.append(_issue("BOS-SECTION", f"unknown section [{name}]", n, "use [Forms], [References], [Transforms] or [Properties]"))
                section = None
            else:
                section = name
            continue
        if section is None:
            errors.append(_issue("BOS-NO-SECTION", "rule outside a section", n, "start with [Forms]"))
            continue
        rules_n += 1
        fields = s.split("|")
        if len(fields) < r["sections"][section]["min"]:
            errors.append(_issue("BOS-FIELDS", f"{section} rule needs at least {r['sections'][section]['min']} '|' fields", n))
            continue
        ids = [fields[0]] + (fields[1].split(",") if section in ("Forms", "References") else [])
        for tok in ids:
            bad = _bos_id(tok)
            if bad:
                errors.append(_issue("BOS-ID", bad, n, "FormID~Plugin.esp or EditorID"))
        extra = fields[2:] if section in ("Forms", "References") else fields[1:]
        for f in extra:
            f = f.strip()
            if not f or f.upper() == "NONE":
                continue
            for part in re.split(r",(?![^()]*\))", f):
                part = part.strip()
                if CHANCE_RX.match(part):
                    v = float(CHANCE_RX.match(part).group(1))
                    if not 0 <= v <= 100:
                        errors.append(_issue("BOS-CHANCE", f"chance {v} outside 0-100", n))
                elif not TRANSFORM_RX.match(part):
                    warnings.append(_issue("BOS-PROPERTY", f"unknown property '{part[:40]}'", n,
                                           tier="author description (fact bos.syntax)"))
    return {"file": str(path), "rules": rules_n, "ok": not errors, "errors": errors, "warnings": warnings, "fact": r["fact"]}
