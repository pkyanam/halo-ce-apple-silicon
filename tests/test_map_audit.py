"""Original synthetic cache fixtures; contain no game assets."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

SPEC = importlib.util.spec_from_file_location('map_audit', Path(__file__).parents[1] / 'scripts/map_audit.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def fixture():
    tags = bytearray(4096)
    struct.pack_into('<4I', tags, 0, audit.BASE + 36, 0, 0, 2)
    tags[32:36] = b'sgat'
    tags[36:40] = b'rncs'
    tags[68:72] = b'mtib'
    struct.pack_into('<I', tags, 88, audit.BASE + 100)
    struct.pack_into('<iIi', tags, 148, 32, 0, 2048)
    struct.pack_into('<iI', tags, 196, 1, audit.BASE + 208)
    struct.pack_into('<I5hH', tags, 208, 0x6269746D, 4, 4, 1, 0, 14, 2)
    struct.pack_into('<h', tags, 228, 2)
    header = bytearray(2048)
    header[:4] = b'daeh'
    header[-4:] = b'toof'
    struct.pack_into('<5I', header, 4, 5, 8192, 0, 4096, 4096)
    header[32:35] = b'a30'
    header[64:77] = b'01.10.12.2276'
    return header, tags


class MapAuditTests(unittest.TestCase):
    def test_compressed_offsets_use_uncompressed_file(self):
        h, tags = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'a30.map'
            path.write_bytes(h + zlib.compress(bytes(2048) + tags) + bytes(100))
            result = audit.audit(path, True)
            self.assertEqual(result['bitmap_formats'], {'DXT1': 1})
            self.assertEqual(result['referenced_bitmap_bytes'], 24)
            self.assertEqual(result['runtime_status'], 'not_tested')

    def test_header_rejections(self):
        for offset, value in ((4, 7), (8, audit.MAX_FILE + 1), (20, audit.MAX_TAGS + 1), (16, 8192)):
            with self.subTest(offset=offset):
                h, _ = fixture()
                struct.pack_into('<I', h, offset, value)
                with self.assertRaises(ValueError):
                    audit.header(h)

    def test_bitmap_rejections(self):
        for offset, fmt, value in ((88, 'I', audit.BASE - 1), (212, 'h', 0),
                                   (218, 'h', 3), (220, 'h', 5), (222, 'H', 256),
                                   (228, 'h', 8), (232, 'i', 31), (196, 'i', -1)):
            with self.subTest(offset=offset):
                h, tags = fixture()
                struct.pack_into('<' + fmt, tags, offset, value)
                with self.assertRaises(ValueError):
                    audit.inspect_tags(tags, audit.header(h))

    def test_truncated_stream(self):
        import io
        h, tags = fixture()
        with self.assertRaises(ValueError):
            audit.tag_region(io.BytesIO(zlib.compress(bytes(2048) + tags)[:-4]), audit.header(h))


if __name__ == '__main__':
    unittest.main()
