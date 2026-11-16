# Gentoo Update Manager v1.2.5

- Enlarged and polished sidebar; ensured title and footer remain on one line.
- Replaced Unicode navigation glyphs with native Qt style icons for consistent appearance.
- Improved transaction error feedback and sudo password prompt recognition.
- Retained in-app PTY transactions for interactive Portage commands.
- Updated version label.

**Authentication:** sudo handles credentials within the embedded PTY. Whether subsequent transactions require a password depends on the system sudoers timestamp configuration; this application does not retain passwords.

**Validation:** Static syntax and archive integrity checks only; interactive Gentoo testing required.
