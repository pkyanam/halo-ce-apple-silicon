#!/usr/bin/env python3
"""Read-only Xbox v5 cache audit; JSON contains filenames, never input paths.

Compressed maps contain a 2048-byte header followed by zlib data. Header spans
refer to the decompressed file. Only the bounded tag region is retained.
"""
import argparse
import collections
import json
from pathlib import Path
import struct
import zlib

BASE = 0x803A6000
MAX_FILE = 0x11600000
MAX_TAGS = 0x01600000
CHUNK = 1024 * 1024
CAMPAIGN = ('a10', 'a30', 'a50', 'b30', 'b40', 'c10', 'c20', 'c40', 'd20', 'd40')
MULTIPLAYER = ('beavercreek', 'bloodgulch', 'boardingaction', 'carousel', 'chillout',
               'damnation', 'hangemhigh', 'longest', 'prisoner', 'putput', 'ratrace',
               'sidewinder', 'wizard')
FORMATS = {0: ('A8', 8), 1: ('Y8', 8), 2: ('AY8', 8), 3: ('A8Y8', 16),
           6: ('R5G6B5', 16), 8: ('A1R5G5B5', 16), 9: ('A4R4G4B4', 16),
           10: ('X8R8G8B8', 32), 11: ('A8R8G8B8', 32), 14: ('DXT1', 4),
           15: ('DXT3', 8), 16: ('DXT5', 8), 17: ('P8-bump', 8)}


def check(ok, message):
    if not ok:
        raise ValueError(message)


def span(start, size, limit):
    return start >= 0 and size >= 0 and start <= limit and size <= limit - start


def header(data):
    check(len(data) == 2048, 'short header')
    check(data[:4] == b'daeh' and data[2044:] == b'toof', 'header/footer signature')
    version, length, _, offset, size = struct.unpack_from('<5I', data, 4)
    check(version == 5, 'requires Xbox cache version 5')
    check(2048 <= length <= MAX_FILE, 'declared file length cap')
    check(0 < size <= MAX_TAGS and offset >= 2048 and span(offset, size, length), 'tag span')
    name = data[32:64].split(b'\0')[0].decode('ascii')
    build = data[64:96].split(b'\0')[0].decode('ascii')
    check(len(name) <= 31, 'map name length')
    check(build in ('01.10.12.2276', '01.01.14.2342'), 'unsupported cache build')
    return dict(name=name, build=build, version=version, uncompressed_bytes=length,
                tag_offset=offset, tag_bytes=size)


def tag_region(stream, info):
    decoder = zlib.decompressobj()
    position = 2048
    output = bytearray()
    start = info['tag_offset']
    end = start + info['tag_bytes']
    while not decoder.eof:
        compressed = stream.read(CHUNK)
        check(bool(compressed), 'truncated zlib stream')
        while compressed and not decoder.eof:
            block = decoder.decompress(compressed, CHUNK)
            compressed = decoder.unconsumed_tail
            check(position + len(block) <= info['uncompressed_bytes'], 'decompressed length exceeds header')
            lo, hi = max(start, position), min(end, position + len(block))
            if lo < hi:
                output.extend(block[lo - position:hi - position])
            position += len(block)
    check(position == info['uncompressed_bytes'], 'decompressed length mismatch')
    check(len(output) == info['tag_bytes'], 'tag region incomplete')
    return output


def inspect_tags(data, info):
    def pointer(address, size):
        offset = address - BASE
        check(span(offset, size, len(data)), 'tag pointer outside region')
        return offset

    check(len(data) >= 36 and data[32:36] == b'sgat', 'tag header signature')
    instances, scenario, _, count = struct.unpack_from('<4I', data)
    check(count <= len(data) // 32, 'tag count cap')
    table = pointer(instances, count * 32)
    check((scenario & 65535) < count, 'scenario index range')
    scenario_group = bytes(data[table + (scenario & 65535) * 32:table + (scenario & 65535) * 32 + 4])
    check(scenario_group == b'rncs', 'scenario group')
    groups, formats, types, flags = (collections.Counter() for _ in range(4))
    max_dimensions = [0, 0, 0]
    mip_range = [32767, 0]
    pixels = 0
    bitmap_count = 0
    for index in range(count):
        at = table + index * 32
        group = bytes(data[at:at + 4])
        groups[group[::-1].decode('ascii', errors='replace')] += 1
        if group != b'mtib':
            continue
        address = struct.unpack_from('<I', data, at + 20)[0]
        tag = pointer(address, 108)
        pixel_size, _, pixel_file = struct.unpack_from('<iIi', data, tag + 48)
        check(span(pixel_file, pixel_size, info['uncompressed_bytes']), 'bitmap group pixel span')
        n, array = struct.unpack_from('<iI', data, tag + 96)
        check(0 <= n <= len(data) // 48, 'bitmap count cap')
        if not n:
            continue
        array = pointer(array, n * 48)
        for number in range(n):
            record = array + number * 48
            signature, w, h, d, kind, fmt, bits = struct.unpack_from('<I5hH', data, record)
            mip = struct.unpack_from('<h', data, record + 20)[0]
            relative = struct.unpack_from('<i', data, record + 24)[0]
            check(signature == 0x6269746D, 'bitmap signature')
            check(w > 0 and h > 0 and d > 0, 'bitmap dimensions')
            check(kind in (0, 1, 2) and fmt in FORMATS and bits < 256, 'bitmap type/format/flags')
            check(0 <= mip <= max(w, h, d).bit_length() - 1, 'bitmap mip count')
            size = 0
            for level in range(mip + 1):
                mw, mh, md = max(w >> level, 1), max(h >> level, 1), max(d >> level, 1)
                if bits & 2:
                    mw, mh = (mw + 3) & ~3, (mh + 3) & ~3
                size += mw * mh * md * (6 if kind == 2 else 1) * FORMATS[fmt][1] // 8
            check(span(relative, size, pixel_size), 'bitmap relative pixel span')
            check(span(pixel_file + relative, size, info['uncompressed_bytes']), 'bitmap file pixel span')
            formats[FORMATS[fmt][0]] += 1
            types[('2D', 'volume', 'cube')[kind]] += 1
            for bit, label in ((1, 'compressed'), (2, 'palettized'), (3, 'swizzled'), (4, 'linear')):
                if bits & (1 << bit):
                    flags[label] += 1
            max_dimensions = [max(a, b) for a, b in zip(max_dimensions, (w, h, d))]
            mip_range = [min(mip_range[0], mip), max(mip_range[1], mip)]
            pixels += size
            bitmap_count += 1
    return dict(tag_count=count, tag_groups=dict(groups), bitmap_count=bitmap_count,
                bitmap_formats=dict(formats), bitmap_types=dict(types), bitmap_flags=dict(flags),
                max_bitmap_dimensions=max_dimensions,
                mip_count_range=mip_range if bitmap_count else [],
                referenced_bitmap_bytes=pixels,
                note='Referenced bytes may share storage; not GPU residency or unique disk bytes.')


def audit(path, tags=False):
    with path.open('rb') as stream:
        result = header(stream.read(2048))
        result.update(file=path.name, physical_bytes=path.stat().st_size,
                      content_type='campaign' if result['name'] in CAMPAIGN else
                      'multiplayer' if result['name'] in MULTIPLAYER else 'ui' if result['name'] == 'ui' else 'unknown',
                      region='NTSC' if result['build'] == '01.10.12.2276' else
                      'PAL' if result['build'] == '01.01.14.2342' else 'unknown',
                      audit_level='tags' if tags else 'header', runtime_status='not_tested')
        if tags:
            result.update(inspect_tags(tag_region(stream, result), result))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('maps', type=Path)
    parser.add_argument('--tags', action='store_true', help='stream-decompress and validate bitmap records')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    records = []
    for path in sorted(args.maps.glob('*.map')):
        try:
            records.append(audit(path, args.tags))
        except (ValueError, UnicodeError, struct.error, zlib.error, OSError) as error:
            message = 'file read error' if isinstance(error, OSError) else str(error)
            records.append(dict(file=path.name, error=message, runtime_status='not_tested'))
    expected = set(CAMPAIGN + MULTIPLAYER + ('ui',))
    report = dict(schema=1, maps=records,
                  missing=sorted(expected - {r.get('name') for r in records}),
                  static_success=bool(records) and not any('error' in r for r in records))
    payload = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload, end='')
    return 0 if report['static_success'] and not report['missing'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
