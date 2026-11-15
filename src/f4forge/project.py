"""Mod projects: manifest f4forge.json, layout data/ plugin/ source/ build/, scaffolding, version bumps."""
from __future__ import annotations

from pathlib import Path

from .util import ForgeError, load_json

MANIFEST = "f4forge.json"


def find_project(explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit)
        if (p / MANIFEST).is_file():
            return p
        raise ForgeError(f"no {MANIFEST} in {p}", "create a project with: f4forge new <Name> --kind <kind>")
    cur = Path.cwd()
    for d in [cur, *cur.parents]:
        if (d / MANIFEST).is_file():
            return d
    raise ForgeError(f"not inside a project (no {MANIFEST} here or above)", "pass --project <folder> or cd into one")


def load_manifest(root: Path) -> dict:
    try:
        return load_json(root / MANIFEST)
    except (OSError, ValueError) as e:
        raise ForgeError(f"{MANIFEST} unreadable: {e}", f"fix {root / MANIFEST}")


def plugin_name(manifest: dict) -> str:
    p = manifest.get("plugin") or {}
    if not p.get("name"):
        raise ForgeError("this project has no plugin", "add one: f4forge new ... --kind plugin")
    return p["name"]


def plugin_build_path(root: Path, manifest: dict) -> Path:
    return root / "build" / "data" / plugin_name(manifest)
