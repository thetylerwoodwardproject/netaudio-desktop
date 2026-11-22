<div align="center">

# NetAudio Monitor

**Live Dante levels, without touching the show.**<br>
A read-only meter for every transmit and receive channel on your Dante network, with live listening to multicast and AES67 feeds.

![Status](https://img.shields.io/badge/status-in%20development-f59e0b?style=flat-square)
![Platforms](https://img.shields.io/badge/platforms-Windows%20%C2%B7%20Linux-3b82f6?style=flat-square)
![C++17](https://img.shields.io/badge/C%2B%2B-17-a1a1aa?style=flat-square)
![Dear ImGui](https://img.shields.io/badge/UI-Dear%20ImGui-a1a1aa?style=flat-square)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)

[**View the mockup**](https://claude.ai/artifact/NxRLrazjCsEf6ZerV3BJ1A) ·
[Spec & plan](docs/SPEC.md) ·
[Features](#-features) ·
[How it works](#-how-it-works) ·
[Roadmap](#-roadmap)

</div>

> **Unofficial.** NetAudio Monitor is built on the open-source [NetAudio](https://github.com/chris-ritsen/network-audio-controller) daemon.
> It is not affiliated with or endorsed by Audinate. “Dante” is a registered trademark of Audinate Pty Ltd.

> [!NOTE]
> **Being rebuilt from scratch.** There is nothing to download yet. The design and plan are in [`docs/SPEC.md`](docs/SPEC.md),
> and the [mockup](https://claude.ai/artifact/NxRLrazjCsEf6ZerV3BJ1A) shows the screens it is building toward.

---

## ✨ Features

| | |
|---|---|
| 📊 **Real dBFS levels** | Every transmit and receive channel, as each device's own meters report it. Values are in 0.5 dB steps, with peak hold, and **CLIP**, muted and no-signal states. |
| 🎚️ **Clear meters** | A −60 to 0 dBFS scale. Green below −12, amber from −12 to −3, red above −3. |
| 🎧 **Listen live** | Feeds that are already **multicast** or **AES67** can be heard by joining them, like any other listener. |
| 🔒 **Read-only by design** | It never creates or removes routing, subscriptions or flows, and never changes device settings. Unicast feeds are levels only. |
| 🤝 **Sits beside Dante Controller** | Uses its own private daemon and metering port, so it doesn't get in the way. |
| 🕒 **Clock at a glance** | Who the clock leader is, and whether every device is locked. |
| 🔎 **Find things fast** | Filter by *with signal*, *above −12 dBFS* or *can listen*, or search everything with `Ctrl+K`. |
| 🧪 **Demo mode** | Simulated devices, levels and audio, so you can try it with no Dante gear. |

## 🖥️ Design

Dark, minimal and shadcn-inspired: the zinc palette, Inter and JetBrains Mono, 1 px borders and no clutter. Two main screens:

- **Levels:** device cards with a meter, dBFS and peak on every channel, and a listen bar docked at the bottom.
- **Flows:** every audio flow on the network, its type, and whether it can be heard.

👉 [**Open the interactive mockup**](https://claude.ai/artifact/NxRLrazjCsEf6ZerV3BJ1A)

## 🔧 How it works

```
 NetAudio Monitor  (native C++ · Dear ImGui)
        │   read-only HTTP + live event stream (localhost)
        ▼
 netaudio-daemon  (bundled, private mode)  ──►  Dante devices: meter values only
        │
        └─ listening: joins existing multicast / AES67 groups  ◄──  audio
```

- **Levels** come from the devices' own meters, the same values Dante Controller reads.
- **Listening** joins a multicast group that already exists. No device is asked to send anything new.
- **The app's client can only read.** It contains the read endpoints plus meter start and stop, and a test fails the build if anything else appears.

## 🗺️ Roadmap

| Phase | What |
|---|---|
| **0 · Foundation** | CMake + CI on Windows and Linux, bundled daemon, checks on real Dante hardware |
| **1 · Core** | Read-only daemon client, meter feed, flow map, demo source |
| **2 · Levels** | The Levels, Flows, Clock and Settings screens, as in the mockup |
| **3 · Listen** | Multicast and AES67 receive, jitter buffer, playback |
| **4 · Release** | Windows installer, `.deb` and AppImage, signed releases |

Full detail: [`docs/SPEC.md`](docs/SPEC.md).

## 💻 Platforms

| | Windows | Linux |
|---|---|---|
| **OS** | Windows 10 22H2+ / 11, x64 | x86_64, e.g. Ubuntu 22.04+, X11 or Wayland |
| **Graphics** | DirectX 11 | GLFW + OpenGL 3.3 |
| **Audio out** | WASAPI | PipeWire / PulseAudio / ALSA |
| **Package** | Installer + portable `.zip` | `.deb` + AppImage |

## 🙏 Credits

- **[NetAudio](https://github.com/chris-ritsen/network-audio-controller)** by chris-ritsen: the daemon and all of the Dante protocol work this app is built on. Go star it.
- **Dante** and **[Audinate](https://www.getdante.com)**: the audio-over-IP technology behind it all. Dante® is a registered trademark of Audinate Pty Ltd.
- **[Dear ImGui](https://github.com/ocornut/imgui)**, **[miniaudio](https://miniaud.io)**, **[nlohmann/json](https://github.com/nlohmann/json)** and **[GLFW](https://www.glfw.org)**.
- **Made with the help of machines.** Designed and written with the help of AI ([Claude](https://www.anthropic.com), by Anthropic), under human direction and review.
- **[The Tyler Woodward Project](https://tylerwoodward.me)**: direction, testing and the app itself.

## 📄 License

[MIT](LICENSE). The bundled `netaudio` daemon is a separate project released into the public domain under the [Unlicense](https://unlicense.org).
