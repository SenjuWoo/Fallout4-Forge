"""Offline suite. Synthetic fixtures only: no game file and nothing extracted from one."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from f4forge import __version__  # noqa: E402
from f4forge import cli, game, home, knowledge, pe, plugin  # noqa: E402

GAME_NAME = "Fallout 4 (test) !"


# --- synthetic builders ---------------------------------------------------------------

def make_pe(version: str) -> bytes:
    """Minimal PE32+ with one .rsrc section holding RT_VERSION / VS_FIXEDFILEINFO."""
    a, b, c, d = (int(x) for x in version.split("."))
    ms, ls = (a << 16) | b, (c << 16) | d
    vi = b"\0" * 40 + b"\xbd\x04\xef\xfe" + struct.pack("<IIIIII", 0x10000, ms, ls, ms, ls, 0x3F) + b"\0" * 24
    rsrc = bytearray()
    rsrc += struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 1) + struct.pack("<II", 16, 0x80000000 | 0x18)
    rsrc += struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 1) + struct.pack("<II", 1, 0x80000000 | 0x30)
    rsrc += struct.pack("<IIHHHH", 0, 0, 0, 0, 0, 1) + struct.pack("<II", 0x409, 0x48)
    rsrc += struct.pack("<IIII", 0x1000 + 0x58, len(vi), 0, 0)
    rsrc += vi
    raw = bytes(rsrc) + b"\0" * (-len(rsrc) % 0x200)
    dos = bytearray(64)
    dos[:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x40)
    coff = struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 240, 0x22)
    opt = bytearray(240)
    struct.pack_into("<H", opt, 0, 0x20B)
    struct.pack_into("<I", opt, 108, 16)
    struct.pack_into("<II", opt, 112 + 16, 0x1000, len(rsrc))
    sec = struct.pack("<8sIIIIIIHHI", b".rsrc", len(rsrc), 0x1000, len(raw), 0x200, 0, 0, 0, 0, 0x40000040)
    head = bytes(dos) + b"PE\0\0" + coff + bytes(opt) + sec
    return head + b"\0" * (0x200 - len(head)) + raw


def make_plugin(hedr: float = 1.0, form_version: int = 131, records: int = 10, flags: int = 0,
                masters: tuple[str, ...] = ()) -> bytes:
    body = b"HEDR" + struct.pack("<H", 12) + struct.pack("<fiI", hedr, records, 0x800)
    for m in masters:
        name = m.encode("cp1252") + b"\0"
        body += b"MAST" + struct.pack("<H", len(name)) + name + b"DATA" + struct.pack("<H", 8) + b"\0" * 8
    return b"TES4" + struct.pack("<IIIIHH", len(body), flags, 0, 0, form_version, 0) + body


def make_ba2_header(version: int, kind: bytes, count: int) -> bytes:
    return struct.pack("<4sI4sIQ", b"BTDX", version, kind, count, 24)


def write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    return path


def make_game(root: Path, runtime: str = "1.11.240.0", ck: bool = True) -> Path:
    write(root / "Fallout4.exe", make_pe(runtime))
    write(root / "f4se_loader.exe", make_pe("0.0.7.9"))
    write(root / "f4se_1_11_240.dll", make_pe("0.0.7.9"))
    write(root / "src" / "f4se-0.7.9.tar.gz", b"\x1f\x8b")
    d = root / "Data"
    write(d / "Fallout4.esm", make_plugin(1.0, 131, 100, plugin.FLAG_ESM))
    write(d / "DLCCoast.esm", make_plugin(0.95, 131, 50, plugin.FLAG_ESM, ("Fallout4.esm",)))
    write(d / "ccTest-Thing.esl", make_plugin(1.0, 131, 3, plugin.FLAG_ESM | plugin.FLAG_ESL, ("Fallout4.esm",)))
    write(d / "MyMod.esp", make_plugin(1.0, 131, 2, 0, ("Fallout4.esm",)))
    write(d / "F4SE" / "Plugins" / "version-1-11-240-0.bin", b"\0")
    write(d / "F4SE" / "Plugins" / "version-1-10-163-0.bin", b"\0")
    write(d / "F4SE" / "Plugins" / "mcm.dll", make_pe("1.0.0.0"))
    write(d / "Test - Main.ba2", make_ba2_header(8, b"GNRL", 5))
    write(d / "Test - Textures.ba2", make_ba2_header(1, b"DX10", 2))
    write(root / "Fallout4.ccc", "ccTest-Thing.esl\n")
    if ck:
        write(root / "CreationKit.exe", make_pe("1.11.246.0"))
        write(root / "Papyrus Compiler" / "PapyrusCompiler.exe", make_pe("2.8.0.4"))
        write(root / "Tools" / "Archive2" / "Archive2.exe", make_pe("1.1.0.5"))
        write(root / "Tools" / "Audio" / "xwmaencode.exe", make_pe("9.28.1876.0"))
        write(root / "Tools" / "LipGen" / "LipGenerator" / "LipGenerator.exe", make_pe("1.0.0.1"))
        write(d / "Scripts" / "Source" / "Base" / "Base.zip", b"PK\5\6" + b"\0" * 18)
    return root


def run_cli(*argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, json.loads(buf.getvalue())


class Base(unittest.TestCase):
    ENV = ("F4FORGE_HOME", "FALLOUT4_ROOT", "FALLOUT4_MYGAMES", "FALLOUT4_APPDATA")

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in self.ENV}
        self.tmp = Path(tempfile.mkdtemp(prefix="f4forge-test-"))
        os.environ["F4FORGE_HOME"] = str(self.tmp / "home")
        os.environ["FALLOUT4_MYGAMES"] = str(self.tmp / "mygames")
        os.environ["FALLOUT4_APPDATA"] = str(self.tmp / "appdata")
        self.game = make_game(self.tmp / GAME_NAME)
        os.environ["FALLOUT4_ROOT"] = str(self.game)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)


# --- repository hygiene helpers (T03) ----------------------------------------------------

CRLF_SUFFIXES = (".bat", ".cmd", ".ps1")
BINARY_SUFFIXES = (".ba2", ".esm", ".esp", ".esl", ".pex", ".dds", ".nif", ".bgsm", ".bgem", ".fuz", ".xwm",
                   ".lip", ".wav", ".png", ".zip", ".7z", ".exe", ".dll", ".gz")


def repo_files(root: Path) -> list[Path]:
    if (root / ".git").exists() and shutil.which("git"):
        cp = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            capture_output=True, check=True)
        names = [n for n in cp.stdout.decode("utf-8").split("\0") if n]
        return [root / n for n in sorted(set(names)) if (root / n).is_file()]
    skip = {".git", ".venv", "__pycache__", "build", "dist"}
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.endswith(".egg-info")]
        out += [Path(dirpath) / f for f in filenames if f not in ("LOCAL.md", "FIELD-REPORTS.md")]
    return sorted(out)


def line_ending_problems(files: list[Path]) -> list[str]:
    problems = []
    for p in files:
        if p.suffix.lower() in BINARY_SUFFIXES:
            continue
        data = p.read_bytes()
        if b"\0" in data:
            continue
        if p.suffix.lower() in CRLF_SUFFIXES:
            if data.count(b"\n") != data.count(b"\r\n"):
                problems.append(f"{p.name}: must be CRLF")
        elif b"\r\n" in data:
            problems.append(f"{p.name}: must be LF")
    return problems


def version_problems(root: Path) -> list[str]:
    def text(rel):
        return (root / rel).read_text(encoding="utf-8")

    v = re.search(r'__version__\s*=\s*"([^"]+)"', text("src/f4forge/__init__.py")).group(1)
    found = {
        "CHANGELOG.md": (re.search(r"^## (\S+)", text("CHANGELOG.md"), re.M) or [None, None])[1],
        "STATE.md": (re.search(r"^- Version:\s*(\d+\.\d+\.\d+)", text("STATE.md"), re.M) or [None, None])[1],
        "skills/fallout4-forge/SKILL.md": (re.search(r"^Version:\s*(\S+)", text("skills/fallout4-forge/SKILL.md"), re.M)
                                           or [None, None])[1],
        "uabs-companion.json": json.loads(text("uabs-companion.json")).get("version"),
    }
    problems = [f"{name}: {got!r} != {v}" for name, got in found.items() if got != v]
    if "f4forge.__version__" not in text("pyproject.toml"):
        problems.append("pyproject.toml: version not read from f4forge.__version__")
    return problems


MIRROR_FILES = ("src/f4forge/__init__.py", "CHANGELOG.md", "STATE.md", "skills/fallout4-forge/SKILL.md",
                "uabs-companion.json", "pyproject.toml")


# --- T02: CLI contract --------------------------------------------------------------------

class CliContractTests(Base):
    def test_version_constant(self):
        self.assertEqual(__version__, "0.1.0")

    def test_json_compact_and_pretty(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cli.main(["facts"]), 0)
        self.assertEqual(buf.getvalue().count("\n"), 1)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cli.main(["facts", "--pretty"]), 0)
        self.assertGreater(buf.getvalue().count("\n"), 3)
        json.loads(buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--pretty", "facts"])
        self.assertGreater(buf.getvalue().count("\n"), 3)

    def test_named_failure_and_usage_error_are_json_exit_2(self):
        code, out = run_cli("facts", "no-such-fact-zzz")
        self.assertEqual(code, 2)
        self.assertIn("fix", out)
        code, out = run_cli("no-such-command")
        self.assertEqual(code, 2)
        self.assertTrue(out["error"].startswith("usage:"))

    def test_bug_is_exit_3(self):
        orig = knowledge.facts
        knowledge.facts = lambda q=None: 1 / 0
        try:
            code, out = run_cli("facts")
        finally:
            knowledge.facts = orig
        self.assertEqual(code, 3)
        self.assertIn("internal error", out["error"])

    def test_invocation_log_and_home(self):
        run_cli("facts")
        log = Path(os.environ["F4FORGE_HOME"]) / "logs" / "f4forge.log"
        line = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(line["argv"], ["facts"])
        self.assertEqual(line["exit"], 0)

    def test_home_resolution(self):
        self.assertEqual(home.home_dir(), Path(os.environ["F4FORGE_HOME"]))
        os.environ.pop("F4FORGE_HOME")
        try:
            h = home.home_dir()
            self.assertTrue(h.name in ("Fallout4Forge", "fallout4-forge"))
        finally:
            os.environ["F4FORGE_HOME"] = str(self.tmp / "home")

    def test_config_set_unset(self):
        code, out = run_cli("config", "--set", f"workspace_root={self.tmp / 'ws'}", "--set", "tools_root=" + str(self.tmp))
        self.assertEqual(code, 0)
        self.assertEqual(out["values"]["workspace_root"], str(self.tmp / "ws"))
        code, out = run_cli("config", "--unset", "workspace_root")
        self.assertIsNone(out["values"]["workspace_root"])
        code, out = run_cli("config", "--set", "bogus=1")
        self.assertEqual(code, 2)


# --- T03: mirrors, line endings, awkward launcher path ----------------------------------------

class MirrorTests(unittest.TestCase):
    def test_version_mirrors_in_tree(self):
        self.assertEqual(version_problems(ROOT), [])

    def test_version_mirror_mismatch_is_caught(self):
        tmp = Path(tempfile.mkdtemp(prefix="f4forge-mirror-"))
        try:
            for rel in MIRROR_FILES:
                write(tmp / rel, (ROOT / rel).read_bytes())
            self.assertEqual(version_problems(tmp), [])
            for rel in MIRROR_FILES[1:5]:
                p = tmp / rel
                good = p.read_bytes()
                p.write_bytes(good.replace(__version__.encode(), b"9.9.9"))
                self.assertTrue(any(rel in x for x in version_problems(tmp)), rel)
                p.write_bytes(good)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_line_endings_in_tree(self):
        self.assertEqual(line_ending_problems(repo_files(ROOT)), [])

    def test_wrong_line_ending_is_caught(self):
        tmp = Path(tempfile.mkdtemp(prefix="f4forge-eol-"))
        try:
            good_cmd = write(tmp / "x.cmd", b"@echo off\r\nexit /b 0\r\n")
            good_py = write(tmp / "x.py", b"a = 1\nb = 2\n")
            self.assertEqual(line_ending_problems([good_cmd, good_py]), [])
            bad_cmd = write(tmp / "y.cmd", b"@echo off\nexit /b 0\r\n")
            bad_md = write(tmp / "y.md", b"# t\r\nline\r\n")
            self.assertEqual(len(line_ending_problems([bad_cmd, bad_md])), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(os.name == "nt", "the .cmd launcher runs on Windows")
    def test_launcher_from_awkward_folder(self):
        tmp = Path(tempfile.mkdtemp(prefix="f4forge-launch-"))
        try:
            dest = tmp / "a !b (c)"
            dest.mkdir()
            shutil.copy2(ROOT / "f4forge.cmd", dest / "f4forge.cmd")
            shutil.copytree(ROOT / "src", dest / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            env = dict(os.environ, F4FORGE_HOME=str(tmp / "home"))
            env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
            cmd = str(dest / "f4forge.cmd")
            r = subprocess.run([cmd, "--version"], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(__version__, r.stdout)
            r = subprocess.run([cmd, "facts", "ba2"], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(json.loads(r.stdout)["facts"])
            r = subprocess.run([cmd, "facts", "no-such-fact-zzz"], capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(r.returncode, 2, "exit code must survive the launcher")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# --- T04: game discovery -------------------------------------------------------------------------

class GameTests(Base):
    def test_pe_version_reader(self):
        p = write(self.tmp / "x.exe", make_pe("1.2.3.4"))
        self.assertEqual(pe.file_version(p), "1.2.3.4")
        self.assertIsNone(pe.file_version(write(self.tmp / "y.exe", b"MZ" + b"\0" * 100)))
        self.assertIsNone(pe.file_version(write(self.tmp / "z.txt", b"hello")))

    def test_report_on_synthetic_tree(self):
        code, r = run_cli("game")
        self.assertEqual(code, 0)
        self.assertEqual(r["found_by"], "FALLOUT4_ROOT")
        self.assertEqual(r["runtime"]["version"], "1.11.240.0")
        self.assertEqual(r["runtime"]["generation"]["id"], "anniversary")
        self.assertEqual(r["f4se"]["version"], "0.7.9")
        self.assertTrue(r["f4se"]["matches_runtime"])
        self.assertEqual(r["f4se"]["source_tarball"]["version"], "0.7.9")
        self.assertTrue(r["address_library"]["for_runtime"])
        ck = r["creation_kit"]
        self.assertEqual(ck["version"], "1.11.246.0")
        self.assertEqual(ck["tier"], "creation-kit")
        for t in ("papyrus_compiler", "archive2", "lipgenerator", "xwmaencode"):
            self.assertTrue(ck["tools"][t]["found"], t)
        self.assertTrue(ck["official_source_zips"]["Base"])
        masters = {m["plugin"]: m for m in r["official_masters"]}
        self.assertEqual(masters["Fallout4.esm"]["hedr_version"], 1.0)
        self.assertEqual(masters["Fallout4.esm"]["form_version"], 131)
        self.assertEqual(masters["DLCCoast.esm"]["hedr_version"], 0.95)
        self.assertFalse(masters["DLCRobot.esm"]["present"])
        self.assertEqual(r["creation_club"]["listed_and_installed"], 1)
        self.assertEqual(r["data_counts"], {"ba2": 2, "esm": 2, "esp": 1, "esl": 1})
        fws = {f["id"]: f["installed"] for f in r["frameworks"]}
        self.assertTrue(fws["f4se"] and fws["mcm"] and fws["address-library"])
        self.assertFalse(fws["robco-patcher"])
        self.assertFalse(r["my_games"]["found"])

    def test_runtime_mismatch_and_no_creation_kit(self):
        g = make_game(self.tmp / "Other Game", runtime="1.10.984.0", ck=False)
        code, r = run_cli("game", "--game", str(g))
        self.assertEqual(r["runtime"]["generation"]["id"], "next-gen")
        self.assertFalse(r["f4se"]["matches_runtime"])
        self.assertFalse(r["address_library"]["for_runtime"])
        self.assertEqual(r["creation_kit"]["tier"], "no-creation-kit")
        self.assertIn("papyrus_compiler", r["creation_kit"]["missing_for_tier"])

    def test_censuses(self):
        code, r = run_cli("game", "--archives", "--plugins")
        self.assertEqual(r["archives"]["by_version_type"], {"v1 DX10": 1, "v8 GNRL": 1})
        self.assertEqual(r["archives"]["errors"], [])
        rows = json.loads(Path(r["archives"]["full_list"]).read_text(encoding="utf-8"))
        self.assertEqual({x["file"]: x["files"] for x in rows}, {"Test - Main.ba2": 5, "Test - Textures.ba2": 2})
        self.assertEqual(r["plugins"]["by_extension_and_hedr"], {"esl 1.0": 1, "esm 0.95": 1, "esm 1.0": 1, "esp 1.0": 1})
        self.assertEqual(r["plugins"]["flags"]["esl_flag"], 1)

    def test_explicit_setting_never_falls_through(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        os.environ["FALLOUT4_ROOT"] = str(empty)
        code, out = run_cli("game")
        self.assertEqual(code, 2)
        self.assertIn("FALLOUT4_ROOT", out["error"])

    def test_config_game_root(self):
        os.environ.pop("FALLOUT4_ROOT")
        home.set_config({"game_root": str(self.game)})
        root, source = game.find_game()
        self.assertEqual(source, "config game_root")
        self.assertEqual(root, self.game)

    def test_steam_library_discovery(self):
        steam = self.tmp / "Steam"
        lib = self.tmp / "Library (2) !"
        vdf = '"libraryfolders"\n{\n  "0"\n  {\n    "path"  "%s"\n  }\n}\n' % str(lib).replace("\\", "\\\\")
        write(steam / "steamapps" / "libraryfolders.vdf", vdf)
        write(lib / "steamapps" / "appmanifest_377160.acf",
              '"AppState"\n{\n  "appid" "377160"\n  "installdir" "%s"\n  "buildid" "42"\n}\n' % GAME_NAME)
        target = make_game(lib / "steamapps" / "common" / GAME_NAME)
        cands = game.steam_candidates([steam])
        self.assertIn(target, [c[0] for c in cands])
        self.assertTrue(cands[0][1].startswith("steam:"))
        self.assertEqual(game.steam_app(lib, "377160")["buildid"], "42")

    def test_vdf_parser(self):
        doc = game.parse_vdf('"a" { "b" "1" "c" { "d" "x\\\\y" } }')
        self.assertEqual(doc, {"a": {"b": "1", "c": {"d": "x\\y"}}})

    def test_plugin_header(self):
        p = write(self.tmp / "t.esp", make_plugin(0.95, 131, 7, plugin.FLAG_ESL, ("Fallout4.esm", "DLCCoast.esm")))
        h = plugin.read_header(p)
        self.assertEqual((h["hedr_version"], h["records"], h["esl"], h["esm"]), (0.95, 7, True, False))
        self.assertEqual(h["masters"], ["Fallout4.esm", "DLCCoast.esm"])


# --- T05: doctor ----------------------------------------------------------------------------------

class DoctorTests(Base):
    def test_sections_and_exit(self):
        code, r = run_cli("doctor")
        for s in ("toolchain", "game", "payload", "tools", "worker"):
            self.assertIn(r[s]["status"], ("ok", "degraded", "fail"), s)
        self.assertEqual(r["toolchain"]["status"], "ok")
        self.assertEqual(r["payload"]["status"], "ok", r["payload"]["problems"])
        self.assertEqual(r["game"]["status"], "ok", r["game"]["problems"])
        self.assertEqual(code, 0)
        self.assertTrue(r["ok"])
        for s in ("tools", "worker"):
            for p in r[s]["problems"]:
                self.assertTrue(p["fix"], s)

    def test_empty_game_folder_fails_game_only(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        os.environ["FALLOUT4_ROOT"] = str(empty)
        code, r = run_cli("doctor")
        self.assertEqual(code, 2)
        self.assertEqual(r["game"]["status"], "fail")
        self.assertEqual(r["toolchain"]["status"], "ok")
        self.assertEqual(r["failed_required"], ["game"])
        self.assertTrue(r["game"]["problems"][0]["fix"])

    def test_optional_gaps_are_degraded(self):
        g = make_game(self.tmp / "NoCK", runtime="1.11.240.0", ck=False)
        code, r = run_cli("doctor", "--game", str(g))
        self.assertEqual(r["game"]["status"], "degraded")
        self.assertEqual(code, 0)

    def test_workspace_root_reported(self):
        ws = self.tmp / "ws"
        write(ws / "WORKSPACE.md", "# ws\n")
        home.set_config({"workspace_root": str(ws)})
        code, r = run_cli("doctor")
        self.assertEqual(r["home"]["workspace_root"], {"path": str(ws), "exists": True, "workspace_md": True})


# --- T06: knowledge -------------------------------------------------------------------------------

class KnowledgeTests(unittest.TestCase):
    def test_payload_valid(self):
        self.assertEqual(knowledge.payload_problems(), [])

    def test_schema_rejects_missing_tier_or_source(self):
        good = {"id": "x", "claim": "c", "tier": "installed", "source": "s", "checked": "2026-11-15", "how": "h"}
        self.assertEqual(knowledge.validate_facts({"facts": [good]}), [])
        for drop in ("tier", "source"):
            bad = {k: v for k, v in good.items() if k != drop}
            errs = knowledge.validate_facts({"facts": [bad]})
            self.assertTrue(any(f"missing {drop}" in e for e in errs), drop)
        self.assertTrue(knowledge.validate_facts({"facts": [dict(good, tier="rumour")]}))
        self.assertTrue(knowledge.validate_facts({"facts": [dict(good, tier="primary")]}), "primary needs a URL")
        self.assertTrue(knowledge.validate_facts({"facts": [good, good]}), "duplicate id")

    def test_knowledge_lists_topics(self):
        code, out = run_cli("knowledge")
        self.assertEqual(code, 0)
        names = [t["topic"] for t in out["topics"]]
        for t in ("plugin-basics", "papyrus", "archives", "light-plugins", "lessons"):
            self.assertIn(t, names)
        declared = set(knowledge.load("routes.json")["topics"])
        for r in knowledge.load("routes.json")["routes"]:
            self.assertTrue(set(r["knowledge"]) <= declared, r["id"])

    def test_facts_ba2(self):
        code, out = run_cli("facts", "ba2")
        self.assertEqual(code, 0)
        ids = [f["id"] for f in out["facts"]]
        self.assertIn("ba2.versions.installed", ids)
        self.assertIn("ba2.header", ids)
        for f in out["facts"]:
            for k in knowledge.FACT_FIELDS:
                self.assertTrue(f[k], (f["id"], k))

    def test_installed_facts_name_a_command(self):
        for f in knowledge.load("facts.json")["facts"]:
            if f["tier"] == "installed":
                self.assertIn("f4forge ", f["how"], f["id"])


# --- T07: routing -----------------------------------------------------------------------------------

ROUTE_FIXTURES = [
    ("create a new misc item record with an EditorID in my esp", "plugin-record"),
    ("inject my new weapons into the leveled lists", "leveled-list-injection"),
    ("write a papyrus script that runs on an event", "papyrus-script"),
    ("add a quest with dialogue for a new companion", "quest-dialogue"),
    ("make an MCM settings menu for my mod", "mcm-menu"),
    ("patch vanilla records at runtime with RobCo Patcher", "robco-patch"),
    ("swap a base object everywhere with Base Object Swapper", "object-swap"),
    ("write an F4SE plugin DLL with CommonLibF4", "f4se-native"),
    ("retexture the 10mm pistol with a new dds texture", "texture"),
    ("edit a BGSM material file to change the shader", "material"),
    ("import a nif mesh into Blender and export it again", "mesh"),
    ("convert an outfit to CBBE with BodySlide sliders", "bodyslide-outfit"),
    ("save a LooksMenu face preset for my character", "looksmenu-preset"),
    ("add voiced lines with lip sync for an NPC", "audio-voice"),
    ("add a new settlement object to the workshop build menu", "workshop-settlement"),
    ("make a new weapon mod attachment for a receiver", "weapon-omod"),
    ("create a new armor piece using biped slot 54", "armor"),
    ("fix flickering buildings after editing cells, previs is broken", "previs"),
    ("change the HUD swf interface", "interface"),
    ("add a custom animation hkx", "animation"),
    ("change a game setting through an ini tweak file", "ini-tweak"),
    ("the game crashes on load, read the crash log", "crash-triage"),
    ("check which mods conflict with mine and overwrite records", "conflict-check"),
    ("package my mod as a FOMOD zip and publish on Nexus", "package-publish"),
]


class RoutingTests(Base):
    def test_every_route_has_a_fixture(self):
        ids = {r["id"] for r in knowledge.load("routes.json")["routes"]}
        self.assertEqual(len(ids), 24)
        self.assertEqual(ids, {e for _, e in ROUTE_FIXTURES})

    def test_fixtures_map_to_expected_route(self):
        for request, expected in ROUTE_FIXTURES:
            r = knowledge.plan(request)
            self.assertTrue(r["matched"], request)
            self.assertEqual(r["routes"][0]["id"], expected, f"{request!r} -> {[x['id'] for x in r['routes']]}")

    def test_plan_output_shape(self):
        code, r = run_cli("plan", "write", "a", "papyrus", "script")
        self.assertEqual(code, 0)
        for k in ("routes", "commands", "knowledge", "tools", "avoid", "gaps", "creation_kit_tier"):
            self.assertIn(k, r)
        self.assertEqual(r["creation_kit_tier"], "creation-kit")
        self.assertTrue(all("available" in c for c in r["commands"]))
        code, r = run_cli("plan", "add", "a", "custom", "animation", "hkx")
        self.assertTrue(r["gaps"], "animation is a named gap in 0.1 (D15)")

    def test_unmatched_request(self):
        code, r = run_cli("plan", "qwerty", "zxcv")
        self.assertEqual(code, 0)
        self.assertFalse(r["matched"])

    def test_capabilities_equals_parser(self):
        code, out = run_cli("capabilities")
        self.assertEqual(code, 0)
        names = [c["command"] for c in out["commands"]]
        self.assertEqual(names, list(cli.subcommands(cli.parser())))
        self.assertEqual(len(names), len(set(names)))

    def test_routes_reference_known_topics_and_tools(self):
        for r in knowledge.load("routes.json")["routes"]:
            self.assertTrue(r["commands"] and r["knowledge"] and r["avoid"], r["id"])
            for t in r["tools"]:
                self.assertIn(t["when"], ("always", "creation-kit", "no-creation-kit", "optional"), r["id"])


# --- T08: tool lock and sync against a local HTTP fixture ---------------------------------------------

class _Server:
    def __init__(self, folder: Path):
        import functools
        import http.server
        import threading
        outer = self
        self.hits = 0

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                outer.hits += 1
                return super().do_GET()

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                                     functools.partial(Handler, directory=str(folder)))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, name):
        return f"http://127.0.0.1:{self.port}/{name}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class ToolsTests(Base):
    def setUp(self):
        super().setUp()
        import hashlib
        import zipfile
        from f4forge import tools
        self.T = tools
        self.www = self.tmp / "www"
        self.www.mkdir()
        z = self.www / "faketool-1.0.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("faketool-1.0/faketool.exe", b"MZ fake tool")
            zf.writestr("faketool-1.0/readme.txt", "hi")
        raw = write(self.www / "single.exe", b"MZ single")
        self.server = _Server(self.www)
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
        self.lock = {"schema": 1, "tools": [
            {"id": "fake", "kind": "github_release", "role": "test", "repo": "x/y", "tag": "1.0",
             "asset": "faketool-1.0.zip", "asset_sha256": sha(z), "url": self.server.url("faketool-1.0.zip"),
             "folder": "Fake Tool 1.0", "exe": "faketool.exe", "exe_sha256": hashlib.sha256(b"MZ fake tool").hexdigest(),
             "copy_as": {"faketool.exe": "faketool-renamed.exe"}},
            {"id": "single", "kind": "github_release", "role": "test", "repo": "x/y", "tag": "1.0",
             "assets": [{"name": "single.exe", "sha256": sha(raw), "extract": False, "url": self.server.url("single.exe")}],
             "folder": "Single", "exe": "single.exe", "exe_sha256": sha(raw)},
            {"id": "maybe", "kind": "manual", "role": "manual", "detect": ["*/maybe.exe"], "optional": True},
        ]}
        self.root = self.tmp / "tools root !"

    def tearDown(self):
        self.server.close()
        super().tearDown()

    def test_dry_run_changes_nothing(self):
        res = self.T.sync(self.lock, self.root, approve=False)
        self.assertTrue(res["dry_run"])
        self.assertEqual([a["action"] for a in res["actions"]], ["install", "install"])
        self.assertFalse(self.root.exists())
        self.assertEqual(self.server.hits, 0)

    def test_good_hash_installs_and_second_sync_downloads_nothing(self):
        res = self.T.sync(self.lock, self.root, approve=True)
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["installed"], ["fake", "single"])
        self.assertTrue((self.root / "Fake Tool 1.0" / "faketool.exe").is_file(), "wrapper folder flattened")
        self.assertTrue((self.root / "Fake Tool 1.0" / "faketool-renamed.exe").is_file())
        rec = json.loads((self.root / "tools.receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(set(rec["tools"]), {"fake", "single"})
        self.assertIn("| fake | github_release | ok |", (self.root / "TOOLS.md").read_text(encoding="utf-8"))
        self.assertTrue(res["required_ok"])
        hits = self.server.hits
        res2 = self.T.sync(self.lock, self.root, approve=True)
        self.assertEqual(res2["downloads"], 0)
        self.assertEqual(self.server.hits, hits, "second sync must not download")
        self.assertEqual({a["action"] for a in res2["actions"]}, {"none"})

    def test_bad_hash_refuses_before_extraction(self):
        self.lock["tools"][0]["asset_sha256"] = "0" * 64
        res = self.T.sync(self.lock, self.root, approve=True, only=["fake"])
        self.assertEqual(len(res["errors"]), 1)
        self.assertIn("not extracted", res["errors"][0]["error"])
        self.assertFalse((self.root / "Fake Tool 1.0").exists())

    def test_unowned_folder_is_never_touched(self):
        mine = write(self.root / "Fake Tool 1.0" / "my file.txt", "user data")
        res = self.T.sync(self.lock, self.root, approve=True, only=["fake"])
        self.assertEqual(len(res["errors"]), 1)
        self.assertIn("does not own", res["errors"][0]["error"])
        self.assertEqual(mine.read_text(encoding="utf-8"), "user data")
        st = self.T.status(self.lock, self.root)
        self.assertEqual({r["id"]: r["status"] for r in st["tools"]}["fake"], "unowned")

    def test_tampered_exe_is_mismatch_and_resync_repairs(self):
        self.T.sync(self.lock, self.root, approve=True)
        (self.root / "Single" / "single.exe").write_bytes(b"tampered")
        st = self.T.status(self.lock, self.root)
        self.assertEqual({r["id"]: r["status"] for r in st["tools"]}["single"], "mismatch")
        self.assertFalse(st["required_ok"])
        res = self.T.sync(self.lock, self.root, approve=True)
        self.assertEqual(res["installed"], ["single"])
        self.assertEqual(res["downloads"], 0, "the cached asset is reused")

    def test_manual_detection(self):
        st = self.T.status(self.lock, self.root)
        self.assertEqual({r["id"]: r["status"] for r in st["tools"]}["maybe"], "manual")
        write(self.root / "Maybe 1" / "maybe.exe", b"x")
        st = self.T.status(self.lock, self.root)
        self.assertEqual({r["id"]: r["status"] for r in st["tools"]}["maybe"], "ok")

    def test_real_lock_is_well_formed(self):
        lock = self.T.load_lock()
        ids = [t["id"] for t in lock["tools"]]
        self.assertEqual(len(ids), len(set(ids)))
        folders = [t["folder"].lower() for t in lock["tools"] if t.get("folder")]
        self.assertEqual(len(folders), len(set(folders)))
        for t in lock["tools"]:
            self.assertIn(t["kind"], self.T.KINDS, t["id"])
            if t["kind"] == "github_release":
                for a in self.T.assets_of(t):
                    self.assertRegex(a["sha256"], r"^[0-9a-f]{64}$", f"{t['id']} {a['name']} pinned")
                if t.get("exe"):
                    self.assertRegex(t["exe_sha256"], r"^[0-9a-f]{64}$", t["id"])
                self.assertTrue(t.get("license"), t["id"])
            if t["kind"] == "git_clone":
                self.assertRegex(t["commit"], r"^[0-9a-f]{40}$", t["id"])


# --- M3: archives, plugins, load order, worker, Spriggit -------------------------------------------

def make_dds(w: int, h: int, mips: int, code: int, cube: bool = False, seed: int = 1) -> bytes:
    from f4forge import dds as D
    size = D.chain_size(w, h, mips, code, 6 if cube else 1)
    body = bytes((i * seed + i // 7) & 0xFF for i in range(size))
    return D.build_header(w, h, mips, code, cube) + body


def make_record(sig: bytes, fid: int, subs: list[tuple[bytes, bytes]], compress: bool = False) -> bytes:
    import zlib
    data = b"".join(s + struct.pack("<H", len(b)) + b for s, b in subs)
    flags = 0
    if compress:
        data = struct.pack("<I", len(data)) + zlib.compress(data)
        flags |= plugin.FLAG_COMPRESSED
    return sig + struct.pack("<IIIIHH", len(data), flags, fid, 0, 131, 0) + data


def make_group(label: bytes, records: list[bytes]) -> bytes:
    body = b"".join(records)
    return b"GRUP" + struct.pack("<I4siHHI", 24 + len(body), label, 0, 0, 0, 0) + body


def make_full_plugin(path: Path, masters=("Fallout4.esm",), hedr=1.0, flags=0, records=None) -> Path:
    head = make_plugin(hedr, 131, 3, flags, masters)
    records = records if records is not None else [
        make_group(b"MISC", [make_record(b"MISC", 0x01000801, [(b"EDID", b"ItemOne\0")]),
                             make_record(b"MISC", 0x01000802, [(b"EDID", b"ItemTwo\0")], compress=True)]),
        make_group(b"WEAP", [make_record(b"WEAP", 0x00004822, [(b"EDID", b"Override10mm\0")])]),
    ]
    return write(path, head + b"".join(records))


class Ba2Tests(Base):
    def test_gnrl_roundtrip_and_hashes(self):
        from f4forge import ba2
        src = self.tmp / "src"
        write(src / "Meshes" / "Thing.nif", b"nif" * 1000)
        write(src / "Scripts" / "Thing.pex", b"pex data that stays stored" * 10)
        write(src / "Materials" / "A.BGSM", b"m")
        out = self.tmp / "Mod - Main.ba2"
        res = ba2.pack(src, out)
        self.assertEqual((res["type"], res["version"], res["files"]), ("GNRL", 1, 3))
        arc = ba2.Archive(out)
        names = sorted(e["name"] for e in arc.entries)
        self.assertEqual(names, ["Materials\\A.BGSM", "Meshes\\Thing.nif", "Scripts\\Thing.pex"])
        pex = arc.find("scripts/thing.pex")
        self.assertEqual(pex["packed"], 0, "pex is stored like vanilla")
        self.assertGreater(arc.find("Meshes\\Thing.nif")["packed"], 0)
        self.assertEqual(arc.read(arc.find("Meshes\\Thing.nif")), b"nif" * 1000)
        self.assertEqual(ba2.crc32_lower("keys"), 0x95CA9BF0, "vanilla Materials\\Keys.BGSM name hash")
        self.assertEqual(ba2.crc32_lower("materials"), 0x7D1E021B)
        ex = ba2.extract(arc, self.tmp / "x")
        self.assertEqual(ex["files"], 3)
        self.assertEqual((self.tmp / "x" / "Meshes" / "Thing.nif").read_bytes(), b"nif" * 1000)
        res8 = ba2.pack(src, self.tmp / "v8.ba2", version=8)
        self.assertEqual(ba2.Archive(self.tmp / "v8.ba2").version, 8)
        self.assertEqual(ba2.verify(out)["ok"], True)

    def test_dx10_roundtrip_chunks_and_header(self):
        from f4forge import ba2, dds
        src = self.tmp / "tex"
        write(src / "Textures" / "Big_d.dds", make_dds(1024, 1024, 11, 71))
        write(src / "Textures" / "Wide_n.dds", make_dds(1024, 256, 11, 83, seed=3))
        write(src / "Textures" / "Small_s.dds", make_dds(256, 256, 9, 98, seed=5))
        write(src / "Textures" / "Sky_e.dds", make_dds(64, 64, 7, 87, cube=True, seed=7))
        out = self.tmp / "Mod - Textures.ba2"
        res = ba2.pack(src, out)
        self.assertEqual(res["type"], "DX10")
        self.assertEqual(res["load"], "NOT RUN")
        arc = ba2.Archive(out)
        plans = {e["name"].split("\\")[-1]: [(c["mip_first"], c["mip_last"]) for c in e["chunks"]] for e in arc.entries}
        self.assertEqual(plans["Big_d.dds"], [(0, 0), (1, 1), (2, 10)])
        self.assertEqual(plans["Wide_n.dds"], [(0, 0), (1, 10)])
        self.assertEqual(plans["Small_s.dds"], [(0, 8)])
        self.assertEqual(plans["Sky_e.dds"], [(0, 6)])
        for name in plans:
            orig = (src / "Textures" / name).read_bytes()
            got = arc.read(arc.find("Textures\\" + name))
            self.assertEqual(got[dds.header_size(got):], orig[dds.header_size(orig):], name)
            a, b = dds.parse(got), dds.parse(orig)
            self.assertEqual((a["width"], a["height"], a["mips"], a["dxgi"], a["cubemap"]),
                             (b["width"], b["height"], b["mips"], b["dxgi"], b["cubemap"]), name)

    def test_rejects_bad_archives(self):
        from f4forge import ba2
        from f4forge.util import ForgeError
        with self.assertRaises(ForgeError):
            ba2.Archive(write(self.tmp / "x.ba2", b"NOPE" + b"\0" * 40))
        with self.assertRaises(ForgeError):
            ba2.Archive(write(self.tmp / "y.ba2", struct.pack("<4sI4sIQ", b"BTDX", 2, b"GNRL", 0, 24)))
        self.assertFalse(ba2.verify(self.tmp / "x.ba2")["ok"])

    def test_extract_refuses_game_folder(self):
        from f4forge import ba2
        from f4forge.util import ForgeError
        with self.assertRaises(ForgeError):
            ba2.guard_out(self.game / "Data" / "out", self.game)

    def test_dds_legacy_and_dx10_headers(self):
        from f4forge import dds
        for code in (71, 77, 80, 83, 87, 28, 61, 98, 99, 72):
            d = make_dds(128, 64, 8, code)
            info = dds.parse(d)
            self.assertEqual(info["dxgi"], code, dds.format_name(code))
            self.assertEqual(info["payload_bytes"], info["payload_expected"])


class PluginTests(Base):
    def test_walker_counts_types_formids_edids(self):
        p = make_full_plugin(self.tmp / "My Mod.esp")
        r = plugin.inspect(p, edids=True)
        self.assertEqual(r["records_walked"], 3)
        self.assertEqual(r["groups"], 2)
        self.assertEqual(r["types"], {"MISC": 2, "WEAP": 1})
        self.assertEqual(r["formids"]["new"], 2)
        self.assertEqual(r["formids"]["overrides_by_master"], {"Fallout4.esm": 1})
        self.assertEqual(r["compressed_records"], 1)
        self.assertEqual(r["edid_sample"]["ItemTwo"], "01000802", "compressed record inflated")

    def test_light_range_rules(self):
        ok = plugin.esl_check(make_full_plugin(self.tmp / "ok.esp"))
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["allowed_range"], ["001", "FFF"])
        self.assertIn("LIGHT-ELIGIBLE", [w["code"] for w in ok["warnings"]])
        low = make_full_plugin(self.tmp / "low.esl", masters=("Fallout4.esm",), hedr=0.95, flags=plugin.FLAG_ESL, records=[
            make_group(b"MISC", [make_record(b"MISC", 0x01000010, [(b"EDID", b"Low\0")])])])
        r = plugin.esl_check(low)
        self.assertEqual(r["allowed_range"], ["800", "FFF"], "HEDR 0.95 keeps the 0x800 floor")
        self.assertIn("LIGHT-BELOW-FLOOR", [e["code"] for e in r["errors"]])
        nomaster = make_full_plugin(self.tmp / "nm.esl", masters=(), hedr=1.0, flags=plugin.FLAG_ESL, records=[
            make_group(b"MISC", [make_record(b"MISC", 0x00000010, [(b"EDID", b"X\0")])])])
        self.assertEqual(plugin.esl_check(nomaster)["allowed_range"], ["800", "FFF"], "the 0x001 floor needs a master")
        high = make_full_plugin(self.tmp / "hi.esl", flags=plugin.FLAG_ESL, records=[
            make_group(b"MISC", [make_record(b"MISC", 0x01001000, [(b"EDID", b"Hi\0")])])])
        self.assertIn("LIGHT-ABOVE-MAX", [e["code"] for e in plugin.esl_check(high)["errors"]])

    def test_cli_resolves_data_names(self):
        code, r = run_cli("plugin", "inspect", "Fallout4.esm")
        self.assertEqual(code, 0)
        self.assertEqual(r["hedr_version"], 1.0)


class LoadOrderTests(Base):
    def test_active_order_and_missing_masters(self):
        from f4forge import loadorder
        write(self.game / "Data" / "Needs.esp", make_plugin(1.0, 131, 1, 0, ("Fallout4.esm", "Absent.esm")))
        ptxt = write(self.tmp / "appdata" / "plugins.txt", "# comment\n*MyMod.esp\nInactive.esp\n*Needs.esp\n*Gone.esp\n")
        r = loadorder.load_order(self.game, ptxt)
        self.assertEqual(r["plugins_txt_starred"], 3)
        self.assertEqual(r["active_from_plugins_txt"], 2)
        self.assertEqual([o["plugin"] for o in r["order"]][:3], ["Fallout4.esm", "DLCCoast.esm", "ccTest-Thing.esl"])
        self.assertEqual(r["missing_files"], ["Gone.esp"])
        self.assertEqual(r["missing_masters"], [{"plugin": "Needs.esp", "missing": ["Absent.esm"]}])
        code, out = run_cli("loadorder", "--plugins-txt", str(ptxt))
        self.assertEqual(code, 1)


def _worker_ready() -> bool:
    try:
        from f4forge import records
        return records.status()["built"]
    except Exception:
        return False


def _tool_ready(tid: str) -> bool:
    try:
        from f4forge import tools
        return tools.find_exe(tid) is not None
    except Exception:
        return False


def _real_paths() -> dict:
    env = {}
    try:
        from f4forge import records, tools
        if records.status()["built"]:
            env["F4FORGE_WORKER_EXE"] = str(records.worker_exe())
        env["F4FORGE_TOOLS_ROOT"] = str(tools.tools_root())
    except Exception:
        pass
    return env


REAL_PATHS = _real_paths()


class WorkerTests(Base):
    """Uses the worker and tools of this machine (read from the real forge home before the test home is set)."""

    def setUp(self):
        super().setUp()
        self._saved = {k: os.environ.get(k) for k in REAL_PATHS}
        os.environ.update(REAL_PATHS)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    @unittest.skipUnless(_worker_ready(), "records worker not built (f4forge worker build)")
    def test_worker_new_agrees_with_python_reader(self):
        from f4forge import records
        target = self.tmp / "Agree Test.esp"
        for edid in ("AgreeA", "AgreeB"):
            r = records.call({"verb": "new", "target": str(target), "type": "MISC", "edid": edid, "light": True, "floor": 0x800})
            self.assertTrue(r["ok"], r)
        r = records.call({"verb": "new", "target": str(target), "type": "QUST", "edid": "AgreeQuest", "floor": 0x800})
        self.assertEqual(r["object_id"], "000802")
        info = plugin.inspect(target, edids=True)
        self.assertEqual(info["types"], {"MISC": 2, "QUST": 1})
        self.assertEqual(info["edid_sample"], {"AgreeA": "00000800", "AgreeB": "00000801", "AgreeQuest": "00000802"})
        self.assertTrue(info["light"])
        self.assertTrue(plugin.esl_check(target)["ok"])
        with self.assertRaises(Exception):
            records.call({"verb": "new", "target": str(target), "type": "MISC", "edid": "AgreeA", "floor": 0x800})

    @unittest.skipUnless(_worker_ready() and _tool_ready("spriggit"), "worker or Spriggit missing")
    def test_spriggit_roundtrip_of_worker_plugin(self):
        from f4forge import records, spriggit
        target = self.tmp / "Sprig.esp"
        records.call({"verb": "new", "target": str(target), "type": "MISC", "edid": "SprigItem", "floor": 0x800})
        rt = spriggit.roundtrip(target, self.tmp / "rt")
        self.assertTrue(rt["record_equal"], rt)


# --- M4: Papyrus ------------------------------------------------------------------------------------

STUBS = ROOT / "tests" / "fixtures" / "psc-stubs"
SMOKE_PSC = ('ScriptName ForgeSmokeQuest extends Quest\n\nEvent OnQuestInit()\n'
             '    Debug.Trace("smoke " + F4SE.GetVersion() + "." + F4SE.GetVersionMinor())\nEndEvent\n')
BROKEN_PSC = 'ScriptName ForgeBroken extends Quest\n\nEvent OnQuestInit()\n    Debug.Trace("x" +)\nEndEvent\n'


def make_pex(name: str, parent: str, source: str) -> bytes:
    strings = [name, parent, "", "None"]
    w = lambda s: struct.pack("<H", len(s)) + s.encode()  # noqa: E731
    body = struct.pack("<IBBHQ", 0xFA57C0DE, 3, 9, 2, 0) + w(source) + w("user") + w("machine")
    body += struct.pack("<H", len(strings)) + b"".join(w(s) for s in strings)
    body += b"\0"                     # no debug info
    body += struct.pack("<H", 0)      # no user flags
    obj = struct.pack("<HHBIH", 1, 2, 0, 0, 2) + b"\0" * 12
    body += struct.pack("<H", 1) + struct.pack("<HI", 0, len(obj) + 4) + obj
    return body


class PapyrusTests(Base):
    def test_pex_reader(self):
        from f4forge import papyrus
        info = papyrus.parse_pex(make_pex("MyQuestScript", "Quest", "C:\\src\\MyQuestScript.psc"))
        self.assertEqual((info["game"], info["version"], info["source"]), ("Fallout 4", "3.9", "C:\\src\\MyQuestScript.psc"))
        self.assertEqual(info["objects"], [{"name": "MyQuestScript", "parent": "Quest"}])
        from f4forge.util import ForgeError
        with self.assertRaises(ForgeError):
            papyrus.parse_pex(b"NOTAPEXFILE!")

    def test_diagnostic_parsers(self):
        from f4forge import papyrus
        off = papyrus.parse_diagnostics("C:\\x\\A.psc(4,21): no viable alternative at input ')'\nNo output generated", "official")
        self.assertEqual(off, [{"file": "C:\\x\\A.psc", "line": 4, "column": 21, "severity": "error",
                                "message": "no viable alternative at input ')'", "compiler": "official"}])
        cap = papyrus.parse_diagnostics("A.psc (4, 22:23): Fatal Error: Unexpected token ')'!", "caprica")
        self.assertEqual((cap[0]["line"], cap[0]["column"], cap[0]["message"]), (4, 22, "Unexpected token ')'!"))

    def test_cache_patches(self):
        from f4forge import papyrus
        d = self.tmp / "cache"
        write(d / "A.psc", " Scriptname A extends ObjectReference\n")
        write(d / "B.psc", "Scriptname B\nstruct Point\n\tstring parent\n\tfloat x\nendstruct\n")
        self.assertEqual(papyrus.patch_cache(d), ["A.psc"])
        self.assertTrue((d / "A.psc").read_text().startswith("Scriptname A"))
        ov = papyrus.caprica_overlay([d])
        self.assertEqual(ov["files"], ["B.psc"])
        self.assertIn("string parent_", Path(ov["path"], "B.psc").read_text())
        self.assertIn("string parent\n", (d / "B.psc").read_text(), "the shared cache keeps the real member name")

    def _compile(self, compiler):
        from f4forge import papyrus
        src = write(self.tmp / "src" / "ForgeSmokeQuest.psc", SMOKE_PSC)
        bad = write(self.tmp / "bad" / "ForgeBroken.psc", BROKEN_PSC)
        ok = papyrus.compile_scripts([src], self.tmp / "out", compiler, [str(STUBS)], self.game)
        self.assertTrue(ok["ok"], ok["diagnostics"])
        self.assertTrue(ok["scripts"][0]["pex_source"].endswith("ForgeSmokeQuest.psc"))
        self.assertEqual(ok["scripts"][0]["objects"], ["ForgeSmokeQuest"])
        nok = papyrus.compile_scripts([bad], self.tmp / "out2", compiler, [str(STUBS)], self.game)
        self.assertFalse(nok["ok"])
        errs = [d for d in nok["diagnostics"] if d["severity"] == "error"]
        self.assertEqual(len(errs), 1, nok["diagnostics"])
        self.assertEqual(errs[0]["line"], 4, errs)

    @unittest.skipUnless(_tool_ready("caprica"), "Caprica not installed (f4forge tools sync --only caprica --approve)")
    def test_caprica_compiles_against_stubs(self):
        os.environ.update(REAL_PATHS)
        self._compile("caprica")

    def test_official_compiles_against_stubs(self):
        from f4forge import game as G
        from f4forge import papyrus
        os.environ.pop("FALLOUT4_ROOT", None)
        if self._env.get("FALLOUT4_ROOT"):
            os.environ["FALLOUT4_ROOT"] = self._env["FALLOUT4_ROOT"]
        try:
            real = G.find_game()[0]
        except Exception:
            self.skipTest("no installed game")
        if not papyrus.official_compiler(real):
            self.skipTest("Creation Kit compiler not installed")
        self.game = real
        self._compile("official")


# --- M5: textures, materials, meshes, audio ---------------------------------------------------------

def make_png(w: int, h: int, alpha: bool = False) -> bytes:
    import zlib
    ch = 4 if alpha else 3
    raw = b"".join(b"\0" + bytes(((x * 7 + y * 3 + c * 50) & 0xFF) for x in range(w) for c in range(ch)) for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6 if alpha else 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def make_nif(textures=("textures\\a_d.dds", "textures\\a_n.dds"), material="Materials\\A.bgsm") -> bytes:
    def ss(s):
        return bytes([len(s) + 1]) + s.encode() + b"\0"

    def sz(s):
        return struct.pack("<I", len(s)) + s.encode()
    types = ["NiNode", "BSShaderTextureSet"]
    node = b"\0" * 20
    tset = struct.pack("<i", len(textures)) + b"".join(sz(t) for t in textures)
    head = b"Gamebryo File Format, Version 20.2.0.7\n" + struct.pack("<IBII", 0x14020007, 1, 12, 2)
    head += struct.pack("<I", 130) + ss("forge") + ss("") + ss("test") + ss("max")
    head += struct.pack("<H", len(types)) + b"".join(sz(t) for t in types)
    head += struct.pack("<HH", 0, 1) + struct.pack("<II", len(node), len(tset))
    head += struct.pack("<II", 1, len(material)) + sz(material) + struct.pack("<I", 0)
    return head + node + tset + struct.pack("<II", 1, 0)


def make_wav(path: Path, rate=44100, channels=1, bits=16, seconds=0.2) -> Path:
    n = int(rate * seconds)
    data = bytes((i * 37) & 0xFF for i in range(n * channels * bits // 8))
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" + b"fmt " + struct.pack(
        "<IHHIIHH", 16, 1, channels, rate, rate * channels * bits // 8, channels * bits // 8, bits)
    return write(path, hdr + b"data" + struct.pack("<I", len(data)) + data)


class AssetTests(Base):
    def test_material_json_roundtrip_both_kinds(self):
        from f4forge import bgsm
        for kind, fields in (("BGSM", bgsm.BGSM), ("BGEM", bgsm.BGEM)):
            doc = {"Type": kind}
            for name, typ, cond in bgsm.BASE + fields:
                if cond is None or cond(doc.get("Version", 2), doc):
                    doc[name] = {"u32": 2 if name == "Version" else 0, "f32": 0.5, "u8": 3, "bool": True,
                                 "str": f"textures\\x\\{name}.dds", "color": [1.0, 0.5, 0.25]}[typ]
            doc["Version"] = 2
            data = bgsm.build(doc)
            back = bgsm.parse(data)
            self.assertEqual(bgsm.build(json.loads(json.dumps(back))), data, kind)
            self.assertTrue(bgsm.textures(back))
        j = bgsm.parse(b'{\r\n "sDiffuseTexture" : "x_d.dds"\r\n}')
        self.assertEqual(j["Type"], "JSON")
        self.assertEqual(bgsm.textures(j), {"sDiffuseTexture": "x_d.dds"})

    def test_texture_roles_and_inspect(self):
        from f4forge import textures
        self.assertEqual(textures.role_for("Gun_d.dds"), "diffuse")
        self.assertEqual(textures.role_for("Face_msn.dds"), "facemask")
        self.assertEqual(textures.role_for("Gun_n.DDS"), "normal")
        good = textures.inspect(write(self.tmp / "Gun_n.dds", make_dds(256, 256, 9, 83)))
        self.assertTrue(good["ok"])
        self.assertEqual(good["warnings"], [])
        odd = textures.inspect(write(self.tmp / "Gun_s.dds", make_dds(256, 256, 3, 71)))
        self.assertEqual(sorted(w["code"] for w in odd["warnings"]), ["TEX-FORMAT", "TEX-MIPS"])

    @unittest.skipUnless(_tool_ready("directxtex"), "texconv not installed")
    def test_png_converts_to_each_preset(self):
        os.environ.update(REAL_PATHS)
        from f4forge import textures
        png = write(self.tmp / "src.png", make_png(64, 64, alpha=True))
        for role in ("diffuse", "normal", "specular", "glow", "generic"):
            r = textures.convert(png, self.tmp / "out", role, name=f"T_{role}.png")
            self.assertEqual(r["inspect"]["format_name"], textures.rules()["roles"][role]["format"], role)
            self.assertEqual(r["inspect"]["mips"], 7, role)

    def test_nif_header_and_refs(self):
        from f4forge import nif
        p = write(self.tmp / "Meshes" / "A.nif", make_nif())
        i = nif.info(p)
        self.assertEqual((i["version"], i["user_version"], i["bs_version"], i["blocks"], i["roots"]), ("20.2.0.7", 12, 130, 2, 1))
        self.assertTrue(i["size_ok"])
        r = nif.check_refs(p, None, {"textures\\a_d.dds", "materials\\a.bgsm"})
        self.assertEqual([m["path"] for m in r["missing"]], ["textures\\a_n.dds"])
        from f4forge.util import ForgeError
        with self.assertRaises(ForgeError):
            nif.read(write(self.tmp / "x.nif", b"not a nif at all"))

    def test_fuz_wav_and_voice_path(self):
        from f4forge import audio
        data = audio.fuz_pack(b"LIPDATA", b"RIFFxxxxXWMA")
        self.assertEqual(audio.fuz_unpack(data), (b"LIPDATA", b"RIFFxxxxXWMA"))
        self.assertTrue(audio.wav_check(make_wav(self.tmp / "ok.wav"))["ok"])
        bad = audio.wav_check(make_wav(self.tmp / "st.wav", channels=2, bits=8))
        self.assertEqual(sorted(e["code"] for e in bad["errors"]), ["WAV-BITS", "WAV-CHANNELS"])
        self.assertEqual(audio.voice_path("My Mod.esp", "NPCMBoston", "0100ABCD", 2),
                         "Sound/Voice/My Mod.esp/NPCMBoston/0000ABCD_2.fuz")
        from f4forge.util import ForgeError
        with self.assertRaises(ForgeError):
            audio.encode(self.tmp / "ok.wav", self.tmp / "o.xwm", self.game / "nope")


if __name__ == "__main__":
    unittest.main()
