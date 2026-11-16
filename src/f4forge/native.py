"""Native F4SE plugins: scaffold from the pinned commonlibf4-template with the pinned CommonLibF4, build with
xmake (it finds MSVC itself; vswhere tells doctor whether the C++ toolset exists), check the DLL's exports.

Entry points (F4SE 0.7.9 PluginAPI.h, fact f4se.plugin_api): a data export F4SEPlugin_Version (version data
declaring runtime compatibility) and F4SEPlugin_Load; F4SEPlugin_Preload is optional; F4SEPlugin_Query is the
pre-Next-Gen entry point. CommonLibF4 is GPL-3.0 with a modding exception: a distributed DLL ships its source.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import pe
from .util import ForgeError, run

REQUIRED_EXPORTS = ["F4SEPlugin_Version", "F4SEPlugin_Load"]
OPTIONAL_EXPORTS = ["F4SEPlugin_Preload", "F4SEPlugin_Query"]
LICENSE_NOTE = ("CommonLibF4 is GPL-3.0 with a modding exception: if you distribute the DLL, publish its source "
                "(this project folder) under a compatible licence.")
RUNTIME_NOTE = ("The DLL declares its runtime compatibility in F4SEPlugin_Version (CommonLibF4's plugin rule writes it). "
                "It relies on the Address Library bin for each runtime it runs on; check f4forge game on the target PC.")


def _safe_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_\-]", "", name.replace(" ", ""))
    if not s:
        raise ForgeError(f"'{name}' gives an empty target name", "use letters and digits")
    return s


def new(name: str, out: Path, author: str = "", description: str = "") -> dict:
    from .tools import tool_path
    tpl = tool_path("commonlibf4-template")
    lib = tool_path("commonlibf4")
    if not tpl or not lib:
        raise ForgeError("commonlibf4-template / CommonLibF4 not installed",
                         "f4forge tools sync --only commonlibf4 --only commonlibf4-template --approve")
    target = _safe_name(name)
    if out.exists() and any(out.iterdir()):
        raise ForgeError(f"{out} is not empty", "choose an empty folder")
    ignore = shutil.ignore_patterns(".git", ".gitmodules", "build", ".xmake")
    shutil.copytree(tpl, out, ignore=ignore, dirs_exist_ok=True)
    if (out / "lib" / "commonlibf4").exists():
        shutil.rmtree(out / "lib" / "commonlibf4")
    shutil.copytree(lib, out / "lib" / "commonlibf4", ignore=shutil.ignore_patterns(".git", "build", ".xmake"))
    x = out / "xmake.lua"
    text = x.read_text(encoding="utf-8")
    text = text.replace('set_project("commonlibf4-template")', f'set_project("{target}")')
    text = text.replace('target("commonlibf4-template")', f'target("{target}")')
    text = text.replace('name = "commonlibf4-template"', f'name = "{target}"')
    text = text.replace('author = "libxse"', f'author = "{author or "unknown"}"')
    text = text.replace('description = "F4SE plugin template using CommonLibF4"',
                        f'description = "{(description or name).replace(chr(34), "")}"')
    x.write_text(text, encoding="utf-8", newline="\n")
    (out / "SOURCE-NOTICE.txt").write_text(LICENSE_NOTE + "\n\n" + RUNTIME_NOTE + "\n", encoding="utf-8", newline="\n")
    from .tools import entry, load_lock
    lk = load_lock()
    return {"folder": str(out), "target": target, "template_commit": entry(lk, "commonlibf4-template")["commit"],
            "commonlibf4_commit": entry(lk, "commonlibf4")["commit"], "license": LICENSE_NOTE, "runtime": RUNTIME_NOTE,
            "next": f"f4forge native build {out}"}


def check_dll(dll: Path) -> dict:
    info = pe.exports(dll)
    missing = [e for e in REQUIRED_EXPORTS if e not in info["exports"]]
    present_optional = [e for e in OPTIONAL_EXPORTS if e in info["exports"]]
    errors = [{"code": "NATIVE-EXPORT", "message": f"missing export {m}", "fix": "use F4SE_PLUGIN_LOAD and the CommonLibF4 plugin rule"}
              for m in missing]
    if info["machine"] != "x64":
        errors.append({"code": "NATIVE-ARCH", "message": f"DLL is {info['machine']}, Fallout 4 is x64", "fix": "build for x64"})
    return {"dll": str(dll), "machine": info["machine"], "exports": info["exports"], "required": REQUIRED_EXPORTS,
            "optional_present": present_optional, "ok": not errors, "errors": errors, "fact": "f4se.plugin_api"}


def build(folder: Path, mode: str = "releasedbg", timeout: int = 3600) -> dict:
    from .tools import find_exe
    xmake = find_exe("xmake")
    if not xmake:
        raise ForgeError("xmake not found", "install xmake 3.0+ and put it on PATH")
    if not (folder / "xmake.lua").is_file():
        raise ForgeError(f"no xmake.lua in {folder}", "scaffold one with: f4forge native new <Name>")
    log = []
    for argv in ([str(xmake), "f", "-y", "-m", mode, "-p", "windows", "-a", "x64"], [str(xmake), "-y"]):
        r = run(argv, timeout=timeout, cwd=folder, env={"XMAKE_ROOT": "y"})
        tail = re.sub(chr(27) + r"[[0-9;]*m", "", (r.get("stdout") or "") + (r.get("stderr") or ""))[-1500:]
        log.append({"argv": argv[1:], "exit": r.get("exit"), "tail": tail})
        if not r["ok"]:
            raise ForgeError(f"xmake {' '.join(argv[1:])} failed: " + log[-1]["tail"][-700:], "read the xmake output")
    dlls = sorted((folder / "build").rglob("*.dll"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not dlls:
        raise ForgeError("xmake finished but no DLL was found under build/", "check the target kind in xmake.lua")
    chk = check_dll(dlls[0])
    return {"folder": str(folder), "mode": mode, "dll": str(dlls[0]), "check": chk, "ok": chk["ok"],
            "license": LICENSE_NOTE, "log": log}
