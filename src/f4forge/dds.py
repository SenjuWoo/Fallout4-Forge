"""DDS headers: parse (legacy and DX10 extension), build, and mip sizes per DXGI format.

Layout from the Microsoft DDS programming guide (primary): magic "DDS ", DDS_HEADER (124 bytes),
DDS_PIXELFORMAT (32 bytes inside it), optional DDS_HEADER_DXT10 (20 bytes) when the FourCC is "DX10".
"""
from __future__ import annotations

import struct

from .util import ForgeError

# DXGI code: (name, block bytes for BC formats or 0, bits per pixel for uncompressed or 0)
DXGI = {
    2: ("R32G32B32A32_FLOAT", 0, 128), 10: ("R16G16B16A16_FLOAT", 0, 64), 11: ("R16G16B16A16_UNORM", 0, 64),
    24: ("R10G10B10A2_UNORM", 0, 32), 28: ("R8G8B8A8_UNORM", 0, 32), 29: ("R8G8B8A8_UNORM_SRGB", 0, 32),
    34: ("R16G16_FLOAT", 0, 32), 35: ("R16G16_UNORM", 0, 32), 41: ("R32_FLOAT", 0, 32),
    49: ("R8G8_UNORM", 0, 16), 54: ("R16_FLOAT", 0, 16), 56: ("R16_UNORM", 0, 16),
    61: ("R8_UNORM", 0, 8), 65: ("A8_UNORM", 0, 8),
    70: ("BC1_TYPELESS", 8, 0), 71: ("BC1_UNORM", 8, 0), 72: ("BC1_UNORM_SRGB", 8, 0),
    73: ("BC2_TYPELESS", 16, 0), 74: ("BC2_UNORM", 16, 0), 75: ("BC2_UNORM_SRGB", 16, 0),
    76: ("BC3_TYPELESS", 16, 0), 77: ("BC3_UNORM", 16, 0), 78: ("BC3_UNORM_SRGB", 16, 0),
    79: ("BC4_TYPELESS", 8, 0), 80: ("BC4_UNORM", 8, 0), 81: ("BC4_SNORM", 8, 0),
    82: ("BC5_TYPELESS", 16, 0), 83: ("BC5_UNORM", 16, 0), 84: ("BC5_SNORM", 16, 0),
    85: ("B5G6R5_UNORM", 0, 16), 86: ("B5G5R5A1_UNORM", 0, 16),
    87: ("B8G8R8A8_UNORM", 0, 32), 88: ("B8G8R8X8_UNORM", 0, 32),
    91: ("B8G8R8A8_UNORM_SRGB", 0, 32), 93: ("B8G8R8X8_UNORM_SRGB", 0, 32),
    94: ("BC6H_TYPELESS", 16, 0), 95: ("BC6H_UF16", 16, 0), 96: ("BC6H_SF16", 16, 0),
    97: ("BC7_TYPELESS", 16, 0), 98: ("BC7_UNORM", 16, 0), 99: ("BC7_UNORM_SRGB", 16, 0),
}
NAME_TO_DXGI = {v[0]: k for k, v in DXGI.items()}
FOURCC_TO_DXGI = {b"DXT1": 71, b"DXT2": 74, b"DXT3": 74, b"DXT4": 77, b"DXT5": 77, b"ATI1": 80, b"BC4U": 80,
                  b"BC4S": 81, b"ATI2": 83, b"BC5U": 83, b"BC5S": 84}
NUMERIC_FOURCC = {113: 10, 116: 2, 111: 54, 114: 41, 36: 11}
LEGACY_OUT = {71: b"DXT1", 74: b"DXT3", 77: b"DXT5", 80: b"ATI1", 83: b"ATI2"}

DDSD_CAPS, DDSD_HEIGHT, DDSD_WIDTH, DDSD_PITCH = 0x1, 0x2, 0x4, 0x8
DDSD_PIXELFORMAT, DDSD_MIPMAPCOUNT, DDSD_LINEARSIZE = 0x1000, 0x20000, 0x80000
DDPF_ALPHAPIXELS, DDPF_ALPHA, DDPF_FOURCC, DDPF_RGB, DDPF_LUMINANCE = 0x1, 0x2, 0x4, 0x40, 0x20000
CAPS_COMPLEX, CAPS_TEXTURE, CAPS_MIPMAP = 0x8, 0x1000, 0x400000
CAPS2_CUBEMAP_ALL = 0xFE00


def format_name(code: int | None) -> str:
    return DXGI.get(code, (f"DXGI_{code}", 0, 0))[0] if code is not None else "unknown"


def is_bc(code: int) -> bool:
    return DXGI.get(code, ("", 0, 0))[1] > 0


def mip_size(w: int, h: int, code: int) -> int:
    name, block, bpp = DXGI.get(code, ("", 0, 0))
    if block:
        return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
    if bpp:
        return w * h * bpp // 8
    raise ForgeError(f"unknown DXGI format {code}", "convert the texture with texconv to a known format")


def chain_size(w: int, h: int, mips: int, code: int, faces: int = 1) -> int:
    return sum(mip_size(max(1, w >> m), max(1, h >> m), code) for m in range(mips)) * faces


def header_size(data: bytes) -> int:
    return 148 if data[84:88] == b"DX10" else 128


def build_header(width: int, height: int, mips: int, code: int, cube: bool = False) -> bytes:
    """A DDS header for a payload; legacy FourCC/masks where one exists, else the DX10 extension."""
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_MIPMAPCOUNT
    if is_bc(code):
        flags |= DDSD_LINEARSIZE
        pitch = mip_size(width, height, code)
    else:
        flags |= DDSD_PITCH
        pitch = (width * DXGI.get(code, ("", 0, 32))[2] + 7) // 8
    dx10 = b""
    if code in LEGACY_OUT:
        pf = struct.pack("<II4sIIIII", 32, DDPF_FOURCC, LEGACY_OUT[code], 0, 0, 0, 0, 0)
    elif code == 87:
        pf = struct.pack("<II4sIIIII", 32, DDPF_RGB | DDPF_ALPHAPIXELS, b"\0\0\0\0", 32,
                         0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    elif code == 28:
        pf = struct.pack("<II4sIIIII", 32, DDPF_RGB | DDPF_ALPHAPIXELS, b"\0\0\0\0", 32,
                         0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000)
    elif code == 61:
        pf = struct.pack("<II4sIIIII", 32, DDPF_LUMINANCE, b"\0\0\0\0", 8, 0xFF, 0, 0, 0)
    else:
        pf = struct.pack("<II4sIIIII", 32, DDPF_FOURCC, b"DX10", 0, 0, 0, 0, 0)
        dx10 = struct.pack("<IIIII", code, 3, 0x4 if cube else 0, 1, 0)
    caps = CAPS_TEXTURE | (CAPS_COMPLEX | CAPS_MIPMAP if mips > 1 else 0) | (CAPS_COMPLEX if cube else 0)
    caps2 = CAPS2_CUBEMAP_ALL if cube else 0
    head = struct.pack("<IIIIIII", 124, flags, height, width, pitch, 0, mips) + b"\0" * 44 + pf + \
        struct.pack("<IIIII", caps, caps2, 0, 0, 0)
    return b"DDS " + head + dx10


def parse(data: bytes) -> dict:
    if len(data) < 128 or data[:4] != b"DDS ":
        raise ForgeError("not a DDS file (no 'DDS ' magic)", "export the texture as DDS")
    size, flags, height, width, pitch, depth, mips = struct.unpack_from("<IIIIIII", data, 4)
    pf_size, pf_flags, fourcc, bits, rm, gm, bm, am = struct.unpack_from("<II4sIIIII", data, 76)
    caps, caps2 = struct.unpack_from("<II", data, 108)
    code, cube, hsize = None, bool(caps2 & 0x200), 128
    if pf_flags & DDPF_FOURCC:
        if fourcc == b"DX10":
            if len(data) < 148:
                raise ForgeError("DDS DX10 header truncated", "re-export the texture")
            code, dim, misc, arr, _ = struct.unpack_from("<IIIII", data, 128)
            cube = cube or bool(misc & 0x4)
            hsize = 148
        elif fourcc in FOURCC_TO_DXGI:
            code = FOURCC_TO_DXGI[fourcc]
        else:
            code = NUMERIC_FOURCC.get(struct.unpack("<I", fourcc)[0])
    elif pf_flags & DDPF_RGB:
        if bits == 32 and (rm, gm, bm) == (0x00FF0000, 0x0000FF00, 0x000000FF):
            code = 87 if (am and pf_flags & DDPF_ALPHAPIXELS) else 88
        elif bits == 32 and (rm, gm, bm) == (0x000000FF, 0x0000FF00, 0x00FF0000):
            code = 28
        elif bits == 16 and (rm, gm, bm) == (0xF800, 0x07E0, 0x001F):
            code = 85
    elif pf_flags & DDPF_LUMINANCE and bits == 8:
        code = 61
    elif pf_flags & DDPF_ALPHA and bits == 8:
        code = 65
    mips = mips if (flags & DDSD_MIPMAPCOUNT and mips) else 1
    out = {"width": width, "height": height, "mips": mips, "dxgi": code, "format_name": format_name(code),
           "cubemap": cube, "header_size": hsize, "fourcc": fourcc.decode("ascii", "replace").strip("\0") if
           pf_flags & DDPF_FOURCC else None, "depth": depth, "bytes": len(data)}
    if code in DXGI:
        expected = chain_size(width, height, mips, code, 6 if cube else 1)
        out["payload_bytes"] = len(data) - hsize
        out["payload_expected"] = expected
    return out
