# Third-party notices

Print Presence is released under the [MIT License](LICENSE). The Windows builds
(`PrintPresence.exe`, the installer and the portable version) also contain the
following software, each under its own license:

| Component | License | Source |
|---|---|---|
| [Python](https://www.python.org) runtime | PSF License 2.0 | https://github.com/python/cpython |
| Tcl/Tk (bundled with Python) | Tcl/Tk License (BSD-style) | https://www.tcl.tk |
| [paho-mqtt](https://github.com/eclipse-paho/paho.mqtt.python) | EPL-2.0 or BSD-3-Clause (EDL-1.0) — used under BSD-3-Clause | https://github.com/eclipse-paho/paho.mqtt.python |
| [pypresence](https://github.com/qwertyquerty/pypresence) | MIT | https://github.com/qwertyquerty/pypresence |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | MIT | https://github.com/TomSchimansky/CustomTkinter |
| [darkdetect](https://github.com/albertosottile/darkdetect) | BSD-3-Clause | https://github.com/albertosottile/darkdetect |
| [packaging](https://github.com/pypa/packaging) | Apache-2.0 or BSD-2-Clause | https://github.com/pypa/packaging |
| [Pillow](https://python-pillow.org) | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| [pystray](https://github.com/moses-palmer/pystray) | **LGPL-3.0** | https://github.com/moses-palmer/pystray |
| [six](https://github.com/benjaminp/six) | MIT | https://github.com/benjaminp/six |
| [PyInstaller](https://pyinstaller.org) bootloader | GPL-2.0-or-later with the bootloader exception (allows distributing the built app under any license) | https://github.com/pyinstaller/pyinstaller |
| [Inno Setup](https://jrsoftware.org/isinfo.php) (installer only) | Inno Setup License | https://github.com/jrsoftware/issrc |

## About pystray (LGPL-3.0)

pystray is used unmodified to show the tray icon. The LGPL lets you replace it with
your own version: the complete source of Print Presence is in this repository, so you
can install a different pystray into the build environment and run `build.bat` to get
an executable that uses it. The LGPL-3.0 text is at https://www.gnu.org/licenses/lgpl-3.0.html.

## Pictures and trademarks

- The status icons and drawn printer icons in [`assets/`](assets) are part of this project (MIT).
- Printer photos shown in the app and in Discord are not part of this repository or the builds:
  they are loaded at runtime from the Discord application's Rich Presence art.
- Bambu Lab and Discord are trademarks of their owners. This project is not affiliated with
  or endorsed by Bambu Lab or Discord.
