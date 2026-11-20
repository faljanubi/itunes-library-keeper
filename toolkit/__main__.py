"""Entry point: python -m toolkit [--background]"""
import argparse
import logging
import os
import sys

from .config import APP_DIR


def main():
    ap = argparse.ArgumentParser(description="iTunes Library Keeper")
    ap.add_argument("--background", action="store_true",
                    help="start in the notification area without opening the window (used at Windows startup)")
    ap.add_argument("--quit", action="store_true",
                    help="ask a running copy to quit (after its current task) and exit; used by Setup/Uninstall")
    args, _unknown = ap.parse_known_args()  # tolerate old shortcuts' --no-browser

    os.makedirs(APP_DIR, exist_ok=True)
    handlers = [logging.FileHandler(os.path.join(APP_DIR, "toolkit.log"), encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)

    from .gui.main import run
    sys.exit(run(background=args.background, quit_running=args.quit))


if __name__ == "__main__":
    main()
