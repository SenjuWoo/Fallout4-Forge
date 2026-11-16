"""Textures: inspect DDS files against the role rules, convert images through texconv with role presets."""
from __future__ import annotations

from pathlib import Path

from . import dds
from .util import KNOWLEDGE_DIR, ForgeError, load_json, run


def rules() -> dict:
    return load_json(KNOWLEDGE_DIR / "textures.json")


def role_for(name: str) -> str:
    stem = Path(name).stem.lower()
    best, blen = "generic", 0
    for role, r in rules()["roles"].items():
        for suf in r["suffixes"]:
            if stem.endswith(suf) and len(suf) > blen:
                best, blen = role, len(suf)
    return best


def inspect(path: Path, role: str | None = None) -> dict:
    path = Path(path)
    info = dds.parse(path.read_bytes())
    r = rules()
    role = role or role_for(path.name)
    rr = r["roles"][role]
    errors, warnings = [], []
    w, h = info["width"], info["height"]
    if w & (w - 1) or h & (h - 1):
        errors.append({"code": "TEX-NOT-POW2", "message": f"{w}x{h} is not a power of two", "fix": "resize to powers of two"})
    full = max(w, h).bit_length()
    allowed_single = any(k in str(path).lower() for k in r["single_mip_allowed"])
    if rr["mips"] and info["mips"] != full and not (info["mips"] == 1 and allowed_single):
        warnings.append({"code": "TEX-MIPS", "message": f"{info['mips']} mips, a full chain is {full}",
                         "fix": "f4forge tex convert (generates mips)"})
    if max(w, h) > r["max_dimension"]:
        errors.append({"code": "TEX-TOO-BIG", "message": f"{max(w, h)} px exceeds {r['max_dimension']}", "fix": "downscale"})
    elif max(w, h) > r["warn_dimension"]:
        warnings.append({"code": "TEX-LARGE", "message": f"{max(w, h)} px; vanilla rarely goes above {r['warn_dimension']}",
                         "fix": "check the VRAM budget"})
    expected = [rr["format"]] + [rr[k] for k in ("format_alpha", "format_noalpha") if k in rr]
    if info["format_name"] not in expected:
        warnings.append({"code": "TEX-FORMAT", "message": f"{info['format_name']} for a {role} texture; vanilla uses "
                         f"{' or '.join(expected)}", "fix": f"f4forge tex convert --role {role}"})
    if info.get("payload_expected") is not None and info["payload_bytes"] < info["payload_expected"]:
        errors.append({"code": "TEX-TRUNCATED", "message": f"payload {info['payload_bytes']} < {info['payload_expected']} bytes",
                       "fix": "re-export the texture"})
    return {"file": str(path), "role": role, **{k: info[k] for k in ("width", "height", "mips", "format_name", "cubemap")},
            "ok": not errors, "errors": errors, "warnings": warnings, "fact": r["fact"]}


def texconv() -> Path:
    from .tools import tool_path
    d = tool_path("directxtex")
    if not d or not (d / "texconv.exe").is_file():
        raise ForgeError("texconv is not installed", "f4forge tools sync --only directxtex --approve")
    return d / "texconv.exe"


def convert(src: Path, out_dir: Path, role: str | None = None, alpha: bool = False, fmt: str | None = None,
            name: str | None = None) -> dict:
    r = rules()
    role = role or role_for(name or src.name)
    if role not in r["roles"]:
        raise ForgeError(f"unknown texture role {role}", "roles: " + ", ".join(r["roles"]))
    rr = r["roles"][role]
    fmt = fmt or (rr.get("format_alpha") if alpha and "format_alpha" in rr else rr["format"])
    out_dir.mkdir(parents=True, exist_ok=True)
    argv = [str(texconv()), "-nologo", "-y", "-f", fmt, "-m", "0" if rr["mips"] else "1", "-o", str(out_dir)]
    argv.append(str(src))
    res = run(argv, timeout=600)
    produced = out_dir / (Path(src).stem + ".dds")
    if not res["ok"] or not produced.is_file():
        raise ForgeError("texconv failed: " + ((res.get("stdout") or "") + (res.get("stderr") or ""))[-500:],
                         "check the input image")
    final = produced
    if name and Path(name).stem != produced.stem:
        final = out_dir / (Path(name).stem + ".dds")
        produced.replace(final)
    return {"input": str(src), "output": str(final), "role": role, "format": fmt, "inspect": inspect(final, role)}
