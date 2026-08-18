"""Headless smoke test: drive the real window against a fake board.

    xvfb-run -a python3 tests/smoke_gui.py      (or just run it on a desktop)

Exits non-zero if anything misbehaves. Screenshots land in /tmp when the
`import` tool from ImageMagick is installed, and are quietly skipped when it
isn't - they are a debugging aid, not an assertion.
"""

import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from fake_device import FakeSerial  # noqa: E402
from pedalcal import gui  # noqa: E402
from pedalcal import i18n  # noqa: E402
from pedalcal import profiles as PR  # noqa: E402
from pedalcal import protocol as P  # noqa: E402
from pedalcal import settings as S  # noqa: E402
from pedalcal import theme as T  # noqa: E402
from pedalcal import widgets as W  # noqa: E402
from pedalcal.device import PedalDevice, PortInfo  # noqa: E402

FAKE_PORT = "COM_FAKE"
FAILURES = []

#: How long the main flow is allowed to take before it is declared stuck. The
#: whole run is about fifteen seconds; a minute is generous even on a loaded
#: CI runner.
WATCHDOG_MS = 60_000


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


#: ImageMagick's screenshot tool, or None where it isn't installed - which is
#: the normal case on a CI runner. Looked up once rather than per call.
IMPORT_TOOL = shutil.which("import")


def shoot(root, name: str) -> None:
    """Save a screenshot if we can, and never fail the run if we can't.

    `check=False` covers the tool exiting non-zero. It does not cover the tool
    being absent: Popen raises FileNotFoundError before the process is ever
    started, which is a different failure and needs catching separately.
    """
    root.update_idletasks()
    root.update()
    if IMPORT_TOOL is None:
        return
    try:
        subprocess.run([IMPORT_TOOL, "-window", "root", f"/tmp/{name}.png"],
                       check=False, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass


def use_fake_board() -> None:
    """Point the app at a fake serial port instead of real hardware."""
    gui.list_serial_ports = lambda: [PortInfo(FAKE_PORT, "fake pedal board")]
    gui.PedalDevice = lambda port, **kw: PedalDevice(
        port, transport=lambda p, b: FakeSerial())


def isolate_settings(tmp: Path, answered: bool = True) -> None:
    S.CONFIG_FILE = tmp / ".pedalcal.json"
    PR.PROFILE_FILE = tmp / ".pedalcal-profiles.json"
    if answered:
        # Record that the language question has been answered. Without this
        # the first-run prompt opens over the main flow and holds a grab, so
        # every screenshot is of the dialog and every check runs behind it.
        settings = S.load()
        settings.language_chosen = True
        S.save(settings)


def watch(root, app, label: str, limit_ms: int = 30_000):
    """Stop a secondary flow that has got stuck, so it reports rather than hangs."""

    def expire():
        FAILURES.append(f"{label} timed out - the window never closed")
        try:
            app.quit_app()
        except Exception:
            root.destroy()

    root.after(limit_ms, expire)


def close_later(root, app, delay_ms: int) -> None:
    """Schedule the window to close, and close it even if the close path
    itself throws - otherwise a failure in teardown hangs the run."""

    def go():
        try:
            app._on_close()
        except Exception:
            FAILURES.append("closing the window raised:\n" + traceback.format_exc())
            root.destroy()

    root.after(delay_ms, go)


class Wheel:
    """A stand-in for an X11 wheel-down event over a given widget."""

    num = 5
    delta = -120

    def __init__(self, widget):
        self.widget = widget


def check_main_flow(tmp: Path) -> None:
    isolate_settings(tmp)
    use_fake_board()
    root = tk.Tk()
    root.geometry("640x820")

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

    def header_wording():
        title = app.master.title()
        check("Lord3D" in title and "Calibrator" in title,
              f"window title is {title!r}")

    def min_max_buttons():
        """MIN/MAX capture the live position; the bar reads output, so
        setting rest with the pedal where it is must empty it."""
        panel = app.panels[0]
        panel.set_limits(0, P.ADC_MAX)
        panel._set_min()
        check(panel.lo == panel.raw, "MIN did not capture the live position")
        check(panel.meter.output < 0.02,
              f"bar should drop to empty after MIN, got {panel.meter.output:.3f}")
        reading = panel.pct_label.cget("text")
        check("%" in reading, "percentage label missing")
        check("." not in reading, f"percentage still has a decimal: {reading!r}")
        # setting full below rest must be refused rather than inverting the axis
        before = panel.hi
        panel.raw = max(0, panel.lo - 5)
        panel._set_max()
        check(panel.hi == before, "allowed full to be set below rest")

    def units_and_smoothing():
        """The readout swaps between percentage and raw, it doesn't show both."""
        panel = app.panels[0]
        percent = panel.pct_label.cget("text")
        check("%" in percent, f"expected a percentage, got {percent!r}")
        panel.units_toggle.toggle()
        raw = panel.pct_label.cget("text")
        check("%" not in raw and raw.strip().isdigit(),
              f"expected a raw number, got {raw!r}")
        check(app.cfg.show_raw[0] is True, "units choice not stored")
        check(panel.units_toggle.value is True, "units toggle did not latch on")
        check("RAW" in panel.units_toggle.text,
              f"units toggle has no caption: {panel.units_toggle.text!r}")
        panel.units_toggle.toggle()
        check("%" in panel.pct_label.cget("text"), "did not switch back")
        check(panel.units_toggle.value is False, "units toggle did not latch off")

        panel.smooth_toggle.toggle()
        check(app.cfg.smoothing[0] is False, "smoothing toggle not stored")
        check(panel.smooth_toggle.text == "SMOOTHING",
              f"toggle label is {panel.smooth_toggle.text!r}")
        panel.smooth_toggle.toggle()

    def help_dot():
        """The question mark next to Smoothing explains what it costs."""
        dot = app.panels[0].help_dot
        check("jitter" in dot.text and "accurate" in dot.text,
              f"help text is {dot.text!r}")
        dot._enter()
        root.update_idletasks()
        check(dot._tip._window is not None, "hovering the help dot showed nothing")
        dot._leave()
        check(dot._tip._window is None, "help tip did not go away")

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

    def calibration_scrolls():
        """The reported bug: the clutch's Advanced section opened below the
        bottom of the window with no way to reach it."""
        for panel in app.panels:
            if not panel.advanced.open:
                panel.advanced.toggle()
        root.update_idletasks()
        area = app.calibration_page
        check(area._content_h() > area.winfo_height(),
              "three open Advanced panels still fit - test proves nothing")
        before = area.yview()[0]
        area._wheel(Wheel(app.panels[2].body))
        check(area.yview()[0] > before,
              "wheel over the calibration page did not scroll it")
        for _ in range(60):
            area._wheel(Wheel(app.panels[2].body))
        bottom = area.yview()[1]
        check(bottom > 0.98,
              f"cannot scroll to the bottom of the calibration page ({bottom:.2f})")
        shoot(root, "v5_calibration_scrolled")
        area.yview_moveto(0)
        for panel in app.panels:
            panel.advanced.toggle()

    def profiles_save():
        """Profiles are per pedal and live on the PC."""
        panel = app.panels[1]
        panel.set_limits(120, 880)
        panel.set_deadzone(6)
        panel.set_linearity(30)
        gui.W.ask_text = lambda *a, **k: "Rain"
        app._profile_save_as(1)
        check(app.store.names(1) == ["Rain"],
              f"profile not saved: {app.store.names(1)}")
        check(app.store.names(0) == [],
              "saving a brake profile leaked onto the throttle")
        check(app.store.selected(1) == "Rain", "saved profile not selected")
        check(panel.profile_select.values == ["None", "Rain"],
              f"dropdown not refreshed: {panel.profile_select.values}")

    def profiles_reload():
        """Change everything, then pick the profile back out of the list."""
        panel = app.panels[1]
        panel.set_limits(0, P.ADC_MAX)
        panel.set_deadzone(0)
        panel.set_linearity(0)
        app._profile_chosen(1, 1)          # row 1 is "Rain"
        check(panel.limits() == (120, 880), f"limits not restored: {panel.limits()}")
        check(panel.deadzone == 6, "deadzone not restored")
        check(panel.linearity == 30, "curve not restored")
        check(app.cfg.deadzones[1] == 6, "restored profile not written to settings")

    def profiles_reset_and_delete():
        panel = app.panels[1]
        app._profile_reset(1)
        check(panel.limits() == (0, P.ADC_MAX), "reset did not restore full travel")
        check(panel.deadzone == 0 and panel.linearity == 0,
              "reset left curve or deadzone behind")
        check(app.store.names(1) == ["Rain"],
              "resetting a pedal deleted its saved profiles")
        app._profile_chosen(1, 1)
        app._profile_delete(1)
        check(app.store.names(1) == [], "profile not deleted")
        check(panel.profile_select.values == ["None"], "dropdown still lists it")

    def profiles_persist():
        reopened = PR.ProfileStore(PR.PROFILE_FILE)
        app.store.put(2, "Dry", PR.PedalProfile(lo=7, hi=900))
        again = PR.ProfileStore(PR.PROFILE_FILE)
        check(again.get(2, "Dry") is not None, "profile did not reach the disk")
        check(reopened.names(2) == [], "stale store saw a future write")
        app.store.delete(2, "Dry")

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
        shoot(root, "v5_calibration")

    def open_settings():
        app.tabs.select(1)
        shoot(root, "v5_settings")

    def disable_clutch():
        app.axis_toggles[2].toggle()
        check(app.cfg.axes == [True, True, False], "clutch toggle not stored")
        app.tabs.select(0)

    def confirm_hidden():
        check(not app.panels[2].winfo_ismapped(),
              "disabled pedal still shown on the calibration tab")
        check(app.panels[1].winfo_ismapped(), "enabled pedal disappeared")
        app.tabs.select(1)
        app.axis_toggles[2].toggle()      # clutch back on

    def refuse_last_pedal():
        app.axis_toggles[0].toggle()
        app.axis_toggles[1].toggle()
        app.axis_toggles[2].toggle()      # would leave nothing visible
        check(any(app.cfg.axes), "app allowed every pedal to be hidden")
        app.axis_toggles[0].toggle()
        app.axis_toggles[1].toggle()

    def scrolling():
        """The reported bug: the wheel did nothing while over a card."""
        area = app.settings_page
        if area._content_h() <= area.winfo_height():
            return          # nothing to scroll at this window size
        before = area.yview()[0]
        area._wheel(Wheel(app.pedals_card.body))   # deep inside the scroll area
        check(area.yview()[0] > before,
              "wheel over a card did not scroll the settings page")
        moved = area.yview()[0]
        area._wheel(Wheel(app.panels[0]))          # a different tab entirely
        check(area.yview()[0] == moved,
              "settings page scrolled from an event outside it")
        area.yview_moveto(0)

    def controller_status():
        check(app.hid is True, f"HID capability not read: {app.hid}")
        check("Active" in app.hid_label.cget("text"),
              f"controller status unclear: {app.hid_label.cget('text')!r}")
        check(app.live_label.cget("fg") == app.p.ok,
              "connected indicator is not green")

    def custom_colour():
        app.custom_var.set("255, 90, 0")
        app._apply_custom_colour()
        check(app.p.accent_seed == "#ff5a00",
              f"RGB input ignored: {app.p.accent_seed}")

    def brightness():
        """The slider replaces the dark/light switch, so it has to reach both
        ends and stay readable everywhere in between."""
        app.bright_slider.set(96)
        app._brightness_dragged(96)
        app._brightness_committed(96)
        check(not app.p.dark, "96% brightness did not give a light window")
        check(T.contrast(app.p.text, app.p.surface) >= 4.5,
              "text unreadable on a bright background")
        check(app.status_label.cget("bg") == app.p.bg,
              "a plain label kept the old background")
        shoot(root, "v5_bright")
        app.bright_slider.set(4)
        app._brightness_dragged(4)
        app._brightness_committed(4)
        check(app.p.dark, "4% brightness did not give a dark window")
        check(S.load().bg_brightness == 4, "brightness not saved")

    def custom_background():
        app.bg_var.set("#2b1d3a")
        app._apply_custom_bg()
        check(app.p.bg == "#2b1d3a", f"typed background ignored: {app.p.bg}")
        check(abs(app.bright_slider.value
                  - T.bg_brightness_of("#2b1d3a")) <= 1,
              "slider did not follow the typed colour")
        app._clear_custom_bg()
        check(app.p.bg != "#2b1d3a", "clearing the custom colour did nothing")

    def switch_to_side_by_side():
        app.layout_tabs.select(1)

    def confirm_side_by_side():
        check(app.cfg.layout == "side", "layout choice not stored")
        check(isinstance(app.panels[0].meter, W.VMeter),
              "side-by-side layout did not stand the bars up")
        info = [p.grid_info() for p in app.panels]
        check(all(i.get("row") == 0 for i in info),
              f"cards are not on one row: {info}")
        check(sorted(i["column"] for i in info) == [0, 1, 2],
              f"cards share a column: {info}")
        app.tabs.select(0)

    def side_by_side_screenshot():
        # Everything a stacked card has, a narrow one has too - the buttons
        # wrap instead of shrinking, and Advanced still opens.
        panel = app.panels[0]
        check(panel.profile_select.winfo_ismapped(),
              "no profile row on a side-by-side card")
        panel.advanced.toggle()
        root.update_idletasks()
        check(panel.advanced_panel.winfo_ismapped(),
              "Advanced did not open on a side-by-side card")
        check(panel.graph.winfo_width() > 60,
              f"curve graph squashed to {panel.graph.winfo_width()}px")
        check(panel.curve_slider.winfo_ismapped()
              and panel.dz_slider.winfo_ismapped(),
              "linearity or deadzone slider missing when the cards are narrow")
        shoot(root, "v5_side_by_side")
        panel.advanced.toggle()
        check(app.panels[0].winfo_width() > 40, "side-by-side card has no width")
        widths = [p.winfo_width() for p in app.panels]
        check(max(widths) - min(widths) <= 2,
              f"cards are not sharing the window evenly: {widths}")
        app.tabs.select(1)
        app.layout_tabs.select(0)

    def switch_language():
        app._language_chosen(i18n.LANGUAGE_CODES.index("de"))

    def confirm_language():
        check(app.cfg.language == "de", "language not stored")
        check(app.tabs.labels[0] == "K A L I B R I E R U N G".replace(" ", ""),
              f"tab not translated: {app.tabs.labels[0]!r}")
        check(app.panels[0].title.cget("text") == W.spaced("GAS"),
              f"pedal name not translated: {app.panels[0].title.cget('text')!r}")
        check("Glättung" in app.panels[0].help_dot.text,
              "help text not translated")
        shoot(root, "v5_german")
        app._language_chosen(i18n.LANGUAGE_CODES.index("en"))

    def confirm_language_back():
        check(app.tabs.labels[0] == "CALIBRATION", "did not switch back")
        check(app.device is not None, "rebuilding the window dropped the device")
        check(app.identified, "rebuilding the window lost the connection state")
        check(any(p.raw for p in app.panels),
              "live data stopped after rebuilding the window")

    def small_window():
        """Everything has to survive being squeezed."""
        root.geometry("520x500")

    def confirm_small_window():
        root.update_idletasks()
        check(app.master.winfo_width() >= 400,
              f"window collapsed to {app.master.winfo_width()}px")
        check(app.calibration_page.winfo_height() > 40,
              "calibration page collapsed in a small window")
        check(app.status_label.winfo_ismapped(),
              "status line pushed off a small window")
        shoot(root, "v5_small")
        root.geometry("640x820")

    def console_open():
        app.console_toggle.toggle()
        check(app.cfg.console_open, "console state not stored")

    def console_visible():
        # winfo_ismapped only updates once the event loop has processed the
        # geometry change, so this has to be a separate step.
        check(app.console_card.winfo_ismapped(), "console did not open")

    def do_reset():
        app.store.put(0, "Doomed", PR.PedalProfile())
        gui.messagebox.askyesno = lambda *a, **k: True
        app.reset_everything()
        check(app.cfg.axes == [True, True, True], "reset left a pedal disabled")
        check(app.p.accent_seed == S.DEFAULT_ACCENT, "reset kept the accent")
        check(app.p.dark, "reset kept a bright background")
        check(app.cfg.bg_brightness == T.DEFAULT_BRIGHTNESS,
              "reset kept the brightness")
        check(app.panels[0].limits_pct() == (0, 100), "reset kept calibration")
        check(all(p.linearity == 0 for p in app.panels), "reset kept a curve")
        check(all(p.deadzone == 0 for p in app.panels), "reset kept a deadzone")
        check(all(not p.show_raw for p in app.panels), "reset kept raw units")
        check(not app.cfg.console_open, "reset left the console open")
        check(app.store.names(0) == [], "reset kept saved profiles")
        check(app.cfg.language_chosen, "reset would ask for a language again")
        shoot(root, "v5_after_reset")

    def finish():
        app.save_calibration()
        app._on_close()

    # Each step is scheduled only once the one before it has returned, with a
    # gap for Tk to settle. Absolute delays looked simpler and were a race:
    # rebuilding the window takes a few hundred milliseconds under Xvfb, so a
    # check timed 200 ms after the click that triggered it sometimes read the
    # old widgets and sometimes the new ones.
    steps = [
        (1500, streaming),
        (1700, stop_learning),
        (60, header_wording),
        (60, min_max_buttons),
        (60, units_and_smoothing),
        (60, help_dot),
        (60, deadzone),
        (60, frame_rate),
        (60, curves),
        (150, calibration_scrolls),
        (150, profiles_save),
        (60, profiles_reload),
        (60, profiles_reset_and_delete),
        (60, profiles_persist),
        (150, open_settings),
        (60, tray_toggles),
        (60, disable_clutch),
        (150, confirm_hidden),
        (150, refuse_last_pedal),
        (60, scrolling),
        (60, controller_status),
        (60, custom_colour),
        (60, brightness),
        (60, custom_background),
        (60, switch_to_side_by_side),
        (500, confirm_side_by_side),
        (300, side_by_side_screenshot),
        (500, switch_language),
        (500, confirm_language),
        (500, confirm_language_back),
        (60, small_window),
        (300, confirm_small_window),
        (150, console_open),
        (150, console_visible),
        (150, do_reset),
        (150, finish),
    ]

    def next_step(remaining):
        if not remaining:
            return
        (delay, step), rest = remaining[0], remaining[1:]

        def go():
            # A step that raises is a failure, not a reason to stop. Letting
            # the exception escape leaves the chain unscheduled, so `finish`
            # never runs, the window never closes and mainloop never returns -
            # the run hangs until the CI job is killed instead of reporting
            # what went wrong. It cost a six-hour build minute budget once.
            try:
                step()
            except Exception:
                FAILURES.append(f"{step.__name__} raised:\n"
                                + traceback.format_exc())
            root.after(1, lambda: next_step(rest))

        root.after(delay, go)

    def watchdog():
        """Last resort. Nothing here should take this long; if it has, the
        run is stuck and a stuck test that reports nothing is the worst kind."""
        FAILURES.append("smoke test timed out - the window never closed")
        try:
            app.quit_app()
        except Exception:
            root.destroy()

    root.after(WATCHDOG_MS, watchdog)
    next_step(steps)
    root.mainloop()


def check_first_run_language_prompt(tmp: Path) -> None:
    """Asked once, then never again - even if it is dismissed."""
    isolate_settings(tmp, answered=False)
    S.CONFIG_FILE.unlink(missing_ok=True)
    use_fake_board()
    asked = []

    def fake_choice(master, palette, title, prompt, options, note=""):
        asked.append(prompt)
        return options.index("Nederlands")

    real_choice = gui.W.ask_choice
    gui.W.ask_choice = fake_choice
    try:
        root = tk.Tk()
        app = gui.CalibratorApp(root)
        root.after(1500, lambda: check(
            app.cfg.language == "nl", f"prompt answer ignored: {app.cfg.language}"))
        watch(root, app, "first-run language prompt")
        close_later(root, app, 1600)
        root.mainloop()
        check(len(asked) == 1, f"language asked {len(asked)} times on first run")
        check(S.load().language_chosen, "answer not recorded")

        root = tk.Tk()
        app = gui.CalibratorApp(root)
        watch(root, app, "second launch after the language prompt")
        close_later(root, app, 1200)
        root.mainloop()
        check(len(asked) == 1, "language asked again on the second launch")
        check(app.cfg.language == "nl", "chosen language not remembered")
    finally:
        gui.W.ask_choice = real_choice
        i18n.set_language("en")


def check_dismissing_the_prompt_still_counts(tmp: Path) -> None:
    isolate_settings(tmp, answered=False)
    S.CONFIG_FILE.unlink(missing_ok=True)
    use_fake_board()
    asked = []

    real_choice = gui.W.ask_choice
    gui.W.ask_choice = lambda *a, **k: asked.append(1)   # returns None
    try:
        root = tk.Tk()
        app = gui.CalibratorApp(root)
        # Close through the app, not root.destroy(): destroying the window out
        # from under a pending timer is exactly the "invalid command name"
        # crash the cancellable scheduler exists to prevent.
        watch(root, app, "dismissed language prompt")
        close_later(root, app, 1500)
        root.mainloop()
        check(S.load().language_chosen,
              "dismissing the language prompt means being asked forever")
    finally:
        gui.W.ask_choice = real_choice
        i18n.set_language("en")


def check_port_is_remembered(tmp: Path) -> None:
    """Second launch should come back on the same port without being told."""
    isolate_settings(tmp)
    use_fake_board()

    root = tk.Tk()
    app = gui.CalibratorApp(root, initial_port=FAKE_PORT)
    watch(root, app, "first launch on the remembered port")
    close_later(root, app, 1800)
    root.mainloop()
    check(S.load().last_port == FAKE_PORT, "port was not saved on connect")

    root = tk.Tk()
    app = gui.CalibratorApp(root)          # no port given this time
    root.after(2000, lambda: check(
        app.identified, "did not reconnect to the remembered port"))
    root.after(2100, lambda: check(
        app._selected_port() == FAKE_PORT, "remembered port not preselected"))
    watch(root, app, "reconnect to the remembered port")
    close_later(root, app, 2400)
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
    watch(root, app, "bad port")
    close_later(root, app, 3000)
    root.mainloop()

    check(bool(shown), "bad port produced no error dialog")
    if shown:
        check("port" in shown[0].lower(), f"unhelpful error: {shown[0]!r}")
    check(app.device is None, "app thinks it is connected after a failed open")


def main() -> int:
    flows = (check_main_flow, check_first_run_language_prompt,
             check_dismissing_the_prompt_still_counts,
             check_port_is_remembered, check_bad_port)
    if IMPORT_TOOL is None:
        print("note: ImageMagick's `import` is not installed, "
              "so no screenshots will be saved")
    with tempfile.TemporaryDirectory() as tmp:
        for flow in flows:
            try:
                flow(Path(tmp))
            except Exception:
                FAILURES.append(f"{flow.__name__} raised:\n"
                                + traceback.format_exc())
    for problem in FAILURES:
        print("FAIL:", problem)
    print("smoke test:", "FAILED" if FAILURES else "OK")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
