# Gentoo Update Manager — Plasma-style GUI

Gentoo-only PySide6/Qt 6 frontend using the original `gentoo-update-manager.py` as its Portage data backend. The interface uses KDE/Qt system palette colors and follows light/dark theme changes while open. It installs a `.desktop` launcher in your user application menu.

## Gentoo dependencies

```sh
sudo emerge --ask dev-python/pyside6
```

Portage (`emerge`) is required. Install/configure `sudo` or `doas` and a terminal emulator such as Konsole for interactive Portage transactions. For KDE integration, use your preferred Breeze or other Qt widget style.

## Install

```sh
chmod +x install.sh
./install.sh
```

Find **Gentoo Update Manager** in the KDE application launcher (usually System), or run `~/.local/bin/gentoo-update-manager`. Log out/in if your desktop menu caches application entries. Run `./uninstall.sh` to remove the installed app without deleting hold rules.

## Functionality and limitations

Updates, installed packages, held-back rules, Portage sync, depclean, preserved rebuild, config merging, and technical logs are provided. Config and hold rules remain compatible with the original script (`~/.config/gentoo-update-manager/config.json`). Holds are app-local, not `/etc/portage/package.mask` rules. Package operations open an external terminal to preserve interactive Portage confirmation; recheck/refresh after transactions. This is a preview, not a tested production release; multi-select installed operations and some TUI keyboard behaviors are not yet reproduced. Do not run the GUI as root. Review Portage's proposed actions before approving.
