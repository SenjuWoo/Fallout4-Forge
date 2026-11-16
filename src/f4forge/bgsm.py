"""BGSM and BGEM materials to JSON and back, byte for byte.

Field order and version conditions follow ousnius/Material-Editor (MIT) MaterialLib/BaseMaterialFile.cs,
BGSM.cs and BGEM.cs at commit 21411873f17454a2442d6785d533499e14c63adb (fact material.layout). Values are
kept raw (booleans as their byte, the alpha blend mode as its three stored numbers, colors as three
floats) so that writing the JSON back reproduces the original file exactly.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from .util import ForgeError

SIG = {b"BGSM": "BGSM", b"BGEM": "BGEM"}

# (name, type, condition(version, values) or None). Types: u32 f32 u8 bool str color
BASE = [
    ("Version", "u32", None), ("TileFlags", "u32", None),
    ("UOffset", "f32", None), ("VOffset", "f32", None), ("UScale", "f32", None), ("VScale", "f32", None),
    ("Alpha", "f32", None), ("AlphaBlendMode0", "u8", None), ("AlphaBlendMode1", "u32", None),
    ("AlphaBlendMode2", "u32", None), ("AlphaTestRef", "u8", None), ("AlphaTest", "bool", None),
    ("ZBufferWrite", "bool", None), ("ZBufferTest", "bool", None), ("ScreenSpaceReflections", "bool", None),
    ("WetnessControlScreenSpaceReflections", "bool", None), ("Decal", "bool", None), ("TwoSided", "bool", None),
    ("DecalNoFade", "bool", None), ("NonOccluder", "bool", None), ("Refraction", "bool", None),
    ("RefractionFalloff", "bool", None), ("RefractionPower", "f32", None),
    ("EnvironmentMapping", "bool", lambda v, d: v < 10), ("EnvironmentMappingMaskScale", "f32", lambda v, d: v < 10),
    ("DepthBias", "bool", lambda v, d: v >= 10),
    ("GrayscaleToPaletteColor", "bool", None), ("MaskWrites", "u8", lambda v, d: v >= 6),
]

BGSM = [
    ("DiffuseTexture", "str", None), ("NormalTexture", "str", None), ("SmoothSpecTexture", "str", None),
    ("GreyscaleTexture", "str", None),
    ("GlowTexture", "str", lambda v, d: v > 2), ("WrinklesTexture", "str", lambda v, d: v > 2),
    ("SpecularTexture", "str", lambda v, d: v > 2), ("LightingTexture", "str", lambda v, d: v > 2),
    ("FlowTexture", "str", lambda v, d: v > 2), ("DistanceFieldAlphaTexture", "str", lambda v, d: v >= 17),
    ("EnvmapTexture", "str", lambda v, d: v <= 2), ("GlowTexture", "str", lambda v, d: v <= 2),
    ("InnerLayerTexture", "str", lambda v, d: v <= 2), ("WrinklesTexture", "str", lambda v, d: v <= 2),
    ("DisplacementTexture", "str", lambda v, d: v <= 2),
    ("EnableEditorAlphaRef", "bool", None),
    ("Translucency", "bool", lambda v, d: v >= 8), ("TranslucencyThickObject", "bool", lambda v, d: v >= 8),
    ("TranslucencyMixAlbedoWithSubsurfaceColor", "bool", lambda v, d: v >= 8),
    ("TranslucencySubsurfaceColor", "color", lambda v, d: v >= 8),
    ("TranslucencyTransmissiveScale", "f32", lambda v, d: v >= 8), ("TranslucencyTurbulence", "f32", lambda v, d: v >= 8),
    ("RimLighting", "bool", lambda v, d: v < 8), ("RimPower", "f32", lambda v, d: v < 8),
    ("BackLightPower", "f32", lambda v, d: v < 8), ("SubsurfaceLighting", "bool", lambda v, d: v < 8),
    ("SubsurfaceLightingRolloff", "f32", lambda v, d: v < 8),
    ("SpecularEnabled", "bool", None), ("SpecularColor", "color", None), ("SpecularMult", "f32", None),
    ("Smoothness", "f32", None), ("FresnelPower", "f32", None), ("WetnessControlSpecScale", "f32", None),
    ("WetnessControlSpecPowerScale", "f32", None), ("WetnessControlSpecMinvar", "f32", None),
    ("WetnessControlEnvMapScale", "f32", lambda v, d: v < 10),
    ("WetnessControlFresnelPower", "f32", None), ("WetnessControlMetalness", "f32", None),
    ("PBR", "bool", lambda v, d: v > 2), ("CustomPorosity", "bool", lambda v, d: v >= 9),
    ("PorosityValue", "f32", lambda v, d: v >= 9),
    ("RootMaterialPath", "str", None), ("AnisoLighting", "bool", None), ("EmitEnabled", "bool", None),
    ("EmittanceColor", "color", lambda v, d: bool(d.get("EmitEnabled"))),
    ("EmittanceMult", "f32", None), ("ModelSpaceNormals", "bool", None), ("ExternalEmittance", "bool", None),
    ("LumEmittance", "f32", lambda v, d: v >= 12),
    ("UseAdaptativeEmissive", "bool", lambda v, d: v >= 13),
    ("AdaptativeEmissive_ExposureOffset", "f32", lambda v, d: v >= 13),
    ("AdaptativeEmissive_FinalExposureMin", "f32", lambda v, d: v >= 13),
    ("AdaptativeEmissive_FinalExposureMax", "f32", lambda v, d: v >= 13),
    ("BackLighting", "bool", lambda v, d: v < 8),
    ("ReceiveShadows", "bool", None), ("HideSecret", "bool", None), ("CastShadows", "bool", None),
    ("DissolveFade", "bool", None), ("AssumeShadowmask", "bool", None), ("Glowmap", "bool", None),
    ("EnvironmentMappingWindow", "bool", lambda v, d: v < 7), ("EnvironmentMappingEye", "bool", lambda v, d: v < 7),
    ("Hair", "bool", None), ("HairTintColor", "color", None), ("Tree", "bool", None), ("Facegen", "bool", None),
    ("SkinTint", "bool", None), ("Tessellate", "bool", None),
    ("DisplacementTextureBias", "f32", lambda v, d: v < 3), ("DisplacementTextureScale", "f32", lambda v, d: v < 3),
    ("TessellationPnScale", "f32", lambda v, d: v < 3), ("TessellationBaseFactor", "f32", lambda v, d: v < 3),
    ("TessellationFadeDistance", "f32", lambda v, d: v < 3),
    ("GrayscaleToPaletteScale", "f32", None), ("SkewSpecularAlpha", "bool", lambda v, d: v >= 1),
    ("Terrain", "bool", lambda v, d: v >= 3),
    ("UnkInt1", "u32", lambda v, d: v == 3 and bool(d.get("Terrain"))),
    ("TerrainThresholdFalloff", "f32", lambda v, d: v >= 3 and bool(d.get("Terrain"))),
    ("TerrainTilingDistance", "f32", lambda v, d: v >= 3 and bool(d.get("Terrain"))),
    ("TerrainRotationAngle", "f32", lambda v, d: v >= 3 and bool(d.get("Terrain"))),
]

BGEM = [
    ("BaseTexture", "str", None), ("GrayscaleTexture", "str", None), ("EnvmapTexture", "str", None),
    ("NormalTexture", "str", None), ("EnvmapMaskTexture", "str", None),
    ("SpecularTexture", "str", lambda v, d: v >= 11), ("LightingTexture", "str", lambda v, d: v >= 11),
    ("GlowTexture", "str", lambda v, d: v >= 11),
    ("GlassRoughnessScratch", "str", lambda v, d: v >= 21), ("GlassDirtOverlay", "str", lambda v, d: v >= 21),
    ("GlassEnabled", "bool", lambda v, d: v >= 21),
    ("GlassFresnelColor", "color", lambda v, d: v >= 21 and bool(d.get("GlassEnabled"))),
    ("GlassBlurScaleBase", "f32", lambda v, d: v >= 21 and bool(d.get("GlassEnabled"))),
    ("GlassBlurScaleFactor", "f32", lambda v, d: v >= 22 and bool(d.get("GlassEnabled"))),
    ("GlassRefractionScaleBase", "f32", lambda v, d: v >= 21 and bool(d.get("GlassEnabled"))),
    ("EnvironmentMapping", "bool", lambda v, d: v >= 10), ("EnvironmentMappingMaskScale", "f32", lambda v, d: v >= 10),
    ("BloodEnabled", "bool", None), ("EffectLightingEnabled", "bool", None), ("FalloffEnabled", "bool", None),
    ("FalloffColorEnabled", "bool", None), ("GrayscaleToPaletteAlpha", "bool", None), ("SoftEnabled", "bool", None),
    ("BaseColor", "color", None), ("BaseColorScale", "f32", None), ("FalloffStartAngle", "f32", None),
    ("FalloffStopAngle", "f32", None), ("FalloffStartOpacity", "f32", None), ("FalloffStopOpacity", "f32", None),
    ("LightingInfluence", "f32", None), ("EnvmapMinLOD", "u8", None), ("SoftDepth", "f32", None),
    ("EmittanceColor", "color", lambda v, d: v >= 11),
    ("AdaptativeEmissive_ExposureOffset", "f32", lambda v, d: v >= 15),
    ("AdaptativeEmissive_FinalExposureMin", "f32", lambda v, d: v >= 15),
    ("AdaptativeEmissive_FinalExposureMax", "f32", lambda v, d: v >= 15),
    ("Glowmap", "bool", lambda v, d: v >= 16), ("EffectPbrSpecular", "bool", lambda v, d: v >= 20),
]

TEXTURE_FIELDS = {n for n, t, _ in BGSM + BGEM if t == "str" and n != "RootMaterialPath"}


def _read(data: bytes, pos: int, typ: str):
    if typ == "u32":
        return struct.unpack_from("<I", data, pos)[0], pos + 4
    if typ == "f32":
        return struct.unpack_from("<f", data, pos)[0], pos + 4
    if typ in ("u8", "bool"):
        b = data[pos]
        return (bool(b) if typ == "bool" and b in (0, 1) else b), pos + 1
    if typ == "color":
        return list(struct.unpack_from("<fff", data, pos)), pos + 12
    if typ == "str":
        n = struct.unpack_from("<I", data, pos)[0]
        raw = data[pos + 4:pos + 4 + n]
        if len(raw) != n:
            raise ForgeError("material string runs past the end of the file", "the material is truncated")
        if raw.endswith(b"\0") and b"\0" not in raw[:-1]:
            return raw[:-1].decode("latin-1"), pos + 4 + n
        return {"raw_hex": raw.hex()}, pos + 4 + n
    raise ValueError(typ)


def _write(typ: str, v) -> bytes:
    if typ == "u32":
        return struct.pack("<I", int(v))
    if typ == "f32":
        return struct.pack("<f", float(v))
    if typ in ("u8", "bool"):
        return bytes([int(v)])
    if typ == "color":
        return struct.pack("<fff", *[float(x) for x in v])
    if typ == "str":
        raw = bytes.fromhex(v["raw_hex"]) if isinstance(v, dict) else (v or "").encode("latin-1") + b"\0"
        return struct.pack("<I", len(raw)) + raw
    raise ValueError(typ)


def parse(data: bytes) -> dict:
    kind = SIG.get(data[:4])
    if not kind and data.decode("utf-8-sig", "replace").lstrip()[:1] == "{":
        # JSON-text materials are accepted by the game too (vanilla Fallout4 - Startup.ba2 ships some).
        try:
            return {"Type": "JSON", "Json": json.loads(data.decode("utf-8-sig"))}
        except ValueError as e:
            raise ForgeError(f"JSON material does not parse: {e}", "fix the JSON")
    if not kind:
        raise ForgeError("not a BGSM or BGEM file", "pass a Fallout 4 material")
    out = {"Type": kind}
    pos = 4
    try:
        for name, typ, cond in BASE + (BGSM if kind == "BGSM" else BGEM):
            if cond is None or cond(out.get("Version", 0), out):
                out[name], pos = _read(data, pos, typ)
    except (struct.error, IndexError):
        raise ForgeError(f"{kind} version {out.get('Version')} ends early at byte {pos}", "the material is truncated")
    if pos != len(data):
        out["TrailingHex"] = data[pos:].hex()
    return out


def build(doc: dict) -> bytes:
    kind = doc.get("Type")
    if kind == "JSON":
        return (json.dumps(doc["Json"], indent=3) + chr(10)).encode("utf-8")
    if kind not in ("BGSM", "BGEM"):
        raise ForgeError("material JSON needs Type BGSM or BGEM", "export one with f4forge material show")
    out = bytearray(kind.encode())
    for name, typ, cond in BASE + (BGSM if kind == "BGSM" else BGEM):
        if cond is None or cond(doc.get("Version", 0), doc):
            if name not in doc:
                raise ForgeError(f"material JSON lacks {name} (needed for version {doc.get('Version')})",
                                 "start from f4forge material show of a similar material")
            out += _write(typ, doc[name])
    if doc.get("TrailingHex"):
        out += bytes.fromhex(doc["TrailingHex"])
    return bytes(out)


def textures(doc: dict) -> dict:
    if doc.get("Type") == "JSON":
        return {k: v for k, v in doc["Json"].items() if k.startswith("s") and k.endswith("Texture") and isinstance(v, str) and v}
    return {k: v for k, v in doc.items() if k in TEXTURE_FIELDS and isinstance(v, str) and v}


def to_json(doc: dict) -> str:
    return json.dumps(doc, indent=2)


def roundtrip_archive(archive: Path) -> dict:
    from . import ba2
    arc = ba2.Archive(archive)
    n, same, json_text, bad, versions = 0, 0, 0, [], {}
    with open(arc.path, "rb") as f:
        for e in arc.entries:
            if not e["name"].lower().endswith((".bgsm", ".bgem")):
                continue
            n += 1
            data = arc.read(e, f)
            try:
                doc = parse(data)
                if doc["Type"] == "JSON":
                    versions["JSON text"] = versions.get("JSON text", 0) + 1
                    json_text += 1  # read and written as JSON; formatting is not byte-preserved
                    continue
                key = f"{doc['Type']} v{doc['Version']}"
                versions[key] = versions.get(key, 0) + 1
                rebuilt = build(json.loads(json.dumps(doc)))
                if rebuilt == data:
                    same += 1
                else:
                    bad.append(e["name"])
            except ForgeError as ex:
                bad.append(f"{e['name']}: {ex}")
    return {"archive": str(archive), "materials": n, "byte_identical": same, "json_text": json_text, "failed": bad[:20],
            "failed_count": len(bad), "versions": dict(sorted(versions.items()))}
