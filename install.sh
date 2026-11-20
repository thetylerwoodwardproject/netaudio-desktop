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

icons="$HOME/.local/share/icons/hicolor"
install -Dm644 "$here/data/app.netaudio.Desktop.svg" "$icons/scalable/apps/app.netaudio.Desktop.svg"
for png in "$here"/data/icons/hicolor/*/apps/app.netaudio.Desktop.png; do
  size="$(basename "$(dirname "$(dirname "$png")")")"
  install -Dm644 "$png" "$icons/$size/apps/app.netaudio.Desktop.png"
done

# Some desktops (notably COSMIC / Pop!_OS) ignore an icon theme directory that has no index.theme,
# so a bare ~/.local/share/icons/hicolor makes the icon invisible there. Provide one.
if [ ! -f "$icons/index.theme" ]; then
  if [ -f /usr/share/icons/hicolor/index.theme ]; then
    cp /usr/share/icons/hicolor/index.theme "$icons/index.theme"
  else
    cat > "$icons/index.theme" <<'THEME'
[Icon Theme]
Name=Hicolor
Comment=Fallback icon theme
Directories=48x48/apps,64x64/apps,128x128/apps,256x256/apps,512x512/apps,scalable/apps

[48x48/apps]
Size=48
Context=Applications
Type=Threshold

[64x64/apps]
Size=64
Context=Applications
Type=Threshold

[128x128/apps]
Size=128
Context=Applications
Type=Threshold

[256x256/apps]
Size=256
Context=Applications
Type=Threshold

[512x512/apps]
Size=512
Context=Applications
Type=Threshold

[scalable/apps]
Size=128
MinSize=1
MaxSize=512
Context=Applications
Type=Scalable
THEME
  fi
fi

# Point the launcher at the installed PNG by absolute path so it shows even where theme lookup is picky.
mkdir -p "$HOME/.local/share/applications"
sed -e "s|@EXEC@|$here/netaudio-desktop|" \
    -e "s|^Icon=.*|Icon=$icons/256x256/apps/app.netaudio.Desktop.png|" \
    "$here/data/app.netaudio.Desktop.desktop" > "$HOME/.local/share/applications/app.netaudio.Desktop.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
gtk-update-icon-cache -f -t "$icons" 2>/dev/null || true
echo "Installed launcher. Search for “NetAudio” in your app menu."

if ! command -v netaudio-daemon >/dev/null && ! command -v netaudio >/dev/null; then
  echo
  echo "The netaudio daemon is not installed yet. Install it with:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh   # if you don't have uv"
  echo "  uv tool install netaudio"
fi
