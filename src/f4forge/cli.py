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
