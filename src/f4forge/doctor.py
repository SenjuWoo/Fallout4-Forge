"""Health check in separate sections: toolchain, game, payload, tools, worker.

Each section is ok / degraded / fail with a named fix. Exit 0 when every required section
(toolchain, game, payload) is ok or degraded; 2 when one fails. A missing optional capability
(Creation Kit, a tool, the records worker) is `degraded`, never a failure.
"""
from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path

from . import __version__
from .home import CONFIG_KEYS, home_dir, load_config
from .util import ForgeError

REQUIRED = ("toolchain", "game", "payload")
SECTIONS = ("toolchain", "game", "payload", "tools", "worker")


def _section(status: str, problems: list[dict] | None = None, **info) -> dict:
    return {"status": status, **info, "problems": problems or []}


def toolchain() -> dict:
    problems = []
    py_ok = sys.version_info >= (3, 10)
    if not py_ok:
        problems.append({"problem": "Python 3.10+ required", "fix": "install Python 3.10 or newer, then rerun Install.ps1"})
    try:
        import yaml  # noqa: F401
        yaml_ok = True
    except ImportError:
        yaml_ok = False
        problems.append({"problem": "PyYAML missing", "fix": "pip install -e . in the forge checkout (or rerun Install.ps1)"})
    venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    return _section("ok" if py_ok and yaml_ok else "fail", problems, python=platform.python_version(),
                    executable=sys.executable, venv=venv, pyyaml=yaml_ok, platform=sys.platform,
                    git=bool(shutil.which("git")))


def game(explicit: str | None) -> dict:
    from . import game as G
    try:
        root, source = G.find_game(explicit)
    except ForgeError as e:
        return _section("fail", [{"problem": str(e), "fix": e.fix}])
    problems = []
    rt = G.runtime(root)
    if not rt["version"]:
        return _section("fail", [{"problem": "Fallout4.exe has no readable version resource",
                                  "fix": "verify the game files in Steam"}], root=str(root), found_by=source)
    f4 = G.f4se(root, rt["version"])
    al = G.address_library(root, rt["version"])
    ck = G.creation_kit(root)
    if not f4["installed"]:
        problems.append({"problem": "F4SE not installed (f4se-native and F4SE-dependent routes unavailable)",
                         "fix": "install F4SE for runtime " + rt["version"]})
    elif not f4["matches_runtime"]:
        problems.append({"problem": f"F4SE has no {f4['runtime_dll']} for runtime {rt['version']}",
                         "fix": "install the F4SE build for this runtime"})
    if not al["for_runtime"]:
        problems.append({"problem": f"Address Library bin missing: {al['expected']}",
                         "fix": "install Address Library for F4SE Plugins for this runtime"})
    if ck["tier"] != "creation-kit":
        problems.append({"problem": "Creation Kit tier unavailable: " + (", ".join(ck["missing_for_tier"]) or "not installed"),
                         "fix": "install the Creation Kit (Steam app 1946160); the forge falls back to Caprica, "
                                "Champollion and its own archive code"})
    if ck["version"] and rt["version"] and ck["version"] != rt["version"]:
        ck_note = f"Creation Kit {ck['version']} and runtime {rt['version']} differ; plugins it saves are checked against the runtime"
    else:
        ck_note = None
    return _section("ok" if not problems else "degraded", problems, root=str(root), found_by=source,
                    runtime=rt["version"], generation=rt["generation"]["id"], f4se=f4["version"],
                    f4se_matches_runtime=f4["matches_runtime"], address_library=al["for_runtime"],
                    creation_kit=ck["version"], creation_kit_tier=ck["tier"], note=ck_note)


def payload() -> dict:
    from .knowledge import DATA_FILES, payload_problems, topics
    bad = payload_problems()
    t = topics()
    return _section("ok" if not bad else "fail",
                    [{"problem": b, "fix": "reinstall or git checkout the forge"} for b in bad],
                    data_files=list(DATA_FILES), topics=len(t), topics_written=sum(1 for x in t if x["available"]))


def tools(game_root: Path | None = None) -> dict:
    from . import tools as T
    try:
        st = T.status(game_root=game_root)
    except ForgeError as e:
        return _section("degraded", [{"problem": str(e), "fix": e.fix}])
    problems = []
    if not st["tools_root"]:
        problems.append({"problem": "no tools folder configured", "fix": "f4forge config --set tools_root=<folder>"})
    for r in st["tools"]:
        if not r["optional"] and r["status"] not in ("ok", "pinned"):
            problems.append({"problem": f"{r['id']}: {r['status']}", "fix": r.get("fix") or "f4forge tools sync --approve"})
    optional_missing = [r["id"] for r in st["tools"] if r["optional"] and r["status"] not in ("ok", "pinned")]
    return _section("ok" if not problems else "degraded", problems, tools_root=st["tools_root"],
                    counts=st["counts"], optional_missing=optional_missing)


def worker() -> dict:
    exe = home_dir() / "worker" / "F4Forge.Records" / ("F4Forge.Records.exe" if sys.platform == "win32" else "F4Forge.Records")
    dotnet = shutil.which("dotnet")
    if exe.is_file():
        return _section("ok", path=str(exe), dotnet=bool(dotnet))
    fix = "f4forge worker build" if dotnet else "install the .NET SDK, then: f4forge worker build"
    return _section("degraded", [{"problem": "records worker not built (records find/show/override/new unavailable)",
                                  "fix": fix}], path=str(exe), dotnet=bool(dotnet))


def run(explicit_game: str | None = None) -> tuple[dict, int]:
    cfg = load_config()
    home = {"path": str(home_dir()), "config": {k: cfg.get(k) for k in CONFIG_KEYS}}
    ws = cfg.get("workspace_root")
    home["workspace_root"] = {"path": ws, "exists": bool(ws and Path(ws).is_dir()),
                              "workspace_md": bool(ws and (Path(ws) / "WORKSPACE.md").is_file())}
    report = {"forge": {"name": "Fallout 4 Forge", "version": __version__}, "home": home}
    report["toolchain"] = toolchain()
    report["game"] = game(explicit_game)
    report["payload"] = payload()
    game_root = Path(report["game"]["root"]) if report["game"].get("root") else None
    report["tools"] = tools(game_root)
    report["worker"] = worker()
    failed = [s for s in REQUIRED if report[s]["status"] == "fail"]
    report["summary"] = {s: report[s]["status"] for s in SECTIONS}
    report["ok"] = not failed
    report["failed_required"] = failed
    return report, (0 if not failed else 2)
