"""Mod projects: manifest f4forge.json; layout data/ (Data-relative payload), plugin/ (Spriggit YAML tree),
source/ (scripts and asset sources), build/ (generated); scaffolding from templates; build; version bumps.

Project paperwork (PLAN.md, STATE.md, CHANGELOG.md, WORKSPACE_OWNERSHIP.md) is created with the project and
never packaged.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import struct
from pathlib import Path

from . import __version__ as FORGE_VERSION
from .util import TEMPLATES_DIR, ForgeError, iter_files, load_json, save_json

MANIFEST = "f4forge.json"
KINDS = ("plugin", "papyrus", "mcm", "robco", "bos", "f4se", "textures", "materials", "mesh", "looksmenu", "bodyslide", "audio")
PAPERWORK = ("PLAN.md", "STATE.md", "CHANGELOG.md", "WORKSPACE_OWNERSHIP.md", MANIFEST)


def find_project(explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit)
        if (p / MANIFEST).is_file():
            return p
        raise ForgeError(f"no {MANIFEST} in {p}", "create a project with: f4forge new <Name> --kind <kind>")
    cur = Path.cwd()
    for d in [cur, *cur.parents]:
        if (d / MANIFEST).is_file():
            return d
    raise ForgeError(f"not inside a project (no {MANIFEST} here or above)", "pass --project <folder> or cd into one")


def load_manifest(root: Path) -> dict:
    try:
        return load_json(root / MANIFEST)
    except (OSError, ValueError) as e:
        raise ForgeError(f"{MANIFEST} unreadable: {e}", f"fix {root / MANIFEST}")


def plugin_name(manifest: dict) -> str:
    p = manifest.get("plugin") or {}
    if not p.get("name"):
        raise ForgeError("this project has no plugin", "add one: f4forge new ... --kind plugin")
    return p["name"]


def plugin_build_path(root: Path, manifest: dict) -> Path:
    return root / "build" / "data" / plugin_name(manifest)


def make_id(name: str) -> str:
    # Capitalise the first letter of each word but keep the rest ("CI Mod" -> "CIMod", "my mod" -> "MyMod").
    words = re.split(r"[^A-Za-z0-9]+", name)
    s = "".join(w[:1].upper() + w[1:] for w in words if w)
    if not s:
        raise ForgeError(f"'{name}' has no letters or digits", "choose another name")
    return s[:40]


def templates() -> dict:
    out = {}
    for k in KINDS:
        t = TEMPLATES_DIR / k / "template.json"
        if t.is_file():
            out[k] = load_json(t)
    return out


def _subst(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace(k, v)
    return text


def write_header_plugin(path: Path, light: bool = True, masters: tuple[str, ...] = ("Fallout4.esm",),
                        author: str = "", description: str = "") -> Path:
    """A header-only plugin (TES4 record, HEDR 1.0, form version 131) the records worker and Spriggit extend."""
    def sub(sig: bytes, data: bytes) -> bytes:
        return sig + struct.pack("<H", len(data)) + data
    body = sub(b"HEDR", struct.pack("<fiI", 1.0, 0, 0x800))
    if author:
        body += sub(b"CNAM", author.encode("cp1252", "replace") + b"\0")
    if description:
        body += sub(b"SNAM", description.encode("cp1252", "replace")[:500] + b"\0")
    for m in masters:
        body += sub(b"MAST", m.encode("cp1252") + b"\0") + sub(b"DATA", b"\0" * 8)
    flags = 0x200 if light else 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"TES4" + struct.pack("<IIIIHH", len(body), flags, 0, 0, 131, 0) + body)
    return path


def _paperwork(root: Path, m: dict) -> None:
    today = _dt.date.today().isoformat()
    kinds = ", ".join(m["kinds"])
    files = {
        "PLAN.md": f"# PLAN - {m['name']}\n\nGoal: {m.get('description') or 'describe the mod in one sentence'}\n\n"
                   f"Kinds: {kinds}\n\n## Steps\n\n- [ ] Records / content\n- [ ] f4forge build\n- [ ] f4forge check\n"
                   "- [ ] f4forge package\n- [ ] In-game test (record what was seen)\n",
        "STATE.md": f"# STATE - {m['name']}\n\n- Version: {m['version']}\n- Created: {today} with Fallout 4 Forge {FORGE_VERSION}\n"
                    "- Evidence: none yet (static checks, then compile, package, load, gameplay)\n\n## Log\n\n"
                    f"- {today} project created\n",
        "CHANGELOG.md": f"# Changelog\n\n## {m['version']} - unreleased\n\n- First version.\n",
        "WORKSPACE_OWNERSHIP.md": f"# Workspace ownership\n\n- Owner record for {m['name']} (`{m['id']}`); one mod per folder.\n"
                                  "- Source of truth: `plugin/` (records, Spriggit YAML), `source/` (scripts and asset sources), "
                                  "`data/` (Data-relative payload).\n- Generated: `build/`, `dist/`. Never edited by hand.\n"
                                  "- Read-only inputs: the game folder, its Data, mod-manager staging, saves, INIs.\n"
                                  "- Releases: `f4forge package` -> `dist/`; the last known-good zip is kept in `dist/last-good/`.\n",
    }
    for name, text in files.items():
        p = root / name
        if not p.exists():
            p.write_text(text, encoding="utf-8", newline="\n")


def new_project(name: str, kinds: list[str], out: Path, author: str = "", description: str = "",
                light: bool = True, force: bool = False) -> dict:
    unknown = [k for k in kinds if k not in KINDS]
    if unknown:
        raise ForgeError(f"unknown kind(s): {', '.join(unknown)}", "kinds: " + ", ".join(KINDS))
    if out.exists() and any(out.iterdir()) and not force:
        raise ForgeError(f"{out} is not empty", "choose an empty folder or pass --force to add kinds")
    out.mkdir(parents=True, exist_ok=True)
    mid = make_id(name)
    existing = load_manifest(out) if (out / MANIFEST).is_file() else None
    m = existing or {"schema": 1, "name": name, "id": mid, "version": "0.1.0", "author": author,
                     "description": description, "kinds": [], "forge_version": FORGE_VERSION,
                     "package": {"archives": False, "ba2_version": 1, "fomod": False},
                     "requirements": [], "version_files": []}
    mid = m["id"]
    needs_plugin = any(k in kinds for k in ("plugin", "papyrus", "mcm", "audio"))
    if needs_plugin and not m.get("plugin"):
        from .spriggit import PACKAGE
        try:
            from .spriggit import default_version
            sver = default_version()
        except ForgeError:
            sver = "0.41.0"
        m["plugin"] = {"name": f"{mid}.esp", "light": light, "masters": ["Fallout4.esm"],
                       "spriggit": {"package": PACKAGE, "version": sver}}
    values = {"__ID__": mid, "__NAME__": m["name"], "__PLUGIN__": (m.get("plugin") or {}).get("name", f"{mid}.esp"),
              "__AUTHOR__": m.get("author") or "", "__VERSION__": m["version"]}
    created, generated, notes = [], [], []
    tpls = templates()
    for k in kinds:
        t = tpls[k]
        for rel in t.get("files", []):
            src = TEMPLATES_DIR / k / rel
            dst = out / _subst(rel, values)
            if dst.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                dst.write_text(_subst(src.read_text(encoding="utf-8"), values), encoding="utf-8", newline="\n")
            except UnicodeDecodeError:
                shutil.copy2(src, dst)
            created.append(dst.relative_to(out).as_posix())
        for req in t.get("requires", []):
            if req["id"] not in [r["id"] for r in m["requirements"]]:
                m["requirements"].append(req)
        if t.get("notes"):
            notes.append(f"{k}: {_subst(t['notes'], values)}")
        if k not in m["kinds"]:
            m["kinds"].append(k)
    for d in ("data", "source", "build"):
        (out / d).mkdir(exist_ok=True)
    if m.get("plugin"):
        bp = plugin_build_path(out, m)
        if not bp.exists():
            write_header_plugin(bp, m["plugin"]["light"], tuple(m["plugin"]["masters"]), m.get("author", ""), m.get("description", ""))
            generated.append(bp.relative_to(out).as_posix())
        (out / "plugin").mkdir(exist_ok=True)
        if not (out / "plugin" / "spriggit-meta.json").is_file():
            try:
                from .spriggit import export
                export(bp, out / "plugin")
                generated.append("plugin/ (Spriggit tree)")
            except ForgeError as e:
                notes.append(f"plugin/: Spriggit tree not created ({e}); run f4forge plugin export after f4forge tools sync")
    if "f4se" in kinds and not (out / "source" / "f4se" / mid).exists():
        try:
            from .native import new as native_new
            native_new(mid, out / "source" / "f4se" / mid, m.get("author", ""), m.get("description", ""))
            generated.append(f"source/f4se/{mid}/")
        except ForgeError as e:
            notes.append(f"f4se: template not copied ({e})")
    save_json(out / MANIFEST, m)
    _paperwork(out, m)
    _register_in_workspace(out, m)
    return {"project": str(out), "id": mid, "kinds": m["kinds"], "created": created, "generated": generated,
            "plugin": (m.get("plugin") or {}).get("name"), "requirements": [r["name"] for r in m["requirements"]],
            "notes": notes, "next": ["f4forge build", "f4forge check", "f4forge package"]}


def _register_in_workspace(root: Path, m: dict) -> None:
    from .home import config_value
    ws = config_value("workspace_root")
    if not ws:
        return
    wsp = Path(ws)
    try:
        root.resolve().relative_to(wsp.resolve())
    except ValueError:
        return
    md = wsp / "WORKSPACE.md"
    if not md.is_file():
        return
    text = md.read_text(encoding="utf-8")
    folder = root.resolve().relative_to(wsp.resolve()).as_posix()
    row = f"| {m['name']} | {folder} | {', '.join(m['kinds'])} | {m['version']} | created |"
    lines = [ln for ln in text.splitlines() if not ln.startswith(f"| {m['name']} | {folder} |")]
    lines.append(row)
    md.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


# --- build ------------------------------------------------------------------------------------------------

def build(root: Path, game_root: Path | None = None, skip: list[str] | None = None) -> dict:
    """Generate the payload from sources: plugin from the YAML tree, scripts, materials, textures, voice lines."""
    skip = set(skip or [])
    m = load_manifest(root)
    steps = []

    def step(name, fn):
        if name in skip:
            steps.append({"step": name, "status": "skipped"})
            return
        try:
            r = fn()
            steps.append({"step": name, "status": "done" if r is not None else "nothing to do", **({"result": r} if r else {})})
        except ForgeError as e:
            steps.append({"step": name, "status": "failed", "error": str(e), "fix": e.fix})

    def do_plugin():
        if not m.get("plugin") or not (root / "plugin" / "spriggit-meta.json").is_file():
            return None
        from .spriggit import build as sbuild
        r = sbuild(root / "plugin", plugin_build_path(root, m), str(root))
        out = root / "data" / plugin_name(m)
        shutil.copy2(plugin_build_path(root, m), out)
        return {"plugin": str(out), "records": r["records"]}

    def do_scripts():
        src = root / "source" / "Scripts"
        if not src.is_dir() or not any(src.rglob("*.psc")):
            return None
        from . import papyrus as PY
        r = PY.compile_scripts([src], root / "data" / "Scripts", (m.get("papyrus") or {}).get("compiler", "auto"),
                               PY.import_dirs(root), game_root)
        if not r["ok"]:
            raise ForgeError(f"{r['errors']} Papyrus error(s): " + "; ".join(
                f"{Path(d['file']).name}({d['line']},{d['column']}): {d['message']}" for d in r["diagnostics"][:5]),
                "fix the scripts (f4forge papyrus compile shows every diagnostic)")
        return {"compiler": r["compiler"], "scripts": len(r["scripts"])}

    def do_materials():
        src = root / "source" / "materials"
        files = list(src.rglob("*.json")) if src.is_dir() else []
        if not files:
            return None
        from . import bgsm
        n = 0
        for f in files:
            rel = f.relative_to(src)
            name = rel.name[:-5] if rel.name.lower().endswith(".json") else rel.name
            if not name.lower().endswith((".bgsm", ".bgem")):
                name += ".bgsm"
            dst = root / "data" / "Materials" / rel.parent / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(bgsm.build(json.loads(f.read_text(encoding="utf-8"))))
            n += 1
        return {"materials": n}

    def do_textures():
        src = root / "source" / "textures"
        files = [p for p in src.rglob("*") if p.suffix.lower() in (".png", ".tga", ".bmp", ".jpg", ".tif", ".tiff")] if src.is_dir() else []
        if not files:
            return None
        from . import textures as TX
        n = 0
        for f in files:
            rel = f.relative_to(src)
            TX.convert(f, root / "data" / "Textures" / rel.parent, None, alpha=f.suffix.lower() in (".png", ".tga"))
            n += 1
        return {"textures": n}

    def do_voice():
        spec = root / "source" / "audio" / "lines.json"
        if not spec.is_file():
            return None
        doc = json.loads(spec.read_text(encoding="utf-8"))
        if not doc.get("lines"):
            return None
        from . import audio
        made = []
        for ln in doc["lines"]:
            r = audio.voice(root / "source" / "audio" / ln["wav"], ln["text"], root / "data", doc.get("plugin") or plugin_name(m),
                            ln["voice_type"], ln["info"], ln.get("response", 1), game_root)
            made.append(r["data_path"])
        return {"voice_files": made}

    step("plugin", do_plugin)
    step("scripts", do_scripts)
    step("materials", do_materials)
    step("textures", do_textures)
    step("voice", do_voice)
    return {"project": str(root), "ok": not any(s["status"] == "failed" for s in steps), "steps": steps}


# --- bump -----------------------------------------------------------------------------------------------

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def bump(root: Path, part: str) -> dict:
    m = load_manifest(root)
    old = m["version"]
    mm = SEMVER.match(old)
    if not mm:
        raise ForgeError(f"version {old} is not X.Y.Z", f"fix {MANIFEST}")
    a, b, c = (int(x) for x in mm.groups())
    if part == "major":
        new = f"{a + 1}.0.0"
    elif part == "minor":
        new = f"{a}.{b + 1}.0"
    elif part == "patch":
        new = f"{a}.{b}.{c + 1}"
    elif SEMVER.match(part):
        new = part
    else:
        raise ForgeError(f"bump part {part!r}", "major | minor | patch | X.Y.Z")
    kept = None
    dist = root / "dist"
    zips = sorted(dist.glob(f"*{old}*.zip")) if dist.is_dir() else []
    if zips:
        lg = dist / "last-good"
        lg.mkdir(exist_ok=True)
        for z in zips:
            shutil.copy2(z, lg / z.name)
        kept = [str(lg / z.name) for z in zips]
    m["version"] = new
    save_json(root / MANIFEST, m)
    changed = [MANIFEST]
    for vf in m.get("version_files", []):
        p = root / vf["file"]
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
            changed.append(vf["file"])
    cl = root / "CHANGELOG.md"
    if cl.is_file():
        text = cl.read_text(encoding="utf-8")
        if f"## {new}" not in text:
            text = text.replace("# Changelog\n", f"# Changelog\n\n## {new} - unreleased\n\n- \n", 1)
            cl.write_text(text, encoding="utf-8", newline="\n")
            changed.append("CHANGELOG.md")
    st = root / "STATE.md"
    if st.is_file():
        st.write_text(re.sub(r"^- Version: .*$", f"- Version: {new}", st.read_text(encoding="utf-8"), count=1, flags=re.M),
                      encoding="utf-8", newline="\n")
        changed.append("STATE.md")
    return {"old": old, "new": new, "changed": changed, "kept_last_good": kept}


def tree(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for p in iter_files(root)]
