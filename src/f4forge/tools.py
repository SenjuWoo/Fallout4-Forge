"""Pinned tools in one tools folder, driven by tools.lock.json (ported from the MarvelRivals Forge lock).

Kinds:
  github_release  download release asset(s), verify SHA-256 BEFORE extraction, extract into
                  <tools_root>/<folder>, verify the main executable's SHA-256
  git_clone       clone at a pinned commit (submodules recursive), verify HEAD
  nuget           a package pinned in a project lock file (restored by its build, never here)
  path            a program found on PATH (or a known install path) and probed
  vswhere         MSVC found through vswhere
  installed       a program at a known location (game-relative for the Creation Kit tools)
  manual          not downloadable by script (Nexus only); detected when present

Rules: the receipt (tools.receipt.json at the tools root) names every folder the forge owns;
a folder it does not own is never touched. Downloads go to a cache under the forge home and
resume when a partial file exists. GH_TOKEN is honoured for GitHub requests and never printed.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from . import pe
from .home import config_value, home_dir
from .util import PKG_DIR, ForgeError, load_json, run, save_json, sha256_file

LOCK_NAME = "tools.lock.json"
RECEIPT_NAME = "tools.receipt.json"
KINDS = ("github_release", "git_clone", "nuget", "path", "vswhere", "installed", "manual")
USER_AGENT = "f4forge"


def forge_root() -> Path:
    return PKG_DIR.parents[1]


def load_lock(path: Path | None = None) -> dict:
    p = Path(path) if path else forge_root() / LOCK_NAME
    if not p.is_file():
        raise ForgeError(f"{LOCK_NAME} not found at {p}", "update the forge checkout")
    return load_json(p)


def tools_root(explicit: str | None = None) -> Path:
    v = explicit or os.environ.get("F4FORGE_TOOLS_ROOT") or config_value("tools_root")
    if not v:
        raise ForgeError("no tools folder configured", "run: f4forge config --set tools_root=<folder>")
    return Path(v)


def entry(lock: dict, tid: str) -> dict:
    for t in lock["tools"]:
        if t["id"] == tid:
            return t
    raise ForgeError(f"{tid} is not in {LOCK_NAME}", "list ids with: f4forge tools status")


def assets_of(t: dict) -> list[dict]:
    if t.get("assets"):
        return t["assets"]
    if t.get("asset"):
        return [{"name": t["asset"], "sha256": t.get("asset_sha256", ""), "url": t.get("url")}]
    return []


def asset_url(t: dict, a: dict) -> str:
    return a.get("url") or f"https://github.com/{t['repo']}/releases/download/{t['tag']}/{a['name']}"


# --- receipt ------------------------------------------------------------------------

def receipt(root: Path) -> dict:
    p = root / RECEIPT_NAME
    if p.is_file():
        try:
            data = load_json(p)
            if isinstance(data, dict) and isinstance(data.get("tools"), dict):
                return data
        except (OSError, ValueError):
            pass
    return {"schema": 1, "owner": "fallout4-forge", "tools": {}}


def owned_folders(rec: dict) -> dict[str, str]:
    return {v["folder"].lower(): k for k, v in rec["tools"].items() if v.get("folder")}


# --- network -------------------------------------------------------------------------

def _request(url: str, headers: dict | None = None) -> urllib.request.Request:
    h = {"User-Agent": USER_AGENT}
    if url.startswith("https://api.github.com/") and os.environ.get("GH_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
    h.update(headers or {})
    return urllib.request.Request(url, headers=h)


def download(url: str, dest: Path, timeout: int = 600) -> int:
    """Download to dest, resuming from dest.part. Returns bytes fetched this call."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.is_file() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    try:
        with urllib.request.urlopen(_request(url, headers), timeout=timeout) as r:
            mode = "ab" if have and getattr(r, "status", 200) == 206 else "wb"
            got = 0
            with open(part, mode) as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have:  # already complete
            got = 0
        else:
            raise ForgeError(f"download failed ({e.code}): {url}", "check the URL in tools.lock.json, or retry")
    except (urllib.error.URLError, OSError) as e:
        raise ForgeError(f"download failed: {url}: {e}", "check the network and retry; the partial file is kept")
    os.replace(part, dest)
    return got


def github_release_info(repo: str, tag: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    with urllib.request.urlopen(_request(url, {"Accept": "application/vnd.github+json"}), timeout=60) as r:
        return json.loads(r.read())


# --- archives -------------------------------------------------------------------------

def seven_zip() -> str | None:
    """A 7-Zip-compatible extractor by capability probe: PATH names first, then the usual install folders."""
    cands = [shutil.which(n) for n in ("7z", "7za", "7zz")]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        if os.environ.get(env):
            cands.append(str(Path(os.environ[env]) / "7-Zip" / "7z.exe"))
    for c in cands:
        if c and Path(c).is_file():
            r = run([c], timeout=30)
            text = (r.get("stdout") or "") + (r.get("stderr") or "")
            # Capability, not brand: 7-Zip and compatible forks (NanaZip) print the same command list.
            if "<Commands>" in text and "x : eXtract" in text:
                return c
    return None


def bsdtar() -> str | None:
    """libarchive's tar (shipped with Windows 10+) reads 7z; GNU tar on PATH does not, so probe for libarchive."""
    cands = []
    if os.environ.get("SystemRoot"):
        cands.append(str(Path(os.environ["SystemRoot"]) / "System32" / "tar.exe"))
    cands += [shutil.which("bsdtar")]
    for c in cands:
        if c and Path(c).is_file():
            r = run([c, "--version"], timeout=30)
            if "libarchive" in (r.get("stdout") or ""):
                return c
    return None


def extract_7z(archive: Path, dest: Path) -> str:
    """Extract a .7z with the first working extractor. Returns which one was used."""
    tried = []
    tar = bsdtar()
    if tar:
        r = run([tar, "-xf", str(archive), "-C", str(dest)], timeout=1800)
        if r["ok"]:
            return "bsdtar"
        tried.append("bsdtar: " + (r.get("stderr") or r.get("error") or "")[-200:])
    exe = seven_zip()
    if exe:
        # A packaged (WindowsApps) 7-Zip fork sees a virtualised AppData; stage in the system temp folder.
        stage = Path(tempfile.mkdtemp(prefix="f4f-7z-"))
        try:
            shutil.copy2(archive, stage / archive.name)
            out = stage / "out"
            r = run([exe, "x", "-y", f"-o{out}", str(stage / archive.name)], timeout=1800)
            if r["ok"] and out.is_dir():
                for p in out.iterdir():
                    shutil.move(str(p), str(dest / p.name))
                return "7z"
            tried.append("7z: " + (r.get("stderr") or r.get("error") or "")[-200:])
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    raise ForgeError(f"no working 7z extractor for {archive.name}" + (f" ({'; '.join(tried)})" if tried else ""),
                     "Windows' tar.exe (libarchive) or 7-Zip is needed for .7z assets")


def _inside(base: Path, target: Path) -> bool:
    base, target = base.resolve(), target.resolve()
    return target == base or base in target.parents


def extract(archive: Path, dest: Path) -> None:
    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for m in zf.infolist():
                if not _inside(dest, dest / m.filename):
                    raise ForgeError(f"archive entry escapes the target folder: {m.filename}", "do not use this asset")
            zf.extractall(dest)
        return
    if name.endswith(".7z"):
        extract_7z(archive, dest)
        for p in dest.rglob("*"):
            if not _inside(dest, p):
                raise ForgeError(f"archive entry escapes the target folder: {p}", "do not use this asset")
        return
    raise ForgeError(f"unsupported archive type: {archive.name}", "use zip or 7z assets, or mark extract: false")


def _flatten(dest: Path, exe_rel: str | None) -> None:
    """Release archives often wrap everything in one folder; lift it so exe sits at its lock path."""
    kids = list(dest.iterdir())
    if exe_rel and (dest / exe_rel).exists():
        return
    if len(kids) == 1 and kids[0].is_dir() and (not exe_rel or (kids[0] / exe_rel).exists()):
        inner = kids[0]
        for p in inner.iterdir():
            shutil.move(str(p), str(dest / p.name))
        inner.rmdir()


# --- status ----------------------------------------------------------------------------

def _probe(argv: list[str], expect: str | None, cwd: Path | None = None) -> dict:
    r = run(argv, timeout=60, cwd=cwd)
    text = ((r.get("stdout") or "") + (r.get("stderr") or "")).strip()
    if r.get("error"):
        return {"ok": False, "output": r["error"]}
    line = next((ln for ln in text.splitlines() if expect and expect in ln), text.splitlines()[0] if text else "")
    return {"ok": (expect in text) if expect else True, "output": line.strip()[:200]}


def _vswhere() -> dict:
    base = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles")
    vsw = Path(base) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe" if base else None
    if not vsw or not vsw.is_file():
        return {"found": False}
    r = run([str(vsw), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
             "-property", "installationPath"], timeout=60)
    path = (r.get("stdout") or "").strip().splitlines()
    if not path:
        return {"found": False, "vswhere": str(vsw)}
    r2 = run([str(vsw), "-latest", "-products", "*", "-property", "catalog_productDisplayVersion"], timeout=60)
    return {"found": True, "path": path[0], "version": (r2.get("stdout") or "").strip(), "vswhere": str(vsw)}


def status_one(t: dict, root: Path | None, rec: dict, game_root: Path | None = None) -> dict:
    kind = t["kind"]
    row = {"id": t["id"], "kind": kind, "role": t.get("role", ""), "optional": bool(t.get("optional")),
           "routes": t.get("routes", [])}
    if kind in ("github_release", "git_clone"):
        if root is None:
            return {**row, "status": "missing", "detail": "no tools folder configured"}
        folder = root / t["folder"]
        row["path"] = str(folder)
        owner = owned_folders(rec).get(t["folder"].lower())
        if not folder.exists():
            return {**row, "status": "missing", "fix": f"f4forge tools sync --only {t['id']} --approve"}
        if owner != t["id"]:
            return {**row, "status": "unowned", "detail": "folder exists but the receipt does not own it; never touched",
                    "fix": "move the folder away, or keep it and use it outside the forge"}
        if kind == "git_clone":
            head = run(["git", "-C", str(folder), "rev-parse", "HEAD"], timeout=60)
            got = (head.get("stdout") or "").strip()
            if got != t.get("commit"):
                return {**row, "status": "mismatch", "detail": f"HEAD {got[:12]} != pinned {t.get('commit', '')[:12]}",
                        "fix": f"f4forge tools sync --only {t['id']} --approve"}
            return {**row, "status": "ok", "commit": got}
        exe = folder / t["exe"] if t.get("exe") else None
        if exe is not None:
            if not exe.is_file():
                return {**row, "status": "mismatch", "detail": f"{t['exe']} missing",
                        "fix": f"f4forge tools sync --only {t['id']} --approve"}
            if t.get("exe_sha256") and sha256_file(exe) != t["exe_sha256"]:
                return {**row, "status": "mismatch", "detail": f"{t['exe']} hash differs from the pin",
                        "fix": f"f4forge tools sync --only {t['id']} --approve"}
            row["exe"] = str(exe)
        return {**row, "status": "ok", "tag": t.get("tag")}
    if kind == "nuget":
        return {**row, "status": "pinned", "package": t.get("package"), "version": t.get("version"),
                "detail": "restored by its project's build from the committed lock file"}
    if kind == "path":
        exe = None
        for n in t.get("names", [t.get("exe")]):
            exe = shutil.which(n) if n else None
            if exe:
                break
        if not exe:
            for c in t.get("known_paths", []):
                c = os.path.expandvars(c)
                if Path(c).is_file():
                    exe = c
                    break
        if not exe:
            return {**row, "status": "missing", "fix": t.get("fix", f"install {t['id']} or put it on PATH")}
        pr = _probe([exe] + t.get("probe", []), t.get("probe_expect")) if t.get("probe") is not None else {"ok": True, "output": ""}
        return {**row, "status": "ok" if pr["ok"] else "mismatch", "exe": exe, "probe": pr["output"]}
    if kind == "vswhere":
        vs = _vswhere()
        if not vs["found"]:
            return {**row, "status": "missing", "fix": t.get("fix", "install Visual Studio Build Tools with the C++ workload")}
        return {**row, "status": "ok", "path": vs["path"], "version": vs.get("version")}
    if kind == "installed":
        loc = t["location"]
        p = None
        if loc.startswith("game:") and game_root:
            from .util import ci_path
            p = ci_path(game_root, loc[5:])
        elif not loc.startswith("game:"):
            p = Path(os.path.expandvars(loc))
            p = p if p.exists() else None
        if not p:
            return {**row, "status": "missing", "fix": t.get("fix", "install it; the forge references it in place")}
        return {**row, "status": "ok", "path": str(p), "version": pe.file_version(p) if p.is_file() else None}
    if kind == "manual":
        found = None
        if root is not None and root.is_dir():
            for name in t.get("detect", []):
                hits = sorted(root.glob(name))
                if hits:
                    found = str(hits[0])
                    break
        return {**row, "status": "ok" if found else "manual", "path": found,
                "page": t.get("page"), "detail": t.get("note", "download by hand from the page")}
    return {**row, "status": "unknown-kind"}


def status(lock: dict | None = None, root: Path | None = None, game_root: Path | None = None) -> dict:
    lock = lock or load_lock()
    if root is None:
        try:
            root = tools_root()
        except ForgeError:
            root = None
    if game_root is None:
        try:
            from .game import find_game
            game_root = find_game()[0]
        except ForgeError:
            game_root = None
    rec = receipt(root) if root else {"tools": {}}
    rows = [status_one(t, root, rec, game_root) for t in lock["tools"]]
    good = ("ok", "pinned")
    required_bad = [r["id"] for r in rows if not r["optional"] and r["status"] not in good]
    return {"tools_root": str(root) if root else None, "lock_updated": lock.get("updated"), "tools": rows,
            "required_ok": not required_bad, "required_not_ok": required_bad,
            "counts": {s: sum(1 for r in rows if r["status"] == s) for s in sorted({r["status"] for r in rows})}}


def find_exe(tid: str, lock: dict | None = None) -> Path | None:
    """Path to a tool's main executable when it is installed and verified, else None."""
    lock = lock or load_lock()
    t = entry(lock, tid)
    try:
        root = tools_root()
    except ForgeError:
        root = None
    st = status_one(t, root, receipt(root) if root else {"tools": {}}, None)
    if st["status"] != "ok":
        return None
    if st.get("exe"):
        return Path(st["exe"])
    if st.get("path"):
        return Path(st["path"])
    return None


def tool_path(tid: str, lock: dict | None = None) -> Path | None:
    """The tool's folder (github_release / git_clone) when installed and owned."""
    lock = lock or load_lock()
    t = entry(lock, tid)
    try:
        root = tools_root()
    except ForgeError:
        return None
    st = status_one(t, root, receipt(root), None)
    return Path(st["path"]) if st["status"] == "ok" and st.get("path") else None


# --- sync -------------------------------------------------------------------------------

def _install_release(t: dict, root: Path, cache: Path) -> dict:
    fetched = 0
    tmp = Path(tempfile.mkdtemp(prefix="f4f-", dir=str(cache)))
    try:
        for a in assets_of(t):
            if not a.get("sha256"):
                raise ForgeError(f"{t['id']}: {a['name']} has no asset_sha256 in the lock", "pin it first: f4forge tools pin")
            cached = cache / t["id"] / a["name"]
            if not cached.is_file() or sha256_file(cached) != a["sha256"]:
                cached.unlink(missing_ok=True)
                fetched += download(asset_url(t, a), cached)
            got = sha256_file(cached)
            if got != a["sha256"]:
                cached.unlink(missing_ok=True)
                raise ForgeError(f"{t['id']}: {a['name']} SHA-256 {got[:16]}... != pinned {a['sha256'][:16]}... (not extracted)",
                                 "the upstream asset changed; review it, then update tools.lock.json")
            if a.get("extract", True) and a["name"].lower().endswith((".zip", ".7z")):
                extract(cached, tmp)
            else:
                shutil.copy2(cached, tmp / a["name"])
        if t.get("flatten", True):
            _flatten(tmp, t.get("exe"))
        if t.get("exe"):
            exe = tmp / t["exe"]
            if not exe.is_file():
                raise ForgeError(f"{t['id']}: {t['exe']} not in the extracted asset", "update tools.lock.json")
            if t.get("exe_sha256") and sha256_file(exe) != t["exe_sha256"]:
                raise ForgeError(f"{t['id']}: {t['exe']} hash differs from the pin", "review the release, then update the lock")
        for src, dst in (t.get("copy_as") or {}).items():
            shutil.copy2(tmp / src, tmp / dst)
        target = root / t["folder"]
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp), str(target))
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    return {"fetched_bytes": fetched}


def _install_clone(t: dict, root: Path) -> dict:
    target = root / t["folder"]
    url = t.get("url") or f"https://github.com/{t['repo']}.git"
    if not target.exists():
        r = run(["git", "clone", "--no-checkout", url, str(target)], timeout=1800)
        if not r["ok"]:
            raise ForgeError(f"{t['id']}: git clone failed: {(r.get('stderr') or r.get('error') or '')[-300:]}", "check the network")
    for argv in (["git", "-C", str(target), "fetch", "--depth", "1", "origin", t["commit"]],
                 ["git", "-C", str(target), "-c", "advice.detachedHead=false", "checkout", "--force", t["commit"]]):
        r = run(argv, timeout=1800)
        if not r["ok"] and argv[3] != "fetch":
            raise ForgeError(f"{t['id']}: {' '.join(argv[3:5])} failed: {(r.get('stderr') or '')[-300:]}", "check the pin")
    if t.get("submodules"):
        r = run(["git", "-C", str(target), "submodule", "update", "--init", "--recursive"], timeout=3600)
        if not r["ok"]:
            raise ForgeError(f"{t['id']}: submodule update failed: {(r.get('stderr') or '')[-300:]}", "retry")
    return {"fetched_bytes": None}


def sync(lock: dict | None = None, root: Path | None = None, only: list[str] | None = None,
         approve: bool = False) -> dict:
    lock = lock or load_lock()
    root = root or tools_root()
    cache = home_dir() / "downloads"
    rec = receipt(root)
    owned = owned_folders(rec)
    actions, errors, done = [], [], []
    for t in lock["tools"]:
        if only and t["id"] not in only:
            continue
        if t["kind"] not in ("github_release", "git_clone"):
            continue
        if t.get("platform") == "windows" and os.name != "nt":
            actions.append({"id": t["id"], "action": "skip", "reason": "windows-only"})
            continue
        st = status_one(t, root, rec, None)
        if st["status"] == "ok":
            actions.append({"id": t["id"], "action": "none", "reason": "installed and verified"})
            continue
        if st["status"] == "unowned" or (owned.get(t["folder"].lower()) not in (None, t["id"])):
            errors.append({"id": t["id"], "error": f"{t['folder']} exists and the receipt does not own it",
                           "fix": "move that folder away; the forge never touches folders it did not create"})
            continue
        actions.append({"id": t["id"], "action": "install", "kind": t["kind"], "folder": str(root / t["folder"])})
    if not approve:
        return {"dry_run": True, "tools_root": str(root), "actions": actions, "errors": errors,
                "hint": "rerun with --approve to download and install"}
    root.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    downloads = 0
    for a in actions:
        if a["action"] != "install":
            continue
        t = entry(lock, a["id"])
        try:
            info = _install_release(t, root, cache) if t["kind"] == "github_release" else _install_clone(t, root)
        except ForgeError as e:
            errors.append({"id": t["id"], "error": str(e), "fix": e.fix})
            continue
        if info.get("fetched_bytes"):
            downloads += 1
        rec["tools"][t["id"]] = {"folder": t["folder"], "kind": t["kind"], "tag": t.get("tag"), "commit": t.get("commit"),
                                 "assets": {x["name"]: x["sha256"] for x in assets_of(t)},
                                 "exe_sha256": t.get("exe_sha256"),
                                 "installed": _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
        save_json(root / RECEIPT_NAME, rec)
        done.append(t["id"])
    st = status(lock, root)
    write_tools_md(root, st)
    return {"dry_run": False, "tools_root": str(root), "installed": done, "downloads": downloads,
            "actions": actions, "errors": errors, "required_ok": st["required_ok"],
            "required_not_ok": st["required_not_ok"]}


def write_tools_md(root: Path, st: dict) -> Path:
    lines = ["# Tools", "", "Generated by `f4forge tools sync` from `tools.lock.json`. The forge owns only the",
             f"folders listed in `{RECEIPT_NAME}`; everything else here is left alone.", "",
             "| id | kind | status | role | optional |", "|---|---|---|---|---|"]
    for r in st["tools"]:
        lines.append(f"| {r['id']} | {r['kind']} | {r['status']} | {r['role']} | {'yes' if r['optional'] else ''} |")
    p = root / "TOOLS.md"
    root.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return p


# --- pin (maintainer helper for T09 and later version bumps) ------------------------------

def pin(tid: str, lock_path: Path | None = None, approve: bool = False) -> dict:
    """Download a release asset once, record its SHA-256 (cross-checked with GitHub's digest) and the
    main executable's SHA-256 into the lock. Without --approve only reports what it would record."""
    lock_path = Path(lock_path) if lock_path else forge_root() / LOCK_NAME
    lock = load_lock(lock_path)
    t = entry(lock, tid)
    if t["kind"] != "github_release":
        raise ForgeError(f"{tid} is a {t['kind']} entry; pin applies to github_release", "edit the lock by hand")
    digests = {}
    try:
        info = github_release_info(t["repo"], t["tag"])
        digests = {a["name"]: a.get("digest") for a in info.get("assets", [])}
    except (urllib.error.URLError, OSError, ValueError) as e:
        digests = {"_error": str(e)}
    cache = home_dir() / "downloads" / tid
    out = {"id": tid, "assets": []}
    tmp = Path(tempfile.mkdtemp(prefix="f4f-pin-"))
    try:
        for a in assets_of(t):
            p = cache / a["name"]
            if not p.is_file():
                download(asset_url(t, a), p)
            h = sha256_file(p)
            d = digests.get(a["name"])
            if d and d.startswith("sha256:") and d[7:] != h:
                raise ForgeError(f"{a['name']}: downloaded SHA-256 differs from GitHub's digest", "do not pin; retry")
            out["assets"].append({"name": a["name"], "sha256": h, "github_digest": d, "size": p.stat().st_size})
            a["sha256"] = h
            if a.get("extract", True) and a["name"].lower().endswith((".zip", ".7z")):
                extract(p, tmp)
            else:
                shutil.copy2(p, tmp / a["name"])
        if t.get("flatten", True):
            _flatten(tmp, t.get("exe"))
        if t.get("exe"):
            exe = tmp / t["exe"]
            if not exe.is_file():
                listing = sorted(str(x.relative_to(tmp)) for x in tmp.rglob("*") if x.is_file())[:40]
                raise ForgeError(f"{t['exe']} not in the asset", "fix exe in the lock; files: " + ", ".join(listing))
            out["exe_sha256"] = sha256_file(exe)
            if t.get("probe") is not None:
                out["probe"] = _probe([str(exe)] + t["probe"], t.get("probe_expect"), cwd=exe.parent)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if approve:
        if not t.get("assets") and out["assets"]:
            t["asset_sha256"] = out["assets"][0]["sha256"]
        if out.get("exe_sha256"):
            t["exe_sha256"] = out["exe_sha256"]
        save_json(lock_path, lock)
        out["written"] = str(lock_path)
    return out


def git_head(repo: str, ref: str) -> str | None:
    r = run(["git", "ls-remote", f"https://github.com/{repo}.git", ref], timeout=120)
    m = re.search(r"^([0-9a-f]{40})", r.get("stdout") or "", re.M)
    return m.group(1) if m else None

