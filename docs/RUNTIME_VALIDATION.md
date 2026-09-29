# Runtime coverage

Validation date: 2026-09-29. The port is experimental. The native target has been exercised on an M3 MacBook Air running macOS 26. These checks distinguish package integrity, map smoke coverage and multiplayer behavior; they do not establish mission completion or physical controller compatibility.

| Area | Observed coverage | Remaining limits |
| --- | --- | --- |
| Startup and audio | Full 481-frame intro, decoded audio, frontend readiness and clean quit | Intro pacing can jitter |
| Campaign | All ten campaign caches reached the requested active scenario and rendered their opening scenes | Per-map control/cutscene details belong in the map matrix; mission completion and transitions remain untested |
| Keyboard/mouse | Campaign movement/interaction/relative look; actual keyboard movement and focus switching in local multiplayer | Retina hit-transform fixtures pass; manual menu-pointer activation remains unverified |
| Multiplayer | Two native engine instances on one Mac joined with distinct logical machine identities, exchanged protocol-4 packets and replicated manual W/A/D movement in both views; both exited cleanly | Blood Gulch and Battle Creek are covered; eleven other multiplayer maps were skipped. Separate physical machines, cross-platform peers and large player counts remain unverified |
| Gamepads | SDL virtual Xbox/DualSense mappings and actual translated XInput adapters | Physical Bluetooth/USB devices and advanced haptics are unverified |
| Graphics performance | Lighter opening scenes around 59.5–60 FPS; tutorial sections about 30–55 FPS | This is scene-specific, not a stable 60 FPS claim |
| HD textures | Offline metadata/manifest tools and isolated research | The texture hook is unapplied and excluded from the default build |

Local multiplayer uses an explicit offline IPv4 transport alias for the second instance. The native boundary preserves packet payloads and retries Darwin's connected-UDP EISCONN only when the destination exactly matches the socket's actual peer. Tests cover normal/aliased delivery, wrong-peer rejection and unchanged peer state. This same-host check does not establish cross-platform compatibility.

First-run profile, playlist and generated language/cache state are distinct from sealed disc data. Expected missing optional state must not be labeled a missing map asset; unexpected errors still require diagnosis. Bundled maps/movies have separate size/hash validation.

The relocated self-contained app completed a normal launch with bundled data, the full intro and clean Command-Q exit. Final F10 acceptance verified the exact 640×480 → 1280×720 → 1920×1080 presets, centered frontend captures, ignored key repeats and persistence to configuration; the game exited cleanly after all 481 intro frames and audio drain. The eleven remaining multiplayer maps were explicitly skipped; build and static preparation records are not gameplay acceptance stamps. Consult [the map matrix](MAP_TEST_MATRIX.md), [build details](BUILD.md) and [upstream review](UPSTREAM.md) for exact scope. No game data, private logs or user-state dumps are included in these documents.
