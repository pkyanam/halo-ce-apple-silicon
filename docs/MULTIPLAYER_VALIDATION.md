# Native macOS multiplayer validation

Validation date: 2026-09-29.

The current source retains upstream protocol 4. The two instances run on one Mac. The local acceptance test uses
two genuine game instances, real maps, normal simulation, and real TCP/UDP
packets. It does not synthesize a lobby handshake or alter packet payloads.

The opt-in, offline-only local IPv4 alias maps a second logical endpoint to
a real loopback endpoint. No OS address alias, router configuration, online
service, or protocol change is required. A shared per-user test lease prevents
conflicting hosts on the fixed game ports. This transport arrangement is a
test mechanism; it does not prove external cross-platform interoperability.

## Reproducing the controlled pair

Run `tools/run_macos_multiplayer_pair.py --help` for the explicit engine, ELF,
asset, host-address, timeout, and evidence arguments. Use movement-only input
and a manual host observer. The harness labels the two windows and cleans up
its own process groups. Automated input is diagnostic only; ordinary launches
leave it disabled. Avoid starting another multiplayer host during the test.

Acceptance requires actual gameplay with two players with distinct logical machine identities,
changing remote authoritative positions visible on the other instance, and
clean shutdown. Lobby text, packet counters, or a rendered menu alone do not
satisfy this check.

## Verified correction

Darwin rejected `sendto` on an already connected socket even when the supplied
destination was its existing peer. This prevented both the local host's input
and the remote client's input/predictions from reaching the server. The native
bridge now retries with a real `send` only after `getpeername` proves an exact
IPv4-address and port match. A different peer retains the original failure;
the bridge never pretends that a packet was delivered.

The native connected-UDP regression reproduces the original `EISCONN`, verifies
exact payload delivery through the corrected bridge, and checks that a
mismatched destination neither delivers a packet nor changes the peer. It
runs with ordinary addressing and the explicit offline test alias.

A bounded two-engine Blood Gulch run then produced 46 gameplay samples per
engine with two players and distinct machine identities. Both player positions
changed on both engines, including physical host keyboard input mirrored on
the client. At one matching simulation tick, the remote player's host/client
positions were `(51.826, -81.194, 0.123)` and `(51.858, -81.174, 0.124)`.
Native UDP succeeded, server machine lookup and input/prediction decoding
accepted the traffic, and no `EISCONN` remained. Both engines exited normally
and their owned process groups were clean.

A subsequent Beaver Creek pair also entered real two-player gameplay with
mirrored movement and clean shutdown. Runtime multiplayer coverage is therefore
**Blood Gulch and Beaver Creek only**; the remaining maps were deliberately
not run.

This is evidence for a working local two-player host/join and state replication.
It is not a 128-player stress test, an external-platform crossplay test, or
proof that every multiplayer scenario/game mode has passed runtime acceptance.

Blood Gulch and Battle Creek (beavercreek) passed local two-instance runtime checks. The remaining eleven multiplayer scenarios were explicitly skipped; their loadability and game-mode coverage are not accepted here.
