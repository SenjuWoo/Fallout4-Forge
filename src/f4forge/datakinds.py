"""Small data kinds: LooksMenu presets (JSON), BodySlide slider presets and slider groups (XML), INI tweak
files, and loose-file replacers. Each validator returns errors/warnings; unknown keys are warnings.
"""
from __future__ import annotations

import configparser
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .util import ForgeError, read_text

LOOKSMENU_KEYS = {"BodyMorphs", "Gender", "HairColor", "HeadParts", "Morphs", "Overlays", "TintOrder", "Tints", "Weight",
                  "Name", "Race", "Version", "Bones", "Skin"}


def _res(path, errors, warnings, **extra):
    return {"file": str(path), "ok": not errors, "errors": errors, "warnings": warnings, **extra}


def looksmenu_validate(path: Path) -> dict:
    errors, warnings = [], []
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as e:
        return _res(path, [{"code": "LM-JSON", "message": f"not valid JSON: {e}", "fix": "fix the JSON"}], [])
    if not isinstance(doc, dict):
        return _res(path, [{"code": "LM-ROOT", "message": "preset root must be an object", "fix": ""}], [])
    for k in doc:
        if k not in LOOKSMENU_KEYS:
            warnings.append({"code": "LM-KEY", "message": f"unknown key '{k}'", "fix": "", "tier": "installed presets"})
    if "Gender" in doc and doc["Gender"] not in (0, 1):
        errors.append({"code": "LM-GENDER", "message": f"Gender {doc['Gender']!r} must be 0 (male) or 1 (female)", "fix": ""})
    for k, typ in (("HeadParts", list), ("Overlays", list), ("TintOrder", list), ("Morphs", dict), ("Tints", dict),
                   ("BodyMorphs", dict), ("Weight", list)):
        if k in doc and not isinstance(doc[k], typ):
            errors.append({"code": "LM-TYPE", "message": f"{k} must be a {typ.__name__}", "fix": ""})
    if isinstance(doc.get("Weight"), list) and doc["Weight"] and len(doc["Weight"]) != 3:
        warnings.append({"code": "LM-WEIGHT", "message": "Weight usually holds 3 values (thin, muscular, large)", "fix": "",
                         "tier": "installed presets"})
    return _res(path, errors, warnings, kind="looksmenu-preset")


def _xml(path: Path):
    try:
        return ET.fromstring(Path(path).read_bytes().lstrip(b"\xef\xbb\xbf"))
    except ET.ParseError as e:
        raise ForgeError(f"{Path(path).name}: XML does not parse: {e}", "fix the XML")


def bodyslide_preset_validate(path: Path) -> dict:
    errors, warnings = [], []
    try:
        root = _xml(path)
    except ForgeError as e:
        return _res(path, [{"code": "BS-XML", "message": str(e), "fix": e.fix}], [])
    if root.tag != "SliderPresets":
        errors.append({"code": "BS-ROOT", "message": f"root <{root.tag}> must be <SliderPresets>", "fix": ""})
    presets = root.findall("Preset")
    if not presets:
        errors.append({"code": "BS-EMPTY", "message": "no <Preset>", "fix": "add a <Preset name=... set=...>"})
    for p in presets:
        if not p.get("name"):
            errors.append({"code": "BS-NAME", "message": "a <Preset> has no name", "fix": ""})
        if not p.get("set"):
            warnings.append({"code": "BS-SET", "message": f"preset '{p.get('name')}' names no slider set", "fix": "", "tier": "installed presets"})
        for s in p.findall("SetSlider"):
            if not s.get("name"):
                errors.append({"code": "BS-SLIDER", "message": f"preset '{p.get('name')}': a SetSlider has no name", "fix": ""})
            if s.get("size") not in ("big", "small"):
                errors.append({"code": "BS-SIZE", "message": f"slider {s.get('name')}: size must be big or small", "fix": ""})
            try:
                v = float(s.get("value", ""))
                if not -100 <= v <= 200:
                    warnings.append({"code": "BS-VALUE", "message": f"slider {s.get('name')}: value {v} is unusual", "fix": "", "tier": "advice"})
            except ValueError:
                errors.append({"code": "BS-VALUE", "message": f"slider {s.get('name')}: value is not a number", "fix": ""})
    return _res(path, errors, warnings, kind="bodyslide-preset", presets=len(presets))


def slider_group_validate(path: Path) -> dict:
    errors, warnings = [], []
    try:
        root = _xml(path)
    except ForgeError as e:
        return _res(path, [{"code": "SG-XML", "message": str(e), "fix": e.fix}], [])
    if root.tag != "SliderGroups":
        errors.append({"code": "SG-ROOT", "message": f"root <{root.tag}> must be <SliderGroups>", "fix": ""})
    groups = root.findall("Group")
    for g in groups:
        if not g.get("name"):
            errors.append({"code": "SG-NAME", "message": "a <Group> has no name", "fix": ""})
        if not g.findall("Member"):
            warnings.append({"code": "SG-EMPTY", "message": f"group '{g.get('name')}' has no members", "fix": "", "tier": "advice"})
    return _res(path, errors, warnings, kind="slider-group", groups=len(groups))


PREFIX_RX = {"b": re.compile(r"^[01]$|^(true|false)$", re.I), "i": re.compile(r"^-?\d+$"),
             "u": re.compile(r"^\d+$"), "f": re.compile(r"^-?\d+(\.\d*)?([eE][-+]?\d+)?$|^-?\.\d+$")}


def ini_validate(path: Path) -> dict:
    errors, warnings = [], []
    cp = configparser.RawConfigParser(strict=False, interpolation=None, comment_prefixes=(";", "#"), inline_comment_prefixes=(";",))
    cp.optionxform = str
    text = read_text(path).lstrip("﻿")
    first = next((ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith((";", "#"))), "")
    if first and not first.startswith("["):
        # Some F4SE plugins read key=value files without sections; the game's own INIs always have sections.
        warnings.append({"code": "INI-NO-SECTION", "message": "keys before any [Section] (fine for some F4SE plugins, "
                         "not for game INI tweaks)", "fix": "add a [Section] for game settings", "tier": "advice"})
        text = "[__top__]\n" + text
    try:
        cp.read_string(text)
    except configparser.Error as e:
        return _res(path, [{"code": "INI-SYNTAX", "message": str(e).splitlines()[0], "fix": "fix the INI"}], warnings)
    n = 0
    for s in cp.sections():
        for k, v in cp.items(s):
            n += 1
            rx = PREFIX_RX.get(k[:1]) if len(k) > 1 and k[1:2].isupper() else None
            if rx and not rx.match(v.strip()):
                warnings.append({"code": "INI-TYPE", "message": f"[{s}] {k}={v}: value does not match its '{k[0]}' prefix",
                                 "fix": "", "tier": "Bethesda INI naming convention"})
    return _res(path, errors, warnings, kind="ini", sections=len(cp.sections()), keys=n)


def replacer_report(data_dir: Path, installed: set | None) -> dict:
    """Which project files replace an installed asset path, and which are new."""
    replaced, new = [], []
    for p in sorted(Path(data_dir).rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(data_dir).as_posix().replace("/", "\\").lower()
        if rel.endswith((".esp", ".esm", ".esl", ".ini")) or rel.startswith(("scripts\\source", "mcm\\", "f4se\\")):
            continue
        (replaced if installed is not None and rel in installed else new).append(rel)
    return {"data": str(data_dir), "replaces_installed": replaced, "new_files": len(new),
            "installed_index": installed is not None, "ok": True}


def validate_any(path: Path) -> dict:
    p = Path(path)
    low = p.as_posix().lower()
    if low.endswith(".json") and "f4ee" in low:
        return looksmenu_validate(p)
    if low.endswith(".xml") and "sliderpresets" in low:
        return bodyslide_preset_validate(p)
    if low.endswith(".xml") and "slidergroups" in low:
        return slider_group_validate(p)
    if low.endswith(".ini"):
        return ini_validate(p)
    raise ForgeError(f"no validator for {p.name}", "LooksMenu .json, BodySlide SliderPresets/SliderGroups .xml, or .ini")
