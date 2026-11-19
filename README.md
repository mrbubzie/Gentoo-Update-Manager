# Gentoo Update Manager — Rust + GTK 4 v2.6.1-final

<img width="2560" height="1583" alt="Screenshot_20261118_211213" src="https://github.com/user-attachments/assets/22e2edb1-a387-47a4-b73a-326e3617bc82" />



Native Gentoo Portage management interface with navy, violet and teal styling inspired by Asahi Startup Disk.

## Recent Changes 2.6.1-Final
- Tone of fixes and UI refinements to make the look more consistat along with optional package dependency helper and additional maitnance options!


## Install

On Gentoo install Rust/Cargo, GTK 4 development files and pkg-config, then:

```sh
unzip Gentoo-Update-Manager-2.6.1-final.zip
cd Gentoo-Update-Manager-2.6.1-final
chmod +x install.sh to install or chmod +x uninstall.sh to uninstall
./install.sh to install ./uninstall.sh to uninstall
```

Launch **Gentoo Update Manager (GTK4)** from the KDE menu. If it does not launch, run `./diagnose.sh`.

## Important limitations

This is a **development preview**, not yet a full replacement for the previous Qt version. The Held Back screen currently reads system masks but does not edit them. Privileged operations use sudo with a password cached in the app's process memory. The application does not provide a fully interactive PTY for all Portage prompts; review transactions carefully. The source has not been compiled or tested in a live Gentoo GTK session here.

