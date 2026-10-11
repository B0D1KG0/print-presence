# Contributing to Print Presence

Thanks for wanting to help! Bug reports, ideas, translations and code are all welcome.
English, Ukrainian and Russian are all fine.

## Reporting a bug

Open an [issue](../../issues/new/choose) using the **Bug report** template and include:

- the app version (shown under the name in the window),
- your printer model and firmware version,
- what you expected and what happened,
- the relevant part of the **Log** tab.

**Never post your Access Code.** If you paste a log or screenshot, hide the serial number and IP address too.

## Suggesting a feature

Use the **Feature request** template. Tell us what problem it solves — that helps more than a ready solution.

## Adding a translation

All texts are in [`print_presence/i18n.py`](print_presence/i18n.py) (interface) and
[`print_presence/presence.py`](print_presence/presence.py) (Discord status).
Add your language code to every entry, add it to `LANGUAGES` / `LANGUAGE_NAMES`, and run the tests —
`tests/test_i18n.py` checks that no string is missing.

Keep the Discord button label within **32 bytes** in UTF-8, otherwise Discord silently hides the whole status from other people.

## Supporting another printer

1. Create a `Printer` subclass in `print_presence/printers/` that returns a `PrinterStatus` (see `bambu.py`).
2. Register it in `print_presence/printers/__init__.py`.
3. Add tests with a sample of the printer's data.

## Development setup

Python 3.11+ on Windows (the app also runs on Linux/macOS for development).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt pytest
python -m pytest                # must pass before you open a pull request
python run_gui.py
```

`build.bat` builds `dist\PrintPresence.exe`.

## Pull requests

- One topic per pull request; keep it small if you can.
- Match the style of the surrounding code.
- Add or update tests for behaviour changes.
- Update the READMEs (all three languages if you can — otherwise say so and someone will help).
- Don't commit `config.toml`, settings files or anything with a real Access Code.
