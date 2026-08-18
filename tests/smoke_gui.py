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
from pedalcal import protocol as P  # noqa: E402
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
    baseline: list = []

    def streaming():
        check(any(p.raw for p in app.panels), "no live data arrived")
        check(app.identified, "handshake never completed")
        check(topmost_calls[:1] == [True], "always-on-top not requested at startup")
        # Snapshot before learning starts: the panel updates live while it
        # runs, so reading it afterwards would compare a value with itself.
        baseline[:] = [p.limits_pct() for p in app.panels]
        app.toggle_learn(1)          # brake only

    def stop_learning():
        """Learning one pedal must leave the other two exactly as they were."""
        before = baseline
        app.toggle_learn(1)
        after = [p.limits_pct() for p in app.panels]
        lo, hi = after[1]
        check(0 <= lo < hi <= 100, f"brake learned a bad range {lo}-{hi}")
        check(after[1] != before[1], "learning the brake changed nothing")
        check(after[0] == before[0] and after[2] == before[2],
              "learning the brake disturbed the other pedals")
        check(not app.learning, "learning state not cleared")

    def min_max_buttons():
        """MIN/MAX capture the live position; the bar reads output, so
        setting rest with the pedal where it is must empty it."""
        panel = app.panels[0]
        panel.set_limits(0, P.ADC_MAX)
        panel._set_min()
        check(panel.lo == panel.raw, "MIN did not capture the live position")
        check(panel.meter.output < 0.02,
              f"bar should drop to empty after MIN, got {panel.meter.output:.3f}")
        check("%" in panel.pct_label.cget("text"), "percentage label missing")
        check("." in panel.pct_label.cget("text"),
              f"percentage has no decimal: {panel.pct_label.cget('text')!r}")
        # setting full below rest must be refused rather than inverting the axis
        before = panel.hi
        panel.raw = max(0, panel.lo - 5)
        panel._set_max()
        check(panel.hi == before, "allowed full to be set below rest")

    def raw_and_smoothing():
        panel = app.panels[0]
        panel.raw_toggle.toggle()
        check(app.cfg.show_raw[0] is True, "raw toggle not stored")
        check(panel.raw_label.cget("text").strip() != "",
              "raw value not shown when enabled")
        panel.raw_toggle.toggle()
        check(panel.raw_label.cget("text").strip() == "",
              "raw value still shown when disabled")
        panel.smooth_toggle.toggle()
        check(app.cfg.smoothing[0] is False, "smoothing toggle not stored")
        panel.smooth_toggle.toggle()

    def deadzone():
        panel = app.panels[0]
        panel._deadzone_dragged(20)
        panel._deadzone_committed(20)
        check(panel.deadzone == 20, "deadzone not applied")
        check(app.cfg.deadzones[0] == 20, "deadzone not stored")
        flat = [y for x, y in panel.graph.points if x < 0.19]
        check(all(v == 0.0 for v in flat), "deadzone not visible on the graph")
        check(abs(panel.graph.points[-1][1] - 1.0) < 0.02,
              "deadzone stole travel from the top of the curve")
        panel._deadzone_dragged(0)
        panel._deadzone_committed(0)

    def frame_rate():
        for index, fps in enumerate(gui.FPS_CHOICES):
            app._fps_chosen(index)
            check(app.cfg.fps == fps, f"fps {fps} not stored")
            check(app._poll_ms() == max(4, round(1000 / fps)),
                  f"poll interval wrong for {fps} fps")
        app._fps_chosen(1)

    def curves():
        panel = app.panels[0]
        panel.advanced.toggle()
        check(panel.advanced.open, "advanced section did not open")
        panel.curve_slider.set(-40)
        panel._curve_dragged(-40)
        panel._curve_committed(-40)
        check(panel.linearity == -40, f"curve not applied: {panel.linearity}")
        check(app.cfg.curves[0] == -40, "curve not stored in settings")
        points = panel.graph.points
        check(len(points) > 8, "curve graph has no points")
        check(points[0] == (0.0, 0.0), "curve does not start at zero")
        check(abs(points[-1][1] - 1.0) < 0.02, "curve does not reach full")
        middle = points[len(points) // 2]
        check(middle[1] > middle[0],
              "negative linearity should give more output at half travel")
        # the reported notches: no step between neighbouring samples should be
        # wildly bigger than its neighbours
        steps = [b[1] - a[1] for a, b in zip(points, points[1:])]
        jumps = [abs(b - a) for a, b in zip(steps, steps[1:])]
        check(max(jumps) < 0.05,
              f"curve has a visible kink, worst step change {max(jumps):.3f}")
        shoot(root, "v4_advanced")

    def tray_toggles():
        """Tray is unavailable in this environment: the app must cope."""
        app.tray_toggle.toggle()
        if not gui.tray_module.available():
            check(app.cfg.tray is False,
                  "app claimed tray support where there is none")
        app.autostart_toggle.toggle()
        if not gui.autostart.supported():
            check(app.cfg.start_with_windows is False,
                  "app claimed a Windows startup entry on a non-Windows host")
        shoot(root, "v3_calibration")

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

    def scrolling():
        """The reported bug: the wheel did nothing while over a card."""
        area = app.settings_page
        if area._content_h() <= area.winfo_height():
            return          # nothing to scroll at this window size
        before = area.yview()[0]

        class FakeWheel:
            widget = app.pedals_card.body   # deep inside the scroll area
            num = 5                         # X11 wheel-down
            delta = -120

        area._wheel(FakeWheel())
        check(area.yview()[0] > before,
              "wheel over a card did not scroll the settings page")

        class Outside:
            widget = app.panels[0]          # a different tab entirely
            num = 5
            delta = -120

        moved = area.yview()[0]
        area._wheel(Outside())
        check(area.yview()[0] == moved,
              "settings page scrolled from an event outside it")

    def controller_status():
        check(app.hid is True, f"HID capability not read: {app.hid}")
        check("ACTIVE" in app.hid_label.cget("text"),
              f"controller status unclear: {app.hid_label.cget('text')!r}")
        check(app.live_label.cget("fg") == app.p.ok,
              "connected indicator is not green")

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
        check(all(p.linearity == 0 for p in app.panels), "reset kept a curve")
        check(all(p.deadzone == 0 for p in app.panels), "reset kept a deadzone")
        check(not app.cfg.console_open, "reset left the console open")
        shoot(root, "v2_after_reset")

    def finish():
        app.save_calibration()
        app._on_close()

    for delay, step in ((1500, streaming), (3200, stop_learning),
                        (3500, open_settings), (3800, disable_clutch),
                        (4100, confirm_hidden), (4400, refuse_last_pedal),
                        (3300, curves), (3400, tray_toggles),
                        (4550, scrolling), (4650, controller_status),
                        (4700, custom_colour), (5100, console_open),
                        (5300, console_visible), (5600, do_reset),
                        (6000, finish)):
        root.after(delay, step)
    root.mainloop()


def check_port_is_remembered(tmp: Path) -> None:
    """Second launch should come back on the same port without being told."""
    isolate_settings(tmp)
    use_fake_board()

    root = tk.Tk()
    app = gui.CalibratorApp(root, initial_port=FAKE_PORT)
    root.after(1800, app._on_close)
    root.mainloop()
    check(S.load().last_port == FAKE_PORT, "port was not saved on connect")

    root = tk.Tk()
    app = gui.CalibratorApp(root)          # no port given this time
    root.after(2000, lambda: check(
        app.identified, "did not reconnect to the remembered port"))
    root.after(2100, lambda: check(
        app._selected_port() == FAKE_PORT, "remembered port not preselected"))
    root.after(2400, app._on_close)
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
        check_port_is_remembered(Path(tmp))
        check_bad_port(Path(tmp))
    for problem in FAILURES:
        print("FAIL:", problem)
    print("smoke test:", "FAILED" if FAILURES else "OK")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
