# Source baseline and related projects

The Mac source patch is based on
[cybersecurity/halo-ce-universal at 0ef2ed7dc7a96299ea7d8d02a1bc3f9fb1c231af](https://github.com/cybersecurity/halo-ce-universal/tree/0ef2ed7dc7a96299ea7d8d02a1bc3f9fb1c231af).
It retains upstream game structures, original Xbox cache/tag data and protocol 4.
The declared limit is 128 players on 128 machines; testing two instances does
not validate that limit or cross-platform sessions.

Related public source references (reviewed 2026-09-29):

| Repository | Inspected commit | Result |
|---|---|---|
| [bnunu/halo-ce-universal](https://github.com/bnunu/halo-ce-universal/tree/706523d354b307cac5a655b0b5b7e25ebea6290f) | `706523d354b307cac5a655b0b5b7e25ebea6290f` | 66 changed files and one removed file relative to the pinned base |
| [bnunu/halo-1](https://github.com/bnunu/halo-1/tree/93f8ec8127876fef2b9e574f6e8c3d0a38cfd8d5) | `93f8ec8127876fef2b9e574f6e8c3d0a38cfd8d5` | The byte-matching decompilation; its README points to the universal ports |

The inspected universal fork declares
[network protocol 3](https://github.com/bnunu/halo-ce-universal/blob/706523d354b307cac5a655b0b5b7e25ebea6290f/port/linux/include/halo_port_limits.h),
whereas the pinned source uses protocol 4. It also lacks newer fixes for idle
player actions, distributed-client update queuing, moving statistics cursors,
removed-object HUD references and PAL first-person animation timing. Those
fixes are retained in the Mac build. Its input difference removes a scripted
bot grenade action; it does not improve controller mappings or frame pacing.
Replacing the current engine with that fork would regress these fixes and the
current wire compatibility, so those differences were not adopted.

The fork adds an extensive experimental Custom Edition/OpenSauce cache loader,
resource-map conversion and Rally tooling. Its
[cache support notes](https://github.com/bnunu/halo-ce-universal/blob/706523d354b307cac5a655b0b5b7e25ebea6290f/docs/custom_edition_caches.md)
describe Windows observations for three maps and remaining sound/script and
OpenSauce feature limits. This is not established Mac functionality. The Mac
build does not claim `.yelo`, general Custom Edition maps, PC DLL plugins or
OpenSauce extensions. Original Xbox-format maps and engine features continue
to use the existing paths. The installer retains the pinned protocol and original cache loader.

Both inspected repositories and the pinned source contain CC0 license files.
XboxRecomp's MIT notice and miniupnpc's BSD notice remain separate. Game data
is user supplied and is not distributed by this port.
