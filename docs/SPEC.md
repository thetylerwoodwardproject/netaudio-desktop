# NetAudio Monitor: spec and phased plan

**Mockup:** [`mockup/`](mockup/), built with shadcn/ui (`npm install && npm run dev`). Screens: **Levels**, **Flows**, **Clock**, **Settings** and **About**. **Roadmap:** [ROADMAP.md](ROADMAP.md).

## Context

NetAudio Monitor is a **read-only Dante level meter** for Windows and Linux, rebuilt from scratch. The previous Linux GTK app has been removed. It is still in git history if anyone needs it for reference.

What it does:
1. **Live dBFS levels** for every transmit and receive channel on the network, as reported by each device.
2. **Listening to feeds that are already multicast or AES67.** It joins them passively, like any other listener.
3. **Never changes anything in production.**
   - No routing, subscriptions or flows are created or deleted.
   - No device settings are touched.
   - Unicast feeds are levels only.

Routing and configuration stay in Dante Controller.

## 1. Product

| Item | Spec |
|---|---|
| Name | NetAudio Monitor |
| Platforms | Windows 10 22H2+ / 11 (x64); Linux x86_64 (Ubuntu 22.04+ or equivalent, X11 or Wayland) |
| UI | Native C++17 with Dear ImGui. DirectX 11 on Windows, GLFW + OpenGL 3.3 on Linux. Same look on both. |
| Architecture | App → C++ core → bundled `netaudio-daemon`, run in `--private` mode (local HTTP/SSE) → Dante devices. For listening, the core joins multicast/AES67 groups itself. |
| Distribution | Windows: signed Inno Setup installer plus a portable `.zip`. Linux: `.deb` and AppImage. |
| Versioning | Calendar versions `YYYY.MM.DD`, from one `VERSION` file |
| License | MIT. The daemon is Unlicense and bundled with attribution. |

## 2. Features

### Levels (main screen)
- **Device cards.** One card per device showing name, model, IP, sample rate / bit depth and clock state (leader / locked / not locked).
- **Channel rows.** One row per flow. A flow with two channels (a stereo pair, such as "1–2 Stage Mix") is one row with an L and an R meter; mono channels have one meter. Each row has:
  - the channel number (or pair, "1–2") and name;
  - a flow label underneath ("Multicast · 239.255.12.4", "AES67 · …" or "Unicast · levels only");
  - a meter, the current dBFS value and a peak value;
  - a listen button, shown only for multicast or AES67 channels.
- **Receive channels** also show their source ("← Stagebox-A · 5 Bass DI · unicast"). The level shown is the one the receiving device measures. "Not subscribed" is shown when a channel has no source.
- **dBFS values.**
  - Meters are mapped through the daemon's `metering_scale`. Device meters report in 0.5 dB steps, so values show one decimal place ("−18.5").
  - Special states: **CLIP** (red), "—" for below threshold or no signal (dimmed), and "muted".
- **Meter.**
  - Linear in dB from −60 to 0 dBFS, with scale labels (−60, −40, −20, −12, 0) and a tick at −12.
  - Green below −12, amber from −12 to −3, red above −3 or on clip.
  - A peak-hold marker and peak value that hold for 2 s, adjustable in Settings.
- **Summary cards:**
  - channels with signal;
  - the loudest feed, with its dBFS;
  - clips in the last 10 minutes and which channel clipped (kept in memory for the session);
  - clock status and leader.
- **Filters:** All channels / With signal / Above −12 dBFS / Can listen, plus search (`Ctrl+K`).

### Listen (multicast and AES67 only)
- Pressing the headphones on a channel joins its existing multicast group or AES67 stream and plays it.
- For a receive channel, it plays the source the channel is subscribed to, but only if that source is multicast or AES67.
- **Listen bar:**
  - source name and path ("Existing multicast flow 239.255.12.4 · passive");
  - a large dBFS meter with the current reading and peak;
  - volume, output device, Stop, and an approximate latency (about 30–60 ms).
- Unicast channels have no listen button. A tooltip says "Unicast flow: levels only".

### Flows screen
- **Counts:** multicast and AES67 flows marked "Can listen", and unicast flows marked "Levels only".
- **Table:** source, channels, type, destination, format, levels (yes) and listen (yes/no).
- **Note** explaining where levels come from.

### Other pages
- **Clock:** read-only PTP status per device, and which device is the leader.
- **Settings:**
  - Dante network adapter, output device, listen buffer;
  - peak-hold time, meter refresh rate, meter colour thresholds;
  - daemon port.
- **About:** credits, including NetAudio upstream and the Dante trademark notice.
- **Demo mode** (`--demo`): simulated devices and levels, and synthesised audio for the listenable channels.

## 3. Read-only guarantee
- **Allowlisted API client.** `DaemonClient` contains only:
  - Reads: `GET /server-info`, `GET /devices`, `GET /settings`, `GET /issues`, `GET /external-flows` and the `GET /events` stream (meters).
  - Meter control: `POST /metering/start` and `/metering/stop`.

  No other endpoint exists in the code. A unit test fails the build if any other path appears.
- **Metering is the only request sent to devices.** It asks a device for its meter values, as Dante Controller's own meters do. It doesn't affect audio, routing or settings. Metering stops on quit.
- **Listening only joins groups.** The app sends an IGMP membership report to the switch, and no device is contacted. The app never sends audio-plane traffic.
- **Private daemon.** The bundled daemon runs with `--private`. In that mode it:
  - exits when the app does;
  - uses a random metering port, so it doesn't clash with Dante Controller on UDP 8752;
  - doesn't announce itself, and has no MCP server.

  The app passes `--interface` for the chosen adapter.

## 4. Daemon (bundled, not rewritten)
- **Upstream already builds for both platforms.** NetAudio (chris-ritsen/network-audio-controller, Unlicense) releases `windows-x86_64` and manylinux `x86_64` builds of the native Rust `netaudio-daemon`, and its CI tests Linux and Windows.
- **Not rewriting it.** Re-implementing Dante discovery and metering would be months of protocol work and would cut us off from upstream fixes.
- **Fetching it in CI:**
  - Download the pinned `netaudio` wheel for each platform from PyPI, check its SHA-256, and extract `netaudio-daemon` / `netaudio-daemon.exe`.
  - Fallback: `cargo build -p netaudio-daemon --release` from the pinned upstream tag.
- **Install location:**
  - Windows: `C:\Program Files\NetAudio Monitor\daemon\`.
  - Linux: `/usr/lib/netaudio-monitor/` (`.deb`) or inside the AppImage.
- **Running it.** `DaemonSupervisor` starts it hidden and waits for `/server-info`. It also owns its stdin pipe, which is how the daemon knows to exit.

## 5. C++ core
- **`DaemonClient`:** HTTP via WinHTTP on Windows and a small POSIX socket client on Linux (the daemon is localhost-only, plain HTTP). JSON via nlohmann/json.
- **`MeterFeed`:** an SSE reader for `/events?meters=1&telemetry=none&patches=0`.
  - Reads `metering_scale.detailed` from the first snapshot. Raw value 0 means clip, 1 means 0 dBFS, then each step is −0.5 dB; 254 means muted and 255 is a marker.
  - Merges partial `meter_values` updates per device.
  - Treats readings as stale after 3 s, and reconnects after 2 s.
  - Keeps the peak hold and the clip history.
- **`FlowMap`:** builds, from `/devices` and `/external-flows`, a map of each channel to its flow: unicast, or multicast/AES67 with group, port, slot and format. Receive channels map through their subscriptions. Phase 0 confirms which fields the daemon reports.
- **Listening:**
  - **Joining:** `MulticastReceiver` joins the group on the Dante adapter (Winsock on Windows, BSD sockets on Linux).
  - **Decoding:** `NativeDecoder` is ported from netaudio-endpoint's multicast receive code (`packages/netaudio-endpoint/src/receive.rs`, Unlicense, credited). `RtpDecoder` handles AES67 (RFC 3550, L16/L24).
  - **Buffering:** a 20 ms jitter buffer (adjustable from 5 to 100 ms) fills lost packets with silence.
  - **Clock drift:** a drift-servoed resampler from miniaudio.
  - **Output:** miniaudio — WASAPI on Windows; PipeWire, PulseAudio or ALSA on Linux.
- **Demo:** `DemoSource` simulates devices, flows and levels, and synthesises audio.
- **Config:**
  - Windows: `%APPDATA%\NetAudio Monitor\config.json`.
  - Linux: `$XDG_CONFIG_HOME/netaudio-monitor/config.json`.

## 6. Design system (shadcn zinc, dark only)
- **Colour tokens** (in `design/tokens.json`, generated into a C++ header):

  | Token | Value | Token | Value |
  |---|---|---|---|
  | bg | `#09090b` | card | `#0f0f11` |
  | raised | `#18181b` | line | `#27272a` |
  | line-2 | `#3f3f46` | meter-track | `#1f1f23` |
  | text | `#fafafa` | text-2 | `#d4d4d8` |
  | dim | `#a1a1aa` | accent | `#3b82f6` |
  | ok | `#22c55e` | warn | `#f59e0b` |
  | clip | `#ef4444` | | |

- **Type:** Inter 400/500/600 for text; JetBrains Mono for dBFS values, IPs and numbers, with tabular figures. Both fonts are embedded in the app.
- **Shape:**
  - Radius: 8 px for controls, 12 px for cards, 999 px for pills.
  - 1 px borders, no shadows, 4 px spacing grid.
- **Layout:**
  - **Sidebar:** Levels, Flows, Clock and Settings, plus a "Read-only" card and the metering/adapter status.
  - **Main column:** a header with search, then summary cards, filter chips and a responsive grid of device cards (minimum 440 px wide).
  - **Listen bar:** docked at the bottom.
- **Components:** button (primary/secondary/ghost), chip, badge/pill, card, meter (row and large), table, select, slider, switch, tooltip, toast.
- **Platform details:**
  - Windows: dark titlebar via DWM.
  - Both: per-monitor DPI scaling.
  - Both: keyboard navigation throughout.
- **Shortcuts:** `Ctrl+1..4` for pages, `Ctrl+K` for search, `L` to listen to the selected channel, `Esc` to stop, `M` to mute, `Ctrl+Q` to quit.

## 7. Repository layout (target)
```
VERSION
CMakeLists.txt
core/        api/ (read-only client, SSE), model/, meters/, flows/, listen/ (receiver, decoders, jitter, player), daemon/, demo/, platform/ (win/, posix/)
app/         ImGui UI: theme, widgets, pages (levels, flows, clock, settings, about), main_win32.cpp (DX11), main_linux.cpp (GLFW + OpenGL)
tests/       doctest unit tests, packet-capture fixtures, mock_daemon.py (dev only)
packaging/   windows/ (Inno Setup), linux/ (.deb, AppImage, .desktop, metainfo)
design/      tokens.json, icon.svg
docs/        README.md, SPEC.md, ROADMAP.md, mockup/ (shadcn/ui, screenshots/)
.github/     ci.yml (Windows + Linux build/test), release.yml
```
**Dependencies** (pinned with CMake FetchContent): Dear ImGui 1.91.x, GLFW 3.4 (Linux), nlohmann/json 3.11.3, miniaudio 0.11.x, doctest.

## 8. Phases

The same phases, grouped as Now / Next / Later, are in [ROADMAP.md](ROADMAP.md).

**Phase 0: foundation and hardware checks**
- CMake skeleton and CI on `windows-latest` and `ubuntu-24.04`.
- Fetch the pinned daemon on both, start it with `--private`, and check that `/server-info` responds.
- On a real Dante network:
  - Confirm metering works while Dante Controller (on Windows) is metering the same device.
  - Record the meter scale.
  - Record which flow fields `/devices` and `/external-flows` report.
  - Capture one multicast flow and one AES67 stream as decoder fixtures.

**Phase 1: core**
- `DaemonClient` with the allowlist test, `MeterFeed`, `FlowMap`, `DaemonSupervisor`, config and `DemoSource`.

**Phase 2: app, levels**
- ImGui shells for both platforms and the theme and widgets.
- The Levels screen as in the mockup, plus the Flows, Clock, Settings and About pages and demo mode.

**Phase 3: listening**
- `MulticastReceiver`, the native and RTP decoders, the jitter buffer, the resampler, the player and the listen bar.

**Phase 4: release**
- Installer with a Windows Firewall rule (inbound UDP, private networks) for the app and the daemon, plus `.deb` and AppImage.
- Signing, an update check, screenshots, and a release on `v*` tags.

## 9. Verification
- **Unit tests** (`ctest` on both CI runners):
  - the allowlist test;
  - meter-scale mapping and peak hold;
  - flow-map building from captured `/devices` JSON;
  - decoders checked against the packet fixtures;
  - jitter and drift simulation.
- **Demo mode:** every interaction in the mockup works.
- **On hardware, on both operating systems:**
  - dBFS values match Dante Controller's meters to within 0.5 dB.
  - Multicast and AES67 feeds play.
  - Unicast feeds show levels only.
  - Dante Controller shows **no changes** before, during or after a session.
  - A packet capture shows the app sends only metering requests and IGMP joins.
