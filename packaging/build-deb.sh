#!/usr/bin/env bash
# Build a .deb with dpkg-deb only (no setuptools/debhelper needed).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
ver="$(python3 -c "import re;print(re.search(r'\"([^\"]+)\"',open('$here/netaudio_desktop/__init__.py').read()).group(1))")"
arch="all"
root="$(mktemp -d)"; trap 'rm -rf "$root"' EXIT
pkg="$root/netaudio-desktop_${ver}_${arch}"

install -d "$pkg/DEBIAN" "$pkg/usr/lib/python3/dist-packages" "$pkg/usr/bin" \
  "$pkg/usr/share/applications" "$pkg/usr/share/icons/hicolor/scalable/apps" \
  "$pkg/usr/share/metainfo" "$pkg/usr/share/doc/netaudio-desktop"
cp -r "$here/netaudio_desktop" "$pkg/usr/lib/python3/dist-packages/"
find "$pkg" -name __pycache__ -prune -exec rm -rf {} +
printf '#!/bin/sh\nexec python3 -m netaudio_desktop "$@"\n' > "$pkg/usr/bin/netaudio-desktop"
chmod 755 "$pkg/usr/bin/netaudio-desktop"
sed 's|@EXEC@|netaudio-desktop|' "$here/data/app.netaudio.Desktop.desktop" > "$pkg/usr/share/applications/app.netaudio.Desktop.desktop"
install -m644 "$here/data/app.netaudio.Desktop.svg" "$pkg/usr/share/icons/hicolor/scalable/apps/"
install -m644 "$here/data/app.netaudio.Desktop.metainfo.xml" "$pkg/usr/share/metainfo/"
install -m644 "$here/LICENSE" "$pkg/usr/share/doc/netaudio-desktop/copyright"

cat > "$pkg/DEBIAN/control" <<EOF
Package: netaudio-desktop
Version: $ver
Section: sound
Priority: optional
Architecture: $arch
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
Recommends: curl
Maintainer: NetAudio Desktop maintainers <noreply@example.invalid>
Homepage: https://netaudio.app/linux
Description: Desktop controller for Dante audio networks (unofficial)
 A native GTK4/libadwaita front end for the NetAudio daemon. Browse Dante
 devices, route channels in a matrix, rename devices and channels, set sample
 rates and identify hardware.
 .
 The netaudio daemon is installed separately (uv tool install netaudio).
 Not affiliated with Audinate.
EOF
cat > "$pkg/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
EOF
chmod 755 "$pkg/DEBIAN/postinst"
mkdir -p "$here/dist"
fakeroot dpkg-deb --build "$pkg" "$here/dist/netaudio-desktop_${ver}_${arch}.deb" >/dev/null
echo "$here/dist/netaudio-desktop_${ver}_${arch}.deb"
