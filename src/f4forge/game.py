"""Find the installed game and read what it has. Read-only: nothing here writes anywhere.

Discovery order: --game argument, FALLOUT4_ROOT, config game_root, Steam (libraryfolders.vdf +
appmanifest_377160.acf), the Bethesda registry key, GOG registry keys. An explicit setting
(argument, environment or config) that does not hold the game is a named failure; it never
falls through to auto-detection, so a wrong setting cannot silently pick another install.
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

from . import ba2, pe, plugin
from .home import config_value
from .util import KNOWLEDGE_DIR, ForgeError, ci_child, ci_path, load_json, read_text

_GAME_DATA = None


def data() -> dict:
    global _GAME_DATA
    if _GAME_DATA is None:
        _GAME_DATA = load_json(KNOWLEDGE_DIR / "game.json")
    return _GAME_DATA


# --- Steam files ---------------------------------------------------------------

def parse_vdf(text: str) -> dict:
    """Valve KeyValues text (libraryfolders.vdf, appmanifest_*.acf) into nested dicts."""
    tokens = re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text)
    stack, cur, key = [], {}, None
    for quoted, brace in tokens:
        if brace == "{":
            new = {}
            if key is not None:
                cur[key] = new
            stack.append(cur)
            cur, key = new, None
        elif brace == "}":
            cur = stack.pop() if stack else cur
            key = None
        elif key is None:
            key = quoted.replace("\\\\", "\\")
        else:
            cur[key] = quoted.replace("\\\\", "\\")
            key = None
    return cur


def _reg(hive: str, path: str, name: str) -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg
        root = {"HKLM": winreg.HKEY_LOCAL_MACHINE, "HKCU": winreg.HKEY_CURRENT_USER}[hive]
        with winreg.OpenKey(root, path) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return str(v) if v else None
    except OSError:
        return None


def _reg_subkeys(path: str) -> list[str]:
    if os.name != "nt":
        return []
    try:
        import winreg
        out = []
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(k, i))
                except OSError:
                    break
                i += 1
        return out
    except OSError:
        return []


def steam_roots() -> list[Path]:
    roots = []
    v = _reg("HKCU", r"Software\Valve\Steam", "SteamPath")
    if v:
        roots.append(Path(v))
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]) / "Steam")
    seen, out = set(), []
    for r in roots:
        k = str(r).lower().replace("/", "\\")
        if k not in seen and r.is_dir():
            seen.add(k)
            out.append(r)
    return out


def steam_libraries(steam_root: Path) -> list[Path]:
    libs = [steam_root]
    for cand in (steam_root / "steamapps" / "libraryfolders.vdf", steam_root / "config" / "libraryfolders.vdf"):
        if cand.is_file():
            doc = parse_vdf(read_text(cand)).get("libraryfolders", {})
            for v in doc.values():
                p = v.get("path") if isinstance(v, dict) else v
                if isinstance(p, str) and p:
                    libs.append(Path(p))
            break
    return libs


def steam_app(library: Path, app: str) -> dict | None:
    acf = library / "steamapps" / f"appmanifest_{app}.acf"
    if not acf.is_file():
        return None
    st = parse_vdf(read_text(acf)).get("AppState", {})
    folder = library / "steamapps" / "common" / st.get("installdir", "")
    return {"manifest": str(acf), "buildid": st.get("buildid"), "installdir": st.get("installdir"),
            "folder": folder}


def steam_candidates(roots: list[Path] | None = None) -> list[tuple[Path, str]]:
    out = []
    for root in steam_roots() if roots is None else roots:
        for lib in steam_libraries(root):
            app = steam_app(lib, data()["steam_app"]["game"])
            if app and app["installdir"]:
                out.append((app["folder"], f"steam:{app['manifest']}"))
    return out


def registry_candidates() -> list[tuple[Path, str]]:
    out = []
    for key in (r"SOFTWARE\WOW6432Node\Bethesda Softworks\Fallout4", r"SOFTWARE\Bethesda Softworks\Fallout4"):
        v = _reg("HKLM", key, "Installed Path")
        if v:
            out.append((Path(v), "registry:bethesda"))
    for base in (r"SOFTWARE\WOW6432Node\GOG.com\Games", r"SOFTWARE\GOG.com\Games"):
        for sub in _reg_subkeys(base):
            name = (_reg("HKLM", f"{base}\\{sub}", "gameName") or "").lower()
            path = _reg("HKLM", f"{base}\\{sub}", "path")
            if path and "fallout 4" in name:
                out.append((Path(path), f"gog:{sub}"))
    return out


# --- discovery -------------------------------------------------------------------

def is_game(root: Path) -> bool:
    return bool(root and root.is_dir() and ci_child(root, data()["executable"]) and ci_child(root, "Data"))


def find_game(explicit: str | None = None) -> tuple[Path, str]:
    for value, source in ((explicit, "argument"), (os.environ.get("FALLOUT4_ROOT"), "FALLOUT4_ROOT"),
                          (config_value("game_root"), "config game_root")):
        if value:
            p = Path(value)
            if is_game(p):
                return p, source
            raise ForgeError(f"{source} points to a folder without Fallout4.exe and Data: {p}",
                             f"set {source} to the Fallout 4 folder, or clear it to auto-detect")
    tried = []
    for p, source in steam_candidates() + registry_candidates():
        tried.append(str(p))
        if is_game(p):
            return p, source
    raise ForgeError("Fallout 4 not found (Steam libraries, Bethesda and GOG registry keys)",
                     "pass --game <folder>, set FALLOUT4_ROOT, or run: f4forge config --set game_root=<folder>")


def require_game(explicit: str | None = None) -> Path:
    return find_game(explicit)[0]


# --- runtime ---------------------------------------------------------------------

def vtuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4]) + (0,) * (4 - len(re.findall(r"\d+", v)[:4]))


def generation(version: str | None) -> dict:
    g = data()["generations"]
    if version:
        t = vtuple(version)
        for line in g["lines"]:
            if vtuple(line["min"]) <= t and (line["max"] is None or t <= vtuple(line["max"])):
                return {"id": line["id"], "label": line["label"], "fact": g["fact"]}
    return {"id": "unknown", "label": "not in knowledge/game.json", "fact": g["fact"]}


def runtime(root: Path) -> dict:
    exe = ci_child(root, data()["executable"])
    v = pe.file_version(exe) if exe else None
    return {"version": v, "generation": generation(v), "exe": str(exe) if exe else None}


def f4se_version_from_resource(v: str | None) -> str | None:
    """F4SE's loader/DLL resource reads 0.A.B.C for F4SE A.B.C (fact f4se.layout)."""
    if not v:
        return None
    parts = v.split(".")
    return ".".join(parts[1:]) if parts[0] == "0" and len(parts) == 4 else v


def f4se(root: Path, runtime_version: str | None) -> dict:
    d = data()["f4se"]
    loader = ci_child(root, d["loader"])
    want = d["dll"].format(*vtuple(runtime_version)[:3]) if runtime_version else None
    dll = ci_child(root, want) if want else None
    others = sorted(p.name for p in root.iterdir() if re.fullmatch(r"f4se_\d+_\d+_\d+\.dll", p.name, re.I))
    ver = f4se_version_from_resource(pe.file_version(dll)) if dll else None
    if not ver and loader:
        ver = f4se_version_from_resource(pe.file_version(loader))
    src = ci_child(root, "src")
    tarball = None
    if src and src.is_dir():
        for p in sorted(src.iterdir()):
            m = re.fullmatch(r"f4se-(\d+\.\d+\.\d+)\.tar\.gz", p.name, re.I)
            if m:
                tarball = {"file": str(p), "version": m.group(1)}
    return {"installed": bool(loader), "loader": str(loader) if loader else None, "version": ver,
            "runtime_dll": want, "matches_runtime": bool(dll), "dlls_present": others,
            "source_tarball": tarball, "fact": d["fact"]}


def address_library(root: Path, runtime_version: str | None) -> dict:
    d = data()["address_library"]
    folder = ci_path(root, "Data/F4SE/Plugins")
    present = sorted(p.name for p in folder.iterdir()
                     if re.fullmatch(r"version-\d+-\d+-\d+-\d+\.bin", p.name, re.I)) if folder and folder.is_dir() else []
    want = d["bin"].format(*vtuple(runtime_version)) if runtime_version else None
    hit = ci_path(root, want) if want else None
    return {"for_runtime": bool(hit), "expected": want, "bins_present": present, "fact": d["fact"]}


# --- content inventory --------------------------------------------------------------

def _header(p: Path) -> dict | None:
    try:
        h = plugin.read_header(p)
        return {"hedr_version": h["hedr_version"], "form_version": h["form_version"], "records": h["records"],
                "esm": h["esm"], "esl": h["esl"]}
    except (OSError, ForgeError):
        return None


def official_masters(root: Path) -> list[dict]:
    dd = ci_child(root, "Data")
    out = []
    for name in data()["official_masters"]["order"]:
        p = ci_child(dd, name) if dd else None
        row = {"plugin": name, "present": bool(p)}
        if p:
            row.update(_header(p) or {"error": "unreadable header"})
        out.append(row)
    return out


def creation_club(root: Path) -> dict:
    d = data()["creation_club"]
    ccc = ci_child(root, d["list"])
    listed = [ln.strip() for ln in read_text(ccc).splitlines() if ln.strip()] if ccc else []
    dd = ci_child(root, "Data")
    installed = sorted(p.name for p in dd.iterdir() if p.name.lower().startswith(d["prefix"])
                       and p.suffix.lower() in (".esl", ".esm", ".esp")) if dd else []
    low = {n.lower() for n in installed}
    return {"ccc": str(ccc) if ccc else None, "listed": len(listed), "installed": len(installed),
            "listed_and_installed": sum(1 for n in listed if n.lower() in low), "fact": d["fact"]}


def creation_kit(root: Path) -> dict:
    d = data()["creation_kit"]
    tools = {}
    for tid, relp in d["tools"].items():
        p = ci_path(root, relp)
        tools[tid] = {"found": bool(p), "path": str(p) if p else None,
                      "version": pe.file_version(p) if p else None}
    sources = {k: bool(ci_path(root, v)) for k, v in d["source_zips"].items()}
    flags = ci_path(root, d["flags_file"])
    ck = tools["creation_kit"]
    missing = [t for t in d["required_for_tier"] if not tools[t]["found"]]
    app = None
    lib = root.parent.parent.parent if root.parent.name.lower() == "common" else None
    if lib:
        a = steam_app(lib, data()["steam_app"]["creation_kit"])
        if a:
            app = {"manifest": a["manifest"], "buildid": a["buildid"]}
    return {"installed": ck["found"], "version": ck["version"], "tier": "creation-kit" if not missing else "no-creation-kit",
            "missing_for_tier": missing, "tools": tools, "official_source_zips": sources,
            "flags_file": str(flags) if flags else None, "steam": app, "fact": d["fact"]}


def marker_hit(root: Path, marker: str) -> bool:
    """A marker is a game-relative path; '*' in the last part globs that folder (case-insensitive)."""
    if "*" not in marker:
        return bool(ci_path(root, marker))
    parent, _, pattern = marker.replace("\\", "/").rpartition("/")
    folder = ci_path(root, parent) if parent else root
    return bool(folder and folder.is_dir() and any(fnmatch.fnmatch(p.name.lower(), pattern.lower())
                                                   for p in folder.iterdir()))


def frameworks(root: Path) -> list[dict]:
    reg = load_json(KNOWLEDGE_DIR / "frameworks.json")["frameworks"]
    out = []
    for fw in reg:
        hits = [m for m in fw.get("markers", []) if marker_hit(root, m)]
        out.append({"id": fw["id"], "name": fw["name"], "installed": bool(hits), "markers_found": hits})
    return out


def archive_census(root: Path) -> dict:
    """Header of every Data/*.ba2: counts for the report, per-file rows under 'files'."""
    dd = ci_child(root, "Data")
    counts, errors, rows = {}, [], []
    for p in sorted(dd.glob("*.ba2")) if dd else []:
        try:
            h = ba2.read_header(p)
            key = f"v{h['version']} {h['type']}"
            counts[key] = counts.get(key, 0) + 1
            rows.append({"file": p.name, "version": h["version"], "type": h["type"], "files": h["files"]})
        except (OSError, ForgeError) as e:
            errors.append({"file": p.name, "error": str(e)})
    return {"total": len(rows) + len(errors), "by_version_type": dict(sorted(counts.items())),
            "errors": errors, "files": rows}


def plugin_census(root: Path) -> dict:
    dd = ci_child(root, "Data")
    by_ext, hedr, flags, errors = {}, {}, {"esm_flag": 0, "esl_flag": 0}, []
    for p in sorted(dd.iterdir()) if dd else []:
        ext = p.suffix.lower()
        if ext not in (".esm", ".esp", ".esl") or not p.is_file():
            continue
        by_ext[ext[1:]] = by_ext.get(ext[1:], 0) + 1
        h = _header(p)
        if not h:
            errors.append(p.name)
            continue
        key = f"{ext[1:]} {h['hedr_version']}"
        hedr[key] = hedr.get(key, 0) + 1
        flags["esm_flag"] += h["esm"]
        flags["esl_flag"] += h["esl"]
    return {"by_extension": by_ext, "by_extension_and_hedr": dict(sorted(hedr.items())), "flags": flags,
            "unreadable": errors}


# --- user folders and mod managers ------------------------------------------------------

def documents_dir() -> Path | None:
    v = _reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders", "Personal")
    if v:
        return Path(os.path.expandvars(v))
    if os.environ.get("USERPROFILE"):
        return Path(os.environ["USERPROFILE"]) / "Documents"
    return None


def my_games() -> dict:
    env = os.environ.get("FALLOUT4_MYGAMES")
    docs = documents_dir()
    folder = Path(env) if env else (docs / "My Games" / "Fallout4" if docs else None)
    appdata = os.environ.get("FALLOUT4_APPDATA") or (
        str(Path(os.environ["LOCALAPPDATA"]) / "Fallout4") if os.environ.get("LOCALAPPDATA") else None)
    ptxt = Path(appdata) / "plugins.txt" if appdata else None
    found = bool(folder and folder.is_dir())
    return {"folder": str(folder) if folder else None, "found": found,
            "ini": bool(found and ci_child(folder, "Fallout4.ini")),
            "f4se_logs": str(ci_child(folder, "F4SE")) if found and ci_child(folder, "F4SE") else None,
            "plugins_txt": str(ptxt) if ptxt and ptxt.is_file() else None}


def mod_managers(root: Path) -> dict:
    out = {}
    dd = ci_child(root, "Data")
    vortex_dep = ci_child(dd, "vortex.deployment.json") if dd else None
    staging = Path(os.environ["APPDATA"]) / "Vortex" / "fallout4" / "mods" if os.environ.get("APPDATA") else None
    out["vortex"] = {"deployed_here": bool(vortex_dep),
                     "staging": str(staging) if staging and staging.is_dir() else None,
                     "mods": sum(1 for p in staging.iterdir() if p.is_dir()) if staging and staging.is_dir() else 0}
    instances = []
    base = Path(os.environ["LOCALAPPDATA"]) / "ModOrganizer" if os.environ.get("LOCALAPPDATA") else None
    if base and base.is_dir():
        for inst in sorted(base.iterdir()):
            ini = inst / "ModOrganizer.ini"
            if ini.is_file() and re.search(r"gameName\s*=\s*Fallout 4", read_text(ini, 1 << 16), re.I):
                instances.append(str(inst))
    out["mo2"] = {"instances": instances}
    out["note"] = "read-only: the forge never writes into mod-manager staging"
    return out


# --- report ---------------------------------------------------------------------------

def report(explicit: str | None = None, archives: bool = False, plugins: bool = False) -> dict:
    root, source = find_game(explicit)
    rt = runtime(root)
    dd = ci_child(root, "Data")
    counts = {}
    for ext in ("ba2", "esm", "esp", "esl"):
        counts[ext] = sum(1 for p in dd.iterdir() if p.suffix.lower() == "." + ext) if dd else 0
    steam = None
    lib = root.parent.parent.parent if root.parent.name.lower() == "common" else None
    if lib:
        a = steam_app(lib, data()["steam_app"]["game"])
        if a:
            steam = {"app": data()["steam_app"]["game"], "buildid": a["buildid"], "manifest": a["manifest"]}
    out = {"root": str(root), "found_by": source, "runtime": rt, "steam": steam,
           "f4se": f4se(root, rt["version"]), "address_library": address_library(root, rt["version"]),
           "official_masters": official_masters(root), "creation_club": creation_club(root),
           "creation_kit": creation_kit(root), "data_counts": counts, "frameworks": frameworks(root),
           "my_games": my_games(), "mod_managers": mod_managers(root)}
    if archives:
        out["archives"] = archive_census(root)
    if plugins:
        out["plugins"] = plugin_census(root)
    return out
