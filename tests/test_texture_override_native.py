"""Build and exercise original native library against synthetic local DDS files."""
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dds_fixtures", ROOT / "tests/test_texture_manifest.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class Image(C.Structure):
    _fields_ = [("width", C.c_uint32), ("height", C.c_uint32), ("levels", C.c_uint32),
                ("xbox_format", C.c_uint32), ("payload_bytes", C.c_size_t), ("payload", C.c_void_p)]


class Entry(C.Structure):
    _fields_ = [("source_key", C.c_char * 65), ("dds_hash", C.c_char * 65), ("file", C.c_char * 96),
                ("source_width", C.c_uint32), ("source_height", C.c_uint32),
                ("attempted", C.c_int), ("image", Image)]


SHA = C.CFUNCTYPE(None, C.c_void_p, C.c_int, C.c_void_p)
SHA_CALLS = []


class Pack(C.Structure):
    _fields_ = [("directory_fd", C.c_int), ("count", C.c_uint), ("resident_bytes", C.c_size_t),
                ("budget_bytes", C.c_size_t), ("sha256", SHA), ("slots", C.c_uint * 256),
                ("entries", Entry * 128)]


@SHA
def sha(data, size, output):
    SHA_CALLS.append(size)
    C.memmove(output, hashlib.sha256(C.string_at(data, size)).digest(), 32)


class NativeTextureTests(unittest.TestCase):
    guest_abi = False
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        target = Path(cls.build.name) / ("texture.dylib" if os.uname().sysname == "Darwin" else "texture.so")
        command = [shutil.which("cc") or "cc", "-std=c11", "-D_GNU_SOURCE", "-D_DARWIN_C_SOURCE",
                   "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared",
                   str(ROOT / "experimental/texture_override/texture_override.c"), "-o", str(target)]
        if cls.guest_abi:
            build = Path(cls.build.name)
            (build / "posix.h").write_text('''#include <stdint.h>
enum { _posix_file_is_directory = 1 };
struct posix_file_information { uint32_t flags, size_low, size_high;
    uint32_t modification_seconds, modification_nanoseconds, access_seconds,
    access_nanoseconds, creation_seconds, creation_nanoseconds; };
int posix_fstat(int, struct posix_file_information *);
''')
            (build / "posix_fixture.c").write_text('''#include <sys/stat.h>
#include <string.h>
#include "posix.h"
int posix_fstat(int fd, struct posix_file_information *info) {
    struct stat st;
    if (fstat(fd, &st)) return -1;
    memset(info, 0, sizeof(*info));
    info->flags = S_ISDIR(st.st_mode) ? 1 : 0;
    info->size_low = (uint32_t)st.st_size;
    info->size_high = (uint32_t)((uint64_t)st.st_size >> 32);
    return 0;
}
''')
            command += ["-DTXO_GUEST_ABI", "-I", str(build), str(build / "posix_fixture.c")]
        subprocess.run(command, check=True)
        cls.lib = C.CDLL(str(target))
        cls.lib.txo_open.argtypes = [C.POINTER(Pack), C.c_char_p, SHA]
        cls.lib.txo_close.argtypes = [C.POINTER(Pack)]
        cls.lib.txo_lookup.argtypes = [C.POINTER(Pack), C.c_char_p, C.c_uint32, C.c_uint32, C.c_uint32]
        cls.lib.txo_lookup.restype = C.POINTER(Image)
        cls.lib.txo_source_key.argtypes = [SHA, C.c_uint32, C.c_uint32, C.c_void_p, C.c_size_t, C.c_void_p]
        cls.lib.txo_describe_dds.argtypes = [C.c_void_p, C.c_size_t, C.POINTER(Image)]
        cls.lib.txo_metadata_bytes.restype = C.c_size_t

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.pack = Pack(directory_fd=-1)
        self.key = b"0" * 64
        SHA_CALLS.clear()

    def tearDown(self):
        self.lib.txo_close(C.byref(self.pack))
        self.temp.cleanup()

    def index(self, data=None, name="pilot.dds", key=None, digest=None, width=4, height=4):
        data = fixture.dds() if data is None else data
        if name == "pilot.dds":
            (self.path / name).write_bytes(data)
        text = ("HALO-XGPU-OVERRIDES-1\n" +
                f"{(key or self.key).decode()} {digest or hashlib.sha256(data).hexdigest()} {width} {height} {name}\n")
        (self.path / "manifest.index").write_text(text)

    def open(self):
        return self.lib.txo_open(C.byref(self.pack), os.fsencode(self.path), sha)

    def lookup(self, key=None, width=4, height=4, format=0x0c):
        return self.lib.txo_lookup(C.byref(self.pack), key or self.key, width, height, format)

    def test_storage_hash_matches_python_and_detects_changes(self):
        for source in (b"a", bytes(range(256))):
            output = C.create_string_buffer(65)
            self.assertEqual(self.lib.txo_source_key(sha, 0xdeadbeef, 0, source, len(source), output), 1)
            expected = hashlib.sha256(b"HALO-XGPU-TEX-V1\0" + struct.pack("<II", 0xdeadbeef, 0) + source).hexdigest()
            self.assertEqual(output.value.decode(), expected)
        self.assertEqual(self.lib.txo_source_key(sha, 0, 0, b"a", 3 * 1024 * 1024, output), 0)

    def test_match_full_mips_cache_and_original_fallback(self):
        self.index()
        self.assertEqual(self.open(), 1)
        self.assertFalse(self.lookup(key=b"1" * 64))
        self.assertFalse(self.lookup(width=8))
        first = self.lookup()
        self.assertTrue(first)
        self.assertEqual((first.contents.width, first.contents.levels, first.contents.payload_bytes), (8, 4, 56))
        self.assertEqual(self.pack.resident_bytes, 56)
        self.assertEqual(SHA_CALLS, [184])
        (self.path / "pilot.dds").unlink()
        second = self.lookup()
        self.assertEqual(first.contents.payload, second.contents.payload)
        self.assertEqual(self.pack.resident_bytes, 56)
        self.assertEqual(SHA_CALLS, [184])
        self.assertFalse(self.lookup(format=0x0f))

    def test_corrupt_files_and_missing_files_cache_misses(self):
        self.index(digest="f" * 64)
        self.assertEqual(self.open(), 1)
        self.assertFalse(self.lookup())
        self.assertEqual(self.pack.resident_bytes, 0)
        self.assertEqual(self.pack.entries[0].attempted, 1)
        self.index()  # failure cached until restart; no repeated disk I/O
        self.assertFalse(self.lookup())

    def test_symlink_and_traversal_rejected(self):
        self.index(name="../pilot.dds")
        self.assertEqual(self.open(), 0)
        self.index(name="linked.dds")
        (self.path / "outside.dds").write_bytes(fixture.dds())
        (self.path / "linked.dds").symlink_to(self.path / "outside.dds")
        self.assertEqual(self.open(), 1)
        self.assertFalse(self.lookup())

    def test_budget_and_format_mismatch_fallback(self):
        self.index()
        self.assertEqual(self.open(), 1)
        self.pack.budget_bytes = 55
        self.assertFalse(self.lookup())
        self.assertEqual(self.pack.resident_bytes, 0)

    def test_native_format_dimension_mip_rejection(self):
        cases = [fixture.dds()[:-1], fixture.dds(width=16, height=16, fourcc=b"DX10")]
        for offset, value in ((16, 2048), (28, 1), (112, 0x200), (24, 4)):
            altered = bytearray(fixture.dds())
            struct.pack_into("<I", altered, offset, value)
            cases.append(bytes(altered))
        for data in cases:
            image = Image()
            self.assertEqual(self.lib.txo_describe_dds(data, len(data), C.byref(image)), 0)

    def test_duplicate_index_and_index_symlink_rejected(self):
        self.index()
        index = self.path / "manifest.index"
        index.write_text(index.read_text() + index.read_text().splitlines()[1] + "\n")
        self.assertEqual(self.open(), 0)
        index.unlink()
        (self.path / "external.index").write_text("HALO-XGPU-OVERRIDES-1\n")
        index.symlink_to(self.path / "external.index")
        self.assertEqual(self.open(), 0)

    def test_offline_index_compiler_roundtrip(self):
        data = fixture.dds()
        (self.path / "pilot.dds").write_bytes(data)
        manifest = {"schema": "halo-xgpu-overrides-v1", "textures": [{
            "source_key": self.key.decode(), "dds": "pilot.dds",
            "dds_sha256": hashlib.sha256(data).hexdigest(),
            "source": {"width": 4, "height": 4, "kind": "static-2d-normalized"},
            "provenance": "Synthetic fixture"}]}
        path = self.path / "manifest.json"
        path.write_text(json.dumps(manifest))
        fixture.texture.write_runtime_index(path, self.path / "manifest.index")
        self.assertEqual(self.open(), 1)
        self.assertTrue(self.lookup())

    def test_fixed_metadata_and_collision_chain(self):
        self.assertEqual(self.lib.txo_metadata_bytes(), C.sizeof(Pack))
        def slot(key):
            h = 2166136261
            for ch in key:
                h = ((h ^ ch) * 16777619) & 0xffffffff
            return h % 256
        keys = {}
        pair = None
        for value in range(1000):
            key = f"{value:064x}".encode()
            bucket = slot(key)
            if bucket in keys:
                pair = (keys[bucket], key)
                break
            keys[bucket] = key
        self.assertIsNotNone(pair)
        self.index(key=pair[0])
        path = self.path / "manifest.index"
        path.write_text(path.read_text() + path.read_text().splitlines()[1].replace(pair[0].decode(), pair[1].decode()) + "\n")
        self.assertEqual(self.open(), 1)
        for key in pair:
            self.assertTrue(self.lookup(key=key))
        self.assertEqual(self.pack.resident_bytes, 112)


class NativeGuestAbiTextureTests(NativeTextureTests):
    """Exercise the guest narrow-stat branch with an independent native ABI fixture.

    This is not execution of the translated guest or its real host import.
    """
    guest_abi = True


if __name__ == "__main__":
    unittest.main()
