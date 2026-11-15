r"""The forge home: config, caches, logs, the records worker. Never inside the game folder.

Resolution: F4FORGE_HOME, else %LOCALAPPDATA%\Fallout4Forge, else ~/.cache/fallout4-forge
(non-Windows CI). config.json there holds tools_root, workspace_root and game_root.
"""
from __future__ import annotations

import os
from pathlib import Path

from .util import ForgeError, load_json, save_json

ENV_HOME = "F4FORGE_HOME"
CONFIG_KEYS = ("tools_root", "workspace_root", "game_root")


def home_dir() -> Path:
    env = os.environ.get(ENV_HOME)
    if env:
        return Path(env)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "Fallout4Forge"
    return Path.home() / ".cache" / "fallout4-forge"


def config_path() -> Path:
    return home_dir() / "config.json"


def load_config() -> dict:
    p = config_path()
    if not p.is_file():
        return {}
    try:
        data = load_json(p)
    except (OSError, ValueError) as e:
        raise ForgeError(f"config.json is not valid JSON: {e}", f"fix or delete {p}")
    return data if isinstance(data, dict) else {}


def config_value(key: str) -> str | None:
    v = load_config().get(key)
    return v if isinstance(v, str) and v else None


def set_config(pairs: dict[str, str | None]) -> dict:
    """Set or clear (None/empty) known keys; unknown keys are a named failure."""
    bad = [k for k in pairs if k not in CONFIG_KEYS]
    if bad:
        raise ForgeError(f"unknown config key(s): {', '.join(bad)}", f"known keys: {', '.join(CONFIG_KEYS)}")
    cfg = load_config()
    for k, v in pairs.items():
        if v:
            cfg[k] = str(Path(v))
        else:
            cfg.pop(k, None)
    save_json(config_path(), cfg)
    return cfg
