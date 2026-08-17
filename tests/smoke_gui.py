"""Headless smoke test: drive the real GUI, both happy path and failure path.

Run with:  xvfb-run -a python3 tests/smoke_gui.py   (or just `python tests/smoke_gui.py`
on a desktop). Exits non-zero if anything misbehaves.
"""

import subprocess
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pedalcal import gui  # noqa: E402
from pedalcal.device import PortInfo  # noqa: E402
from pedalcal.gui import CalibratorApp  # noqa: E402
from pedalcal.icon_data import ICON_PNG_B64  # noqa: E402

FAILURES = []


def check_simulator() -> None:
    """Connect to the simulator, watch data flow, learn a range, save."""
    root = tk.Tk()
    root.geometry("620x680")
    try:
        root._icon = tk.PhotoImage(data=ICON_PNG_B64)
        root.iconphoto(True, root._icon)
    except Exception as exc:
        FAILURES.append(f"embedded icon failed to load: {exc}")

    app = CalibratorApp(root, initial_port="SIMULATOR")  # auto-connects

    def check_streaming():
        if all(p.raw == 0 for p in app.panels):
            FAILURES.append("no live data arrived from the device")
        if not app.identified:
            FAILURES.append("handshake never completed")
        app.toggle_learn()

    def stop_learning():
        app.toggle_learn()
        for panel in app.panels:
            lo, hi = panel.limits()
            if not (0 <= lo < hi <= 1023):
                FAILURES.append(f"axis {panel.index} bad range {lo}-{hi}")

    def shoot():
        root.update_idletasks()
        subprocess.run(["import", "-window", "root", "/tmp/pedalcal.png"],
                       check=False)

    def finish():
        app.save_calibration()
        app._on_close()   # the real close path

    root.after(1500, check_streaming)
    root.after(4000, stop_learning)
    root.after(4400, shoot)
    root.after(4800, finish)
    root.mainloop()


def check_bad_port() -> None:
    """A port that cannot be opened must show an error, not kill the app."""
    shown = []
    real_list, real_error = gui.list_serial_ports, gui.messagebox.showerror
    gui.list_serial_ports = lambda include_simulator=True: [
        PortInfo("COM_DOES_NOT_EXIST", "pretend device")]
    gui.messagebox.showerror = lambda title, message, **kw: shown.append(message)
    try:
        root = tk.Tk()
        app = CalibratorApp(root, initial_port="COM_DOES_NOT_EXIST")
        root.after(3000, app._on_close)
        root.mainloop()
    finally:
        gui.list_serial_ports, gui.messagebox.showerror = real_list, real_error

    if not shown:
        FAILURES.append("bad port produced no error dialog")
    elif "port" not in shown[0].lower():
        FAILURES.append(f"unhelpful error text: {shown[0]!r}")
    if app.device is not None:
        FAILURES.append("app thinks it is connected after a failed open")


def main() -> int:
    check_simulator()
    check_bad_port()
    for problem in FAILURES:
        print("FAIL:", problem)
    print("smoke test:", "FAILED" if FAILURES else "OK")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
