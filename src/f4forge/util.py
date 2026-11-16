"""Small shared helpers: errors, JSON output, files, hashes, external processes."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = PKG_DIR / "knowledge"
TEMPLATES_DIR = PKG_DIR / "templates"


class ForgeError(Exception):
    """An expected failure with a named cause and a fix. Exit code 2 unless given."""

    def __init__(self, message: str, fix: str = "", code: int = 2):
        super().__init__(message)
        self.fix = fix
        self.code = code


def dumps(value, pretty: bool = False) -> str:
    kw = {"indent": 2} if pretty else {"separators": (",", ":")}
    return json.dumps(value, ensure_ascii=False, default=str, **kw)


def emit(value, pretty: bool = False) -> None:
    try:
        sys.stdout.write(dumps(value, pretty) + "\n")
    except UnicodeEncodeError:
        kw = {"indent": 2} if pretty else {"separators": (",", ":")}
        sys.stdout.write(json.dumps(value, ensure_ascii=True, default=str, **kw) + "\n")


def load_json(path: Path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path: Path, value) -> None:
    """Atomic write: temp file in the same folder, then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path, limit: int | None = None) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read(limit) if limit else f.read()


def iter_files(root: Path, suffixes: tuple[str, ...] | None = None):
    """Sorted, deterministic walk. Suffixes are matched case-insensitively."""
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if suffixes is None or name.lower().endswith(suffixes):
                yield Path(dirpath) / name


def ci_child(parent: Path, name: str) -> Path | None:
    """Case-insensitive child lookup (game folders mix case; CI runs on Linux too)."""
    p = parent / name
    if p.exists():
        return p
    if not parent.is_dir():
        return None
    low = name.lower()
    for c in parent.iterdir():
        if c.name.lower() == low:
            return c
    return None


def ci_path(root: Path, relpath: str) -> Path | None:
    cur = root
    for part in relpath.replace("\\", "/").split("/"):
        if not part:
            continue
        nxt = ci_child(cur, part)
        if nxt is None:
            return None
        cur = nxt
    return cur


def run(argv: list[str], timeout: int = 120, cwd: Path | None = None, input_text: str | None = None,
        env: dict | None = None) -> dict:
    """Run a program from an argv list (never a shell string). Output is captured."""
    try:
        cp = subprocess.run([str(a) for a in argv], capture_output=True, text=True, errors="replace", encoding="utf-8",
                            timeout=timeout, cwd=str(cwd) if cwd else None, input=input_text,
                            stdin=None if input_text is not None else subprocess.DEVNULL,
                            env={**os.environ, **env} if env else None)
    except FileNotFoundError as e:
        return {"ok": False, "exit": None, "error": f"not found: {e}"}
    except OSError as e:
        return {"ok": False, "exit": None, "error": f"cannot run {argv[0]}: {e}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit": None, "error": f"timed out after {timeout}s"}
    return {"ok": cp.returncode == 0, "exit": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}
