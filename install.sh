#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
TARGET="$DATA/gentoo-update-manager"
BIN="$HOME/.local/bin"
mkdir -p "$TARGET/assets" "$BIN" "$DATA/applications"
cp "$HERE/assets/gentoo-update-manager.svg" "$TARGET/assets/"
mkdir -p "$DATA/icons/hicolor/scalable/apps"
cp "$HERE/assets/gentoo-update-manager.svg" "$DATA/icons/hicolor/scalable/apps/gentoo-update-manager.svg"
cp "$HERE/app.py" "$HERE/gentoo-update-manager.py" "$TARGET/"
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
printf 'Installed Gentoo Update Manager. Find it in the application launcher under System, or run %s\n' "$BIN/gentoo-update-manager"
