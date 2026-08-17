"""Entry point: ``python -m pedalcal``."""

from __future__ import annotations

import argparse

from .device import list_serial_ports


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pedalcal", description="Sim racing pedal calibrator")
    parser.add_argument("--port", help="connect to this port on startup "
                                       "(e.g. COM4, /dev/ttyACM0)")
    parser.add_argument("--list", action="store_true",
                        help="print the serial ports found and exit")
    args = parser.parse_args()

    if args.list:
        for port in list_serial_ports():
            print(port)
        return

    from .gui import run  # imported late so --list works without a display

    run(initial_port=args.port)


if __name__ == "__main__":
    main()
