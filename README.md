# Gentoo Update Manager — Rust + GTK 4 v0.3.0

Native Gentoo Portage management interface with navy, violet and teal styling inspired by Asahi Startup Disk.

## Changes

- Overview now contains a focused dashboard; package queries and selection are confined to their own pages.
- Updates parses only valid `[ebuild ...]` Portage entries. No selectable output headings or empty rows.
- Installed packages are discovered from `/var/db/pkg` without requiring optional `qlist`.
- Package queries run asynchronously, report errors, and discard stale results when navigating away.
- Consistent GTK symbolic sidebar icons, active-page highlighting, compact maintenance cards.
- Transaction output is collapsible and automatically expands when operations begin.
- Gentoo detection checks `/etc/os-release`, `ID_LIKE`, `/etc/gentoo-release`, and Portage's package database.
- Existing blue Gentoo icon, session password popup and separate desktop launcher retained.

## Install

On Gentoo install Rust/Cargo, GTK 4 development files and pkg-config, then:

```sh
chmod +x install.sh diagnose.sh
./install.sh
```

Launch **Gentoo Update Manager (GTK4)** from the KDE menu. If it does not launch, run `./diagnose.sh`.

## Important limitations

This is a **development preview**, not yet a full replacement for the previous Qt version. The Held Back screen currently reads system masks but does not edit them. Privileged operations use sudo with a password cached in the app's process memory. The application does not provide a fully interactive PTY for all Portage prompts; review transactions carefully. The source has not been compiled or tested in a live Gentoo GTK session here.


## v2.0 RC1 polish

Bundled white sidebar icons, single-line labels, balanced maintenance grid, and elapsed time for Portage update queries. See CHANGELOG-v2.0 RC1.md.
