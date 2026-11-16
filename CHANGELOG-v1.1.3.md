# v1.1.3 — Icon rendering fix

- Converted all icon PNGs to opaque RGB to prevent black rendering from alpha-compositing problems.
- Launcher now points directly to the installed 256px icon, avoiding stale themed-icon resolution.
- Installer invalidates old hicolor cache and rebuilds KDE application database.
