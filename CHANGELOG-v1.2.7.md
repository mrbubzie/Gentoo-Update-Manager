# v1.2.7 — Session authentication

- Ask for administrator credentials in a password-masked popup only when a privileged Portage action is requested.
- Reuse the password for subsequent privileged actions until the application closes.
- Automatically answer sudo PTY prompts without displaying the password in the transaction panel.
- Re-prompt if sudo rejects the password; cancellation interrupts the transaction.
- Never persist credentials to configuration or disk.

Security note: For session reuse across distinct sudo PTYs, the password remains in the application's process memory until exit. This is not a system-wide sudo credential cache. Avoid leaving the application running unattended.
