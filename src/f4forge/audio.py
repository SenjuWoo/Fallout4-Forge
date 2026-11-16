"""Audio and voice: native FUZ pack/unpack and WAV checks; XWM through xwmaencode, LIP through LipGenerator
(both ship with the Creation Kit); voice files laid out as Sound/Voice/<Plugin>/<VoiceType>/<INFO>_<n>.fuz.

FUZ (fact audio.fuz): "FUZE", u32 version 1, u32 LIP size, LIP bytes, then the audio (RIFF XWMA).
Without the Creation Kit, encode/lip/voice report a named gap; FUZ and WAV work everywhere.
"""
from __future__ import annotations

import shutil
import struct
import tempfile
from pathlib import Path

from .util import KNOWLEDGE_DIR, ForgeError, ci_path, load_json, run


def rules() -> dict:
    return load_json(KNOWLEDGE_DIR / "audio.json")


def fuz_unpack(data: bytes) -> tuple[bytes, bytes]:
    if len(data) < 12 or data[:4] != b"FUZE":
        raise ForgeError("not a FUZ file (no FUZE magic)", "pass a .fuz")
    ver, lip_size = struct.unpack_from("<II", data, 4)
    if 12 + lip_size > len(data):
        raise ForgeError("FUZ LIP size runs past the end", "the file is truncated")
    return data[12:12 + lip_size], data[12 + lip_size:]


def fuz_pack(lip: bytes, audio: bytes) -> bytes:
    return b"FUZE" + struct.pack("<II", 1, len(lip)) + lip + audio


def riff_info(data: bytes) -> dict:
    if data[:4] != b"RIFF":
        raise ForgeError("not a RIFF file", "pass a WAV or XWM")
    kind = data[8:12].decode("ascii", "replace")
    pos, out = 12, {"riff": kind}
    while pos + 8 <= len(data):
        cid, size = struct.unpack_from("<4sI", data, pos)
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt " and len(body) >= 16:
            tag, ch, rate, byterate, align, bits = struct.unpack_from("<HHIIHH", body)
            out.update(format_tag=tag, channels=ch, sample_rate=rate, bits=bits, byte_rate=byterate)
        elif cid == b"data":
            out["data_bytes"] = size
        pos += 8 + size + (size & 1)
    if out.get("byte_rate") and out.get("data_bytes") is not None and kind == "WAVE":
        out["seconds"] = round(out["data_bytes"] / out["byte_rate"], 3)
    return out


def wav_check(path: Path) -> dict:
    r = rules()["wav"]
    info = riff_info(Path(path).read_bytes())
    errors, warnings = [], []
    if info.get("riff") != "WAVE":
        errors.append({"code": "WAV-NOT-WAVE", "message": f"RIFF type {info.get('riff')}", "fix": "export a WAV"})
    if info.get("format_tag") != 1:
        errors.append({"code": "WAV-NOT-PCM", "message": f"format tag {info.get('format_tag')}", "fix": "export 16-bit PCM"})
    if info.get("bits") != r["bits"]:
        errors.append({"code": "WAV-BITS", "message": f"{info.get('bits')}-bit", "fix": f"export {r['bits']}-bit PCM"})
    if info.get("channels") != r["channels"]:
        errors.append({"code": "WAV-CHANNELS", "message": f"{info.get('channels')} channels", "fix": "export mono"})
    if info.get("sample_rate") not in r["sample_rates"]:
        warnings.append({"code": "WAV-RATE", "message": f"{info.get('sample_rate')} Hz", "fix": f"use {r['sample_rates'][0]} Hz"})
    return {"file": str(path), **info, "ok": not errors, "errors": errors, "warnings": warnings, "fact": r["fact"]}


def _ck_tool(game_root: Path | None, rel: str, name: str) -> Path:
    p = ci_path(game_root, rel) if game_root else None
    if not p:
        raise ForgeError(f"{name} not found (Creation Kit tier gap)",
                         "install the Creation Kit (Steam app 1946160); FUZ pack/unpack and WAV checks still work")
    return p


def encode(wav: Path, out: Path, game_root: Path | None, bitrate: int | None = None) -> dict:
    exe = _ck_tool(game_root, "Tools/Audio/xwmaencode.exe", "xwmaencode")
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = [str(exe)] + (["-b", str(bitrate)] if bitrate else []) + [str(wav), str(out)]
    r = run(argv, timeout=600)
    if not r["ok"] or not out.is_file():
        raise ForgeError("xwmaencode failed: " + ((r.get("stdout") or "") + (r.get("stderr") or ""))[-400:], "check the WAV")
    return {"wav": str(wav), "xwm": str(out), "bytes": out.stat().st_size, "info": riff_info(out.read_bytes())}


def lip(wav: Path, text: str, out: Path, game_root: Path | None, language: str = "USEnglish") -> dict:
    """LipGenerator <wav> "<text>" [-Language:..] (command line from the tool's own usage text, fact audio.lipgen).
    It writes <wav stem>.lip beside the WAV, so it runs on a temp copy and the result is moved."""
    exe = _ck_tool(game_root, "Tools/LipGen/LipGenerator/LipGenerator.exe", "LipGenerator")
    tmp = Path(tempfile.mkdtemp(prefix="f4f-lip-"))
    try:
        w = tmp / (out.stem + ".wav")
        shutil.copy2(wav, w)
        r = run([str(exe), str(w), text, f"-Language:{language}"], timeout=600, cwd=exe.parent)
        produced = w.with_suffix(".lip")
        if not produced.is_file():
            raise ForgeError("LipGenerator wrote no .lip: " + ((r.get("stdout") or "") + (r.get("stderr") or ""))[-400:],
                             "check the WAV is 16-bit PCM mono and the text matches the line")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), str(out))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"wav": str(wav), "lip": str(out), "bytes": out.stat().st_size}


def voice_path(plugin: str, voice_type: str, info_formid: str, response: int = 1) -> str:
    fid = int(info_formid, 16) & 0xFFFFFF if isinstance(info_formid, str) else int(info_formid) & 0xFFFFFF
    return rules()["voice"]["path"].format(plugin=plugin, voicetype=voice_type, info=fid, response=response)


def voice(wav: Path, text: str, data_root: Path, plugin: str, voice_type: str, info_formid: str, response: int,
          game_root: Path | None) -> dict:
    chk = wav_check(wav)
    if not chk["ok"]:
        raise ForgeError("WAV fails the voice rules: " + "; ".join(e["message"] for e in chk["errors"]),
                         chk["errors"][0]["fix"])
    rel = voice_path(plugin, voice_type, info_formid, response)
    target = data_root / rel
    tmp = Path(tempfile.mkdtemp(prefix="f4f-voice-"))
    try:
        x = encode(wav, tmp / "line.xwm", game_root)
        lp = lip(wav, text, tmp / "line.lip", game_root)
        data = fuz_pack(Path(lp["lip"]).read_bytes(), Path(x["xwm"]).read_bytes())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    l2, a2 = fuz_unpack(target.read_bytes())
    return {"fuz": str(target), "data_path": rel, "bytes": len(data), "lip_bytes": len(l2), "xwm_bytes": len(a2),
            "unpacks": 12 + len(l2) + len(a2) == len(data)}
