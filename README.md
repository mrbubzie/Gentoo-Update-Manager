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

## Embedded transactions (v1.1 preview)

Portage transactions now run in a built-in interactive Qt dialog backed by a
pseudo-terminal (PTY). **Konsole/xterm are no longer required.** The dialog
streams output, accepts replies to Portage prompts, and displays the exit code.

Authentication uses `pkexec` when available (requires a running graphical
Polkit agent), otherwise `sudo` or `doas` using the embedded PTY. Configure
one of these before running privileged actions. The main GUI runs unprivileged.

Interactive config merge tools (`dispatch-conf` and `etc-update`) also run
inside this window. They retain their terminal-oriented interaction, but do
not open a separate terminal application.

This is a preview: it has been syntax-checked but not tested on a live Gentoo
installation. PTY output currently strips ANSI escape sequences; advanced
full-screen terminal controls may not render correctly. Avoid using this
preview for critical upgrades without a tested recovery method.

## Gentoo logo icon (v1.1.2)

The application and desktop launcher use `assets/gentoo-update-manager-256.png`, a blue
Gentoo-inspired mark with a Breeze-style update arrow. Running `./install.sh`
replaces the previously installed icon and refreshes KDE's application database.
If a running launcher still shows the old icon, restart the launcher or log out
and back in; existing Plasma processes may retain cached pixmaps.

Version 1.1.2 includes a new blue Plasma-style icon featuring the Gentoo g symbol and a refresh badge. The installer installs PNG icons in six sizes and removes the obsolete SVG.
