#!/usr/bin/env python3
"""Entry point for Mothership Lights.

    python3 mothership_lights.py            # launch the GUI
    python3 mothership_lights.py --selftest # headless checks (no display/audio HW)
"""

import sys


def main():
    if "--selftest" in sys.argv:
        from mslights.selftest import run   # no tkinter import on this path
        run()
        return
    from mslights.app import main as app_main
    app_main()


if __name__ == "__main__":
    main()
