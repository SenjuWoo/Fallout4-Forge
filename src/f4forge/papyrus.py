"""Papyrus: PEX reader, the source cache (official or decompiled), compile with two drivers, decompile.

PEX (Fallout 4, little-endian; Skyrim files are big-endian): u32 magic 0xFA57C0DE, u8 major, u8 minor,
u16 game id (2 = Fallout 4), u64 compile time, wstring source, user, machine; string table (u16 count of
u16-length strings); debug info (u8 flag; functions; Fallout 4 adds property groups and struct orders);
user flags; objects (u16 name index, u32 size including itself, data: u16 parent class index, ...).

Source cache under the forge home (papyrus/): `official` (Creation Kit Base.zip + DLC0x.zip, extracted
there, never into the game) or `decompiled` (game .pex through Champollion). Import order for a compile:
project sources, F4SE's modified scripts, the game's Data/Scripts/Source (read-only), then the cache.
"""
from __future__ import annotations

import re
import shutil
import struct
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

from .home import home_dir
from .util import KNOWLEDGE_DIR, ForgeError, ci_path, iter_files, load_json, run, save_json

PEX_MAGIC = 0xFA57C0DE
FLAGS_NAME = "F4Forge_Papyrus_Flags.flg"


# --- PEX -------------------------------------------------------------------------------------

class _R:
    def __init__(self, data: bytes, endian: str):
        self.d, self.i, self.e = data, 0, endian

    def u8(self):
        v = self.d[self.i]
        self.i += 1
        return v

    def u16(self):
        v = struct.unpack_from(self.e + "H", self.d, self.i)[0]
        self.i += 2
        return v

    def u32(self):
        v = struct.unpack_from(self.e + "I", self.d, self.i)[0]
        self.i += 4
        return v

    def u64(self):
        v = struct.unpack_from(self.e + "Q", self.d, self.i)[0]
        self.i += 8
        return v

    def wstr(self):
        n = self.u16()
        s = self.d[self.i:self.i + n].decode("cp1252", "replace")
        self.i += n
        return s


def parse_pex(data: bytes) -> dict:
    if len(data) < 8:
        raise ForgeError("not a PEX file (too short)", "pass a compiled .pex")
    if struct.unpack_from("<I", data)[0] == PEX_MAGIC:
        r = _R(data, "<")
    elif struct.unpack_from(">I", data)[0] == PEX_MAGIC:
        r = _R(data, ">")
    else:
        raise ForgeError("not a PEX file (bad magic)", "pass a compiled .pex")
    r.u32()
    major, minor, game = r.u8(), r.u8(), r.u16()
    out = {"endian": "little" if r.e == "<" else "big", "version": f"{major}.{minor}", "game_id": game,
           "game": {1: "Skyrim", 2: "Fallout 4", 3: "Fallout 76", 4: "Starfield"}.get(game, str(game)),
           "compile_time": r.u64(), "source": r.wstr(), "user": r.wstr(), "machine": r.wstr()}
    strings = [r.wstr() for _ in range(r.u16())]
    out["strings"] = len(strings)
    try:
        if r.u8():
            r.u64()
            for _ in range(r.u16()):
                r.u16(), r.u16(), r.u16(), r.u8()
                count = r.u16()  # read first: "r.i += 2 * r.u16()" would drop the 2-byte advance
                r.i += 2 * count
            if game == 2:
                for _ in range(r.u16()):
                    r.u16(), r.u16(), r.u16(), r.u32()
                    count = r.u16()  # read first: "r.i += 2 * r.u16()" would drop the 2-byte advance
                    r.i += 2 * count
                for _ in range(r.u16()):
                    r.u16(), r.u16()
                    count = r.u16()  # read first: "r.i += 2 * r.u16()" would drop the 2-byte advance
                    r.i += 2 * count
        for _ in range(r.u16()):
            r.u16(), r.u8()
        objects = []
        for _ in range(r.u16()):
            name = strings[r.u16()]
            size = r.u32()
            start = r.i
            parent = strings[struct.unpack_from(r.e + "H", data, start)[0]] if size >= 6 else ""
            objects.append({"name": name, "parent": parent})
            r.i = start + size - 4
        out["objects"] = objects
    except (IndexError, struct.error) as e:
        raise ForgeError(f"PEX tables unreadable: {e}", "the file is truncated or not a Fallout 4 PEX")
    return out


# --- source cache ---------------------------------------------------------------------------------

def cache_dir() -> Path:
    return home_dir() / "papyrus"


def manifest_path() -> Path:
    return cache_dir() / "sources.json"


def load_manifest() -> dict | None:
    p = manifest_path()
    return load_json(p) if p.is_file() else None


def _extract_zip(z: Path, dest: Path) -> int:
    n = 0
    with zipfile.ZipFile(z) as zf:
        for m in zf.infolist():
            if m.is_dir():
                continue
            target = (dest / m.filename).resolve()
            if dest.resolve() not in target.parents:
                raise ForgeError(f"zip entry escapes the cache: {m.filename}", "the zip is unsafe")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            n += 1
    return n


def f4se_scripts(game_root: Path | None, vanilla_dir: Path) -> tuple[Path | None, str]:
    """F4SE's Papyrus scripts, merged the way F4SE's own build does it (scripts/build_multithread.py):
    each file in scripts/modified is appended to the vanilla script of the same name (fact f4se.scripts_merge).
    Source: the pinned F4SE source, else the game's own f4se-<ver>.tar.gz."""
    from .tools import tool_path
    modified: dict[str, str] = {}
    repo_vanilla: dict[str, str] = {}
    origin = "missing"
    src = tool_path("f4se-src")
    if src and (src / "scripts" / "modified").is_dir():
        for p in sorted((src / "scripts" / "modified").glob("*.psc")):
            modified[p.name] = p.read_text(encoding="utf-8", errors="replace")
        for p in sorted((src / "scripts" / "vanilla").glob("*.psc")):
            repo_vanilla[p.name.lower()] = p.read_text(encoding="utf-8", errors="replace")
        origin = "tools: F4SE source (pinned)"
    elif game_root:
        tb = next(iter(sorted((ci_path(game_root, "src") or Path("/nonexistent")).glob("f4se-*.tar.gz"))), None)
        if tb:
            with tarfile.open(tb) as t:
                for m in t.getmembers():
                    f = t.extractfile(m) if m.isfile() and m.name.endswith(".psc") else None
                    if f and "/scripts/modified/" in m.name:
                        modified[Path(m.name).name] = f.read().decode("utf-8", "replace")
                    elif f and "/scripts/vanilla/" in m.name:
                        repo_vanilla[Path(m.name).name.lower()] = f.read().decode("utf-8", "replace")
            origin = f"game: {tb.name}"
    if not modified:
        return None, origin
    dest = cache_dir() / "f4se"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name, extra in modified.items():
        van = vanilla_dir / name
        base = van.read_text(encoding="utf-8", errors="replace") if van.is_file() else repo_vanilla.get(name.lower(), "")
        nl = chr(10)
        text = (base.rstrip(nl) + nl + nl + extra) if base else extra
        (dest / name).write_text(text, encoding="utf-8", newline=nl)
    return dest, origin + f" merged with {vanilla_dir.name} vanilla scripts ({len(modified)} files)"


def build_sources(game_root: Path, route: str = "auto", sample: int | None = None) -> dict:
    from . import game as G
    t = time.time()
    ck = G.creation_kit(game_root)
    zips = {k: ci_path(game_root, v) for k, v in G.data()["creation_kit"]["source_zips"].items()}
    if route == "auto":
        route = "official" if zips.get("Base") else "decompiled"
    out = {"route": route, "creation_kit": ck["version"], "built": time.strftime("%Y-%m-%dT%H:%M:%S")}
    base = cache_dir() / route
    if route == "official":
        if not zips.get("Base"):
            raise ForgeError("the Creation Kit's Base.zip is missing", "install the Creation Kit, or use --route decompiled")
        if base.exists():
            shutil.rmtree(base)
        base.mkdir(parents=True)
        counts = {}
        for k, z in zips.items():
            if z:
                counts[k] = _extract_zip(z, base)
        flg = ci_path(game_root, G.data()["creation_kit"]["flags_file"])
        if flg:
            shutil.copy2(flg, base / flg.name)
            out["flags"] = flg.name
        out["files"] = counts
    else:
        out.update(_decompile_game(game_root, base, sample))
    out["patched"] = patch_cache(base)
    shutil.copy2(KNOWLEDGE_DIR / FLAGS_NAME, cache_dir() / FLAGS_NAME)
    f4se_dir, f4se_from = f4se_scripts(game_root, base)
    data_src = ci_path(game_root, "Data/Scripts/Source")
    imports = []
    if f4se_dir:
        imports.append({"path": str(f4se_dir), "tier": "f4se", "from": f4se_from})
    if data_src:
        # Caprica scans import folders recursively, so the game's sources are mirrored (read-only copy) without
        # the official Base/DLC folders the cache already holds; the mirror gets the same cache patches.
        mirror = cache_dir() / "installed"
        if mirror.exists():
            shutil.rmtree(mirror)
        skip = {"base"} | {f"dlc0{i}" for i in range(1, 10)}
        n = 0
        for p in iter_files(data_src, (".psc",)):
            rel = p.relative_to(data_src)
            if len(rel.parts) > 1 and rel.parts[0].lower() in skip:
                continue
            (mirror / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, mirror / rel)
            n += 1
        out["patched"] += ["installed/" + x for x in patch_cache(mirror)] if mirror.is_dir() else []
        user = next((p for p in mirror.iterdir() if p.is_dir() and p.name.lower() == "user"), None) if mirror.is_dir() else None
        if user:
            # Source/User is the Creation Kit's own import folder (MCM.psc and most mod sources live there).
            imports.append({"path": str(user), "tier": "installed", "from": "game Data/Scripts/Source/User"})
        imports.append({"path": str(mirror), "tier": "installed", "from": f"game Data/Scripts/Source ({n} files, "
                        "official Base/DLC folders left out)"})
    imports.append({"path": str(base), "tier": route, "from": "forge cache"})
    out["caprica_overlay"] = caprica_overlay([Path(i["path"]) for i in imports])
    out["imports"] = imports
    out["import_order_note"] = "the compiler searches imports in this order after the project's own sources"
    out["check"] = {name: bool(list(base.rglob(name))) for name in ("ScriptObject.psc", "Form.psc", "Actor.psc", "Quest.psc")}
    out["seconds"] = round(time.time() - t, 1)
    save_json(manifest_path(), out)
    return out


INDENTED_SCRIPTNAME = re.compile(rb"^[ \t]+(scriptname[ \t])", re.I | re.M)


def patch_cache(base: Path) -> list[str]:
    """Cache-only fixes so both compilers can import every file (assumption A2's fallback). Caprica stops on
    a ScriptName line that does not start the line (one official test script does this). The game folder is
    never touched; the patched list is recorded in sources.json."""
    patched = []
    for p in iter_files(base, (".psc",)):
        data = p.read_bytes()
        new = INDENTED_SCRIPTNAME.sub(rb"\1", data, count=1)
        if new != data:
            p.write_bytes(new)
            patched.append(p.relative_to(base).as_posix())
    return patched


PARENT_MEMBER = re.compile(r"^(\s*[\w:\[\]]+\s+)(parent)(\s*(?:=.*)?)$", re.I | re.M)


def caprica_overlay(dirs: list[Path]) -> dict:
    """Caprica reads 'Parent' as a keyword, so a struct member named parent (F4SE's ObjectReference
    ConnectPoint) stops it. A Caprica-only overlay, searched first, renames that member to parent_; the
    official compiler never sees it. Scripts that read ConnectPoint.parent must use the official compiler."""
    overlay = cache_dir() / "caprica_overlay"
    if overlay.exists():
        shutil.rmtree(overlay)
    done, seen = [], set()
    for d in dirs:
        for p in iter_files(d, (".psc",)):
            rel = p.relative_to(d).as_posix().lower()
            if rel in seen:
                continue  # an earlier import already provides this script
            seen.add(rel)
            text = p.read_text(encoding="utf-8", errors="replace")
            if "struct" not in text.lower():
                continue
            new = PARENT_MEMBER.sub(r"\1parent_\3", text)
            if new != text:
                target = overlay / p.relative_to(d)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(new, encoding="utf-8", newline=chr(10))
                done.append(p.relative_to(d).as_posix())
    return {"path": str(overlay), "files": done,
            "gap": "on the Caprica route the struct member 'parent' is read as 'parent_'; scripts that use it compile "
                   "with the official compiler only" if done else None}


def _game_pex(game_root: Path) -> list[tuple[str, Path]]:
    from .util import ci_child
    dd = ci_child(game_root, "Data")
    archives = [p for p in sorted(dd.glob("*.ba2")) if p.name.lower() == "fallout4 - misc.ba2"
                or (p.name.lower().startswith("dlc") and p.name.lower().endswith("- main.ba2"))]
    return [(a.stem, a) for a in archives]


def _decompile_game(game_root: Path, dest: Path, sample: int | None) -> dict:
    from . import ba2
    from .tools import find_exe
    champ = find_exe("champollion")
    if not champ:
        raise ForgeError("Champollion is not installed", "f4forge tools sync --only champollion --approve")
    pexdir = cache_dir() / "pex"
    for d in (pexdir, dest):
        if d.exists():
            shutil.rmtree(d)
    pexdir.mkdir(parents=True)
    n = 0
    for _, arc_path in _game_pex(game_root):
        arc = ba2.Archive(arc_path)
        with open(arc.path, "rb") as f:
            for e in arc.entries:
                if not e["name"].lower().endswith(".pex"):
                    continue
                if sample and n >= sample:
                    break
                rel = e["name"].replace("\\", "/")
                target = pexdir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(arc.read(e, f))
                n += 1
    dest.mkdir(parents=True)
    r = run([str(champ), "-p", str(dest), "-r", "-s", "-t", str(pexdir)], timeout=7200)
    psc = list(dest.rglob("*.psc"))
    failures = [ln.strip() for ln in ((r.get("stdout") or "") + (r.get("stderr") or "")).splitlines()
                if re.search(r"fail|error|exception", ln, re.I)]
    return {"pex": n, "psc": len(psc), "failures": failures[:50], "failure_count": len(failures),
            "champollion_exit": r.get("exit")}


def import_dirs(project_root: Path | None = None) -> list[str]:
    m = load_manifest()
    if not m:
        raise ForgeError("the Papyrus source cache is not built", "f4forge papyrus sources build")
    dirs = []
    if project_root:
        for d in (project_root / "source" / "Scripts", project_root / "data" / "Scripts" / "Source" / "User"):
            if d.is_dir():
                dirs.append(str(d))
    return dirs + [i["path"] for i in m["imports"]]


# --- compile ----------------------------------------------------------------------------------------

DIAG_OFFICIAL = re.compile(r"^(?P<file>.+?\.psc)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<msg>.+)$", re.I)
DIAG_CAPRICA = re.compile(r"^(?P<file>.+?\.psc)\s*\((?P<line>\d+),\s*(?P<col>\d+)(?::\d+)?\):\s*(?P<sev>Fatal Error|Error|Warning)?(?:\s+(?P<code>W?\d+))?:?\s*(?P<msg>.+)$", re.I)


def parse_diagnostics(text: str, compiler: str) -> list[dict]:
    out = []
    rx = DIAG_OFFICIAL if compiler == "official" else DIAG_CAPRICA
    for ln in text.splitlines():
        m = rx.match(ln.strip())
        if not m:
            continue
        sev = (m.groupdict().get("sev") or "error").lower()
        msg = m.group("msg").strip()
        if compiler == "official" and msg.lower().startswith("warning"):
            sev = "warning"
        out.append({"file": m.group("file"), "line": int(m.group("line")), "column": int(m.group("col")),
                    "severity": "warning" if "warn" in sev else "error", "message": msg, "compiler": compiler})
    return out


def official_compiler(game_root: Path | None) -> Path | None:
    if not game_root:
        return None
    return ci_path(game_root, "Papyrus Compiler/PapyrusCompiler.exe")


def choose_compiler(requested: str, game_root: Path | None) -> str:
    if requested in ("official", "caprica"):
        return requested
    return "official" if official_compiler(game_root) else "caprica"


def compile_scripts(targets: list[Path], out: Path, compiler: str = "auto", imports: list[str] | None = None,
                    game_root: Path | None = None, release: bool = False, final: bool = False,
                    optimize: bool = False, flags: Path | None = None, timeout: int = 900) -> dict:
    compiler = choose_compiler(compiler, game_root)
    out.mkdir(parents=True, exist_ok=True)
    if imports is None:
        imports = import_dirs(None)
    flag_file = flags or (cache_dir() / FLAGS_NAME)
    if not flag_file.is_file():
        flag_file = KNOWLEDGE_DIR / FLAGS_NAME
    flag_dir = str(flag_file.parent)
    if compiler == "caprica":
        m = load_manifest() or {}
        ov = (m.get("caprica_overlay") or {}).get("path")
        if ov and Path(ov).is_dir():
            imports = [ov] + list(imports)
    results, diags, argvs = [], [], []
    for target in targets:
        target = Path(target)
        is_dir = target.is_dir()
        src_dirs = [str(target if is_dir else target.parent)]
        imp = ";".join(dict.fromkeys(src_dirs + imports + [flag_dir]))
        if compiler == "official":
            exe = official_compiler(game_root)
            if not exe:
                raise ForgeError("the official Papyrus compiler is not installed", "use --compiler caprica")
            argv = [str(exe), str(target), f"-f={flag_file.name}", f"-i={imp}", f"-o={out}"]
            argv += ["-all"] if is_dir else []
            argv += (["-release"] if release else []) + (["-final"] if final else []) + (["-op"] if optimize else [])
        else:
            from .tools import find_exe
            exe = find_exe("caprica")
            if not exe:
                raise ForgeError("Caprica is not installed", "f4forge tools sync --only caprica --approve")
            argv = [str(exe), "-g", "fallout4", "-f", str(flag_file), "-i", imp, "-o", str(out), "--ignorecwd"]
            argv += (["-R"] if is_dir else []) + (["-r"] if release else []) + (["--final"] if final else [])
            argv += (["-O"] if optimize else []) + [str(target)]
        argvs.append(argv)
        r = run(argv, timeout=timeout, cwd=out)
        text = (r.get("stdout") or "") + "\n" + (r.get("stderr") or "")
        # Caprica 0.3.0 fails on some source folder paths with "ios_base::failbit set" every time for that
        # path (fact papyrus.caprica_failbit); the same files compile from another folder. Retry from fresh
        # temporary copies so the result reflects the code, not the folder name.
        stage_tries = 0
        while compiler == "caprica" and "ios_base::failbit" in text and stage_tries < 5:
            stage_tries += 1
            stage = Path(tempfile.mkdtemp(prefix="f4f-cap-"))
            try:
                staged = stage / target.name
                (shutil.copytree if is_dir else shutil.copy2)(target, staged)
                retry = [a if a != str(target) else str(staged) for a in argv]
                retry[retry.index("-i") + 1] = ";".join([str(staged if is_dir else stage)] + imp.split(";")[1:])
                r = run(retry, timeout=timeout, cwd=out)
                text = (r.get("stdout") or "") + "\n" + (r.get("stderr") or "")
                text = text.replace(str(staged), str(target))
            finally:
                shutil.rmtree(stage, ignore_errors=True)
        d = parse_diagnostics(text, compiler)
        diags += d
        names = [p.stem for p in (iter_files(target, (".psc",)) if is_dir else [target])]
        for n in names:
            pex = next(iter(out.rglob(n + ".pex")), None)
            results.append({"script": n, "pex": str(pex) if pex else None})
        if not d and not r["ok"]:
            diags.append({"file": str(target), "line": 0, "column": 0, "severity": "error", "compiler": compiler,
                          "message": (r.get("error") or text.strip().splitlines()[-1:] or ["compile failed"])[0][:300]})
    errors = [x for x in diags if x["severity"] == "error"]
    ok = not errors and all(x["pex"] for x in results)
    for x in results:
        if x["pex"]:
            try:
                info = parse_pex(Path(x["pex"]).read_bytes())
                x["pex_source"] = info["source"]
                x["objects"] = [o["name"] for o in info["objects"]]
            except ForgeError as e:
                x["pex_error"] = str(e)
    return {"ok": ok, "compiler": compiler, "scripts": results, "diagnostics": diags, "errors": len(errors),
            "output": str(out), "argv": argvs}


def decompile(paths: list[Path], out: Path) -> dict:
    from .tools import find_exe
    champ = find_exe("champollion")
    if not champ:
        raise ForgeError("Champollion is not installed", "f4forge tools sync --only champollion --approve")
    out.mkdir(parents=True, exist_ok=True)
    res = []
    for p in paths:
        r = run([str(champ), "-p", str(out)] + (["-r", "-s"] if Path(p).is_dir() else []) + [str(p)], timeout=1800)
        res.append({"input": str(p), "exit": r.get("exit"), "output": ((r.get("stdout") or "")[-400:]).strip()})
    return {"out": str(out), "psc": len(list(out.rglob("*.psc"))), "runs": res}


def script_header(psc: Path) -> tuple[str, str] | None:
    """(ScriptName, extends) from a .psc, lower-cased, or None."""
    try:
        text = psc.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = re.search(r"^\s*ScriptName\s+([\w:]+)(?:\s+extends\s+([\w:]+))?", text, re.I | re.M)
    return (m.group(1).lower(), (m.group(2) or "").lower()) if m else None
