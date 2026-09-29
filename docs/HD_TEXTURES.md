# Optional HD textures: feasibility and pilot contract

Research checked 2026-09-29. **No compatible, redistribution-cleared, off-the-shelf HD pack was verified for this Xbox-based port.** The normal patch ships no texture pack and currently has no enabled runtime external-texture loader. An isolated experimental C loader and an unapplied renderer hook are available under `experimental/texture_override`; they are not part of the default app or a claim of verified HD rendering. The script described below validates potential inputs.

The practical next step is a small, opt-in override of static environment color textures, prepared offline with complete DDS mip chains. Start at 2x the original dimensions, cap each axis at 1024, and keep a 64 MiB compressed payload budget. Benchmark before expanding. This could preserve the original draw/shader workload, but 60 FPS cannot be promised: the existing A10 tutorial already has slower phases without HD textures.

## Packs found and permission status

| Candidate | Source and availability | Actual target and compatibility | Distribution decision |
| --- | --- | --- | --- |
| Delta117 / Miguel Adro, Halo CE Remastered Textures Mod | [Author's project page](https://www.moddb.com/mods/halo-ce-remastered-textures-mod) remains public. It links a 2019 creator download through a URL shortener; a working archive was not verified. | Author specifies Halo PC/Custom Edition and prefers Refined or Ruby's maps. Project tags identify TexMod. Windows texture interception is not supported by this Xbox/OpenGL port. It needs unpacking and texture-by-texture remapping, assuming permission. | No asset license granting redistribution was found. The author credits permission from Masterz1337 to use SPV3 textures; that specific grant to that author does not establish a grant to this project. No automatic downloader or assets included. |
| Refined replacement tags | [Team-authored release description](https://haloce3.com/downloads/tags/misc-tags/refined-halo-1-replacement-tags/) offers a download and lists a 968 MB tag archive. Archive contents/download success were not tested. | The team explicitly describes extracting Xbox/PC tags and converting them **to Custom Edition**. This is useful restoration/tag reference, not a verified Xbox version-5 HD texture drop-in. | No redistribution grant was found on the release page. Original textures and original audio are among its dependencies. No assets included. |
| SPV3 | [Official project](https://halospv3.github.io/) has project/download navigation. [Official technical update](https://halospv3.github.io/2022/09/09/devupdate-3.html) documents its engine requirements. | Custom Edition plus OpenSauce 4.0, a campaign overhaul with its own effects and gameplay. This port has neither the Windows extension nor its shader/tag extensions. Importing SPV3 maps is not a texture-only change. | The [official loader repository](https://github.com/HaloSPV3/SPV3.Loader) explicitly limits its license to that repository, excluding the rest of SPV3 source/assets. A tooling license is not an asset license. No assets included. |
| ANTRAX Halo 4 + HD Textures Anniversary | [Release page](https://www.moddb.com/games/halo-combat-evolved/addons/halo-ce-halo-4-mod-hd-textures-anniversary-mod-by-antrax) lists a download, 1,469,726,436-byte ZIP and MD5 `387f3489bae7e3762a251d9811293ef3`. Download was not performed. | Description says a full campaign remake with changed models, weapons, sounds, shading, maps and textures. Filename explicitly says Anniversary on PC. It is not a standalone original-Xbox texture pack; the parent game's generic Mac/Xbox platform labels do not establish mod compatibility. The listing credits ANTRAX but is uploaded by another account. | Listing explicitly marks the license **Proprietary**. No redistribution/conversion permission verified. Do not bundle it. |

This is a scoped search, not proof that no other pack exists. Public download availability, author attribution and an open-source loader do not establish permission to rehost or convert assets. A future optional download fixture needs a verified author distribution URL, immutable SHA-256, explicit license evidence covering conversion/distribution, and a known texture mapping. None of the candidates above meets all four requirements yet. The project includes no downloaded texture archive or third-party asset redistribution.

## What the current engine accepts

Audit reference: `cybersecurity/halo-ce-universal` commit `0ef2ed7dc7a96299ea7d8d02a1bc3f9fb1c231af`, plus this project's macOS overlay. These are source findings; there was no new game launch or texture benchmark.

* `source/cache/cache_files.c:cache_file_header_verify` requires cache version **5** and applies a cache-size bound. The original Xbox build string is `01.01.14.2342`; the native build relaxes that build-string requirement, not the version requirement. PC/Custom Edition maps should not simply replace Xbox maps.
* `source/bitmaps/bitmap_group.h` stores bitmap dimensions, format, flags, mip count, pixel offset/size, cache block and hardware pointers. A bitmap tag is a structured game record, not an image file. [The community editing documentation](https://c20.reclaimers.net/h1/tags/bitmap/) also explains multiple images, cube maps, sprites and format-dependent alpha.
* `port/linux/src/xbox_textures.c:xgpu_texture_describe` reads Xbox D3D resource words. Power-of-two non-DXT texels are Morton-swizzled; a nonzero Size word specifies pitched linear storage. DXT1/3/5 are plain 4x4 blocks. Cube faces have Xbox-specific alignment. The existing decoder includes palettes, luminance, vector/bump formats, and 3D textures; these are not interchangeable with ordinary RGB images.
* `upload` passes DXT1/3/5 directly to `glCompressedTexImage2D/3D` and uploads supplied mip levels. Other formats become BGRA/RGBA8 on upload. The compressed fallback is currently Android-only, so a Mac pilot must verify `GL_EXT_texture_compression_s3tc` and successful uploads; the extension is probed in `d3d8_gl.c`. Do not assume BC7, ASTC, or DX10 DDS support.
* `xgpu_texture_get` caches using guest data/format/size plus palette variants. Memory-watch generation changes trigger a new upload. Recently used nonpalettized textures have a fast lookup, and idle textures are evicted. No external-file lookup or content-hash replacement exists today.
* `d3d8_gl.c:bind_textures` divides linear-texture coordinates by the original dimensions and controls sampler mip use from the description. Upsizing a linear HUD texture and returning its replacement dimensions would change its UV mapping. Render targets have a separate path. The pilot excludes both.
* `sdl_platform.c` requests an SDL OpenGL **4.1 core** context on macOS. The patch uses Apple's OpenGL driver, not a newly implemented direct Metal renderer. DDS payloads would enter that existing GL upload path.

## Experimental override implementation

1. At an actual texture upload/cache miss, identify the original static, nonpalettized normalized-coordinate 2D texture. Start with environment color textures that already have mipmaps. Skip render targets, linear-coordinate images, P8/vector maps, lightmaps, HUD/sprite sheets, cubes and volumes. The low-level header alone cannot prove semantic use; a local author-maintained allowlist must establish that a candidate is a color texture and is static.
2. Hash only on a cache miss or memory-watch invalidation. Proposed key: SHA-256 of `b"HALO-XGPU-TEX-V1\0" + little_endian_u32(format_word) + little_endian_u32(size_word) + original_texture_storage`. Storage means exactly the engine's described texture byte span, including supplied mip levels. Do not use guest addresses or upload sequence numbers as portable identities. Do not hash every bind/frame. If memory changes, recompute and fall back when no mapping matches.
3. Look up the key in a manifest read once at startup. Validate the replacement DDS and expected SHA-256, then upload only its compressed mip payload. Keep source memory watches and cache identity tied to original guest storage. Keep original guest texture/tag dimensions unchanged; retain original coordinate interpretation separately from replacement GPU dimensions/mip count. If a source had no mipmaps, preserve its sampler behavior until separately reviewed.
4. File miss, bad checksum, unsupported texture, GL error or memory-budget exhaustion must retain the original texture. Log original/replacement dimensions, compressed uploaded bytes and CPU/GL upload duration. Read/preprocess asynchronously or during map preload; perform GL uploads on the context thread. An uploader can still stall on first use, so preloading and measured cold loads matter.
5. Keep files in a per-user optional directory outside the app and maps. Default off; removal restores original rendering. No original map changes, checksum modifications, shader injection, runtime AI inference or per-frame image processing are required by this design.

TexMod IDs are not assumed identical to this proposed key: D3D9 PC storage, Xbox swizzling, channel order, mip chains and palette interpretation differ. Mapping needs local visual inspection and an explicit per-texture association. Offline upscaling of personally extracted textures is another possible input workflow, subject to asset/model rights; no AI model or upscaler is included here. Ordinary filtering can be used for a structural pilot but does not invent detail.

## Memory and 60 FPS risk

Approximate per-texture memory for a square image with full mips (small block-rounded tail adds a few bytes):

| Size | DXT1 | DXT3/5 | RGBA8 |
| --- | ---: | ---: | ---: |
| 512x512 | 0.167 MiB | 0.333 MiB | 1.333 MiB |
| 1024x1024 | 0.667 MiB | 1.333 MiB | 5.333 MiB |

Doubling both axes multiplies payload by roughly four. Fifty 1024-square textures are approximately 33.3 MiB DXT1, 66.7 MiB DXT5, or 266.7 MiB RGBA8. GPU allocation/driver staging, original guest storage and the existing fingerprint cache are additional; on Apple Silicon these compete for unified memory. The validator reports exact block-rounded compressed and hypothetical RGBA8 sizes. Its budget is a payload policy, not an observed GPU-residency limit.

Compressed offline mips avoid runtime conversion and huge uncompressed uploads. They keep shader/draw counts unchanged, but larger textures can increase bandwidth/cache pressure and add disk read/upload stalls, especially during first encounters or cache eviction. Full-chain mips reduce distant sampling cost and aliasing; they do not guarantee deadline compliance. A10 tutorial frame time already sometimes exceeds 16.67 ms. No amount of HD texture installation establishes “flat-out 60”.

## Offline validation prototype

Run `python3 scripts/texture_manifest.py path/to/manifest.json`. It reads files and prints a JSON report with `runtime_supported: false`, because the standard app has no enabled hook. Run its synthetic tests with `python3 tests/test_texture_manifest.py`.

Example schema; replace both hashes with actual values. This example is not a working texture mapping:

```json
{
  "schema": "halo-xgpu-overrides-v1",
  "textures": [
    {
      "source_key": "<64 lowercase hex SHA-256 characters>",
      "source": {"width": 512, "height": 512, "kind": "static-2d-normalized"},
      "dds": "environment/pilot.dds",
      "dds_sha256": "<64 lowercase hex SHA-256 characters>",
      "provenance": "Author, asset license and permission evidence URL, or local personal-use source"
    }
  ]
}
```

The validator accepts legacy DDS DXT1/3/5 2D power-of-two images with full mip chains, aspect-ratio preservation, at most 2x upscaling and 1024 pixels per axis. It verifies file hashes, checks payload length, blocks escaped/symlinked paths outside the manifest directory, rejects duplicate source keys and totals the payload against a 64 MiB default budget. A provenance string records review context; it is **not** license verification. This prototype does not prove a source key came from the game or that an override is semantically safe.

For an experimental runtime index, keep the DDS files flat beside the JSON manifest and run `python3 scripts/texture_manifest.py pack/manifest.json --runtime-index pack/manifest.index`. This explicitly writes a checked ASCII index consumed by the isolated C prototype; it does not copy assets or modify the game. See [experimental implementation](../experimental/texture_override/README.md) for review/build requirements and limitations.

## Benchmark plan

First collect baseline warm/cold frame-time data at 1280x720 and 1920x1080 with the same settings, save, route and runtime binary. Record the cryotube/tutorial separately from the settled corridor; include effects-heavy combat and a larger outdoor scene when available. After a runtime hook and legitimate mapped assets exist, compare baseline to 10–20 approved 2x color textures, then a budget-limited larger set. No verified HD pack or benchmark exists yet.

Capture p50/p95/p99/max frame times, fraction over 16.67/33.33 ms, upload count/bytes/time, map-load duration, resident/unified-memory use, texture evictions and GL errors. Separate cold first-use stalls from warm traversal and repeat each route. Check alpha cutouts, color channels, mip transitions, tiling, bump/reflection combinations, distant shimmer and fallback behavior. Confirm multiplayer map checks and original map bytes stay unchanged. Judge each resolution/scene by measured deadline misses, not average FPS alone; leave HD off by default if it worsens the 60 FPS target.
