#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
TARGET="$DATA/gentoo-update-manager"
BIN="$HOME/.local/bin"
mkdir -p "$TARGET/assets/navigation" "$BIN" "$DATA/applications"
cp "$HERE"/assets/navigation/*.svg "$TARGET/assets/navigation/"
# Install raster icons at standard hicolor sizes for KDE Plasma and other desktops.
for size in 32 48 64 128 256 512; do
  mkdir -p "$DATA/icons/hicolor/${size}x${size}/apps"
  cp "$HERE/assets/gentoo-update-manager-${size}.png" "$DATA/icons/hicolor/${size}x${size}/apps/gentoo-update-manager.png"
  cp "$HERE/assets/gentoo-update-manager-${size}.png" "$TARGET/assets/"
done
# Install a predictable named icon for desktop launchers.
mkdir -p "$DATA/pixmaps"
cp "$HERE/assets/gentoo-update-manager-256.png" "$DATA/pixmaps/gentoo-update-manager.png"
# Remove obsolete icon from older previews to avoid theme lookup ambiguity.
rm -f "$DATA/icons/hicolor/scalable/apps/gentoo-update-manager.svg" "$TARGET/assets/gentoo-update-manager.svg"
touch "$DATA/icons/hicolor" "$DATA/applications"
# Remove stale icon-theme caches left by older versions.
rm -f "$DATA/icons/hicolor/icon-theme.cache"
# Remove any old user-level desktop entry with the same name before rewriting it.
rm -f "$DATA/applications/gentoo-update-manager.desktop"
cp "$HERE/app.py" "$HERE/transaction.py" "$HERE/gentoo-update-manager.py" "$TARGET/"
cat > "$BIN/gentoo-update-manager" <<EOF
#!/bin/sh
exec python3 "$TARGET/app.py" "\$@"
EOF
chmod +x "$BIN/gentoo-update-manager"
cat > "$DATA/applications/gentoo-update-manager.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Gentoo Update Manager
GenericName=Portage Package Manager
Comment=Manage Gentoo updates, installed packages, holds and maintenance
Exec=$BIN/gentoo-update-manager
Icon=gentoo-update-manager
Categories=System;Settings;PackageManager;
Keywords=Gentoo;Portage;emerge;updates;packages;
Terminal=false
StartupNotify=true
EOF
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DATA/applications" 2>/dev/null || true
fi
# Refresh desktop entry, icon caches, and KDE Plasma application menus.
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f "$DATA/icons/hicolor" >/dev/null 2>&1 || true
fi
if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 --noincremental >/dev/null 2>&1 || true
fi
# KDE Plasma can cache launcher menus; request an in-session refresh when available.
if command -v qdbus6 >/dev/null 2>&1; then
  qdbus6 org.kde.kded6 /kded org.kde.kded6.reconfigure >/dev/null 2>&1 || true
fi
# Notify Plasma launchers to reload desktop metadata where possible.
if command -v dbus-send >/dev/null 2>&1; then
  dbus-send --session --dest=org.kde.KBuildSycoca6 /KBuildSycoca org.kde.KBuildSycoca6.recreate >/dev/null 2>&1 || true
fi
printf 'Installed Gentoo Update Manager. Find it in the application launcher under System, or run %s\n' "$BIN/gentoo-update-manager"
