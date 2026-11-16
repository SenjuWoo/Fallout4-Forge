"""Nexus Mods: look up mods through the public Nexus GraphQL v2 API (no key; read-only) and write a page kit
(BBCode description with requirement links, changelog, file description) for a project. Uploading is manual.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from .util import ForgeError

API = "https://api.nexusmods.com/v2/graphql"


def _query(query: str, variables: dict) -> dict:
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "f4forge"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            doc = json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ForgeError(f"Nexus API unreachable: {e}", "check the network; the page kit works offline")
    if doc.get("errors"):
        raise ForgeError("Nexus API error: " + "; ".join(e.get("message", "") for e in doc["errors"]), "check the query")
    return doc["data"]


def mod(mod_id: int, game: str = "fallout4", description: bool = False) -> dict:
    fields = "name modId version summary updatedAt endorsements game { domainName }"
    if description:
        fields += " description"
    data = _query("query($ids:[CompositeDomainWithIdInput!]!){ legacyModsByDomain(ids:$ids){ nodes{ %s } } }" % fields,
                  {"ids": [{"gameDomain": game, "modId": int(mod_id)}]})
    nodes = data["legacyModsByDomain"]["nodes"]
    if not nodes:
        raise ForgeError(f"no mod {mod_id} on {game}", "check the ID")
    n = nodes[0]
    if description and n.get("description"):
        t = re.sub(r"<br\s*/?>", "\n", n["description"])
        n["description_text"] = re.sub(r"\n\s*\n+", "\n", re.sub(r"\[/?[a-z]+[^\]]*\]", "", t)).strip()[:6000]
        n.pop("description")
    n["url"] = f"https://www.nexusmods.com/{game}/mods/{n['modId']}"
    return n


def find(name: str, game: str = "fallout4", limit: int = 10) -> list[dict]:
    data = _query('query($f:ModsFilter,$c:Int){ mods(filter:$f, count:$c, sort:[{endorsements:{direction:DESC}}]){ '
                  'nodes{ name modId version summary endorsements } } }',
                  {"f": {"gameDomainName": [{"value": game, "op": "EQUALS"}], "name": [{"value": name, "op": "WILDCARD"}]},
                   "c": limit})
    return [{**n, "url": f"https://www.nexusmods.com/{game}/mods/{n['modId']}"} for n in data["mods"]["nodes"]]


def page_kit(root: Path) -> dict:
    from .project import load_manifest
    m = load_manifest(root)
    reqs = m.get("requirements", [])
    req_bb = "\n".join(f"[*][url={r['nexus']}]{r['name']}[/url]" + (f" ({r['when']})" if r.get("when") else "") for r in reqs if r.get("nexus"))
    cl = root / "CHANGELOG.md"
    changelog = cl.read_text(encoding="utf-8") if cl.is_file() else ""
    plugin = (m.get("plugin") or {}).get("name")
    desc = (f"[size=5][b]{m['name']}[/b][/size]\n\n{m.get('description') or ''}\n\n"
            f"[size=4][b]Requirements[/b][/size]\n[list]\n{req_bb or '[*]Fallout 4'}\n[/list]\n\n"
            f"[size=4][b]Installation[/b][/size]\nInstall with a mod manager"
            + (f" and enable [b]{plugin}[/b]" if plugin else "") + ".\n\n"
            f"[size=4][b]Version[/b][/size]\n{m['version']}\n")
    out = root / "dist" / "nexus"
    out.mkdir(parents=True, exist_ok=True)
    (out / "description.bbcode").write_text(desc, encoding="utf-8", newline="\n")
    (out / "changelog.md").write_text(changelog, encoding="utf-8", newline="\n")
    (out / "file-description.txt").write_text(f"{m['name']} {m['version']}" + (f" - main file ({plugin})" if plugin else ""),
                                              encoding="utf-8", newline="\n")
    return {"folder": str(out), "files": ["description.bbcode", "changelog.md", "file-description.txt"],
            "requirements_linked": len([r for r in reqs if r.get("nexus")]), "upload": "manual (Nexus has no public upload API)"}
