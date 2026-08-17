"""Headless smoke test: drive the real window against a fake board.

    xvfb-run -a python3 tests/smoke_gui.py      (or just run it on a desktop)

Exits non-zero if anything misbehaves. Screenshots land in /tmp when the
`import` tool from ImageMagick is available.
"""

import subprocess
import sys
import tempfile
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from fake_device import FakeSerial  # noqa: E402
from pedalcal import gui  # noqa: E402
from pedalcal import settings as S  # noqa: E402
from pedalcal.device import PedalDevice, PortInfo  # noqa: E402

FAKE_PORT = "COM_FAKE"
FAILURES = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def shoot(root, name: str) -> None:
    root.update_idletasks()
    root.update()
    subprocess.run(["import", "-window", "root", f"/tmp/{name}.png"], check=False)


def use_fake_board() -> None:
    """Point the app at a fake serial port instead of real hardware."""
    gui.list_serial_ports = lambda: [PortInfo(FAKE_PORT, "fake pedal board")]
    gui.PedalDevice = lambda port, **kw: PedalDevice(
        port, transport=lambda p, b: FakeSerial())


def isolate_settings(tmp: Path) -> None:
    S.CONFIG_FILE = tmp / ".pedalcal.json"


def check_main_flow(tmp: Path) -> None:
    isolate_settings(tmp)
    use_fake_board()
    root = tk.Tk()
    root.geometry("620x800")

    # Xvfb has no window manager, so -topmost never reads back what we set.
    # Record what the app asks for instead - that is the part we control.
    topmost_calls = []
    real_attributes = root.attributes

    def spy(*args):
        if len(args) == 2 and args[0] == "-topmost":
            topmost_calls.append(bool(args[1]))
        return real_attributes(*args)

    root.attributes = spy
    app = gui.CalibratorApp(root, initial_port=FAKE_PORT)

    def streaming():
        check(any(p.raw for p in app.panels), "no live data arrived")
        check(app.identified, "handshake never completed")
        check(topmost_calls[:1] == [True], "always-on-top not requested at startup")
        app.toggle_learn()

    def stop_learning():
        app.toggle_learn()
        for panel in app.panels:
            lo, hi = panel.limits_pct()
            check(0 <= lo < hi <= 100, f"axis {panel.index} bad range {lo}-{hi}")
        shoot(root, "v2_calibration")

    def open_settings():
        app.tabs.select(1)
        shoot(root, "v2_settings")

    def disable_clutch():
        app.axis_toggles[2].toggle()
        check(app.cfg.axes == [True, True, False], "clutch toggle not stored")
        app.tabs.select(0)

    def confirm_hidden():
        check(not app.panels[2].winfo_ismapped(),
              "disabled pedal still shown on the calibration tab")
        check(app.panels[1].winfo_ismapped(), "enabled pedal disappeared")
        shoot(root, "v2_two_pedals")

    def refuse_last_pedal():
        app.tabs.select(1)
        app.axis_toggles[0].toggle()
        app.axis_toggles[1].toggle()      # would leave nothing visible
        check(app.cfg.axes[1] is True, "app allowed every pedal to be hidden")
        app.axis_toggles[0].toggle()      # back on

    def custom_colour():
        app.custom_var.set("255, 90, 0")
        app._apply_custom_colour()
        check(app.p.accent_seed == "#ff5a00",
              f"RGB input ignored: {app.p.accent_seed}")
        app._set_base("light")
        shoot(root, "v2_light")

    def console_open():
        app.console_toggle.toggle()
        check(app.cfg.console_open, "console state not stored")

    def console_visible():
        # winfo_ismapped only updates once the event loop has processed the
        # geometry change, so this has to be a separate step.
        check(app.console_card.winfo_ismapped(), "console did not open")

    def do_reset():
        gui.messagebox.askyesno = lambda *a, **k: True
        app.reset_everything()
        check(app.cfg.axes == [True, True, True], "reset left a pedal disabled")
        check(app.p.accent_seed == S.DEFAULT_ACCENT, "reset kept the accent")
        check(app.p.dark, "reset kept the light theme")
        check(app.panels[0].limits_pct() == (0, 100), "reset kept calibration")
        check(not app.cfg.console_open, "reset left the console open")
        shoot(root, "v2_after_reset")

    def finish():
        app.save_calibration()
        app._on_close()

    for delay, step in ((1500, streaming), (3200, stop_learning),
                        (3500, open_settings), (3800, disable_clutch),
                        (4100, confirm_hidden), (4400, refuse_last_pedal),
                        (4700, custom_colour), (5100, console_open),
                        (5300, console_visible), (5600, do_reset),
                        (6000, finish)):
        root.after(delay, step)
    root.mainloop()


def check_bad_port(tmp: Path) -> None:
    """A port that cannot be opened must explain itself, not kill the app."""
    isolate_settings(tmp)
    shown = []
    gui.list_serial_ports = lambda: [PortInfo("COM_NOPE", "pretend device")]
    gui.PedalDevice = PedalDevice
    gui.messagebox.showerror = lambda title, message, **kw: shown.append(message)

    root = tk.Tk()
    app = gui.CalibratorApp(root, initial_port="COM_NOPE")
    root.after(3000, app._on_close)
    root.mainloop()

    check(bool(shown), "bad port produced no error dialog")
    if shown:
        check("port" in shown[0].lower(), f"unhelpful error: {shown[0]!r}")
    check(app.device is None, "app thinks it is connected after a failed open")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        check_main_flow(Path(tmp))
        check_bad_port(Path(tmp))
    for problem in FAILURES:
        print("FAIL:", problem)
    print("smoke test:", "FAILED" if FAILURES else "OK")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
