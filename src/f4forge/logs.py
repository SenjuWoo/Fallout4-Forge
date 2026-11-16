"""Logs: F4SE loader log (plugins loaded, failures with reasons), per-plugin logs, the Papyrus log, crash logs
from whichever crash logger is installed (Buffout 4, Addictol Crash Logger), and the signature registry.
Read-only: logs are never deleted or rewritten.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .util import KNOWLEDGE_DIR, load_json, read_text

PLUGIN_LINE = re.compile(r"^plugin (?P<dll>.+?\.dll) \((?P<a>[0-9A-F]{8}) ?(?P<name>.*?) ?(?P<b>[0-9A-F]{8})\) (?P<status>.+?) \(handle (?P<h>-?\d+)\)$", re.I)


def signatures() -> list[dict]:
    return load_json(KNOWLEDGE_DIR / "errors.json")["signatures"]


def explain(text: str) -> list[dict]:
    out = []
    for s in signatures():
        if re.search(s["match"], text, re.I):
            out.append({k: s[k] for k in ("id", "meaning", "fix", "log", "fact")})
    return out


def f4se_log(path: Path) -> dict:
    loaded, failed, preload = [], [], []
    runtime = None
    for ln in read_text(path).splitlines():
        s = ln.strip()
        if s.startswith("F4SE runtime:"):
            runtime = s
        m = PLUGIN_LINE.match(s)
        if m:
            st = m.group("status")
            row = {"dll": m.group("dll"), "name": m.group("name").strip() or None, "status": st}
            if st.startswith("loaded correctly"):
                loaded.append(row)
            else:
                row["explained"] = explain(st)
                failed.append(row)
        elif s.startswith("preloading plugin"):
            preload.append(s.split('"')[1] if '"' in s else s)
    return {"file": str(path), "runtime_line": runtime, "loaded": len(loaded), "failed": failed, "preloaded": preload,
            "loaded_names": [r["name"] or r["dll"] for r in loaded]}


def crash_dirs(my_games: Path, game_root: Path | None) -> list[Path]:
    dirs = [my_games / "F4SE"]
    if game_root:
        from .util import ci_path
        toml = ci_path(game_root, "Data/F4SE/Plugins/AddictolCrashLogger.toml")
        if toml:
            m = re.search(r'^\s*sCrashLogDirectory\s*=\s*"([^"]*)"', read_text(toml), re.M)
            if m and m.group(1):
                dirs.append(Path(m.group(1).replace("\\\\", "\\")))
    return [d for d in dirs if d.is_dir()]


def crash_summary(path: Path, lines: int = 40) -> dict:
    text = read_text(path)
    head = text.splitlines()[:lines]
    exc = re.search(r'Unhandled (?:native )?exception "?([A-Z_]+)"? at (0x[0-9A-Fa-f]+)\s*(\S+)?', text)
    stack = re.findall(r"^\s*\[\s*\d+\]\s+0x[0-9A-F]+\s+(\S+?\.(?:dll|exe))\+", text, re.I | re.M)
    modules = []
    for mname in stack:
        if mname.lower() not in [x.lower() for x in modules]:
            modules.append(mname)
    return {"file": str(path), "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime)),
            "exception": exc.group(1) if exc else None, "address": exc.group(2) if exc else None,
            "where": exc.group(3) if exc and exc.group(3) else None,
            "stack_modules": modules[:12], "explained": explain(text[:20000]), "head": head[:12]}


def collect(game_root: Path | None, lines: int = 25, mod: str | None = None) -> dict:
    from .game import my_games
    mg = my_games()
    out = {"my_games": mg["folder"]}
    if not mg["found"]:
        out["note"] = "My Games/Fallout4 not found; pass logs explicitly with f4forge explain"
        return out
    folder = Path(mg["folder"])
    f4 = folder / "F4SE"
    if (f4 / "f4se.log").is_file():
        out["f4se"] = f4se_log(f4 / "f4se.log")
    if (f4 / "f4se_loader.log").is_file():
        out["f4se_loader_tail"] = read_text(f4 / "f4se_loader.log").splitlines()[-5:]
    plugin_logs = []
    for p in sorted(f4.glob("*.log")) if f4.is_dir() else []:
        if p.name.lower() in ("f4se.log", "f4se_loader.log") or p.name.lower().startswith("crash"):
            continue
        if mod and mod.lower() not in p.name.lower():
            continue
        text_lines = read_text(p).splitlines()
        bad = [ln.strip() for ln in text_lines if re.search(r"\b(error|fail|warn|exception|critical)", ln, re.I)]
        plugin_logs.append({"log": p.name, "lines": len(text_lines), "problems": bad[-lines:] if bad else []})
    out["plugin_logs"] = [p for p in plugin_logs if p["problems"]] or []
    out["plugin_logs_clean"] = [p["log"] for p in plugin_logs if not p["problems"]]
    pap = folder / "Logs" / "Script" / "Papyrus.0.log"
    if pap.is_file():
        text_lines = read_text(pap).splitlines()
        hits = [ln for ln in text_lines if re.search(r"error|warning|None object|stack", ln, re.I)]
        if mod:
            hits = [h for h in hits if mod.lower() in h.lower()]
        out["papyrus"] = {"file": str(pap), "lines": len(text_lines), "problems": hits[-lines:],
                          "explained": explain("\n".join(hits[-200:]))}
    else:
        out["papyrus"] = {"file": None, "note": "Papyrus logging is off (Fallout4Custom.ini [Papyrus] bEnableLogging=1 turns it on)"}
    crashes = []
    for d in crash_dirs(folder, game_root):
        crashes += [p for p in d.glob("crash-*.log")]
    crashes.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out["crash_logs"] = {"found": len(crashes), "latest": [crash_summary(p) for p in crashes[:3]],
                         "searched": [str(d) for d in crash_dirs(folder, game_root)]}
    return out
