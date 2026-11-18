# Gentoo Update Manager — Rust + GTK 4 v2.0-final

<img width="2560" height="1585" alt="Screenshot_20261117_000932" src="https://github.com/user-attachments/assets/1ca45e9d-2052-4a6b-bad8-8fc188d936d9" />


Native Gentoo Portage management interface with navy, violet and teal styling inspired by Asahi Startup Disk.

## Recent Changes 2.0-Final
- Includes the existing Portage package-atom validation fix and prior GTK4 interface updates. No new functional changes are in this 2.0-final update. Primarily bug fixes!


## Install

On Gentoo install Rust/Cargo, GTK 4 development files and pkg-config, then:

```sh
unzip Gentoo-Update-Manager-2.0-final.zip
cd Gentoo-Update-Manager-2.0-final
chmod +x install.sh to install or chmod +x uninstall.sh to uninstall
./install.sh to install ./uninstall.sh to uninstall
```

Launch **Gentoo Update Manager (GTK4)** from the KDE menu. If it does not launch, run `./diagnose.sh`.

## Important limitations

This is a **development preview**, not yet a full replacement for the previous Qt version. The Held Back screen currently reads system masks but does not edit them. Privileged operations use sudo with a password cached in the app's process memory. The application does not provide a fully interactive PTY for all Portage prompts; review transactions carefully. The source has not been compiled or tested in a live Gentoo GTK session here.

