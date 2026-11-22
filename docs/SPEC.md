# NetAudio Monitor for Windows: spec and phased plan

Mockup: https://claude.ai/artifact/NxRLrazjCsEf6ZerV3BJ1A (two screens: **Levels and live listen**, and **Listen sources**).

## Context

Dante Controller already handles routing and configuration on Windows. This app does not compete with it. It is a **read-only monitor**:

1. Show live audio levels for every transmit and receive channel on the Dante network.
2. Let you listen live to any feed it can reach.
3. **Never change anything in production.** No routing, no flows, no subscriptions, no device settings.

It replaces the current Linux GTK app (`netaudio_desktop/`). Linux support and every mention of it are removed. Windows (x64) is the only platform. The UI is native C++ with Dear ImGui on DirectX 11, in the same shadcn zinc dark style as podstudio.

## 1. Product

| Item | Spec |
|---|---|
| Name | NetAudio Monitor (the repo can keep its name) |
| Platform | Windows 10 22H2+ / 11, x64 |
| Scope | Read-only: discovery, levels, clock status, listen. Routing and configuration stay in Dante Controller. |
| Architecture | ImGui app → C++ core → bundled `netaudio-daemon.exe`, run privately (local HTTP/SSE) → Dante devices. For listening, the core receives audio packets itself. |
| Distribution | Signed Inno Setup installer plus a portable `.zip` |
| Versioning | Calendar versions `YYYY.MM.DD`, from one `VERSION` file |
| License | MIT. The daemon is Unlicense and bundled with attribution. |

## 2. Features

**Levels (main screen)**
- One card per device, showing its name, model, IP, format and clock state (leader / locked / not locked).
- Transmit channels: number, name, a live meter and the dBFS reading.
- Receive channels: name, source ("← Stagebox-A · 1 Kick") and the source's level. "Not subscribed" when it has no source.
- Meter colours: green for signal, amber above −12 dBFS, red at clip.
- A summary row: devices online, channels with signal, hot or clipping count, clock leader.
- Filters (All / With signal / Listenable) and a search box (`Ctrl+K`).

**Listen**
- Every channel row has a headphones button. One click plays it; clicking again or Stop ends it.
- Listening to a receive channel plays the transmit channel it is subscribed to.
- The listen bar at the bottom shows the source, how it is being heard, a level meter, volume, the output device, the latency (about 30–60 ms) and Stop.
- Channels the app can't reach passively have a disabled button with a tooltip explaining why (for example "Unicast flow: turn on mirror capture to hear it").

**Listen sources screen**
- The three passive methods and whether each is ready.
- A table of the flows on the network: source, channels, multicast/AES67/unicast, destination, format, and whether they can be heard.
- A short guide to setting up a mirror port.

**Also:** a Clock page (read-only PTP status, from the existing `clock.py` logic), Settings (the Dante adapter, the mirror adapter, the output device, buffer size, meter rate), About/credits, and a demo mode (`--demo`) with simulated devices and synthesised audio.

**Removed from the old app:** routing matrix, renaming, presets, audio/gain settings, preferred leader, network-interface changes on the daemon side, identify.

## 3. How "never changes anything" is enforced

- **Allowlisted API client.** The C++ `DaemonClient` exposes only:
  - Reads: `GET /server-info`, `GET /devices`, `GET /settings`, `GET /issues`, and the `GET /events` live stream.
  - `POST /metering/start` and `/metering/stop`.

  No other endpoint exists in the code, so there's nothing for a bug to call. A unit test fails the build if a non-allowlisted path appears.
- **Metering is the one request sent to devices.** It asks a device to send its meter values, as Dante Controller's own meters do. It doesn't touch audio, routing or settings. The app stops metering on quit.
- **Listening sends nothing to devices.**
  - Multicast and AES67: the app only joins the group. The switch receives an IGMP membership report, and no device is contacted.
  - Mirror capture: the mirror adapter is receive-only. The app never transmits on it.
- **Private daemon.** The bundled daemon runs with `--private`. In that mode it:
  - exits when the app does (it watches the app's stdin pipe);
  - uses a random local metering port, so it doesn't clash with Dante Controller on UDP 8752;
  - doesn't announce itself on the network, and turns off its MCP server.

  The app passes `--interface` for the chosen Dante adapter.

## 4. Daemon on Windows (bundled, not rewritten)
- Upstream NetAudio already ships a `windows-x86_64` build. Its CI builds and tests on `windows-latest`, and the daemon has `#[cfg(windows)]` code. Only the virtual soundcard, the JACK/PulseAudio bridge and the video tools are Linux-only, and this app uses none of them.
- Re-implementing Dante discovery and metering in C++ would be months of reverse-engineered protocol work, and would cut us off from upstream fixes. So we bundle the daemon instead.
- CI downloads the pinned `netaudio` `win_amd64` wheel from PyPI, checks its SHA-256 and extracts `netaudio-daemon.exe`. The fallback is building it from the pinned upstream tag with `cargo build -p netaudio-daemon --release`.
- The installer puts it in `C:\Program Files\NetAudio Monitor\daemon\` and adds an Unlicense notice to `NOTICE`.
- `DaemonSupervisor` starts it hidden (`CREATE_NO_WINDOW`) and waits for `/server-info`.

## 5. Listening pipeline (C++ core)

| Method | When | How | Setup |
|---|---|---|---|
| **Multicast flow** | The source already sends this channel in a multicast flow | Join the group on the Dante adapter (Winsock `IP_ADD_MEMBERSHIP`) | None |
| **AES67 stream** | The device has AES67 on and announces the stream with SAP | Join the SDP's group; RTP L24/L16 (RFC 3550) | None |
| **Mirror capture** | Unicast flows, which are most production routing | A raw socket on the mirror adapter (`SIO_RCVALL`, needs admin) filters UDP to the flow's destination and port. If the user has installed Npcap, it can be used instead; it is not bundled because of its licence. | A switch mirror (SPAN) port into a second network adapter |

- **Finding a channel:** `/devices` gives the subscriptions (receive channel → source device and channel) and the flow details. The core builds a map from transmit channel to flow (address, port, slot) for each method. Phase 0 confirms exactly which flow fields the daemon reports.
- **Decoding:** `Native2Decoder` is a C++ port of netaudio-endpoint's native PCM receive code (`packages/netaudio-endpoint/src/receive.rs`, Unlicense, credited). It handles 16/24/32-bit samples, sequence numbers and timestamps. `RtpDecoder` handles AES67.
- **Playback:** a 20 ms jitter buffer (5–100 ms in Settings) with silence for lost packets. A drift-servoed resampler (miniaudio) converts to the output rate, and output goes through WASAPI shared mode with volume, mute and a soft limiter.
- **Can't be heard:** encrypted flows; unicast flows whose switch port isn't mirrored; mirrors that drop packets because they are overloaded. The UI says which applies.

## 6. Design system (shadcn zinc, dark)
- **Colours** (from podstudio `native/app/theme.h`, kept in `design/tokens.json`):

  | Token | Value | Token | Value |
  |---|---|---|---|
  | bg | `#09090b` | card | `#0f0f11` |
  | raised | `#18181b` | line | `#27272a` |
  | line-2 | `#3f3f46` | text | `#fafafa` |
  | dim | `#a1a1aa` | accent | `#3b82f6` |
  | ok | `#22c55e` | warn | `#f59e0b` |
  | clip | `#ef4444` | | |

- **Type:** Inter 400/500/600; JetBrains Mono (or Cousine) for numbers, dB and IPs. Fonts are embedded in the exe.
- **Shape:** radius 8 px for controls and 12 px for cards. 1 px borders, no shadows, 4 px spacing grid.
- **Layout:**
  - Left sidebar: Levels, Listen sources, Clock, Settings, plus a "Read-only" card and the engine/adapter status.
  - Header with title, search and the mirror-capture switch.
  - Summary cards, filter chips, a grid of device cards, and the listen bar docked at the bottom.
- **Components** (build on podstudio `widgets.h`): button (primary/secondary/ghost), chip, switch, badge, card, meter, table, select, slider, tooltip, toast.
- **Windows:** dark titlebar via DWM, per-monitor DPI v2, keyboard navigation.
- **Shortcuts:**
  - Pages and search: `Ctrl+1..4`, `Ctrl+K`.
  - Listening: `L` listens to the selected channel, `Esc` stops, `M` mutes.
  - Quit: `Ctrl+Q`.

## 7. Repository layout (target)
```
VERSION
core/          C++17, no UI: api/ (read-only client, SSE), model/, logic/ (clock, meters), demo/, listen/ (sources, decoders, jitter, player), platform/ (WinHTTP, Winsock, raw capture), daemon/
windows/       Win32 + DX11 + Dear ImGui app: theme, widgets, pages, .rc, manifest, installer/
tests/         doctest unit tests, golden fixtures, packet-capture fixtures
tools/         mock_daemon.py (dev only), daemon fetch script, screenshot script
design/        tokens.json, icon.svg
docs/          SPEC.md, screenshots/
.github/       windows.yml (build + test), release.yml
```
**Removed:** `netaudio_desktop/`, the `netaudio-desktop` launcher, `install.sh`, `packaging/build-deb.sh`, `snap/`, `data/*.desktop`, `data/*.metainfo.xml`, `data/icons/hicolor/`, `pyproject.toml`. The Python app stays in git history as a reference.

## 8. Phases

**Phase 0: clean-up and checks**
- Capture golden fixtures from the Python `clock.py` and `meters.py` logic. Then delete the Linux artifacts, and rewrite the README for Windows.
- Remove the Linux wording; `grep -rniI "linux\|gtk\|gnome\|adwaita\|snap\|\.deb\|cosmic\|flatpak"` must return nothing.
- In CI on `windows-latest`, extract the pinned daemon, start it with `--private`, and call `/server-info`.
- **Hardware check** on a Windows PC on a Dante network:
  - the daemon's metering works while Dante Controller is metering the same device;
  - record which flow fields `/devices` reports;
  - capture a multicast flow and a mirrored unicast flow to commit as decoder fixtures.

**Phase 1: C++ core**
- The read-only `DaemonClient` with the allowlist test.
- The SSE meter feed (a port of `meters.py`), the clock logic (a port of `clock.py`), `DemoClient`, `DaemonSupervisor`, and the config and paths code.

**Phase 2: Windows app, levels**
- Win32/DX11/ImGui shell, adapted from podstudio's `main_win32.cpp`, `theme.*`, `widgets.*` and fonts.
- The Levels screen exactly as in the mockup, plus the Clock and Settings pages and demo mode.

**Phase 3: listening (multicast and AES67)**
- The source map, multicast join, SAP/SDP, the native and RTP decoders, the jitter buffer, the resampler, the WASAPI player, and the listen bar.
- Demo mode synthesises audio.

**Phase 4: mirror capture**
- The raw-socket capture on the mirror adapter (with optional Npcap), unicast flow matching, the Listen sources screen, and the mirror setup guide.

**Phase 5: release**
- Inno Setup installer with firewall rules (inbound UDP, private networks, for the app and the daemon), signing, and an update check.
- `release.yml` builds and publishes on a `v*` tag.

## 9. Verification
- **Unit tests** (`ctest` on `windows-latest`):
  - golden-fixture parity with the Python logic;
  - the allowlist test;
  - decoders checked against the captured packets;
  - jitter and drift simulation.
- **Demo mode:** every mockup interaction works: filters, search, listen and stop, the mirror switch, volume.
- **On hardware:**
  - Levels match Dante Controller's meters.
  - Listening works for multicast, AES67 and mirrored unicast.
  - With Dante Controller open, its device view shows **no changes** to routing, flows or settings before, during or after a session.
  - A packet capture on the Dante adapter shows the app sending only metering requests and IGMP joins.
