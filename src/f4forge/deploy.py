"""Deploy a project's data/ into the game's Data (or a mod-manager mod folder with --to) for testing.

Dry run unless --approve. Writes a receipt under the forge home; backs up any file it replaces; refuses to
overwrite a file its receipt does not own unless --force (which backs it up first). Files are replaced by
rename, so a file a mod manager hard-linked from its staging folder is never changed in staging.
plugins.txt is untouched unless --enable-plugin (backed up first). undeploy removes what deploy wrote and
restores the backups.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from .home import home_dir
from .util import ForgeError, ci_child, save_json, sha256_file


def _receipt_path(mid: str, target: Path) -> Path:
    tag = "data" if target.name.lower() == "data" else "to-" + "".join(c for c in target.name if c.isalnum())[:30]
    return home_dir() / "deploy" / f"{mid}-{tag}.json"


def _target(game_root: Path | None, to: str | None) -> Path:
    if to:
        return Path(to)
    if not game_root:
        raise ForgeError("no game folder to deploy into", "pass --game or --to <mod folder>")
    d = ci_child(game_root, "Data")
    if not d:
        raise ForgeError(f"no Data folder in {game_root}", "check the game folder")
    return d


def deploy(root: Path, game_root: Path | None, approve: bool = False, force: bool = False, to: str | None = None,
           enable_plugin: bool = False) -> dict:
    from .package import payload_files
    from .project import load_manifest
    m = load_manifest(root)
    target = _target(game_root, to)
    rp = _receipt_path(m["id"], target)
    old = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else {"files": {}}
    actions, refused = [], []
    for rel, src in payload_files(root):
        dst = target / rel
        owned = rel in old["files"]
        if dst.exists():
            if owned and sha256_file(dst) == old["files"][rel]["sha256"]:
                act = "update" if sha256_file(dst) != sha256_file(src) else "same"
            elif owned:
                act = "update-changed"  # ours, but changed since: back it up again
            elif force:
                act = "overwrite-backup"
            else:
                refused.append(rel)
                continue
        else:
            act = "create"
        actions.append({"file": rel, "action": act})
    out = {"project": m["id"], "target": str(target), "dry_run": not approve, "actions": actions, "refused": refused,
           "refused_reason": "exists and this project did not deploy it (use --force to back it up and replace)" if refused else None}
    if enable_plugin and m.get("plugin"):
        out["enable_plugin"] = m["plugin"]["name"]
    if not approve:
        out["hint"] = "rerun with --approve to copy (a mod manager's next deployment may revert direct Data changes)"
        return out
    if refused and not force:
        raise ForgeError(f"{len(refused)} file(s) exist that this project did not deploy", "review them, or pass --force")
    backup = home_dir() / "deploy" / "backups" / m["id"] / time.strftime("%Y%m%d-%H%M%S")
    rec = {"project": m["id"], "target": str(target), "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": dict(old["files"])}
    for a in actions:
        rel = a["file"]
        src = root / "data" / rel
        dst = target / rel
        if a["action"] == "same":
            continue
        if dst.exists() and a["action"] in ("overwrite-backup", "update-changed"):
            b = backup / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, b)
            rec["files"].setdefault(rel, {})["backup"] = str(b)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".f4forge-tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)  # rename: never writes through a hard link
        rec["files"][rel] = {**rec["files"].get(rel, {}), "sha256": sha256_file(dst)}
    save_json(rp, rec)
    out["receipt"] = str(rp)
    if enable_plugin and m.get("plugin"):
        out["plugins_txt"] = _enable_plugin(m["plugin"]["name"])
    return out


def _enable_plugin(name: str) -> dict:
    from .game import my_games
    p = my_games().get("plugins_txt")
    if not p:
        raise ForgeError("plugins.txt not found", "enable the plugin in your mod manager")
    p = Path(p)
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if any(ln.strip().lstrip("*").lower() == name.lower() and ln.strip().startswith("*") for ln in lines):
        return {"file": str(p), "changed": False}
    b = home_dir() / "deploy" / "backups" / f"plugins.txt.{time.strftime('%Y%m%d-%H%M%S')}"
    b.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, b)
    lines = [ln for ln in lines if ln.strip().lstrip("*").lower() != name.lower()] + ["*" + name]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"file": str(p), "changed": True, "backup": str(b)}


def undeploy(root: Path, game_root: Path | None, approve: bool = False, to: str | None = None) -> dict:
    from .project import load_manifest
    m = load_manifest(root)
    target = _target(game_root, to)
    rp = _receipt_path(m["id"], target)
    if not rp.is_file():
        raise ForgeError("nothing deployed by this project here (no receipt)", "nothing to undo")
    rec = json.loads(rp.read_text(encoding="utf-8"))
    plan, skipped = [], []
    for rel, info in rec["files"].items():
        dst = target / rel
        if dst.is_file() and info.get("sha256") and sha256_file(dst) != info["sha256"]:
            skipped.append(rel)  # changed after deploy: leave it
            continue
        plan.append({"file": rel, "action": "restore" if info.get("backup") else "remove"})
    out = {"project": m["id"], "target": str(target), "dry_run": not approve, "actions": plan, "skipped_changed": skipped}
    if not approve:
        return out
    for a in plan:
        dst = target / a["file"]
        info = rec["files"][a["file"]]
        if a["action"] == "restore":
            shutil.copy2(info["backup"], dst)
        elif dst.is_file():
            dst.unlink()
    rp.unlink()
    out["done"] = True
    return out
