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


if __name__ == "__main__":
    unittest.main()
