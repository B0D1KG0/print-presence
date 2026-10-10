from __future__ import annotations

import argparse
import logging
import sys
import tomllib
from pathlib import Path

from . import i18n
from .runner import Runner

log = logging.getLogger("print_presence")


def default_config_path() -> Path:
    # Next to the .exe when frozen with PyInstaller, otherwise the current folder.
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    return base / "config.toml"


def main() -> int:
    parser = argparse.ArgumentParser(prog="print-presence", description="Discord Rich Presence for 3D printers")
    parser.add_argument("-c", "--config", type=Path, default=default_config_path())
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    i18n.set_language("auto")
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

    try:
        runner = Runner(cfg)
    except ValueError as e:
        log.error("%s", e)
        return 1

    log.info("Running. Press Ctrl+C to stop.")
    try:
        runner.run_forever()
    except KeyboardInterrupt:
        log.info("Stopping...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
