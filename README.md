# Gentoo Update Manager — Plasma GUI Preview v1.0.0
<img width="1343" height="1304" alt="Screenshot_20261114_141333" src="https://github.com/user-attachments/assets/50147c1f-c9a2-4e8d-bf28-34577522042e" />

Introducing a redesigned **Gentoo Update Manager**, featuring a modern KDE Plasma-inspired graphical interface built with Python and PySide6 (Qt 6).

Originally developed as a terminal-based update manager, this version replaces the curses TUI with a graphical application while retaining Gentoo Portage integration.

### What's New

- **Modern Plasma-inspired interface:** Breeze-friendly styling with automatic light and dark theme support.
- **Improved navigation:** Fixed horizontal tabs for Updates, Installed Software, and Held Back.
- **New application icon:** Custom scalable Gentoo-inspired SVG icon.
- **Automatic menu refresh:** The installer refreshes KDE Plasma's application menu and icon caches.
- **Package management:** Check updates, select packages, install, reinstall, and remove software.
- **Hold management:** Hold specific package versions or entire packages.
- **System maintenance:** Repository synchronization, dependency cleanup, preserved library rebuilds, and configuration file updates.
- **Interactive Portage transactions:** Package operations launch in a terminal so users can review and approve changes.

### Requirements

- Gentoo Linux
- Python 3
- PySide6 / Qt 6
- Portage
- Konsole or another supported terminal emulator
- sudo or doas configured for administrative operations

### Installation

Install the graphical dependency:

```bash
sudo emerge --ask dev-python/pyside6
```

Extract the source archive and run:

```bash
chmod +x install.sh
./install.sh
```

Launch **Gentoo Update Manager** from the KDE application menu.

### Known Limitations

This is a preview release. Package transactions currently use an external terminal, and some multi-selection and keyboard features from the original TUI are still being implemented.

Package hold rules apply within the application rather than modifying Portage's system-wide package masks.

### Compatibility

Designed exclusively for Gentoo Linux and its Portage package manager.

### Source Code

The release includes the original Python backend, Qt 6 frontend, installer, uninstaller, application icon, and documentation.
