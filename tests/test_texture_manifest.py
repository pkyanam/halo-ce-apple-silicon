"""Synthetic DDS fixtures; no original or third-party game textures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("texture_manifest", Path(__file__).resolve().parents[1]
                                           / "scripts" / "texture_manifest.py")
texture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(texture)


def dds(width=8, height=8, fourcc=b"DXT1"):
    levels = max(width, height).bit_length()
    words = [0] * 31
    words[:7] = [124, 0xA1007, height, width, 0, 0, levels]
    words[18:21] = [32, 4, int.from_bytes(fourcc, "little")]
    words[26] = 0x401008
    block = 8 if fourcc == b"DXT1" else 16
    length = sum(((max(1, width >> i) + 3) // 4) * ((max(1, height >> i) + 3) // 4)
                 * block for i in range(levels))
    return b"DDS " + struct.pack("<31I", *words) + bytes(length)


class TextureManifestTests(unittest.TestCase):
    def test_complete_dxt_payloads(self):
        for fourcc, size in ((b"DXT1", 56), (b"DXT3", 112), (b"DXT5", 112)):
            self.assertEqual(texture.inspect_dds(dds(fourcc=fourcc))["compressed_bytes"], size)

    def test_reject_truncated_unknown_cube_and_missing_mips(self):
        cases = [dds()[:-1], dds(fourcc=b"DX10")]
        cube = bytearray(dds())
        struct.pack_into("<I", cube, 112, 0x200)
        cases.append(cube)
        missing = bytearray(dds())
        struct.pack_into("<I", missing, 28, 1)
        cases.append(missing)
        for data in cases:
            with self.assertRaises(ValueError):
                texture.inspect_dds(data)

    def test_source_key_changes_with_content_and_format(self):
        self.assertNotEqual(texture.source_key(1, 0, b"a"), texture.source_key(1, 0, b"b"))
        self.assertNotEqual(texture.source_key(1, 0, b"a"), texture.source_key(2, 0, b"a"))

    def test_manifest_rejects_hash_mismatch_escape_duplicates_and_scale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = dds()
            (root / "pilot.dds").write_bytes(data)
            entry = {"source_key": "0" * 64, "dds": "pilot.dds",
                     "dds_sha256": hashlib.sha256(data).hexdigest(),
                     "source": {"width": 4, "height": 4, "kind": "static-2d-normalized"},
                     "provenance": "Synthetic test fixture"}
            manifest = {"schema": "halo-xgpu-overrides-v1", "textures": [entry]}
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest))
            self.assertEqual(texture.validate_manifest(path)["compressed_bytes"], 56)
            for field, value in (("dds_sha256", "f" * 64), ("dds", "../pilot.dds"),
                                 ("source", {"width": 2, "height": 2,
                                             "kind": "static-2d-normalized"})):
                changed = dict(entry, **{field: value})
                path.write_text(json.dumps(dict(manifest, textures=[changed])))
                with self.assertRaises(ValueError):
                    texture.validate_manifest(path)
            path.write_text(json.dumps(dict(manifest, textures=[entry, entry])))
            with self.assertRaises(ValueError):
                texture.validate_manifest(path)
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                texture.validate_manifest(path, budget_mib=0)

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pack").mkdir()
            data = dds()
            (root / "outside.dds").write_bytes(data)
            (root / "pack" / "linked.dds").symlink_to(root / "outside.dds")
            manifest = {"schema": "halo-xgpu-overrides-v1", "textures": [{
                "source_key": "0" * 64, "dds": "linked.dds",
                "dds_sha256": hashlib.sha256(data).hexdigest(),
                "source": {"width": 4, "height": 4, "kind": "static-2d-normalized"},
                "provenance": "Synthetic fixture"}]}
            path = root / "pack" / "manifest.json"
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                texture.validate_manifest(path)


if __name__ == "__main__":
    unittest.main()
