# Xbox map coverage and runtime acceptance

`scripts/map_audit.py MAPS_DIRECTORY --tags --output audit.json` performs a read-only structural audit. Omit `--tags` for header inventory only. No map data is extracted or changed. Reports use filenames and contain no installation paths. Original synthetic fixtures run with `python3 -m unittest discover -s tests -p test_map_audit.py`.

The original Xbox inventory contains 24 caches: 10 campaign, 13 multiplayer, and UI. A complete static report must contain every expected name, no error, cache version 5, supported build, valid decompressed spans, scenario tag, and valid bitmap records. Static success **does not establish that a map loads or plays**. The script is an offline audit, outside the game renderer and default build.

| Class | Cache names | Runtime acceptance |
| --- | --- | --- |
| Campaign | a10, a30, a50, b30, b40, c10, c20, c40, d20, d40 | Scenario selected, tags/BSP loaded, simulation and presented frames advance, visible scene, player control after any opening cutscene |
| Multiplayer | beavercreek, bloodgulch, boardingaction, carousel, chillout, damnation, hangemhigh, longest, prisoner, putput, ratrace, sidewinder, wizard | Selected scenario loaded, simulation and presented frames advance, visible scene and local player control; remote join is a separate test |
| UI | ui | Frontend ready, intro playback complete, responsive menu and presented frames advance |

Campaign display names in order are The Pillar of Autumn, Halo, The Truth and Reconciliation, The Silent Cartographer, Assault on the Control Room, 343 Guilty Spark, The Library, Two Betrayals, Keyes, and The Maw. Xbox multiplayer cache aliases include carousel (Derelict), putput (Chiron TL-34), and beavercreek (Battle Creek).

For each runtime row record: app/source/build identity, asset build, resolution and graphics settings, cache name, expected scenario, load start time, first loaded-state time, observed simulation ticks and frame counter at two separated samples, local player/control evidence, screenshot, exit reason, and any errors. Use statuses `not_tested`, `load_failed`, `loaded_cutscene`, `playable_smoke_pass`, or `failed`. A bounded smoke interval must include at least 30 seconds of advancing simulation after the loaded-state signal; a cutscene-only run remains `loaded_cutscene`. A forced timeout is a test termination reason, not evidence of a clean game exit. Mission completion and transition coverage require separate runs.

The loaded-state signal should combine `game_in_progress()`, a matching loaded scenario, main menu inactive, valid scenario/BSP state, advancing game ticks, and advancing presented GL frames. Neither process survival, completed decompression, tag registration, audio, nor an intro movie alone satisfies it. If these signals are unavailable, record the limitation and retain visual/control evidence rather than asserting a machine-verified load. Load timeout is declared per run; initialization timing differs by mission.

## Cache and texture boundaries

NTSC build `01.10.12.2276` and PAL build `01.01.14.2342` use Xbox v5 caches; PAL normalization is handled by the source's PAL tag layer. Region identification here uses the build string, not an independent disc provenance check. All 24 caches in the inspected NTSC inventory have the former build. A localized cache tree must be audited independently; these results do not validate other releases.

The 2048-byte header precedes a zlib stream. Its file length and tag/pixel offsets refer to the **decompressed** file, so an offset greater than the physical compressed file size is expected. The script bounds declared file length to the source's cache limit, retains at most 22 MiB of tags, and decompresses in 1 MiB blocks. It validates tag-relative pointers against the fixed Xbox tag base, scenario group, bitmap block counts, positive dimensions, type, known format, 8-bit flags, mip count, and relative/absolute pixel spans. It uses the engine's compressed 4-by-4 rounding, depth reduction, six cube faces, and mip count excluding the base level. Referenced bitmap byte totals can double-count shared resources and **are not GPU residency measurements**.

Supported source format identifiers include A8, Y8, AY8, A8Y8, R5G6B5, A1R5G5B5, A4R4G4B4, X8R8G8B8, A8R8G8B8, DXT1/3/5, and P8 bump. The audit records cube/volume, swizzled, linear and palettized content; its structural pass does not verify native conversion or uploads for those paths. It does not verify geometry, vertex/index buffer contents, BSP relocation, sound, strings, scripts, compressed-payload checksums against original media, swizzle correctness, cube-face upload alignment, or shader semantics. Those remain runtime gates.

The experimental DDS override is unapplied and disabled by default. Map coverage must use original textures; this matrix makes no HD texture or 60 FPS claim. Texture-copy symbol coexistence and normal game loads are separate regressions from map integrity. A copy helper with the same symbol as a guest import alias can recurse before any content-format issue arises.

Source references: [cache headers and limits](https://github.com/cybersecurity/halo-ce-universal/blob/0ef2ed7d/source/cache/cache_files.c), [bitmap layout](https://github.com/cybersecurity/halo-ce-universal/blob/0ef2ed7d/source/bitmaps/bitmap_group.h), [bitmap mip sizes](https://github.com/cybersecurity/halo-ce-universal/blob/0ef2ed7d/source/bitmaps/bitmaps.c). See the pinned upstream URL in the project manifest if its repository location changes.
