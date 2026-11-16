# Gentoo Update Manager v1.2.4 — UI and transaction fixes

- Moved the brand icon above the complete one-line “Gentoo Update Manager” title to eliminate clipping.
- Corrected footer wording and version.
- Increased sidebar width and minimum window size.
- Fixed the `sudo: a password is required` error caused by checking credentials on a different terminal than the Portage PTY. Sudo now authenticates in the embedded transaction view, with masked password entry.
- Improved transaction feedback and status text.

**Authentication limitation:** sudo's credential cache is governed by the host's sudoers timestamp policy. On systems using per-TTY tickets, authentication may be requested for each new transaction. No password is saved by the application.

**Testing:** static checks only; validate interactive prompts on Gentoo before a production release.
