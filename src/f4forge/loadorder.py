"""Load order: implicit official masters, Creation Club (Fallout4.ccc), plugins.txt, missing masters.

plugins.txt: one plugin per line, '*' marks an active plugin, '#' starts a comment. The official
masters (game.json official_masters, confirmed against xEdit's FO4 game definition) and installed
Creation Club plugins load implicitly before it. Read-only.
"""
from __future__ import annotations

from pathlib import Path

from . import plugin
from .game import data as game_data
from .game import my_games
from .util import ForgeError, ci_child, read_text


def read_plugins_txt(path: Path) -> list[dict]:
    rows = []
    for ln in read_text(path).splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        active = s.startswith("*")
        rows.append({"plugin": s.lstrip("*").strip(), "active": active})
    return rows


def load_order(root: Path, plugins_txt: Path | None = None) -> dict:
    dd = ci_child(root, "Data")
    if not dd:
        raise ForgeError(f"no Data folder in {root}", "check the game folder")
    present = {p.name.lower(): p for p in dd.iterdir() if p.suffix.lower() in (".esm", ".esp", ".esl")}
    implicit = [n for n in game_data()["official_masters"]["order"] if n.lower() in present]
    ccc = ci_child(root, game_data()["creation_club"]["list"])
    cc = [ln.strip() for ln in read_text(ccc).splitlines() if ln.strip()] if ccc else []
    cc = [n for n in cc if n.lower() in present and n.lower() not in {x.lower() for x in implicit}]
    ptxt = plugins_txt or (Path(my_games()["plugins_txt"]) if my_games()["plugins_txt"] else None)
    rows = read_plugins_txt(ptxt) if ptxt and ptxt.is_file() else []
    order, seen = [], set()
    for n in implicit + cc:
        order.append({"plugin": present[n.lower()].name, "source": "implicit" if n in implicit else "ccc"})
        seen.add(n.lower())
    starred = 0
    missing_files = []
    for r in rows:
        if not r["active"]:
            continue
        starred += 1
        low = r["plugin"].lower()
        if low in seen:
            continue
        if low not in present:
            missing_files.append(r["plugin"])
            continue
        order.append({"plugin": present[low].name, "source": "plugins.txt"})
        seen.add(low)
    loaded = set()
    missing_masters = []
    light = full = 0
    for i, o in enumerate(order):
        p = present[o["plugin"].lower()]
        try:
            h = plugin.read_header(p)
        except ForgeError as e:
            o["error"] = str(e)
            continue
        o["index"] = i
        o["light"] = plugin.is_light(p, h)
        light += o["light"]
        full += not o["light"]
        miss = [m for m in h["masters"] if m.lower() not in loaded]
        if miss:
            missing_masters.append({"plugin": o["plugin"], "missing": miss})
        loaded.add(o["plugin"].lower())
    return {"plugins_txt": str(ptxt) if ptxt else None, "implicit": len(implicit), "creation_club": len(cc),
            "plugins_txt_entries": len(rows), "plugins_txt_starred": starred,
            "active_from_plugins_txt": sum(1 for o in order if o["source"] == "plugins.txt"), "active": len(order),
            "active_full": full, "active_light": light, "full_slot_limit": 254, "light_slot_limit": 4096,
            "missing_files": missing_files, "missing_masters": missing_masters, "order": order,
            "fact": "load_order.official_masters"}
