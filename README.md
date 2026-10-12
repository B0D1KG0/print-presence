<p align="center"><img src="assets/logo.png" width="128" alt="Print Presence logo"></p>

<h1 align="center">Print Presence</h1>

**English** · [Русский](README.ru.md) · [Українська](README.uk.md)

Discord Rich Presence for 3D printers: your friends see what you're printing, the current layer, progress and time left.

<p align="center"><b><a href="https://github.com/B0D1KG0/print-presence/releases/latest/download/PrintPresence-Setup.exe">⬇ Download installer</a></b> · <a href="https://github.com/B0D1KG0/print-presence/releases/latest/download/PrintPresence-Portable.zip">Portable (zip)</a> · <a href="https://github.com/B0D1KG0/print-presence/releases">All releases</a></p>

<p>
  <img src="docs/home-en.png" width="760" alt="Home tab: Discord preview and print progress"><br>
  <img src="docs/settings-en.png" width="760" alt="Settings tab with automatic printer discovery">
  <br><img src="docs/constructor-en.png" width="760" alt="Rich Presence constructor with a live preview">
</p>

Supports **Bambu Lab** printers (tested on P1S) over the local network. Other printers can be added as separate modules in `print_presence/printers/`.

> Unofficial project, not affiliated with Bambu Lab or Discord.

## Features

- Status in Discord: printing / preparing / paused / finished / failed / idle, file name, layer `87/240`, percent, countdown to the end; filament (`PLA Basic · Black`) and temperatures on hover
- **Finds printers on the network automatically**: IP, serial number and model — you only type the Access Code
- **Rich Presence constructor**: write your own status lines with variables and see a live preview — changes reach Discord within seconds, no restart needed
- **Several printers** (print farm): Discord shows the one that is printing right now
- Printer picture in Discord matches your model (X1, P1S, P1P, A1, A1 mini, H2D)
- Dashboard with a card per printer: photo, progress ring, layer, time left, filament
- **Runs in the tray** and can **start with Windows**; tells you when a new version is out
- Privacy: optionally hide the file name
- Nothing to set up in Discord — the shared app with icons is built in
- Works locally: talks to the printer over your LAN, no Bambu cloud, the Access Code never leaves your PC
- English, Russian and Ukrainian interface, picked from your system language

## Requirements

- Windows 10/11
- The Discord **desktop app** (Rich Presence doesn't work in the browser) running on the same PC
- The printer and the PC on the same local network

## Install

1. Download one of the versions (always the latest):

   | File | For whom |
   |---|---|
   | **[PrintPresence-Setup.exe](https://github.com/B0D1KG0/print-presence/releases/latest/download/PrintPresence-Setup.exe)** | Most people. Installs the app with Start menu / desktop shortcuts and an uninstaller. No administrator rights needed. |
   | **[PrintPresence-Portable.zip](https://github.com/B0D1KG0/print-presence/releases/latest/download/PrintPresence-Portable.zip)** | Unzip anywhere (even a USB stick) and run. Settings stay in the `data` folder next to the app, nothing is written to the system. |
   | [PrintPresence.exe](https://github.com/B0D1KG0/print-presence/releases/latest/download/PrintPresence.exe) | A single file without installing; settings go to `%APPDATA%\PrintPresence`. |

2. Run it. Windows may say "Windows protected your PC" because the app isn't code-signed: click **More info → Run anyway**.
3. On first launch the app looks for printers on your network and fills in the **IP, serial number and model**. If Windows asks about the firewall, allow access on private networks — otherwise discovery can't work.
4. Enter the **Access Code** (the printer doesn't announce it: printer screen → Settings → WLAN) and press **▶ Start**.

If discovery doesn't find the printer (different subnet, VPN, blocked by the firewall), enter the IP and serial number by hand.

Settings are saved to `%APPDATA%\PrintPresence\settings.json` (portable version: the `data` folder next to the app).

- **Several printers**: Settings → Printers → **+ Add**, or **Find printers on network** adds every printer it finds. Discord shows the busiest one (printing > paused > preparing > finished > idle).
- **Tray**: closing the window keeps the app running next to the clock; right-click the icon for Open / Start / Stop / Quit.
- **Launch with Windows**: the app starts minimised in the tray and turns the status on by itself.
- "Name in Discord" is shown when hovering the picture in your status; leave it empty to use the printer model. The title after "Playing" is always the Discord application name.
- The **“Get Print Presence”** button in your status is visible to other people only (Discord never shows your own buttons to you). You can turn it off.

## Rich Presence constructor

The **Constructor** tab lets you write every line of the status yourself. Turn on **Own status template** and type, e.g. `🖨 {status}[: {job}]`.

- `{name}` is replaced with a value; a part in `[square brackets]` disappears when a value inside it is empty — `[ · {progress}]` is shown only while printing.
- Click a variable chip to insert it into the selected line. The preview on the right shows sample states (printing, paused, done, idle) or the real printer.
- While the status is running, every change is sent to Discord within a few seconds (Discord allows about 5 updates per 20 seconds).
- **Own text per state**: pick a state under "Text for" (printing, paused, done, error, idle) and turn on "Own text for this state".
- Every line except the first can be switched off; each one shows a `used/128` counter.
- **Display**: timer (time left / elapsed / off), counter `(87 of 240)` by layers or percent, status badge on/off, activity type (Playing / Watching / Listening / Competing) and what the member list shows (app name, 1st or 2nd line).
- **Own button**: a second button with your link (e.g. the model on MakerWorld). Discord allows 2 buttons and 32 bytes per label — a Cyrillic letter takes 2 bytes, longer text is cut.
- Discord's limits that can't be changed: 2 text lines of up to 128 characters, the name after "Playing" is the Discord application name, pictures must be uploaded to the application.

| Variable | Example | | Variable | Example |
|---|---|---|---|---|
| `{status}` | Printing | | `{filament}` | PLA Basic · Black |
| `{job}` | Benchy.3mf | | `{material}` / `{color}` | PLA Basic / Black |
| `{layer}` | Layer 87/240 | | `{nozzle}` / `{bed}` | 220°C / 65°C |
| `{layer_num}` / `{total_layers}` | 87 / 240 | | `{temps}` | Nozzle 220°C · Bed 65°C |
| `{progress}` | 42% | | `{printer}` | Bambu Lab P1S |
| `{remaining}` / `{eta}` | 1h 23m / 18:45 | | | |

## Own Discord application (optional)

By default the app uses the shared Print Presence application — icons are already uploaded, nothing to do.
You only need your own app for your own icons or your own name after "Playing".

1. Open <https://discord.com/developers/applications> → **New Application**.
2. The application name is what shows after "Playing", e.g. `Bambu Lab P1S`.
3. On **General Information** copy the **Application ID**.
4. **Rich Presence → Art Assets**: upload images (at least 512×512, you can start from [`assets/`](assets)). The asset name is the file name without `.png`:

   | Asset name | What it is |
   |---|---|
   | `printer` | large image — the printer |
   | `printing` | "printing" badge |
   | `paused` | "paused" badge |
   | `finished` | "finished" badge |
   | `failed` | "failed" badge |
   | `idle` | "idle" badge |

   Discord sometimes takes 5–10 minutes to show newly uploaded images.
5. In the app, turn off **Standard design** and paste the Application ID into **Own Application ID**.

## Troubleshooting

- **"Printer refused the connection" / "Not authorized"**: check the IP and Access Code (it changes if you refresh it on the printer).
- If they're definitely correct and the printer still refuses (newer Bambu firmware restricts third-party access): enable **LAN Only Mode** and then **Developer Mode** on the printer. Note that LAN Only disables the cloud and Bambu Handy.
- **Discovery finds nothing**: allow the app in Windows Firewall (private networks). Bambu Studio may hold the same ports — close it while searching, or enter the IP by hand.
- **"Discord is not running"**: start the Discord desktop app, Print Presence reconnects by itself.
- Details are in the **Log** tab.

## Build from source

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt pytest
python -m pytest
python run_gui.py               # desktop app
python -m print_presence -v     # console version, reads config.toml (see config.example.toml)
```

Build: run `build.bat` — it installs everything and creates `dist\PrintPresence.exe`, `dist\PrintPresence-Portable.zip` and, if [Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed (`winget install JRSoftware.InnoSetup`), `dist\PrintPresence-Setup.exe`.
To sign it, set `SIGN_CERT` (path to a `.pfx`) and `SIGN_PASSWORD` before running `build.bat` (needs `signtool` from the Windows SDK).
The **Build Windows exe** workflow in the Actions tab does the same on GitHub and publishes a release for the current version.

Adding another printer: create a `Printer` subclass in `print_presence/printers/` that returns `PrinterStatus`, and register it in `printers/__init__.py`.

## License

[MIT](LICENSE) © B0D1KG0. Third-party components: [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Bambu Lab is a trademark of its owner; this project is not endorsed by Bambu Lab.
