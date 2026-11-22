# NetAudio Desktop for Windows: spec and phased plan

## Context

NetAudio Desktop is currently a Linux-only app: Python with GTK4/libadwaita (~3,000 lines in `netaudio_desktop/`), shipped as a `.deb`, a snap and a wheel. It is a front end for the `netaudio` daemon (chris-ritsen/network-audio-controller), which it talks to over a local HTTP + SSE API (`127.0.0.1:4780`).

Goals:
1. Turn it into a **Windows (x64) app in native C++**. Windows is the only supported platform.
2. **Drop Linux** (and do not add macOS) and remove every mention of Linux from the repo.
3. Add **listening to any transmit or receive channel**, if the API allows it.
4. A sleek, minimal, **shadcn-style** design like **podstudio**.

Decisions:
- Windows UI: Dear ImGui + DX11, the same stack as podstudio.
- Listening: confirm once per session; the app tracks and removes the flows it creates.
- Theme: dark only.

### Research findings that shape the plan
- **The daemon runs on Windows.** Its README lists Windows as a supported platform for the CLI and daemon. So the app keeps using the daemon. It is a native Rust binary, `netaudio-daemon`, and we bundle it with the app.
- **The daemon's HTTP API has no audio streaming endpoint.** `/metering/*` and `/events` carry levels only.
- **The daemon's virtual Dante receiver is Linux-only.** `netaudio audio serve` is behind `#[cfg(target_os = "linux")]`, and `docs/audio-endpoint.md` says Windows network endpoint support remains separate work.
- **Multicast flows can be received on Windows.** `netaudio audio receive` records an existing native-v2 multicast PCM flow. Its socket code is portable (only `set_multicast_all_v4` is Linux-gated, in `packages/netaudio-endpoint/src/receive.rs`).
- **The daemon can create flows.** `/transmit-flows/plan`, `/transmit-flows/create` and `/transmit-flows/delete` all exist (`packages/netaudio-daemon/src/http/devices/flow_authoring.rs`), and create/delete require `confirmed: true`.
- **Listening is therefore possible.** The app has the daemon create a temporary 1-channel multicast transmit flow (or reuses an existing one), joins the multicast group itself, decodes the PCM, and plays it out of the speakers. Listening to a **receive** channel means listening to the transmit channel it is subscribed to. AES67 (RTP L24/L16 with SAP announcements) is a second, standards-based source when a device has AES67 enabled.
- **Licensing:** netaudio is released under the Unlicense, so its native-v2 packet parsing can be ported to C++ freely (credit it anyway).
- **podstudio's native Windows app** is the template: C++17, CMake with FetchContent (nlohmann/json, imgui, miniaudio), Win32 + DX11, WinHTTP, Inter and Cousine fonts compiled into the exe, `theme.h`/`theme.cpp` with zinc tokens, `widgets.h` (card, chip, pill_tabs, toggle, primary/danger buttons, meters), an Inno Setup installer, a Linux GLFW preview build for screenshots, and a `core/` library with no OS code.

---

## Spec sheet

### 1. Product
| Item | Spec |
|---|---|
| Name | NetAudio Desktop |
| Platform | Windows 10 22H2+ / 11, x64 (arm64 later) |
| Other platforms | Not supported. All Linux code, packaging and wording is removed; no macOS build. |
| Architecture | App (ImGui UI) → C++ core → bundled `netaudio-daemon` (local HTTP/SSE) → Dante devices. Listening adds: core receives multicast/RTP directly → audio output. |
| Versioning | Calendar versions `YYYY.MM.DD`, as now. One version file, `VERSION`, read by CMake. |
| License | MIT (app). The daemon is Unlicense and bundled with attribution. |
| Distribution | Windows: signed `NetAudioDesktop-Setup-x.y.z.exe` (Inno Setup) plus a portable `.zip`. |

### 2. Repository layout (target)
```
VERSION
core/                    C++17 library, no UI code, unit-tested
  api/                   daemon client (HTTP + SSE), JSON models, errors
  model/                 Device, Channel, Subscription, ClockStatus, Issue, Preset types
  logic/                 clock.cpp, devsettings.cpp, presets.cpp, routing.cpp (ports of the .py files)
  demo/                  DemoClient + DemoMeterFeed (port of demo.py / meters.py)
  listen/                flow manager, native-v2 + RTP/AES67 decoder, jitter buffer, resampler, player
  platform/              http_win.cpp (WinHTTP) · net_win.cpp (Winsock multicast) · paths_win.cpp
  daemon/                locate/launch/supervise bundled netaudio-daemon
include/netaudio/        public C++ headers
windows/                 Win32 + DX11 + Dear ImGui app (theme, widgets, pages), .rc, manifest, installer/
tests/                   core unit tests (doctest), golden JSON fixtures, mock daemon
tools/                   mock_daemon.py (dev only), fetch_daemon scripts, screenshot scripts
docs/                    SPEC.md, ARCHITECTURE.md, DESIGN.md, screenshots/
.github/workflows/       windows.yml, release.yml
```
Removed: `netaudio_desktop/`, `netaudio-desktop` launcher, `install.sh`, `packaging/build-deb.sh`, `snap/`, `data/*.desktop`, `data/*.metainfo.xml`, `data/icons/hicolor/`, `pyproject.toml`. The Python app stays in git history as the behavioural reference.

### 3. C++ core
- **Language and build:** C++17, the same as podstudio. CMake 3.25+, Visual Studio 2022 (MSVC, static runtime). Dependencies via FetchContent, pinned: nlohmann/json 3.11.3, miniaudio 0.11.22, doctest. No Boost.
- **Threading:** every network call runs off the UI thread on a small worker pool. Results reach the UI through a lock-free `EventQueue` that the UI drains once per frame. Same idea as `util.run_async` today.
- **`DaemonClient`:** a one-to-one port of `netaudio_desktop/api.py` (sends the `NetAudio-API-Version: 1` header; JSON errors become `ApiError`; same timeouts per call). Endpoints: `/server-info`, `/devices`, `/refresh`, `/subscribe`, `/unsubscribe`, `/rename-device`, `/rename-channel`, `/identify`, `/presets/{save,preview,plan,load}`, `/settings`, `/settings/network`, `/metering/{start,stop}`, `/refresh-clock`, `/set-preferred-leader`, `/set-latency`, `/set-encoding`, `/set-sample-rate-pullup`, `/set-gain`, `/set-sample-rate`, `/issues`. New for listening: `/transmit-flows/{plan,create,delete}` and `/set-aes67` (read only, for the hint shown in the UI).
- **`EventStream`:** an SSE reader for `/events?meters=1&telemetry=none&patches=0`. It ports `MeterFeed`: the `metering_scale` snapshot, `meter_values` merging, a 3 s staleness cutoff, and reconnecting after 2 s.
- **Logic ports:** each is pure functions with tests built from the Python behaviour.
  - `clock.py`: `ident`, `health` keyword heuristic, `summarize`.
  - `devsettings.py`: `can_write`, rates, encodings, latency choices and hint, pull-up, gain.
  - `presets.py`: `PresetStore` (XML + JSON sidecar), `summarize_plan`, `describe_result`.
- **`DemoClient`:** a port of `demo.py`, with the same five devices and behaviours, so demo mode and screenshots match the old app.
- **`DaemonSupervisor`:** finds the bundled daemon first, then `NETAUDIO_DAEMON_BIN`, then `PATH`, then a uv/pipx install. It starts it with `--port`, waits for `/server-info` (8 s), owns its lifetime when the app started it, and stops it on quit. Existing daemons are respected.
- **Paths:**
  - Windows: `%APPDATA%\NetAudio Desktop\config.json`, `%APPDATA%\NetAudio Desktop\Presets\`.
  - Presets stay plain XML and are compatible with the old app's files.

### 3a. Daemon on Windows (bundled, not rewritten)
- **Upstream already supports Windows.** NetAudio's release CI builds a `windows-x86_64` wheel containing the native Rust `netaudio-daemon.exe`, its quality checks run on `windows-latest`, and the daemon has `#[cfg(windows)]` code paths. Only the virtual soundcard (`audio serve`, `clock-serve`), the `/host-audio/*` JACK/PulseAudio bridge and the video adapters are Linux-only, and this app uses none of them.
- **Not rewriting.** Re-implementing the Dante control protocol in C++ would be tens of thousands of lines of reverse-engineered work, and would cut us off from upstream fixes. The app stays a C++ front end that talks to the daemon over localhost HTTP/SSE.
- **Shipping:** CI downloads the pinned `netaudio` `win_amd64` wheel from PyPI, checks its SHA-256 and extracts `netaudio-daemon.exe`. The fallback is `cargo build -p netaudio-daemon --release` from the pinned upstream tag. The installer puts it in `C:\Program Files\NetAudio Desktop\daemon\`, adds an Unlicense notice to `NOTICE`, and adds Windows Firewall rules for private networks.
- **Running it:** `DaemonSupervisor` starts it hidden (`CREATE_NO_WINDOW`, `--port 4780`), waits for `/server-info`, and stops it on quit. A daemon that is already running is reused.
- **Risk:** upstream's Windows checks are automated, not done on real Dante gear, so Phase 2 includes a hardware smoke test. If the daemon couldn't be bundled at all, the fallback is linking upstream's C library `netaudio-core` (`packages/netaudio-core/include/netaudio_core.h`), not a full rewrite.
- **Check:** in Phase 0, CI extracts the daemon on `windows-latest`, runs `--help`, starts it and calls `GET /server-info`.

### 4. Channel listening (new feature)
**User experience**
- Every transmit and receive channel, in the matrix headers and on device pages, gets a 🎧 listen button. One channel plays at a time, plus optional "add to mix" for up to 4 at once.
- The **Listen bar** is docked above the status bar. It shows the source ("Stagebox-A · Ch 3 Kick"), a level meter, volume and mute, an output device picker, a latency readout and Stop.
- **Receive channel:** listening follows its subscription to the source transmit channel. The label reads "Rx FOH-Console 1 ← Stagebox-A 3". If the channel has no subscription, the button is disabled with the tooltip "Not subscribed".
- **Confirm once per session per device:** a dialog lists what will be created ("1 multicast transmit flow on Stagebox-A, 1 of 4 flow slots in use"). An existing multicast or AES67 flow that already carries the channel is reused without asking.
- Shortcut: `L` listens to the hovered or selected channel; `Esc` stops.

**How a source is chosen (`ListenSourceResolver`)**
1. An existing native multicast transmit flow on the device already contains the channel → join it.
2. AES67 is enabled and a SAP/SDP stream contains the channel → join the RTP stream.
3. Otherwise, `/transmit-flows/plan` a 1-channel multicast flow (the plan is read-only and is shown in the confirm dialog), then `/transmit-flows/create` with `confirmed: true` → join the flow.
4. If the device refuses (no free flow slots, multicast unsupported, locked or DDM-denied), show the reason from the daemon and a suggestion. Never retry automatically.

**Flow ownership and cleanup (`FlowLedger`)**
- Every flow the app creates is recorded in `listen-ledger.json` with the device, flow id, creation time, app instance id and channel, before the app joins it.
- The flow is deleted on stop, on switching source (after a 5 s grace period so rapid A/B listening reuses it), on quit, and on daemon reconnect.
- At startup, flows left in the ledger by a crash are listed in a toast ("2 listen flows left from last session — Remove"). They are never deleted silently.
- The app only deletes flows it created.

**Receive pipeline (core/listen)**
- `MulticastSocket` (per OS): joins the group on the chosen Dante interface (the same interface the daemon uses, from `/settings`), with SO_REUSEADDR.
- `Native2Decoder`: a C++ port of netaudio-endpoint's native-v2 PCM receive and parse (sequence numbers, sample timestamps, 16/24/32-bit big-endian). Credited in NOTICE.
- `RtpL24Decoder`: RFC 3550 RTP with L16/L24 payloads, plus SDP from SAP (`239.255.255.255:9875`).
- `JitterBuffer`: 20 ms target, adjustable from 5 to 100 ms, conceals packet loss with silence, counts underruns and overruns.
- `DriftResampler`: miniaudio linear resampler with a slowly servoed ratio (±200 ppm) to keep the buffer level steady. It also converts the network rate to the output device rate.
- `Player`: miniaudio playback (WASAPI shared mode; exclusive mode optional later). Float32, mono channels panned centre (or L/R for a stereo pair). Volume, mute and a soft limiter.
- Expected latency is about 30–60 ms from network to ear. This is a monitoring tool, not a sample-accurate path; the UI says so.

**Limits and risks (stated in the UI and docs)**
- Encrypted or DDM-restricted flows cannot be heard.
- Devices have few multicast flow slots (often 2–32).
- Some Dante chipsets (e.g. Ultimo) may not support multicast flow authoring. In that case only option 2 (AES67) or nothing is available.
- Multicast needs IGMP to work on the switch and the computer on the Dante VLAN.
- Windows Firewall must allow inbound UDP for the app; the installer adds that rule (private networks only).
- **Gate:** Phase 4 starts with a hardware spike. If native-v2 flow creation or decoding fails on real gear, ship AES67-only listening and file an upstream request for a daemon `GET /listen` PCM-over-HTTP endpoint (which would make listening trivial for clients).

### 5. Design system ("shadcn zinc, dark")
- **Tokens** (from `podstudio/native/app/theme.h`, kept in `design/tokens.json` and generated into `windows/theme_tokens.h`):

  | Token | Value | Token | Value |
  |---|---|---|---|
  | bg | #09090b | text | #fafafa |
  | raised | #18181b | dim | #a1a1aa |
  | muted / line | #27272a | faint | #71717a |
  | line-2 | #3f3f46 | popup | #111113 |
  | accent | #3b82f6 (blue, primary actions and selection; podstudio's red is used for destructive actions) | danger | #ef4444 |
  | ok | #22c55e | warn | #f59e0b |
- **Type:** Inter Regular and Semibold (15/12.5/22 px), with Cousine (or JetBrains Mono) for numbers and IDs, using tabular figures. Fonts are embedded in the exe, as in podstudio.
- **Shape and spacing:**
  - Radius: 8 px for controls, 12 px for cards, 10 px for popovers.
  - 1 px borders in `line` instead of shadows.
  - 4 px spacing grid: controls have 12×7 px padding and 10 px gaps.
- **Layout:**
  - Left sidebar, 220 px, collapsible to icons: Routing, Devices, Presets, Issues (badge), plus a Settings cog at the bottom.
  - Top bar: page title, a search field in command style (`Ctrl+K` command palette), and Rescan, Meters and Listen toggles.
  - Bottom status bar: daemon state, interface, clock health chip, issues chip.
- **Components** (build on podstudio `widgets.h`): Button (primary/secondary/ghost/destructive), Badge, Card, Tabs (pill), Switch, Select, Input, Dialog/Sheet, Toast (bottom-right), Tooltip, Command palette, Table, Meter (h/v), Listen bar, Matrix cell.
- **Routing matrix:**
  - Cells are 22 px squares in a 2 px grid, colour-coded: empty = `raised`, patched = `text` dot, pending = pulsing `dim`, error = `danger` ring.
  - Hovering shows a crosshair across the row and column.
  - Device headers collapse and expand.
  - Column headers are vertical names (drawn as rotated text in ImGui).
  - Meters sit inline in the headers.
- **Motion:** 120–160 ms ease-out for hover and appear. No bouncing. Respects the OS "reduce motion" setting.
- **Windows specifics:**
  - Mica-style dark titlebar via `DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE)`.
  - Per-monitor DPI v2 (`theme::setup(scale)` re-runs on `WM_DPICHANGED`).
  - Keyboard navigation through ImGui nav.

### 6. Feature parity checklist
Routing matrix (patch/unpatch, hover crosshair, rename on click, jump to device) · Device pages (info, audio settings with confirm-before-disruptive, clock & sync, preferred leader, per-channel names and gain, identify) · Live meters (opt-in, stop on close) · Presets (capture, list, import/export, preview → plan → confirm → apply, stale-digest refusal) · Issues tab + badge · Network interface picker (first-run + status bar, redundant pair) · Demo mode (`--demo`) · Auto-start daemon · Preferences (port, auto-start, meter rate, listen buffer, output device) · About/credits · **New:** channel listening, command palette.

Shortcuts: `Ctrl+1..4` pages · `Ctrl+M` meters · `Ctrl+F` search · `Ctrl+K` palette · `F5` rescan · `L` listen · `Esc` stop · `Ctrl+Q` quit.

### 7. Security and safety
- Safety principles stay as now: presets never apply blindly, disruptive changes ask first, locked devices are disabled, meters are opt-in, and demo mode never touches the network.
- Listening adds: confirm before creating a flow, the ledger-based cleanup, and never deleting flows the app didn't create.
- The daemon only binds to 127.0.0.1.
- Windows: Authenticode signing (Azure Trusted Signing or an OV certificate). The installer adds firewall rules for `NetAudioDesktop.exe` and `netaudio-daemon.exe`, private networks only.

---

## Phases

### Phase 0: Foundation and Linux removal (1 PR)
- Add `docs/SPEC.md` (sections 1–7 above), `docs/DESIGN.md` (tokens and components) and `docs/ARCHITECTURE.md`.
- Delete the Linux artifacts listed in §2.
- Rewrite `README.md` for Windows with status "in development". Remove Linux, GTK, libadwaita, COSMIC, snap and .deb wording. Change the `netaudio.app/linux` credit link to `netaudio.app`.
- Keep `docs/screenshots/` until new ones exist, then replace them. Move the icon SVG to `design/icon.svg`.
- Replace `release.yml` with a placeholder CI that builds core tests on `windows-latest`.
- Check with `grep -rniI "linux\|gtk\|gnome\|adwaita\|snap\|\.deb\|cosmic\|flatpak"`. It must return nothing outside `.git` (the one allowed exception is daemon-docs links, if any are needed).

### Phase 1: C++ core
- Write the CMake skeleton, `core/` with the API client, models, SSE, logic ports, DemoClient, presets store and daemon supervisor.
- `tests/`: doctest unit tests with golden fixtures captured from the Python implementation's outputs (`clock.summarize`, `devsettings.*`, `presets.summarize_plan`) before it is deleted. Generate these in Phase 0 and commit them as JSON, the same way podstudio's `make_reference.py` works.
- `tools/mock_daemon.py`: a dev-only mock of the HTTP/SSE API for integration tests. Python is only used as a dev tool, never shipped.
- Done when `ctest` is green on Windows CI.

### Phase 2: Windows app (ImGui + DX11)
- `windows/`: `main_win32.cpp`, DX11 swapchain, DPI and dark titlebar (adapt podstudio's `main_win32.cpp` and `platform_win32.cpp`).
- Copy and adapt podstudio's `theme.*`, `widgets.*` and `fonts/*.inc`. Add the new components (sidebar, matrix, command palette, toast, dialog).
- Pages: `page_routing.cpp`, `page_devices.cpp`, `page_presets.cpp`, `page_issues.cpp`, `page_settings.cpp`, `about.cpp`.
- Bundle `netaudio-daemon.exe` next to the exe. CI fetches it by building `cargo build -p netaudio-daemon --release` from a pinned upstream tag, or by extracting it from the pinned PyPI wheel.
- Inno Setup installer (based on `podstudio/native/installer/podstudio.iss`) with firewall rules and a Start menu entry.
- Done when every parity item in §6 works in demo mode and against the mock daemon, and CI produces the setup.exe.

### Phase 3: Polish and release 1.0 (without listening)
- New screenshots in demo mode via an ImGui offscreen capture on the Windows CI runner (podstudio's `tools/ci-screenshots.ps1` pattern).
- Accessibility pass, crash logging to a local file, and an update check against GitHub Releases (port podstudio's `core/updates.cpp`).
- Write `release.yml` so a `v*` tag builds, signs and attaches the installer and portable zip.

### Phase 4: Channel listening
1. **Hardware spike (gate):** on real Dante gear, create a 1-channel multicast flow through the daemon, and capture it with `netaudio audio receive` on Windows. Record the packet format, flow limits and failures per device model.
2. Core: `FlowLedger`, `ListenSourceResolver`, `MulticastSocket`, `Native2Decoder`, `RtpL24Decoder` + SAP, `JitterBuffer`, `DriftResampler`, `Player`.
   - Unit tests: decode recorded packet captures from the spike (committed as fixtures), jitter and drift simulation, and ledger crash recovery.
3. Demo mode: synthesises audio (tones or noise shaped by the demo meter levels), so the feature can be shown without hardware.
4. UI: listen buttons, confirm dialog, Listen bar, crash-leftover toast, settings (buffer, output device, mix).
5. If step 1 fails for native flows: ship AES67-only listening, and open an upstream issue proposing a daemon PCM stream endpoint.

### Phase 5 (later, optional)
Windows arm64, multi-channel listen mix with panning, recording a listened channel to WAV, transmit-flow editor UI, DDM awareness.

---

## Critical files
- **Port sources:** `netaudio_desktop/api.py`, `meters.py`, `clock.py`, `devsettings.py`, `presets.py`, `demo.py`. UI behaviour reference: `app.py` (RoutingView at L182, DeviceDetail at L441, Window at L713), `presets_ui.py`, `issues_ui.py`.
- **Reuse from podstudio:** `native/app/theme.{h,cpp}`, `native/app/widgets.{h,cpp}`, `native/app/fonts/`, `native/app/main_win32.cpp`, `native/app/platform_win32.cpp`, `native/app/http_win32.cpp`, `native/core/updates.cpp`, `native/installer/podstudio.iss`, `native/CMakeLists.txt` (FetchContent pattern), `.github/workflows/packages.yml`.
- **Upstream reference:** `packages/netaudio-endpoint/src/receive.rs` (native-v2 receive), `packages/netaudio-daemon/src/http/devices/flow_authoring.rs` (flow API), and the daemon's OpenAPI at `GET /api/docs` for exact request schemas.

## Verification
- **Phase 0:** the grep in Phase 0 returns nothing, and CI is green.
- **Phase 1:** `cmake -S . -B build && cmake --build build && ctest --test-dir build` passes on `windows-latest`. Golden-fixture tests match the Python outputs exactly.
- **Phases 2–3:** launch with `--demo` and walk through the §6 checklist. Integration tests run against `tools/mock_daemon.py`, including the preset plan → apply path and a stale digest being refused. Run the installer on clean Windows 10 and 11 VMs, confirm the bundled daemon starts, and confirm quitting stops it.
- **Phase 4:**
  - Packet-capture fixtures decode to the expected PCM.
  - On hardware: listen to a transmit channel, and to a receive channel that follows its subscription. Confirm the flow appears in the device's flow list and is gone after Stop.
  - Kill the app while listening, relaunch, and confirm the leftover-flow toast appears and removes the flow.
  - Measure the network-to-ear latency.
