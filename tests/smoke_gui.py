"""Headless smoke test: drive the real GUI against the simulator.

Run with:  xvfb-run -a python3 tests/smoke_gui.py
Exits non-zero if the app never receives live data or never applies limits.
"""

import subprocess
import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pedalcal.gui import CalibratorApp  # noqa: E402

FAILURES = []


def main() -> int:
    root = tk.Tk()
    root.geometry("620x680")
    app = CalibratorApp(root, initial_port="SIMULATOR")  # auto-connects

    def check_streaming():
        if all(p.raw == 0 for p in app.panels):
            FAILURES.append("no live data arrived from the device")
        app.toggle_learn()          # start learning

    def stop_learning():
        app.toggle_learn()          # stop -> writes observed range + applies
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
        app.disconnect()
        root.destroy()

    root.after(1500, check_streaming)
    root.after(4000, stop_learning)
    root.after(4400, shoot)
    root.after(4800, finish)
    root.mainloop()

    for problem in FAILURES:
        print("FAIL:", problem)
    print("smoke test:", "FAILED" if FAILURES else "OK")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
