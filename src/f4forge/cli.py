"""f4forge command line. Every command prints JSON on stdout (compact; --pretty indents).

Exit codes: 0 ok, 1 findings, 2 named failure, 3 forge bug. Each run is logged as one JSON line
in <forge home>/logs/f4forge.log.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback

from . import __version__
from .util import ForgeError, emit

EXIT_CODES = {"0": "ok", "1": "findings", "2": "named failure", "3": "forge bug"}


class ForgeParser(argparse.ArgumentParser):
    """Usage errors become a named failure in JSON instead of argparse's text and exit."""

    def error(self, message):
        raise ForgeError(f"usage: {message}", f"see: {self.prog} --help")


# --- commands --------------------------------------------------------------------

def cmd_doctor(args):
    from .doctor import run
    return run(args.game)


def cmd_capabilities(args):
    return capabilities(), 0


def capabilities() -> dict:
    """Generated from the parser, never a hand-kept list."""
    p = parser()
    cmds = []
    for name, sub in subcommands(p).items():
        opts = []
        for a in sub._actions:
            if a.dest in ("help", "pretty", "game"):
                continue
            opts.append({"name": a.option_strings[0] if a.option_strings else a.dest,
                         "required": bool(a.required) or not a.option_strings,
                         "choices": list(a.choices) if a.choices else None, "help": a.help or ""})
        cmds.append({"command": name, "help": sub.description or "", "args": opts})
    return {"forge": "Fallout 4 Forge", "version": __version__, "commands": cmds,
            "global": ["--game <folder>", "--pretty"], "exit_codes": EXIT_CODES}


def subcommands(p: argparse.ArgumentParser) -> dict:
    for action in p._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def cmd_plan(args):
    from .knowledge import plan
    tier = None
    try:
        from .game import creation_kit, find_game
        tier = creation_kit(find_game(args.game)[0])["tier"]
    except ForgeError:
        tier = None
    return plan(" ".join(args.request), set(subcommands(parser())), tier), 0


def cmd_knowledge(args):
    from .knowledge import topic, topics
    if args.topic:
        return topic(args.topic), 0
    t = topics()
    return {"topics": t, "written": sum(1 for x in t if x["available"]), "hint": "f4forge knowledge <topic>"}, 0


def cmd_facts(args):
    from .knowledge import facts
    return facts(" ".join(args.query) if args.query else None), 0


def cmd_game(args):
    from .game import report
    out = report(args.game, archives=args.archives, plugins=args.plugins)
    if args.archives:
        from .home import home_dir
        from .util import save_json
        full = home_dir() / "reports" / "archives.json"
        save_json(full, out["archives"].pop("files"))
        out["archives"]["full_list"] = str(full)
    return out, 0


def cmd_ba2(args):
    from pathlib import Path

    from . import ba2
    from .home import home_dir
    from .util import save_json
    if args.action == "verify":
        targets = [Path(t) for t in args.targets]
        if args.all_installed:
            from .game import find_game
            from .util import ci_child
            root = find_game(args.game)[0]
            targets += sorted(ci_child(root, "Data").glob("*.ba2"))
        if not targets:
            raise ForgeError("ba2 verify needs archives or --all-installed", "f4forge ba2 verify --all-installed")
        rows = [ba2.verify(p, args.sample) for p in targets]
        bad = [r for r in rows if not r["ok"]]
        full = home_dir() / "reports" / "ba2-verify.json"
        save_json(full, rows)
        by = {}
        for r in rows:
            if r["ok"]:
                k = f"v{r['version']} {r['type']}"
                by[k] = by.get(k, 0) + 1
        return {"archives": len(rows), "ok": len(rows) - len(bad), "errors": len(bad),
                "by_version_type": dict(sorted(by.items())), "first_errors": bad[:5], "full_result": str(full)}, \
            (0 if not bad else 1)
    if not args.targets:
        raise ForgeError(f"ba2 {args.action} needs a path", "f4forge ba2 --help")
    if args.action == "pack":
        if not args.out:
            raise ForgeError("ba2 pack needs --out <archive.ba2>", "f4forge ba2 pack <folder> --out <Mod - Main.ba2>")
        return ba2.pack(Path(args.targets[0]), Path(args.out), args.type, args.ba2_version, args.filter and [args.filter]), 0
    arc = ba2.Archive(Path(args.targets[0]))
    if args.action == "list":
        rows = ba2.list_entries(arc, args.filter, args.limit)
        return {**arc.summary(), "shown": len(rows), "entries": rows}, 0
    if not args.out:
        raise ForgeError("ba2 extract needs --out <folder>", "f4forge ba2 extract <archive> --out <folder>")
    out = Path(args.out)
    ba2.guard_out(out, _game_root_or_none(args))
    return ba2.extract(arc, out, args.filter), 0


def _resolve_plugin(name: str, args) -> "Path":
    """A plugin path, or a bare plugin name looked up in the installed game's Data."""
    from pathlib import Path
    p = Path(name)
    if p.is_file():
        return p
    from .game import find_game
    from .util import ci_path
    root = find_game(args.game)[0]
    hit = ci_path(root, "Data/" + name)
    if not hit:
        raise ForgeError(f"plugin not found: {name}", "pass a path, or a file name present in the game's Data")
    return hit


def cmd_plugin(args):
    from pathlib import Path

    from . import plugin as P
    if args.action == "inspect":
        return P.inspect(_resolve_plugin(args.target, args), args.edids, args.limit), 0
    if args.action == "esl-check":
        r = P.esl_check(_resolve_plugin(args.target, args))
        return r, (0 if r["ok"] else 1)
    from . import spriggit as S
    if args.action == "export":
        return S.export(_resolve_plugin(args.target, args), Path(args.out) if args.out else None, args.project), 0
    r = S.build(Path(args.target) if args.target else None, Path(args.out) if args.out else None, args.project)
    return r, (0 if r.get("ok", True) else 1)


def cmd_loadorder(args):
    from pathlib import Path

    from .game import find_game
    from .loadorder import load_order
    r = load_order(find_game(args.game)[0], Path(args.plugins_txt) if args.plugins_txt else None)
    if not args.full:
        r["order"] = r["order"][: args.limit]
    return r, (1 if r["missing_masters"] or r["missing_files"] else 0)


def cmd_worker(args):
    from . import records as R
    if args.action == "build":
        return R.build(), 0
    st = R.status()
    return st, (0 if st["built"] and not st["stale"] else 1)


def _project_plugin_target(args):
    """--target, else the current project's build plugin (records then refresh the project's YAML tree)."""
    from pathlib import Path
    if args.target:
        return Path(args.target), None
    from .project import find_project, load_manifest, plugin_build_path
    root = find_project(getattr(args, "project", None))
    return plugin_build_path(root, load_manifest(root)), root


def cmd_records(args):
    from pathlib import Path

    from . import records as R
    from .game import find_game
    game_root = find_game(args.game)[0]
    plugins = [p.strip() for p in args.plugins.split(",")] if args.plugins else None
    if args.action == "find" and args.index:
        if not args.edid:
            raise ForgeError("records find --index needs --edid", "f4forge records find --index --edid 10mm")
        from .index import find_records
        rows = find_records(args.edid, args.limit)
        if args.type:
            rows = [r for r in rows if r["type"].upper() == args.type.upper()]
        return {"source": "local index (f4forge index)", "count": len(rows), "results": rows}, (0 if rows else 1)
    if args.action == "find":
        if not (args.edid or args.name or args.type):
            raise ForgeError("records find needs --edid, --name or --type", "f4forge records find --edid 10mm --type WEAP")
        req = {"verb": "find", **R.base_request(game_root, plugins), "edid": args.edid, "name": args.name,
               "type": args.type, "exact": args.exact, "limit": args.limit, "plugin": args.plugin}
        r = R.call(req)
        return r, (0 if r.get("count") else 1)
    if args.action == "show":
        if not args.formkey:
            raise ForgeError("records show needs a FormKey", "f4forge records show 004822:Fallout4.esm")
        return R.call({"verb": "show", **R.base_request(game_root, plugins), "formkey": args.formkey}), 0
    if args.action == "conflicts":
        if not args.plugin:
            raise ForgeError("records conflicts needs --plugin", "f4forge records conflicts --plugin MyMod.esp")
        return R.call({"verb": "conflicts", **R.base_request(game_root, plugins, [args.plugin]), "plugin": args.plugin,
                       "limit": args.limit}), 0
    target, project_root = _project_plugin_target(args)
    from . import plugin as P
    floor = P.light_floor(P.read_header(target)) if target.is_file() else P.rules()["object_id_floor"]["default_floor"]
    if args.action == "validate":
        req = {"verb": "validate", **R.base_request(game_root, plugins), "target": str(target), "floor": floor}
        r = R.call(req)
        return r, (0 if r.get("ok") else 1)
    if args.action == "override":
        if not args.formkey:
            raise ForgeError("records override needs a FormKey", "f4forge records override 004822:Fallout4.esm --target X.esp")
        req = {"verb": "override", **R.base_request(game_root, plugins), "formkey": args.formkey, "target": str(target),
               "light": args.light}
    else:
        if not (args.type and args.edid):
            raise ForgeError("records new needs --type and --edid", "f4forge records new --type MISC --edid MyItem")
        req = {"verb": "new", "target": str(target), "type": args.type, "edid": args.edid, "light": args.light,
               "master": args.master, "floor": floor}
        if plugins:
            req.update(R.base_request(game_root, plugins))
    r = R.call(req)
    if project_root is not None and r.get("ok"):
        from . import spriggit as S
        r["yaml"] = S.export(target, None, str(project_root))
    return r, (0 if r.get("ok") else 1)


def cmd_papyrus(args):
    from pathlib import Path

    from . import papyrus as PY
    if args.action != "sources" and args.what:
        args.paths = [args.what] + list(args.paths)
    if args.action == "sources":
        from .game import find_game
        if args.what not in ("build", "status", None):
            raise ForgeError(f"papyrus sources {args.what}?", "f4forge papyrus sources build | status")
        if args.what != "build":
            m = PY.load_manifest()
            return ({"built": False, "fix": "f4forge papyrus sources build"} if not m else m), (0 if m else 1)
        return PY.build_sources(find_game(args.game)[0], args.route, args.sample), 0
    if args.action == "pex":
        rows = []
        for t in args.paths:
            info = PY.parse_pex(Path(t).read_bytes())
            rows.append({"file": t, **{k: info[k] for k in ("version", "game", "source", "user", "objects")}})
        return {"pex": rows}, 0
    if args.action == "decompile":
        if not args.out:
            raise ForgeError("papyrus decompile needs --out", "f4forge papyrus decompile X.pex --out <folder>")
        return PY.decompile([Path(p) for p in args.paths], Path(args.out)), 0
    # compile
    game_root = _game_root_or_none(args)
    project_root = None
    targets = [Path(p) for p in args.paths]
    if not targets:
        from .project import find_project
        project_root = find_project(args.project)
        targets = [project_root / "source" / "Scripts"]
        out = Path(args.out) if args.out else project_root / "data" / "Scripts"
    else:
        out = Path(args.out) if args.out else Path.cwd() / "build" / "Scripts"
    imports = list(args.import_dir or [])
    if not args.no_cache:
        imports += PY.import_dirs(project_root)
    r = PY.compile_scripts(targets, out, args.compiler, imports, game_root, args.release, args.final, args.optimize,
                           Path(args.flags) if args.flags else None)
    return r, (0 if r["ok"] else 1)


def cmd_material(args):
    import json as _json
    from pathlib import Path

    from . import bgsm
    if args.action == "show":
        doc = bgsm.parse(Path(args.target).read_bytes())
        if args.out:
            Path(args.out).write_text(bgsm.to_json(doc) + "\n", encoding="utf-8", newline="\n")
        return {"file": args.target, "material": doc, "textures": bgsm.textures(doc), "json": args.out}, 0
    if args.action == "build":
        if not args.out:
            raise ForgeError("material build needs --out <file.bgsm|.bgem>", "f4forge material build m.json --out m.bgsm")
        doc = _json.loads(Path(args.target).read_text(encoding="utf-8"))
        data = bgsm.build(doc)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_bytes(data)
        return {"file": args.out, "bytes": len(data), "type": doc["Type"], "version": doc.get("Version")}, 0
    # verify
    from .home import home_dir
    from .util import save_json
    targets = [Path(args.target)] if args.target else []
    if args.all_installed:
        from .game import find_game
        from .util import ci_child
        from . import ba2
        for p in sorted(ci_child(find_game(args.game)[0], "Data").glob("*.ba2")):
            try:
                if ba2.read_header(p)["type"] == "GNRL":
                    targets.append(p)
            except ForgeError:
                pass
    if not targets:
        raise ForgeError("material verify needs an archive or --all-installed", "f4forge material verify --all-installed")
    rows = [r for r in (bgsm.roundtrip_archive(t) for t in targets) if r["materials"]]
    full = home_dir() / "reports" / "material-roundtrip.json"
    save_json(full, rows)
    total = sum(r["materials"] for r in rows)
    same = sum(r["byte_identical"] for r in rows)
    jt = sum(r.get("json_text", 0) for r in rows)
    vers = {}
    for r in rows:
        for k, v in r["versions"].items():
            vers[k] = vers.get(k, 0) + v
    return {"archives_with_materials": len(rows), "materials": total, "byte_identical": same, "json_text": jt,
            "failed": total - same - jt, "versions": dict(sorted(vers.items())), "full_result": str(full)}, (0 if total == same + jt else 1)


def cmd_tex(args):
    from pathlib import Path

    from . import textures as TX
    if args.action == "inspect":
        rows = [TX.inspect(Path(t), args.role) for t in args.targets]
        bad = [r for r in rows if not r["ok"]]
        return ({"results": rows} if len(rows) > 1 else rows[0]), (1 if bad else 0)
    out = Path(args.out) if args.out else Path.cwd()
    rows = [TX.convert(Path(t), out, args.role, args.alpha, args.format, args.name) for t in args.targets]
    return ({"results": rows} if len(rows) > 1 else rows[0]), 0


def cmd_nif(args):
    from pathlib import Path

    from . import nif
    if args.action == "info":
        return nif.info(Path(args.target)), 0
    installed = None
    if not args.no_index:
        from .index import assets
        installed = assets()
    project_data = Path(args.project) / "data" if args.project else None
    r = nif.check_refs(Path(args.target), project_data, installed)
    return r, (0 if r["ok"] else 1)


def cmd_mesh(args):
    from pathlib import Path

    from . import nif
    src = Path(args.source)
    if args.action == "import":
        out = Path(args.out) if args.out else src.with_suffix(".blend")
        return nif.blender_run("import", src, out), 0
    if args.action == "export":
        if not args.out:
            raise ForgeError("mesh export needs --out <file.nif>", "f4forge mesh export model.blend --out Meshes/X.nif")
        r = nif.blender_run("export", src, Path(args.out))
    else:
        out = Path(args.out) if args.out else src.with_name(src.stem + ".roundtrip.nif")
        r = nif.blender_run("roundtrip", src, out)
    r["nif"] = nif.info(Path(r["output"]))
    return r, 0


def cmd_index(args):
    from .game import find_game
    from .index import build
    return build(find_game(args.game)[0], records=not args.no_records), 0


def cmd_audio(args):
    from pathlib import Path

    from . import audio as A
    game_root = _game_root_or_none(args)
    t = Path(args.target) if args.target else None
    if args.action == "check":
        r = A.wav_check(t)
        return r, (0 if r["ok"] else 1)
    if args.action == "unfuz":
        lip, snd = A.fuz_unpack(t.read_bytes())
        out = Path(args.out) if args.out else t.parent
        out.mkdir(parents=True, exist_ok=True)
        (out / (t.stem + ".lip")).write_bytes(lip)
        (out / (t.stem + ".xwm")).write_bytes(snd)
        return {"fuz": str(t), "lip_bytes": len(lip), "xwm_bytes": len(snd), "sum_ok": 12 + len(lip) + len(snd) == t.stat().st_size,
                "xwm": A.riff_info(snd) if snd[:4] == b"RIFF" else None, "out": str(out)}, 0
    if args.action == "fuz":
        if not (args.lip and args.out):
            raise ForgeError("audio fuz needs <audio.xwm> --lip <file.lip> --out <file.fuz>", "f4forge audio --help")
        data = A.fuz_pack(Path(args.lip).read_bytes(), t.read_bytes())
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_bytes(data)
        return {"fuz": args.out, "bytes": len(data)}, 0
    if args.action == "encode":
        return A.encode(t, Path(args.out) if args.out else t.with_suffix(".xwm"), game_root, args.bitrate), 0
    if not args.text:
        raise ForgeError(f"audio {args.action} needs --text \"<the spoken line>\"", "f4forge audio --help")
    if args.action == "lip":
        return A.lip(t, args.text, Path(args.out) if args.out else t.with_suffix(".lip"), game_root, args.language), 0
    if not (args.plugin and args.voice_type and args.info):
        raise ForgeError("audio voice needs --plugin, --voice-type and --info <INFO FormID>", "f4forge audio --help")
    data_root = Path(args.out) if args.out else None
    if data_root is None:
        from .project import find_project
        data_root = find_project(args.project) / "data"
    return A.voice(t, args.text, data_root, args.plugin, args.voice_type, args.info, args.response, game_root), 0


def cmd_logs(args):
    from .logs import collect
    return collect(_game_root_or_none(args), args.lines, args.mod), 0


def cmd_explain(args):
    from .logs import explain
    hits = explain(" ".join(args.text))
    return {"matches": hits, "hint": None if hits else "no known signature; f4forge logs shows the surrounding lines"}, (0 if hits else 1)


def cmd_mcm(args):
    from pathlib import Path

    from .mcm import validate, validate_installed
    lo = None
    try:
        from .game import find_game
        from .loadorder import load_order
        lo = {o["plugin"].lower() for o in load_order(find_game(args.game)[0])["order"]}
    except ForgeError:
        lo = None
    if args.installed:
        from .game import find_game
        r = validate_installed(find_game(args.game)[0], lo)
        r.pop("results")
        return r, (0 if not r["with_errors"] else 1)
    if not args.folder:
        raise ForgeError("mcm needs a MCM/Config/<Mod> folder or --installed", "f4forge mcm <folder>")
    r = validate(Path(args.folder), lo)
    return r, (0 if r["ok"] else 1)


def cmd_validate_cfg(args):
    from pathlib import Path

    from . import datakinds, frameworks_cfg
    lo = None
    try:
        from .game import find_game
        from .loadorder import load_order
        lo = {o["plugin"].lower() for o in load_order(find_game(args.game)[0])["order"]}
    except ForgeError:
        lo = None
    rows = []
    for f in args.files:
        p = Path(f)
        low = p.as_posix().lower()
        if "robco_patcher" in low and low.endswith(".ini"):
            rows.append(frameworks_cfg.robco_validate(p, None, lo))
        elif low.endswith("_swap.ini"):
            rows.append(frameworks_cfg.bos_validate(p))
        else:
            rows.append(datakinds.validate_any(p))
    bad = [r for r in rows if not r["ok"]]
    return ({"results": rows} if len(rows) > 1 else rows[0]), (1 if bad else 0)


def cmd_native(args):
    from pathlib import Path

    from . import native
    if args.action == "new":
        if not args.target:
            raise ForgeError("native new needs a plugin name", "f4forge native new MyPlugin --out <folder>")
        out = Path(args.out) if args.out else Path.cwd() / native._safe_name(args.target)
        return native.new(args.target, out, args.author or "", args.description or ""), 0
    if args.action == "check":
        r = native.check_dll(Path(args.target))
        return r, (0 if r["ok"] else 1)
    folder = Path(args.target) if args.target else Path.cwd()
    r = native.build(folder, args.mode)
    return r, (0 if r["ok"] else 1)


def cmd_ck(args):
    from . import ck
    from .game import find_game
    root = find_game(args.game)[0]
    if args.action == "info":
        return ck.info(root), 0
    if args.action == "ckpe-install":
        return ck.ckpe_install(root, args.approve), 0
    if args.action == "ckpe-uninstall":
        return ck.ckpe_uninstall(root, args.approve), 0
    if not args.plugin:
        raise ForgeError(f"ck {args.action} needs --plugin <file in Data>", "f4forge ck previs --plugin MyMod.esp")
    return ck.run_job(args.action, root, args.plugin, args.approve, args.mode, args.scope, args.platform), 0


def _project(args):
    from .project import find_project
    return find_project(getattr(args, "project", None))


def cmd_new(args):
    import re as _re
    from pathlib import Path

    from .project import make_id, new_project
    kinds = args.kind or ["plugin"]
    folder = _re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", args.name).strip(". ") or make_id(args.name)
    out = Path(args.out) if args.out else Path.cwd() / folder
    if args.out is None:
        from .home import config_value
        ws = config_value("workspace_root")
        if ws and Path(ws).is_dir():
            out = Path(ws) / folder
    return new_project(args.name, kinds, out, args.author or "", args.description or "", not args.full_plugin, args.force), 0


def cmd_templates(args):
    from .project import templates
    return {"templates": [{"kind": k, "title": v.get("title"), "files": v.get("files", []), "generated": v.get("generated", []),
                           "requires": [r["name"] for r in v.get("requires", [])], "notes": v.get("notes", "")}
                          for k, v in templates().items()]}, 0


def cmd_build(args):
    from .project import build
    r = build(_project(args), _game_root_or_none(args), args.skip)
    return r, (0 if r["ok"] else 1)


def cmd_check(args):
    from .check import check_project
    r = check_project(_project(args), args.game, args.compile)
    return r, (0 if r["ok"] else 1)


def cmd_package(args):
    from pathlib import Path

    from .package import build
    r = build(_project(args), Path(args.out) if args.out else None, True if args.archives else None,
              args.ba2_version, True if args.fomod else None)
    return r, (0 if r["validation"]["ok"] else 1)


def cmd_validate(args):
    from pathlib import Path

    from .package import validate
    r = validate(Path(args.zip))
    if args.simulate is not None and r.get("fomod"):
        import zipfile

        from .fomod import simulate
        with zipfile.ZipFile(args.zip) as zf:
            r["simulation"] = simulate(zf, args.simulate)
    return r, (0 if r["ok"] else 1)


def cmd_deploy(args):
    from .deploy import deploy
    return deploy(_project(args), _game_root_or_none(args), args.approve, args.force, args.to, args.enable_plugin), 0


def cmd_undeploy(args):
    from .deploy import undeploy
    return undeploy(_project(args), _game_root_or_none(args), args.approve, args.to), 0


def cmd_bump(args):
    from .project import bump
    return bump(_project(args), args.part), 0


def cmd_nexus(args):
    from . import nexus
    if args.action == "mod":
        if not args.query:
            raise ForgeError("nexus mod needs an ID", "f4forge nexus mod 42147")
        return nexus.mod(int(args.query[0]), args.game_domain, args.description), 0
    if args.action == "find":
        if not args.query:
            raise ForgeError("nexus find needs a name", "f4forge nexus find RobCo Patcher")
        return {"results": nexus.find(" ".join(args.query), args.game_domain, args.limit)}, 0
    return nexus.page_kit(_project(args)), 0


def cmd_conflicts(args):
    from .datakinds import replacer_report
    from .game import find_game
    from .index import asset_source, assets
    from .project import load_manifest, plugin_build_path
    root = _project(args)
    m = load_manifest(root)
    game_root = find_game(args.game)[0]
    out = {"project": str(root)}
    inst = assets(game_root)
    if inst is None:
        out["assets"] = {"skipped": "no asset index", "fix": "f4forge index"}
    else:
        rep = replacer_report(root / "data", inst)
        out["assets"] = {"replaces_installed": [{"file": f, "provided_by": asset_source(f)} for f in rep["replaces_installed"][: args.limit]],
                         "count": len(rep["replaces_installed"])}
    if m.get("plugin"):
        bp = (root / "data" / m["plugin"]["name"]) if (root / "data" / m["plugin"]["name"]).is_file() else plugin_build_path(root, m)
        if bp.is_file():
            from . import records as R
            try:
                out["records"] = R.call({"verb": "overlap", **R.base_request(game_root, None), "target": str(bp), "limit": args.limit})
            except ForgeError as e:
                out["records"] = {"skipped": str(e), "fix": e.fix}
    return out, 0


def cmd_selftest(args):
    from .selftest import run
    r = run()
    return r, (0 if r["ok"] else 1)


def cmd_tools(args):
    from . import tools as T
    root = T.tools_root(args.tools_root) if args.action != "status" or args.tools_root else None
    if args.action == "status":
        st = T.status(root=root, game_root=_game_root_or_none(args))
        return st, (0 if st["required_ok"] else 1)
    if args.action == "sync":
        res = T.sync(root=root, only=args.only, approve=args.approve)
        return res, (0 if not res["errors"] else 1)
    if not args.only or len(args.only) != 1:
        raise ForgeError("tools pin needs exactly one --only <id>", "f4forge tools pin --only spriggit --approve")
    return T.pin(args.only[0], approve=args.approve), 0


def _game_root_or_none(args):
    try:
        from .game import find_game
        return find_game(args.game)[0]
    except ForgeError:
        return None


def cmd_config(args):
    from .home import CONFIG_KEYS, config_path, load_config, set_config
    if args.set or args.unset:
        pairs = {}
        for item in args.set or []:
            if "=" not in item:
                raise ForgeError(f"--set needs key=value, got {item!r}", f"keys: {', '.join(CONFIG_KEYS)}")
            k, v = item.split("=", 1)
            pairs[k.strip()] = v.strip()
        for k in args.unset or []:
            pairs[k] = None
        cfg = set_config(pairs)
    else:
        cfg = load_config()
    return {"config": str(config_path()), "values": {k: cfg.get(k) for k in CONFIG_KEYS}}, 0


# --- parser ------------------------------------------------------------------------

def parser() -> argparse.ArgumentParser:
    p = ForgeParser(prog="f4forge", description="Fallout 4 Forge: make, check, package and ship Fallout 4 mods.")
    p.add_argument("--version", action="version", version=f"f4forge {__version__}")
    p.add_argument("--pretty", action="store_true", help="indent the JSON output")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=ForgeParser)

    def add(name, fn, desc):
        sp = sub.add_parser(name, description=desc, help=desc)
        sp.add_argument("--game", help="game folder (default: FALLOUT4_ROOT, config game_root, then auto-detect)")
        sp.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help="indent the JSON output")
        sp.set_defaults(fn=fn)
        return sp

    add("doctor", cmd_doctor, "health in sections: toolchain, game, payload, tools, worker")
    add("capabilities", cmd_capabilities, "list commands and arguments (generated from the parser)")
    add("selftest", cmd_selftest, "offline self-test in a temp folder: data, topics, routing, BA2, materials, scaffold/check/package")
    s = add("plan", cmd_plan, "route a request: routes, commands in order, knowledge, tools and tiers, what to avoid")
    s.add_argument("request", nargs="+", help="what you want to make or fix, in words")
    s = add("knowledge", cmd_knowledge, "list knowledge topics or print one")
    s.add_argument("topic", nargs="?", help="topic name, e.g. archives")
    s = add("facts", cmd_facts, "facts with tier and source; a query filters by id or claim text")
    s.add_argument("query", nargs="*", help="text to match, e.g. ba2")
    s = add("game", cmd_game, "installed runtime, F4SE, Address Library, DLC, Creation Club, Creation Kit, mod managers")
    s.add_argument("--archives", action="store_true", help="also read every BA2 header (full list saved to the forge home)")
    s.add_argument("--plugins", action="store_true", help="also read every plugin header (counts by HEDR version)")
    s = add("ba2", cmd_ba2, "BA2 archives: list, extract, verify (one sampled entry inflated), pack (GNRL or DX10)")
    s.add_argument("action", choices=["list", "extract", "verify", "pack"], help="list | extract | verify | pack")
    s.add_argument("targets", nargs="*", help="archive(s); for pack the Data-relative source folder")
    s.add_argument("--out", help="extract: output folder; pack: archive to write")
    s.add_argument("--filter", help="glob on archive paths, e.g. '*.pex' or 'textures\\\\*'")
    s.add_argument("--limit", type=int, default=200, help="list: max entries")
    s.add_argument("--all-installed", action="store_true", help="verify every Data/*.ba2 of the installed game")
    s.add_argument("--sample", default="middle", choices=["first", "middle", "last"], help="verify: which entry to inflate")
    s.add_argument("--type", default="auto", choices=["auto", "GNRL", "DX10"], help="pack: archive type")
    s.add_argument("--ba2-version", type=int, default=1, choices=[1, 7, 8], help="pack: header version (default 1, D13)")
    s = add("plugin", cmd_plugin, "plugins: inspect, esl-check, export (plugin -> Spriggit YAML), build (YAML -> plugin)")
    s.add_argument("action", choices=["inspect", "esl-check", "export", "build"], help="inspect | esl-check | export | build")
    s.add_argument("target", nargs="?", help="plugin path or Data file name; build: the YAML tree (default: project plugin/)")
    s.add_argument("--edids", action="store_true", help="inspect: also index EditorIDs (inflates compressed records)")
    s.add_argument("--limit", type=int, default=50, help="inspect: max record types listed")
    s.add_argument("--out", help="export: YAML folder; build: plugin file to write")
    s.add_argument("--project", help="project folder (default: current folder or a parent with f4forge.json)")
    s = add("papyrus", cmd_papyrus, "Papyrus: sources build|status, compile (official or Caprica), decompile, pex")
    s.add_argument("action", choices=["sources", "compile", "decompile", "pex"], help="sources | compile | decompile | pex")
    s.add_argument("what", nargs="?", help="sources: build | status; other actions: the first path")
    s.add_argument("paths", nargs="*", help="compile: .psc files or folders (default: the project's source/Scripts); "
                                             "decompile/pex: .pex files")
    s.add_argument("--compiler", default="auto", choices=["auto", "official", "caprica"], help="compile driver")
    s.add_argument("--out", help="output folder (compile default: project data/Scripts)")
    s.add_argument("--import-dir", action="append", help="extra import folder (repeatable, searched first)")
    s.add_argument("--no-cache", action="store_true", help="compile: do not add the source cache imports")
    s.add_argument("--flags", help="compile: flags file (default: the forge's F4Forge_Papyrus_Flags.flg)")
    s.add_argument("--release", action="store_true", help="compile: strip DebugOnly code")
    s.add_argument("--final", action="store_true", help="compile: strip BetaOnly code")
    s.add_argument("--optimize", action="store_true", help="compile: optimise")
    s.add_argument("--route", default="auto", choices=["auto", "official", "decompiled"], help="sources build route")
    s.add_argument("--sample", type=int, help="sources build (decompiled): only the first N scripts")
    s.add_argument("--project", help="project folder (default: current folder or a parent with f4forge.json)")
    s = add("tex", cmd_tex, "textures: inspect DDS against role rules, convert images with role presets (texconv)")
    s.add_argument("action", choices=["inspect", "convert"], help="inspect <dds...> | convert <image...>")
    s.add_argument("targets", nargs="+", help="DDS files (inspect) or source images (convert)")
    s.add_argument("--role", help="texture role (default: from the file suffix): diffuse normal specular glow facemask "
                                  "environment greyscale generic ui")
    s.add_argument("--alpha", action="store_true", help="convert: keep alpha (diffuse -> BC3)")
    s.add_argument("--format", help="convert: explicit DXGI format, e.g. BC7_UNORM")
    s.add_argument("--name", help="convert: output file name (default: the input stem)")
    s.add_argument("--out", help="convert: output folder (default: current folder)")
    s = add("audio", cmd_audio, "audio/voice: check WAV, encode XWM, lip, voice (WAV+text -> FUZ in voice layout), fuz, unfuz")
    s.add_argument("action", choices=["check", "encode", "lip", "voice", "fuz", "unfuz"],
                   help="check <wav> | encode <wav> | lip <wav> --text | voice <wav> --text ... | fuz <xwm> --lip | unfuz <fuz>")
    s.add_argument("target", help="input file")
    s.add_argument("--text", help="lip/voice: the spoken line")
    s.add_argument("--out", help="output file (voice: Data-relative root folder; default: project data/)")
    s.add_argument("--lip", help="fuz: the .lip file")
    s.add_argument("--bitrate", type=int, help="encode: xWMA bitrate (20000 ... 192000)")
    s.add_argument("--language", default="USEnglish", help="lip: LipGenerator language")
    s.add_argument("--plugin", help="voice: plugin file name, e.g. MyMod.esp")
    s.add_argument("--voice-type", help="voice: voice type EditorID, e.g. NPCMBoston")
    s.add_argument("--info", help="voice: topic INFO FormID (hex)")
    s.add_argument("--response", type=int, default=1, help="voice: response number")
    s.add_argument("--project", help="project folder")
    s = add("logs", cmd_logs, "collect and triage F4SE, plugin, Papyrus and crash logs (read-only)")
    s.add_argument("--mod", help="only lines or logs mentioning this mod")
    s.add_argument("--lines", type=int, default=25, help="max problem lines per log")
    s = add("explain", cmd_explain, "match an error text against the known-signature registry")
    s.add_argument("text", nargs="+", help="error text")
    s = add("mcm", cmd_mcm, "validate an MCM/Config/<Mod> folder (config.json, settings.ini, keybinds.json)")
    s.add_argument("folder", nargs="?", help="the MCM config folder")
    s.add_argument("--installed", action="store_true", help="validate every installed MCM config")
    s = add("validate-config", cmd_validate_cfg, "validate RobCo Patcher INIs, *_SWAP.ini, LooksMenu presets, BodySlide XML, INI files")
    s.add_argument("files", nargs="+", help="files to check")
    s = add("native", cmd_native, "native F4SE plugins: new (CommonLibF4 template), build (xmake/MSVC), check (DLL exports)")
    s.add_argument("action", choices=["new", "build", "check"], help="new <Name> | build [folder] | check <dll>")
    s.add_argument("target", nargs="?", help="new: plugin name; build: folder; check: DLL")
    s.add_argument("--out", help="new: output folder")
    s.add_argument("--author", help="new: author")
    s.add_argument("--description", help="new: description")
    s.add_argument("--mode", default="releasedbg", choices=["releasedbg", "debug", "release"], help="build: xmake mode")
    s = add("ck", cmd_ck, "Creation Kit tier: info, precombine, previs, facegen, ckpe-install/uninstall (dry run unless --approve)")
    s.add_argument("action", choices=["info", "precombine", "previs", "facegen", "ckpe-install", "ckpe-uninstall"])
    s.add_argument("--plugin", help="plugin file name in Data")
    s.add_argument("--mode", default="clean", choices=["clean", "filtered"], help="precombine/previs: clean or filtered")
    s.add_argument("--scope", default="all", choices=["all", "main", "ints", "other"], help="precombine/previs: cells")
    s.add_argument("--platform", default="X64", choices=["X64", "W32", "XB1", "PS4"], help="facegen: platform")
    s.add_argument("--approve", action="store_true", help="really run / install (writes into the game folder)")
    s = add("templates", cmd_templates, "list project kinds and what each scaffolds")
    s = add("new", cmd_new, "create a mod project (default folder: the workspace root) from one or more kinds")
    s.add_argument("name", help="mod name")
    s.add_argument("--kind", action="append", help="kind (repeatable): plugin papyrus mcm robco bos f4se textures materials "
                                                   "mesh looksmenu bodyslide audio")
    s.add_argument("--out", help="project folder (default: <workspace_root>/<Name>, else ./<Name>)")
    s.add_argument("--author", help="author")
    s.add_argument("--description", help="one-line description")
    s.add_argument("--full-plugin", action="store_true", help="plugin without the ESL flag")
    s.add_argument("--force", action="store_true", help="add kinds to an existing project folder")
    for name, fn, desc in (("build", cmd_build, "build the payload: plugin from YAML, scripts, materials, textures, voice"),
                           ("check", cmd_check, "validate the project: plugin, scripts, configs, assets, references, privacy; evidence tiers"),
                           ("package", cmd_package, "deterministic release zip from data/ (+ BA2, FOMOD) with receipt and validation"),
                           ("deploy", cmd_deploy, "copy data/ into the game (or --to a mod folder); dry run until --approve"),
                           ("undeploy", cmd_undeploy, "remove what deploy wrote and restore backups; dry run until --approve"),
                           ("bump", cmd_bump, "bump the version everywhere and keep the last good zip"),
                           ("conflicts", cmd_conflicts, "project vs installed: replaced assets and contested record overrides")):
        s = add(name, fn, desc)
        s.add_argument("--project", help="project folder (default: current folder or a parent with f4forge.json)")
        if name == "build":
            s.add_argument("--skip", action="append", choices=["plugin", "scripts", "materials", "textures", "voice"], help="skip a step")
        if name == "check":
            s.add_argument("--compile", action="store_true", help="also compile the scripts")
        if name == "package":
            s.add_argument("--out", help="output folder (default: <project>/dist)")
            s.add_argument("--archives", action="store_true", help="pack into <Plugin> - Main.ba2 / - Textures.ba2")
            s.add_argument("--ba2-version", type=int, choices=[1, 7, 8], help="BA2 header version (default 1)")
            s.add_argument("--fomod", action="store_true", help="add a basic FOMOD installer")
        if name in ("deploy", "undeploy"):
            s.add_argument("--approve", action="store_true", help="really copy/remove")
            s.add_argument("--to", help="a mod-manager mod folder instead of the game's Data")
        if name == "deploy":
            s.add_argument("--force", action="store_true", help="back up and replace files this project did not deploy")
            s.add_argument("--enable-plugin", action="store_true", help="also activate the plugin in plugins.txt (backed up)")
        if name == "bump":
            s.add_argument("part", help="major | minor | patch | X.Y.Z")
        if name == "conflicts":
            s.add_argument("--limit", type=int, default=100, help="max entries per list")
    s = add("validate", cmd_validate, "check any mod zip: layout, paperwork, dev files, script sources, paths, secrets, FOMOD")
    s.add_argument("zip", help="zip file")
    s.add_argument("--simulate", nargs="*", help="FOMOD: simulate an install choosing these optional plugins")
    s = add("nexus", cmd_nexus, "Nexus Mods: mod <id>, find <name> (public API, read-only), page (project page kit)")
    s.add_argument("action", choices=["mod", "find", "page"], help="mod <id> | find <name> | page")
    s.add_argument("query", nargs="*", help="mod ID or name")
    s.add_argument("--game-domain", default="fallout4", help="Nexus game domain")
    s.add_argument("--description", action="store_true", help="mod: include the description text")
    s.add_argument("--limit", type=int, default=10, help="find: max results")
    s.add_argument("--project", help="page: project folder")
    s = add("nif", cmd_nif, "NIF meshes: info (header, blocks, strings), refs (materials/textures checked)")
    s.add_argument("action", choices=["info", "refs"], help="info <nif> | refs <nif>")
    s.add_argument("target", help="NIF file")
    s.add_argument("--project", help="refs: project folder whose data/ also counts")
    s.add_argument("--no-index", action="store_true", help="refs: do not use the installed asset index")
    s = add("mesh", cmd_mesh, "meshes through headless Blender + PyNifly: import (nif->blend), export, roundtrip")
    s.add_argument("action", choices=["import", "export", "roundtrip"], help="import | export | roundtrip")
    s.add_argument("source", help="NIF (import/roundtrip) or .blend (export)")
    s.add_argument("--out", help="output file")
    s = add("index", cmd_index, "build the local index: asset paths, script names, EditorIDs (under the forge home)")
    s.add_argument("--no-records", action="store_true", help="skip the EditorID index (worker)")
    s = add("material", cmd_material, "BGSM/BGEM materials: show (to JSON), build (from JSON), verify (byte round trip)")
    s.add_argument("action", choices=["show", "build", "verify"], help="show <file> | build <json> --out | verify")
    s.add_argument("target", nargs="?", help="material file, JSON file, or archive for verify")
    s.add_argument("--out", help="show: write the JSON here; build: material file to write")
    s.add_argument("--all-installed", action="store_true", help="verify every material in the installed GNRL archives")
    s = add("worker", cmd_worker, "records worker (.NET, Mutagen): build | status")
    s.add_argument("action", choices=["build", "status"], help="build | status")
    s = add("records", cmd_records, "records via the worker: find, show, override, new, conflicts, validate")
    s.add_argument("action", choices=["find", "show", "override", "new", "conflicts", "validate"],
                   help="find | show <FormKey> | override <FormKey> | new | conflicts | validate")
    s.add_argument("formkey", nargs="?", help="show/override: FormKey such as 004822:Fallout4.esm")
    s.add_argument("--edid", help="find: EditorID text (substring unless --exact); new: the new EditorID")
    s.add_argument("--name", help="find: display name text")
    s.add_argument("--type", help="record signature, e.g. WEAP, ARMO, MISC, QUST, OMOD, COBJ")
    s.add_argument("--exact", action="store_true", help="find: EditorID must match exactly")
    s.add_argument("--index", action="store_true", help="find: use the local EditorID index (instant, no worker run)")
    s.add_argument("--limit", type=int, default=50, help="max results")
    s.add_argument("--plugin", help="find: only this plugin; conflicts: the plugin to check")
    s.add_argument("--plugins", help="restrict the load order to these comma-separated plugins (faster)")
    s.add_argument("--target", help="override/new/validate: plugin file to write or check (default: project build plugin)")
    s.add_argument("--light", action="store_true", help="new plugin: set the ESL flag")
    s.add_argument("--master", action="store_true", help="new plugin: set the ESM flag")
    s.add_argument("--project", help="project folder (default: current folder or a parent with f4forge.json)")
    s = add("loadorder", cmd_loadorder, "active load order: implicit masters, Creation Club, plugins.txt, missing masters")
    s.add_argument("--plugins-txt", help="plugins.txt to read (default: %%LOCALAPPDATA%%\\Fallout4\\plugins.txt)")
    s.add_argument("--full", action="store_true", help="list the whole order")
    s.add_argument("--limit", type=int, default=40, help="entries of the order shown without --full")
    s = add("tools", cmd_tools, "pinned tools: status, sync (dry run until --approve), pin (maintainer)")
    s.add_argument("action", choices=["status", "sync", "pin"], help="status | sync | pin")
    s.add_argument("--only", action="append", help="limit to one tool id (repeatable)")
    s.add_argument("--approve", action="store_true", help="really download and install (sync) or write the lock (pin)")
    s.add_argument("--tools-root", help="tools folder (default: config tools_root)")
    s = add("config", cmd_config, "show or set the forge config (tools_root, workspace_root, game_root)")
    s.add_argument("--set", action="append", metavar="KEY=VALUE", help="set a key (repeatable)")
    s.add_argument("--unset", action="append", metavar="KEY", help="clear a key (repeatable)")
    return p


def _log(argv, code, seconds):
    try:
        from .home import home_dir
        d = home_dir() / "logs"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "f4forge.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "v": __version__, "argv": argv,
                                "exit": code, "s": seconds}) + "\n")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    t = time.time()
    pretty = "--pretty" in argv
    try:
        args = parser().parse_args(argv)
        pretty = bool(getattr(args, "pretty", False))
        result, code = args.fn(args)
        emit(result, pretty)
    except ForgeError as e:
        emit({"error": str(e), "fix": e.fix}, pretty)
        code = e.code
    except KeyboardInterrupt:
        code = 130
    except Exception as e:  # a forge bug: still JSON, with the trace tail for the report
        emit({"error": f"internal error: {e}", "trace": traceback.format_exc().splitlines()[-6:],
              "fix": "report this with the command you ran"}, pretty)
        code = 3
    _log(argv, code, round(time.time() - t, 2))
    return code
