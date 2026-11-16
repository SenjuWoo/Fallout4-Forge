"""Creation Kit tier: info, wrapped command-line runs (precombines, previs, facegen) and CKPE deployment.

Switches come from CreationKit.exe's own usage strings (fact creation_kit.switches), e.g.
  -GeneratePreCombined:<ESMFilename> [clean,filtered] [all,main,ints,other] [currentset] [totalsetcount]
  -GeneratePreVisData:<ESMFilename> [clean,filtered] [all,main,ints,other] ...
  -ExportFaceGenData:<ESMFilename> <XB1|X64|PS4|W32>
Every command here is a dry run unless --approve; an approved run snapshots Data first and lists every file
the Creation Kit wrote, in a receipt under the forge home. These are, with deploy, the only writers into the game.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from .home import home_dir
from .util import ForgeError, ci_child, ci_path, run, save_json, sha256_file

PRECOMBINE_FOLLOWUPS = ["-CompressPSG:{plugin}", "-BuildCDX:{plugin}"]


def info(game_root: Path) -> dict:
    from .game import creation_kit
    ck = creation_kit(game_root)
    from .tools import tool_path
    staged = tool_path("ckpe")
    ck_ver = ck["version"]
    supports = None
    if staged and (staged / "CKPE.Fallout4.dll").is_file() and ck_ver:
        supports = ck_ver.encode() in (staged / "CKPE.Fallout4.dll").read_bytes()
    deployed = bool(ci_child(game_root, "CKPE.dll") and ci_child(game_root, "ckpe_loader.exe"))
    return {"creation_kit": ck_ver, "tier": ck["tier"], "tools": {k: v["found"] for k, v in ck["tools"].items()},
            "ckpe": {"staged": str(staged) if staged else None, "deployed": deployed,
                     "supports_this_ck": supports,
                     "how_checked": "CKPE.Fallout4.dll names the Creation Kit versions it patches (fact creation_kit.ckpe)"},
            "switches": ["-GeneratePreCombined", "-GeneratePreVisData", "-CompressPSG", "-BuildCDX", "-ExportFaceGenData"],
            "fact": "creation_kit.switches"}


def _ck(game_root: Path) -> Path:
    exe = ci_child(game_root, "CreationKit.exe")
    if not exe:
        raise ForgeError("CreationKit.exe not found (Creation Kit tier gap)", "install the Creation Kit (Steam app 1946160)")
    return exe


def plan(kind: str, game_root: Path, plugin: str, mode: str = "clean", scope: str = "all", platform: str = "X64") -> list[list[str]]:
    exe = str(_ck(game_root))
    if not ci_path(game_root, "Data/" + plugin):
        raise ForgeError(f"{plugin} is not in the game's Data", "deploy the plugin first (f4forge deploy --approve)")
    if kind == "precombine":
        cmds = [[exe, f"-GeneratePreCombined:{plugin}", mode, scope]]
        cmds += [[exe, f.format(plugin=plugin)] for f in PRECOMBINE_FOLLOWUPS]
        return cmds
    if kind == "previs":
        return [[exe, f"-GeneratePreVisData:{plugin}", mode, scope]]
    if kind == "facegen":
        return [[exe, f"-ExportFaceGenData:{plugin}", platform]]
    raise ForgeError(f"unknown Creation Kit job {kind}", "precombine | previs | facegen")


def _snapshot(data: Path) -> dict[str, tuple[int, float]]:
    out = {}
    for dirpath, _, files in os.walk(data):
        for f in files:
            p = Path(dirpath) / f
            try:
                st = p.stat()
                out[str(p.relative_to(data))] = (st.st_size, st.st_mtime)
            except OSError:
                pass
    return out


def run_job(kind: str, game_root: Path, plugin: str, approve: bool, mode: str = "clean", scope: str = "all",
            platform: str = "X64", timeout: int = 6 * 3600) -> dict:
    cmds = plan(kind, game_root, plugin, mode, scope, platform)
    out = {"job": kind, "plugin": plugin, "argv": cmds, "cwd": str(game_root), "dry_run": not approve,
           "writes_into": "the game's Data folder", "fact": "creation_kit.switches"}
    if not approve:
        out["hint"] = "review the argv, back up the plugin, then rerun with --approve (long-running; the CK may show a window)"
        return out
    data = ci_child(game_root, "Data")
    before = _snapshot(data)
    runs = []
    for argv in cmds:
        t = time.time()
        r = run(argv, timeout=timeout, cwd=game_root)
        runs.append({"argv": argv, "exit": r.get("exit"), "seconds": round(time.time() - t), "error": r.get("error")})
        if r.get("exit") not in (0, None) or r.get("error"):
            break
    after = _snapshot(data)
    written = sorted(k for k, v in after.items() if before.get(k) != v)
    receipt = {"job": kind, "plugin": plugin, "runs": runs, "written": written,
               "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
    rp = home_dir() / "ck-runs" / f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}.json"
    save_json(rp, receipt)
    out.update(runs=runs, written=written, receipt=str(rp))
    return out


# --- CKPE deployment ------------------------------------------------------------------------------------

def _receipt_path() -> Path:
    return home_dir() / "ckpe-receipt.json"


def ckpe_install(game_root: Path, approve: bool) -> dict:
    from .tools import tool_path
    staged = tool_path("ckpe")
    if not staged:
        raise ForgeError("CKPE is not staged", "f4forge tools sync --only ckpe --approve")
    inf = info(game_root)
    if inf["ckpe"]["supports_this_ck"] is False:
        raise ForgeError(f"the staged CKPE does not name Creation Kit {inf['creation_kit']}",
                         "update the ckpe pin, or keep the Creation Kit unpatched")
    files = [p for p in staged.rglob("*") if p.is_file()]
    plan_rows = []
    for p in files:
        rel = p.relative_to(staged)
        dest = game_root / rel
        plan_rows.append({"file": rel.as_posix(), "exists": dest.exists()})
    out = {"source": str(staged), "target": str(game_root), "files": plan_rows, "dry_run": not approve,
           "supports_this_ck": inf["ckpe"]["supports_this_ck"]}
    if not approve:
        out["hint"] = "rerun with --approve; existing files are backed up and f4forge ck ckpe-uninstall --approve restores them"
        return out
    backup = home_dir() / "ckpe-backup" / time.strftime("%Y%m%d-%H%M%S")
    rec = {"installed": [], "backups": {}, "backup_dir": str(backup), "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
    for p in files:
        rel = p.relative_to(staged)
        dest = game_root / rel
        if dest.exists():
            b = backup / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, b)
            rec["backups"][rel.as_posix()] = str(b)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        rec["installed"].append({"file": rel.as_posix(), "sha256": sha256_file(dest)})
    save_json(_receipt_path(), rec)
    out.update(installed=len(rec["installed"]), backed_up=len(rec["backups"]), receipt=str(_receipt_path()))
    return out


def ckpe_uninstall(game_root: Path, approve: bool) -> dict:
    rp = _receipt_path()
    if not rp.is_file():
        raise ForgeError("no CKPE receipt: the forge did not install CKPE", "nothing to undo")
    rec = json.loads(rp.read_text(encoding="utf-8"))
    out = {"remove": [r["file"] for r in rec["installed"]], "restore": list(rec["backups"]), "dry_run": not approve}
    if not approve:
        return out
    skipped = []
    for r in rec["installed"]:
        dest = game_root / r["file"]
        if dest.is_file() and sha256_file(dest) != r["sha256"]:
            skipped.append(r["file"])  # changed since install: not ours any more
            continue
        if r["file"] in rec["backups"]:
            shutil.copy2(rec["backups"][r["file"]], dest)
        elif dest.is_file():
            dest.unlink()
    rp.unlink()
    out.update(done=True, skipped_changed=skipped)
    return out
