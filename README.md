# NetAudio Desktop

A native GTK4 / libadwaita desktop app for Ubuntu (and other GNOME-based Linux) that controls
Dante devices through the [NetAudio](https://netaudio.app/linux) daemon
([chris-ritsen/network-audio-controller](https://github.com/chris-ritsen/network-audio-controller)).
Unofficial; not affiliated with Audinate.

- **Routing**: matrix of receivers (rows) vs. transmitters (columns). Click a cell to subscribe, click again to clear.
- **Devices**: info, **clock & sync details** (role, grandmaster, who each device syncs to, offset, ports, preferred-leader switch), rename device/channels, set sample rate, identify.
- **Status bar**: connection, device/route counts and overall clock health (grandmaster · N/M in sync).
- **Rename channels from the matrix**: click a receive channel name (row) or transmit channel number (column header).
- Starts `netaudio-daemon` for you if it isn't running; talks to it over its local HTTP API.

- **Demo mode**: switch it on from the app menu (☰ → Demo mode) or the “Try Demo Mode” button on the empty screen. It runs against simulated devices, no Dante network needed. (`--demo` starts directly in it.)

## Install
    sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
    uv tool install netaudio      # provides netaudio-daemon
    ./install.sh                  # adds “NetAudio” to your app menu

Or just run `./netaudio-desktop`. Settings (port, auto-start) are in the app menu → Preferences
(default port 4780, stored in `~/.config/netaudio-desktop/config.json`).

## Packages
Tagged releases (`vX.Y.Z`) build and attach to the GitHub Release:
- `netaudio-desktop_X.Y.Z_all.deb` — `sudo apt install ./netaudio-desktop_*.deb` (install the daemon separately: `uv tool install netaudio`)
- `netaudio-desktop_*.snap` — `sudo snap install --dangerous ./netaudio-desktop_*.snap` (bundles the daemon)
- Python wheel/sdist — `pipx install netaudio-desktop` (needs the GTK4/libadwaita system packages above)

Build the .deb locally: `./packaging/build-deb.sh` (output in `dist/`).

## License
MIT. The bundled/used `netaudio` daemon is a separate project under the Unlicense.
