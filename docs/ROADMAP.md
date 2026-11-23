# Roadmap

**Platforms:** Windows and Linux · **Language:** C++17 (Dear ImGui) · **Status:** in development, nothing to download yet

The full plan is in [SPEC.md](SPEC.md) §8. The screens being built toward are in [mockup/](mockup/).

## Now

**Phase 0: foundation and hardware checks**
- CMake skeleton and CI on `windows-latest` and `ubuntu-24.04`.
- Fetch the pinned daemon on both, start it with `--private`, and check that `/server-info` responds.
- On a real Dante network: confirm metering works while Dante Controller is metering the same device, record the meter scale and which flow fields the daemon reports, and capture one multicast flow and one AES67 stream as decoder fixtures.

## Next

**Phase 1: core**
- `DaemonClient` with the allowlist test, `MeterFeed`, `FlowMap`, `DaemonSupervisor`, config and `DemoSource`.

**Phase 2: app, levels**
- ImGui shells for both platforms, the theme and widgets.
- Levels as in the mockup, plus Flows, Clock, Settings and About, and demo mode.

## Later

**Phase 3: listening**
- `MulticastReceiver`, the native and RTP decoders, the jitter buffer, the resampler, the player and the listen bar.

**Phase 4: release**
- Windows installer with a firewall rule, `.deb` and AppImage, signing, an update check, screenshots, and releases on `v*` tags.

## Done

- The old Linux GTK app was removed and the rebuild started. It is still in git history.
- Spec and phased plan: [SPEC.md](SPEC.md).
- Clickable shadcn/ui mockup of Levels, Flows, Clock and Settings: [mockup/](mockup/).
