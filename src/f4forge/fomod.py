"""Basic FOMOD: fomod/info.xml and fomod/ModuleConfig.xml with a required group (the main files) and an optional
group (one folder per option under Options/<Name>/), generation, validation and an install simulation.
Schema: the FOMOD ModuleConfig format (fomod-docs.readthedocs.io; ModuleConfig.xsd 5.0).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape


def generate(manifest: dict, entries: list[str]) -> dict[str, bytes]:
    name = escape(manifest["name"])
    reqs = "".join(f"\n    <Element>{escape(r['name'])}</Element>" for r in manifest.get("requirements", []))
    info = (f'<?xml version="1.0" encoding="UTF-8"?>\n<fomod>\n  <Name>{name}</Name>\n  <Author>{escape(manifest.get("author") or "")}</Author>\n'
            f'  <Version>{escape(manifest["version"])}</Version>\n  <Description>{escape(manifest.get("description") or "")}</Description>\n'
            f'  <Groups>\n    <element>Fallout 4</element>\n  </Groups>\n</fomod>\n')
    options = sorted({e.split("/")[1] for e in entries if e.lower().startswith("options/") and e.count("/") >= 2})
    opt_xml = ""
    if options:
        plugins = "".join(
            f'\n            <plugin name="{escape(o)}">\n              <description>{escape(o)}</description>\n'
            f'              <files><folder source="Options/{escape(o)}" destination="" priority="0"/></files>\n'
            f'              <typeDescriptor><type name="Optional"/></typeDescriptor>\n            </plugin>' for o in options)
        opt_xml = (f'\n  <installSteps order="Explicit">\n    <installStep name="Options">\n      <optionalFileGroups order="Explicit">\n'
                   f'        <group name="Optional files" type="SelectAny">\n          <plugins order="Explicit">{plugins}\n'
                   f'          </plugins>\n        </group>\n      </optionalFileGroups>\n    </installStep>\n  </installSteps>')
    module = (f'<?xml version="1.0" encoding="UTF-8"?>\n<config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
              f'xsi:noNamespaceSchemaLocation="http://qconsulting.ca/fo3/ModConfig5.0.xsd">\n  <moduleName>{name}</moduleName>\n'
              f'  <requiredInstallFiles>\n    <folder source="Data" destination=""/>\n  </requiredInstallFiles>{opt_xml}\n</config>\n')
    _ = reqs
    return {"fomod/info.xml": info.encode("utf-8"), "fomod/ModuleConfig.xml": module.encode("utf-8")}


def _parse(data: bytes):
    return ET.fromstring(data.lstrip(b"\xef\xbb\xbf"))


def validate_xml(zf) -> list[dict]:
    errs = []
    names = {n.lower(): n for n in zf.namelist()}
    mc = names.get("fomod/moduleconfig.xml")
    if not mc:
        return [{"code": "FOMOD-NO-CONFIG", "message": "fomod/ folder without ModuleConfig.xml", "fix": "add ModuleConfig.xml"}]
    try:
        root = _parse(zf.read(mc))
    except ET.ParseError as e:
        return [{"code": "FOMOD-XML", "message": f"ModuleConfig.xml does not parse: {e}", "fix": "fix the XML"}]
    if root.tag != "config":
        errs.append({"code": "FOMOD-ROOT", "message": f"root <{root.tag}> must be <config>", "fix": ""})
    if root.find("moduleName") is None:
        errs.append({"code": "FOMOD-NAME", "message": "<moduleName> missing", "fix": ""})
    sources = [el.get("source") for el in root.iter() if el.tag in ("file", "folder") and el.get("source")]
    for s in sources:
        key = s.replace("\\", "/").lower().rstrip("/")
        if not any(n == key or n.startswith(key + "/") for n in names):
            errs.append({"code": "FOMOD-SOURCE", "message": f"source {s} is not in the archive", "fix": "fix the path"})
    for g in root.iter("group"):
        if g.get("type") not in ("SelectAny", "SelectAll", "SelectExactlyOne", "SelectAtMostOne", "SelectAtLeastOne"):
            errs.append({"code": "FOMOD-GROUP", "message": f"group {g.get('name')} has type {g.get('type')}", "fix": ""})
    if "fomod/info.xml" in names:
        try:
            _parse(zf.read(names["fomod/info.xml"]))
        except ET.ParseError as e:
            errs.append({"code": "FOMOD-INFO", "message": f"info.xml does not parse: {e}", "fix": "fix the XML"})
    return errs


def simulate(zf, choices: list[str] | None = None) -> dict:
    """Files a FOMOD installer would place, for the required files plus the chosen optional plugins."""
    names = {n.lower(): n for n in zf.namelist() if not n.endswith("/")}
    root = _parse(zf.read(names["fomod/moduleconfig.xml"]))
    picked = set(c.lower() for c in (choices or []))
    out = []

    def place(el):
        src = el.get("source", "").replace("\\", "/").rstrip("/")
        dst = el.get("destination", "").replace("\\", "/").strip("/")
        for low, real in names.items():
            if el.tag == "file" and low == src.lower():
                out.append((dst or src.rsplit("/", 1)[-1]))
            elif el.tag == "folder" and low.startswith(src.lower() + "/"):
                out.append(((dst + "/") if dst else "") + real[len(src) + 1:])

    req = root.find("requiredInstallFiles")
    for el in (req if req is not None else []):
        place(el)
    for p in root.iter("plugin"):
        if p.get("name", "").lower() in picked:
            for el in p.find("files") or []:
                place(el)
    return {"files": sorted(set(out)), "count": len(set(out))}


SAFE_NAME = re.compile(r"[^A-Za-z0-9 _.-]")
