# v1.2.3 — Integrated interface polish

- Fixed truncated application name and sidebar footer (real line breaks rather than literal escape sequences).
- Widened sidebar and improved branding spacing.
- Rounded the blue Gentoo icon with antialiased transparent corners; regenerated every installed size.
- Portage transactions now run in an embedded application page, with live PTY output, text responses, and cancellation, rather than a separate dialog.
- Administrator authentication is requested on the first privileged operation, with sudo credential validation and periodic keepalive during the application session. No password is stored.
- On exit the application stops its keepalive and invalidates sudo credentials.

**Limitations:** Complex full-screen terminal programs may not render correctly in the PTY text viewer. The sudo session requires sudo configuration that permits password authentication; Polkit fallback follows its own authentication policy. Not tested on a live Gentoo installation.
