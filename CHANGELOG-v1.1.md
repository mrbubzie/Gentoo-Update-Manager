# Gentoo Update Manager v1.1.0-preview

- Replaced external Konsole/xterm transaction launching with an embedded Qt dialog.
- Interactive Portage confirmations can be answered directly in the application.
- Live output, exit codes, cancellation with confirmation, and post-transaction refresh.
- Polkit (`pkexec`) authentication preferred; `sudo`/`doas` fallback.
- Original Gentoo-only Portage backend and Plasma styling retained.

**Known limitation:** PTY text viewer is not a complete terminal emulator;
interactive full-screen programs may not display properly. Not live-tested.
