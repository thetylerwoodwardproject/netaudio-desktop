<div align="center">

<img src="data/app.netaudio.Desktop.svg" width="96" alt="NetAudio Desktop icon">

# NetAudio Desktop

**A native Linux desktop app for Dante audio networks.**<br>
Discover devices, patch channels in a routing matrix, and keep an eye on clock sync — all from a clean GNOME-style window.

[![Release](https://img.shields.io/github/v/release/thetylerwoodwardproject/netaudio-desktop?style=flat-square&color=3584e4)](https://github.com/thetylerwoodwardproject/netaudio-desktop/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Linux-informational?style=flat-square)
![GTK4 + libadwaita](https://img.shields.io/badge/GTK4-libadwaita-4a86cf?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-yellow?style=flat-square)

<img src="docs/screenshots/routing.png" width="560" alt="Routing matrix">

</div>

> **Unofficial.** Built on the open-source [NetAudio](https://netaudio.app/linux) daemon
> ([chris-ritsen/network-audio-controller](https://github.com/chris-ritsen/network-audio-controller)).
> Not affiliated with or endorsed by Audinate. “Dante” is a trademark of Audinate Pty Ltd.

---

## ✨ Features

| | |
|---|---|
| 🔀 **Routing matrix** | Receivers as rows, transmitters as columns, with channel names on both axes (transmit names read vertically above each column). Click a cell to subscribe, click again to clear. One source per receive channel, kept in sync with the network every few seconds. |
| ✏️ **Rename in place** | Click a receive channel name (row) or a transmit channel number (column header) to rename it right from the matrix. |
| 🎚️ **Live meters** | Press the speaker button in the header to show level bars on every channel in the matrix and on device pages. Channel names turn green when **audio is present**; bars go amber when hot and red on clipping. Opt-in, since it asks devices to stream meter data. |
| 🎛️ **Audio settings & gain** | Change sample rate, bit depth, receive latency and sample-rate pull-up from the device page, using the choices each device advertises. Per-channel **reference-level (gain)** dropdowns appear on devices that support them. Anything that can interrupt audio asks first. |
| ⚠️ **Issues** | An **Issues** tab (with a badge and a status-bar chip) lists what the daemon is flagging — clock not locked, tight receive latency, failed subscriptions, reboot needed — with a suggested fix and a link to the device. Recently resolved problems stay visible for reference. |
| 💾 **Presets** | Save the current routing, channel names, audio settings and device controls as a preset, and restore it later. Restoring **always shows a plan first** — every setting that will change, already matches, or can't be applied — and nothing is written until you confirm. Presets are plain XML files you can export, import and share. |
| 🌐 **Pick your Dante network** | On first launch (when you have more than one network interface) the app asks which one your Dante devices are on — or two, for a redundant network. Change it any time from the status bar or the ☰ menu. |
| 🔗 **Click through** | Click a device name in the routing matrix to jump straight to its page; a hover crosshair shows exactly which row and column you're about to patch. |
| 🕒 **Clock & sync** | See each device’s clock role, sync state, frequency offset, drift, **who the grandmaster is** and who each device syncs to, plus per-port status. Toggle **Preferred leader** from the app. |
| 📟 **Device details** | IP/MAC, sample rate, encoding, latency, channel counts. Rename devices, change sample rate, or flash a device’s identify light. |
| 📊 **Status bar** | Daemon connection, devices online, route count and overall clock health (`grandmaster Stagebox-A · 5/5 in sync`) at a glance. |
| 🧪 **Demo mode** | No Dante gear? Flip on **Demo mode** for a fully interactive simulated network. |
| 🚀 **Zero setup** | Starts the NetAudio daemon for you if it isn’t already running. |

<div align="center">
<img src="docs/screenshots/presets.png" width="560" alt="Restoring a preset: review the plan before anything changes">
<br><br>
<img src="docs/screenshots/issues.png" width="560" alt="Issues tab with suggested fixes">
<br><br>
<img src="docs/screenshots/devices.png" width="560" alt="Device details with clock and sync information">
</div>

## 📦 Install

Download the latest package from the [Releases page](https://github.com/thetylerwoodwardproject/netaudio-desktop/releases).

### Debian / Ubuntu (`.deb`)

```bash
sudo apt install ./netaudio-desktop_*_all.deb
uv tool install netaudio          # provides the netaudio daemon (see below)
```

### Snap (bundles the daemon)

```bash
sudo snap install --dangerous ./netaudio-desktop_*.snap
```

### From source

```bash
git clone https://github.com/thetylerwoodwardproject/netaudio-desktop
cd netaudio-desktop
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
uv tool install netaudio          # the daemon
./install.sh                      # adds “NetAudio” to your app menu
# …or just run it in place:
./netaudio-desktop
```

<details>
<summary><b>Installing the daemon</b></summary>

NetAudio Desktop is a front end; the Dante protocol work is done by the
[`netaudio`](https://netaudio.app/linux) daemon. Install it with [uv](https://docs.astral.sh/uv/):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # if you don't have uv yet
uv tool install netaudio
```

Connect the computer to the network your Dante devices are on. A Dante PCIe card is **not** required for device control.
</details>

## 🧪 Try it without any hardware

Open the main menu (☰) → **Demo mode**, or press **Try Demo Mode** on the empty screen.
You get five simulated devices with routes and a live clock — route channels, rename things,
change the grandmaster. Nothing touches your network. Launch straight into it with:

```bash
netaudio-desktop --demo
```

## 🖱️ Using it

- **Routing** — click a cell to patch, click a lit cell to unpatch. Hover headers for full channel names.
- **Rename channels** — click a channel label in the matrix, or edit it on the **Devices** page.
- **Devices** — pick a device on the left for details, clock & sync, and settings.
- **Meters** — the 🔊 button in the header turns live levels and signal-presence on or off (remembered between runs). Hover a channel for its exact dBFS.
- **Audio settings** — on a device's page, change sample rate, bit depth, latency or pull-up (you'll be asked to confirm); gain dropdowns sit beside each channel on devices that expose reference levels. Controls are disabled when a device is locked.
- **Issues** — the **Issues** tab shows open problems and a short history; expand one for what's happening, a suggested fix and **Open device page**.
- **Presets** — on the **Presets** tab choose **Save Current Setup…**, pick the devices and what to include, and name it. **Restore…** maps the preset's devices onto devices on your network (handy when hardware changed), shows the plan, and asks you to confirm before applying. Files live in `~/.local/share/netaudio-desktop/presets/`.
- **Network interface** — shown in the status bar (`Network: enp3s0`); click it, or use ☰ → *Network interface…*, to switch. Turn on *Ask every time I launch* if you move between networks.
- **Open a device** — click its name in the matrix; **Show in Routing** on the device page takes you back. Use the search box to filter long device lists.
- **Keyboard** — `Ctrl+1` Routing · `Ctrl+2` Devices · `Ctrl+3` Presets · `Ctrl+4` Issues · `Ctrl+F` search · `Ctrl+M` meters · `F5` rescan.
- **Rescan** — `F5` or the ↻ button.
- **Preferences** — daemon port (default `4780`) and auto-start, in the ☰ menu.

## 🔧 How it works

```
 NetAudio Desktop (GTK4 / libadwaita)
          │  HTTP + JSON  (127.0.0.1:4780)
          ▼
   netaudio daemon  ──►  Dante devices on your LAN
```

The app talks only to the daemon’s documented local HTTP API (`/devices`, `/subscribe`,
`/rename-channel`, `/set-preferred-leader`, `/metering/*`, `/presets/*`, `/issues`, `/set-gain`, `/set-latency`, …), reads live meter values from its
`/events` stream,, uses just the Python standard library for
networking, and keeps the UI responsive by doing all requests off the main thread.

## 🛠️ Building packages

| Package | Command |
|---|---|
| `.deb` | `./packaging/build-deb.sh` → `dist/` |
| Python wheel | `python -m build` |
| Snap | `snapcraft` |

Pushing a tag like `v2026.11.20` runs [the release workflow](.github/workflows/release.yml), which builds
all three and attaches them to a GitHub Release. Versions are calendar-based: `YYYY.MM.DD`.

## ⚠️ Status

This project is young. It is built against the daemon’s published API and exercised against a
built-in simulator, but **it has not yet been tested on a real Dante network**. Expect rough edges —
especially around clock-health colouring, which interprets the daemon’s status text heuristically
(the raw values are always shown next to it). Bug reports and hardware feedback are very welcome.

## 📄 License

[MIT](LICENSE). The `netaudio` daemon is a separate project released under the Unlicense.
