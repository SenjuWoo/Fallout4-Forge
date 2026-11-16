"""Offline self-test of an installed forge: data files, topics, templates, and a scaffold -> check -> package ->
validate round in a temporary folder, plus BA2 and material round trips. Touches nothing outside a temp folder
(the forge home is redirected there for the duration)."""
from __future__ import annotations

import json
import os
import shutil
import struct
import tempfile
import time
from pathlib import Path


def run() -> dict:
    checks = []
    t0 = time.time()

    def check(name, fn):
        t = time.time()
        try:
            detail = fn()
            checks.append({"check": name, "ok": True, "detail": detail, "s": round(time.time() - t, 2)})
        except Exception as e:  # every failure becomes a row; selftest itself never crashes
            checks.append({"check": name, "ok": False, "error": f"{type(e).__name__}: {e}", "s": round(time.time() - t, 2)})

    tmp = Path(tempfile.mkdtemp(prefix="f4forge-selftest-"))
    saved = {k: os.environ.get(k) for k in ("F4FORGE_HOME", "FALLOUT4_ROOT")}
    os.environ["F4FORGE_HOME"] = str(tmp / "home")
    try:
        from . import knowledge

        def data_files():
            bad = knowledge.payload_problems()
            if bad:
                raise AssertionError("; ".join(bad))
            return {"facts": len(knowledge.load("facts.json")["facts"]), "routes": len(knowledge.load("routes.json")["routes"])}
        check("knowledge data", data_files)

        def topics():
            ts = knowledge.topics()
            missing = [t["topic"] for t in ts if not t["available"]]
            if missing:
                raise AssertionError("missing topics: " + ", ".join(missing))
            return {"topics": len(ts)}
        check("knowledge topics", topics)

        def routing():
            r = knowledge.plan("write a papyrus script for my quest")
            if r["routes"][0]["id"] != "papyrus-script":
                raise AssertionError(r["routes"][0]["id"])
            return {"route": "papyrus-script"}
        check("routing", routing)

        def ba2_roundtrip():
            from . import ba2
            src = tmp / "ba2src"
            (src / "Meshes").mkdir(parents=True)
            (src / "Meshes" / "x.nif").write_bytes(b"nif" * 500)
            out = tmp / "x.ba2"
            ba2.pack(src, out)
            a = ba2.Archive(out)
            if a.read(a.entries[0]) != b"nif" * 500:
                raise AssertionError("payload differs")
            return {"files": a.count}
        check("ba2 round trip", ba2_roundtrip)

        def material_roundtrip():
            from . import bgsm
            from .util import TEMPLATES_DIR
            doc = json.loads((TEMPLATES_DIR / "materials" / "source" / "materials" / "__ID__" / "__ID__Example.bgsm.json")
                             .read_text(encoding="utf-8"))
            data = bgsm.build(doc)
            if bgsm.build(bgsm.parse(data)) != data:
                raise AssertionError("BGSM differs after a round trip")
            return {"bytes": len(data)}
        check("material round trip", material_roundtrip)

        def project_round():
            from . import check as C
            from . import package, project
            game = tmp / "Fallout 4"
            (game / "Data").mkdir(parents=True)
            (game / "Fallout4.exe").write_bytes(b"MZ")
            body = b"HEDR" + struct.pack("<H", 12) + struct.pack("<fiI", 1.0, 0, 0x800)
            (game / "Data" / "Fallout4.esm").write_bytes(b"TES4" + struct.pack("<IIIIHH", len(body), 1, 0, 0, 131, 0) + body)
            os.environ["FALLOUT4_ROOT"] = str(game)
            out = tmp / "Self Test"
            project.new_project("Self Test", ["mcm", "looksmenu", "bos", "robco", "materials"], out)
            res = C.check_project(out)
            if res["errors"]:
                raise AssertionError(json.dumps(res["errors"][:3]))
            project.build(out, None, ["plugin", "scripts", "textures", "voice"])
            a = package.build(out)
            b = package.build(out)
            if a["sha256"] != b["sha256"] or not a["validation"]["ok"]:
                raise AssertionError("package not deterministic or not valid")
            return {"kinds": 5, "zip_sha256": a["sha256"][:16]}
        check("scaffold, check, package", project_round)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [c["check"] for c in checks if not c["ok"]]
    return {"ok": not failed, "failed": failed, "checks": checks, "seconds": round(time.time() - t0, 2)}
