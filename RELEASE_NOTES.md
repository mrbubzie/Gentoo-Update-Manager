# Gentoo Update Manager — Plasma GUI Preview v1.0.0-preview

A Gentoo-only graphical frontend for Portage, redesigned from the original Python curses TUI with a modern KDE Plasma-inspired Qt 6 interface.

## Highlights

- Qt 6 / PySide6 graphical interface with Breeze-friendly light and dark themes
- Corrected horizontal navigation tabs for Updates, Installed Software, and Held Back
- Custom scalable Gentoo-inspired SVG application icon
- Installer that refreshes the desktop database, icon cache, and KDE Plasma application menu when supported
- Check and select Portage updates; view package changes and installed packages
- Hold or release packages using the original application's JSON configuration
- Portage maintenance actions: repository sync, depclean, preserved rebuild, and config file review
- External terminal for interactive Portage confirmations; technical output and help dialogs

## Requirements

Gentoo Linux, Python 3, Portage (`emerge`), `dev-python/pyside6`, a terminal emulator (Konsole recommended), and configured `sudo` or `doas` for privileged operations.

```bash
sudo emerge --ask dev-python/pyside6
```

## Install

```bash
chmod +x install.sh
./install.sh
```

Launch **Gentoo Update Manager** from the application menu, or run `~/.local/bin/gentoo-update-manager`.

## Known limitations

This is a preview, not a production-tested release. Package transactions launch in an external terminal and require manual refresh afterward. Some multi-selection and TUI keyboard features are not yet replicated. Hold rules apply only inside this application; they do not write Portage package masks. Review every proposed Portage transaction before approving.

## Source

The release archive includes the original Gentoo update manager backend, the Qt frontend, the installer/uninstaller, the SVG icon, and README.

See CHANGELOG-v1.2.3.md for the integrated interface and authentication changes.
