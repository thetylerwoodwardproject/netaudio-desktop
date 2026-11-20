#!/usr/bin/env bash
# Installs NetAudio Desktop for the current user (no sudo needed).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"

missing=()
python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")' 2>/dev/null \
  || missing+=("python3-gi gir1.2-gtk-4.0 gir1.2-adw-1")
if ((${#missing[@]})); then
  echo "Missing GUI packages. Run: sudo apt install ${missing[*]}" >&2; exit 1
fi

install -Dm644 "$here/data/app.netaudio.Desktop.svg" \
  "$HOME/.local/share/icons/hicolor/scalable/apps/app.netaudio.Desktop.svg"
sed "s|@EXEC@|$here/netaudio-desktop|" "$here/data/app.netaudio.Desktop.desktop" \
  > "$HOME/.local/share/applications/app.netaudio.Desktop.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "Installed launcher. Search for “NetAudio” in your app menu."

if ! command -v netaudio-daemon >/dev/null && ! command -v netaudio >/dev/null; then
  echo
  echo "The netaudio daemon is not installed yet. Install it with:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh   # if you don't have uv"
  echo "  uv tool install netaudio"
fi
