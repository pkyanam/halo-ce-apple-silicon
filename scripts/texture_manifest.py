#!/usr/bin/env python3
"""Offline validation for a proposed texture override. Does not install or render.

Only legacy DDS DXT1/3/5, 2D power-of-two images with complete mip chains
are accepted. The conservative pilot limits are 2x and 1024 pixels per axis.
No downloads, game assets, runtime hooks, or third-party modules are required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


def inspect_dds(data):
    if len(data) < 128 or data[:4] != b"DDS ":
        raise ValueError("expected legacy DDS header")
    words = struct.unpack_from("<31I", data, 4)
    size, flags, height, width, _, depth, levels = words[:7]
    if size != 124 or words[18] != 32 or not words[19] & 4:
        raise ValueError("invalid DDS header or pixel format")
    if flags & 0x1007 != 0x1007 or not words[26] & 0x1000:
        raise ValueError("DDS must declare caps, dimensions, pixel format and texture storage")
    fourcc = bytes(data[84:88])
    block_bytes = {b"DXT1": 8, b"DXT3": 16, b"DXT5": 16}.get(fourcc)
    if block_bytes is None:
        raise ValueError("only DXT1, DXT3 and DXT5 are supported")
    if depth not in (0, 1) or words[27] != 0 or flags & 0x800000:
        raise ValueError("only 2D DDS is supported; no cubes, arrays or volumes")
    if any(n < 1 or n > 1024 or n & (n - 1) for n in (width, height)):
        raise ValueError("dimensions must be powers of two, at most 1024")
    expected_levels = max(width, height).bit_length()
    levels = levels or 1
    if levels != expected_levels:
        raise ValueError("complete mip chain through 1x1 is required")
    if levels > 1 and (not flags & 0x20000 or words[26] & 0x400008 != 0x400008):
        raise ValueError("DDS must declare mip count and mipmapped complex texture caps")
    payload = sum(max(1, (max(1, width >> level) + 3) // 4)
                  * max(1, (max(1, height >> level) + 3) // 4) * block_bytes
                  for level in range(levels))
    if len(data) != 128 + payload:
        raise ValueError("DDS payload length does not match mip chain")
    return {"width": width, "height": height, "levels": levels,
            "format": fourcc.decode("ascii"), "compressed_bytes": payload,
            "rgba8_bytes": sum(max(1, width >> level) * max(1, height >> level) * 4
                               for level in range(levels))}


def source_key(format_word, size_word, texels):
    """Proposed v1 identity for nonpalettized Xbox texture storage, not a tag ID."""
    return hashlib.sha256(b"HALO-XGPU-TEX-V1\0" +
                          struct.pack("<II", format_word, size_word) + texels).hexdigest()


def validate_manifest(path, budget_mib=64):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text())
    if manifest.get("schema") != "halo-xgpu-overrides-v1":
        raise ValueError("unsupported manifest schema")
    rows = []
    seen = set()
    for entry in manifest["textures"]:
        key = entry["source_key"]
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key) or key in seen:
            raise ValueError("source keys must be unique lowercase SHA-256 values")
        seen.add(key)
        relative = Path(entry["dds"])
        dds_path = (path.parent / relative).resolve()
        if relative.is_absolute() or not dds_path.is_relative_to(path.parent):
            raise ValueError("DDS path must remain within the manifest directory")
        data = dds_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["dds_sha256"]:
            raise ValueError("DDS SHA-256 mismatch")
        info = inspect_dds(data)
        source = entry["source"]
        width, height = source["width"], source["height"]
        if any(type(n) is not int or n < 1 or n > 1024 or n & (n - 1)
               for n in (width, height)):
            raise ValueError("invalid source dimensions")
        if source.get("kind") != "static-2d-normalized":
            raise ValueError("pilot excludes palettes, linear coordinates, cubes and dynamic textures")
        if info["width"] * height != info["height"] * width:
            raise ValueError("replacement aspect ratio differs from source")
        if not (width <= info["width"] <= 2 * width and height <= info["height"] <= 2 * height):
            raise ValueError("pilot replacement dimensions must be between 1x and 2x")
        if not isinstance(entry.get("provenance"), str) or not entry["provenance"].strip():
            raise ValueError("record author/license or local personal-use provenance")
        rows.append({"source_key": key, "dds": str(relative), "dds_sha256": entry["dds_sha256"],
                     "source_width": width, "source_height": height, **info})
    total = sum(row["compressed_bytes"] for row in rows)
    if total > budget_mib * 1024 * 1024:
        raise ValueError("compressed payload exceeds pilot budget")
    return {"runtime_supported": False, "texture_count": len(rows),
            "compressed_bytes": total,
            "rgba8_bytes": sum(row["rgba8_bytes"] for row in rows),
            "budget_mib": budget_mib, "textures": rows,
            "note": "Offline format checks only; provenance text is not permission verification."}


def write_runtime_index(manifest_path, index_path):
    """Compile an optional flat-file index for the isolated experimental C loader."""
    report = validate_manifest(manifest_path)
    manifest_path, index_path = Path(manifest_path).resolve(), Path(index_path).resolve()
    if index_path.parent != manifest_path.parent or index_path.name != "manifest.index":
        raise ValueError("runtime index must be manifest.index beside the input manifest")
    if not 1 <= len(report["textures"]) <= 128:
        raise ValueError("runtime pilot requires between 1 and 128 mappings")
    lines = ["HALO-XGPU-OVERRIDES-1"]
    for row in report["textures"]:
        name = row["dds"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,94}", name) or ".." in name:
            raise ValueError("runtime pilot requires flat safe DDS filenames; no subdirectories")
        lines.append(f'{row["source_key"]} {row["dds_sha256"]} {row["source_width"]} '
                     f'{row["source_height"]} {name}')
    text = "\n".join(lines) + "\n"
    if len(text.encode("ascii")) > 32768:
        raise ValueError("runtime index exceeds loader limit")
    index_path.write_text(text, encoding="ascii")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--budget-mib", type=int, default=64)
    parser.add_argument("--runtime-index", type=Path,
                        help="write experimental manifest.index beside the input manifest; flat DDS files only")
    args = parser.parse_args()
    if args.budget_mib < 1:
        parser.error("budget must be positive")
    try:
        report = validate_manifest(args.manifest, args.budget_mib)
        if args.runtime_index:
            write_runtime_index(args.manifest, args.runtime_index)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"texture manifest rejected: {error}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
