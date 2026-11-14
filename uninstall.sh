#!/bin/sh
set -eu
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -f "$HOME/.local/bin/gentoo-update-manager" "$DATA/applications/gentoo-update-manager.desktop"
rm -rf "$DATA/gentoo-update-manager"
rm -f "$DATA/icons/hicolor/scalable/apps/gentoo-update-manager.svg"
if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "$DATA/applications" 2>/dev/null || true; fi
printf 'Uninstalled application files. Your configuration and hold rules were preserved.\n'
