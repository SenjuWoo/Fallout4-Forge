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
