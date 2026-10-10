from __future__ import annotations

import argparse
import logging
import sys
import time
import tomllib
from pathlib import Path

from .presence import DiscordPresence, build_activity
from .printers import create_printer
from .status import State

log = logging.getLogger("print_presence")

# Discord rate-limits presence updates to about one per 15 seconds.
MIN_INTERVAL_S = 15


def default_config_path() -> Path:
    # Next to the .exe when frozen with PyInstaller, otherwise the current folder.
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    return base / "config.toml"


def main() -> int:
    parser = argparse.ArgumentParser(prog="print-presence", description="Discord Rich Presence for 3D printers")
    parser.add_argument("-c", "--config", type=Path, default=default_config_path())
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.config.exists():
        log.error("Config not found: %s (copy config.example.toml to config.toml)", args.config)
        return 1
    with args.config.open("rb") as f:
        cfg = tomllib.load(f)

    client_id = str(cfg.get("discord", {}).get("client_id", "")).strip()
    if not client_id:
        log.error("[discord] client_id is not set in %s", args.config)
        return 1
    opts = cfg.get("presence", {})
    lang = opts.get("language", "ru")
    show_idle = opts.get("show_when_idle", True)
    interval = max(MIN_INTERVAL_S, int(opts.get("update_interval", MIN_INTERVAL_S)))

    try:
        printer = create_printer(cfg.get("printer", {}))
    except ValueError as e:
        log.error("%s", e)
        return 1

    discord = DiscordPresence(client_id)
    printer.start()
    log.info("Running. Press Ctrl+C to stop.")
    try:
        while True:
            status = printer.status()
            activity = None
            if status.state != State.IDLE or show_idle:
                activity = build_activity(status, printer.name, lang)
            discord.set(activity)
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("Stopping...")
    finally:
        discord.close()
        printer.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
