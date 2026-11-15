"""Records through the .NET worker (workers/F4Forge.Records, Mutagen.Bethesda.Fallout4 pinned in its lock file).

`f4forge worker build` publishes it under the forge home. Every `records` command sends one JSON request
and gets one JSON result. Without the worker the commands return a named `degraded` result.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .home import home_dir
from .util import ForgeError, run, save_json, sha256_file

WORKER = "F4Forge.Records"


def source_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "workers" / WORKER


def worker_dir() -> Path:
    return home_dir() / "worker" / WORKER


def worker_exe() -> Path:
    import os
    if os.environ.get("F4FORGE_WORKER_EXE"):
        return Path(os.environ["F4FORGE_WORKER_EXE"])
    return worker_dir() / (WORKER + (".exe" if sys.platform == "win32" else ""))


def source_hash() -> str:
    import hashlib
    h = hashlib.sha256()
    src = source_dir()
    for p in sorted(src.glob("*")):
        if p.is_file() and p.suffix in (".cs", ".csproj", ".json"):
            h.update(p.name.encode() + sha256_file(p).encode())
    return h.hexdigest()


def status() -> dict:
    exe = worker_exe()
    rec = worker_dir() / "worker.receipt.json"
    built = exe.is_file()
    stale = None
    if built and rec.is_file() and source_dir().is_dir():
        try:
            stale = json.loads(rec.read_text(encoding="utf-8")).get("source_sha256") != source_hash()
        except (OSError, ValueError):
            stale = None
    return {"built": built, "path": str(exe), "stale": stale, "dotnet": bool(shutil.which("dotnet"))}


def build() -> dict:
    if not shutil.which("dotnet"):
        raise ForgeError("the .NET SDK is not on PATH", "install the .NET 9 SDK or newer, then: f4forge worker build")
    src = source_dir()
    if not (src / f"{WORKER}.csproj").is_file():
        raise ForgeError(f"worker source missing: {src}", "update the forge checkout")
    out = worker_dir()
    r = run(["dotnet", "publish", str(src / f"{WORKER}.csproj"), "-c", "Release", "-o", str(out), "--nologo",
             "-p:RestoreLockedMode=true"], timeout=1800)
    if not r["ok"] or not worker_exe().is_file():
        tail = ((r.get("stdout") or "") + (r.get("stderr") or "") + (r.get("error") or ""))[-1200:]
        raise ForgeError("worker build failed: " + tail, "read the build output; the lock file pins every package")
    save_json(out / "worker.receipt.json", {"source_sha256": source_hash(), "exe": str(worker_exe())})
    ver = call({"verb": "version"})
    return {"built": True, "path": str(worker_exe()), "worker": ver.get("worker"), "mutagen": ver.get("mutagen")}


def call(req: dict, timeout: int = 3600) -> dict:
    exe = worker_exe()
    if not exe.is_file():
        raise ForgeError("records worker not built (degraded)", "f4forge worker build")
    r = run([str(exe), "-"], timeout=timeout, input_text=json.dumps(req))
    text = (r.get("stdout") or "").strip()
    if not text:
        raise ForgeError(f"records worker gave no output: {(r.get('stderr') or r.get('error') or '')[-400:]}",
                         "rebuild it: f4forge worker build")
    try:
        out = json.loads(text.splitlines()[-1])
    except ValueError:
        raise ForgeError("records worker output is not JSON: " + text[-300:], "rebuild it: f4forge worker build")
    if r.get("exit") == 2:
        raise ForgeError(out.get("error", "worker failure"), out.get("fix", ""))
    if r.get("exit") == 3:
        raise ForgeError(out.get("error", "worker exception"), "report this with the request: " + json.dumps(req)[:200], code=3)
    return out


def load_order_names(game_root: Path, only: list[str] | None = None) -> list[str]:
    from .loadorder import load_order
    names = [o["plugin"] for o in load_order(game_root)["order"]]
    if only:
        want = {o.lower() for o in only}
        names = [n for n in names if n.lower() in want]
        missing = want - {n.lower() for n in names}
        if missing:
            raise ForgeError(f"not in the active load order: {', '.join(sorted(missing))}", "check f4forge loadorder")
    return names


def base_request(game_root: Path, plugins: list[str] | None, extra: list[str] | None = None) -> dict:
    from .util import ci_child
    lo = load_order_names(game_root, plugins)
    for e in extra or []:
        if e not in lo:
            lo.append(e)
    return {"data_folder": str(ci_child(game_root, "Data")), "load_order": lo}
