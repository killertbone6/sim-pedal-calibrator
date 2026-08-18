"""The calibration window - a flat HUD drawn on canvases, not stock widgets."""

from __future__ import annotations

import datetime
import queue
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox

from . import autostart
from . import i18n
from . import profiles as PR
from . import protocol as P
from . import settings as S
from . import theme as T
from . import tray as tray_module
from . import widgets as W
from .device import PedalDevice, PortInfo, explain_port_error, list_serial_ports
from .i18n import t
from .icon_data import ICON_PNG_B64

#: The pedals this app is built for.
BRAND = "Lord3D"

#: Errors and connection attempts are appended here, so a crash in the packaged
#: .exe (which has no console to print to) still leaves something to read.
LOG_FILE = Path.home() / "pedalcal.log"

#: Refresh rates offered in Settings. The board streams at the same rate, so
#: the number is real rather than the UI redrawing stale data faster.
FPS_CHOICES = (30, 60, 120, 240)
PAD = 14       # outer window padding

#: Smallest the window may get, per layout. Side by side needs the width for
#: three cards; stacked needs almost none, so it gets almost none - the page
#: scrolls rather than clipping.
MIN_SIZE = {"stacked": (460, 460), "side": (680, 560)}

#: Width of the captions down the left of the Device card, in characters.
#: Letter-spacing doubles a word's length, so "HANDBRAKE" needs seventeen -
#: at eleven it came out as "HANDBRA".
CAPTION_CHARS = 18


def write_log(text: str) -> None:
    try:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}  {text}\n")
    except Exception:
        pass  # logging must never be the thing that breaks the app


class AxisPanel(W.Card):
    """One pedal: live output, calibration points, profile, curve and deadzone.

    The bar shows calibrated output rather than raw sensor position, so
    pressing MIN with your foot off empties it and pressing MAX at the floor
    fills it. Raw counts still travel over the wire - the firmware works in
    them - but they only reach the screen if you ask for them.

    The same class draws both layouts. Side by side it stands the bar on end
    and stacks the controls in a narrow column; the readings, hooks and
    behaviour are identical, which is why there is one class and not two.
    """

    CURVE_SAMPLES = 96

    def __init__(self, master, index: int, name: str, palette: T.Palette,
                 hooks: dict, vertical: bool = False) -> None:
        super().__init__(master, palette, padding=14 if vertical else 16)
        self.index = index
        self.name = name
        self.hooks = hooks
        self.vertical = vertical
        self.raw = 0
        self.lo = 0
        self.hi = P.ADC_MAX
        self.linearity = 0
        self.deadzone = 0
        self.show_raw = False
        self.themed: list[W.Themed] = []
        self.plain: list[tuple[tk.Widget, dict]] = []

        body = self.body
        body.columnconfigure(0, weight=1)

        self._build_header(body)
        self._build_meter(body)
        self._build_controls(body)
        self._build_profile(body)

        self.advanced = W.Disclosure(body, t("Advanced"), False,
                                     self._toggle_advanced, palette)
        self.advanced.configure(bg=palette.surface)
        self.advanced.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        self.themed.append(self.advanced)
        self._build_advanced(body)

    # -- construction ----------------------------------------------------

    def _build_header(self, body) -> None:
        palette = self.p
        header = self._row(body, 0)
        self.title = tk.Label(header, text=W.spaced(t(self.name).upper()),
                              font=W.ui(9, "bold"), bg=palette.surface,
                              fg=palette.text_dim)
        self.title.pack(side="left")
        self._reg(self.title, bg="surface", fg="text_dim")

        # One readout, not two. The toggle below swaps it between the
        # calibrated percentage a game would see and the raw sensor number.
        self.pct_label = tk.Label(header, text="0%",
                                  font=W.mono(17 if self.vertical else 19,
                                              "bold"),
                                  width=5, anchor="e", bg=palette.surface,
                                  fg=palette.accent, cursor="hand2")
        self.pct_label.pack(side="right")
        self.pct_label.bind("<Button-1>", lambda _e: self._toggle_units())
        self._reg(self.pct_label, bg="surface", fg="accent")

    def _build_meter(self, body) -> None:
        if self.vertical:
            holder = tk.Frame(body, bg=self.p.surface)
            holder.grid(row=1, column=0, sticky="ew", pady=(10, 12))
            self._reg(holder, bg="surface")
            self.meter = W.VMeter(holder, self.p)
            self.meter.pack()
        else:
            self.meter = W.Meter(body, self.p)
            self.meter.grid(row=1, column=0, sticky="ew", pady=(10, 12))
        self.themed.append(self.meter)

    def _build_controls(self, body) -> None:
        palette = self.p
        controls = self._row(body, 2)
        buttons = self._wrap(controls, per_row=2 if self.vertical else 3)
        # Keyed rather than matched on the handler: `self._learn` builds a new
        # bound-method object on every attribute access, so `is` never matches
        # and the Learn button would go unrecorded.
        for key, label, handler, fits in (
                ("min", t("Min"), self._set_min, None),
                ("max", t("Max"), self._set_max, None),
                ("learn", t("Learn"), self._learn, [t("Stop")])):
            button = W.HudButton(next(buttons), label, handler, palette,
                                 height=30, pad=12 if self.vertical else 14,
                                 fits=fits)
            button.configure(bg=palette.surface)
            button.pack(side="left", padx=(0, 6), pady=2)
            self.themed.append(button)
            if key == "learn":
                self.learn_btn = button

        toggles = self._row(body, 3)
        toggles.grid_configure(pady=(8, 0))

        smoothing_row = tk.Frame(toggles, bg=palette.surface)
        smoothing_row.pack(anchor="w")
        self._reg(smoothing_row, bg="surface")
        tracking = "" if self.vertical else " "
        self.smooth_toggle = W.Toggle(smoothing_row, t("Smoothing"), True,
                                      self._smoothing_changed, palette,
                                      spacing=tracking)
        self.smooth_toggle.configure(bg=palette.surface)
        self.smooth_toggle.pack(side="left")
        self.themed.append(self.smooth_toggle)

        self.help_dot = W.HelpDot(
            smoothing_row,
            t("Smoothing reduces jitter but makes pedals less accurate."),
            palette)
        self.help_dot.pack(side="left", padx=(8, 0))
        self.themed.append(self.help_dot)

        # A labelled switch, not a cryptic "%" button: the caption says which
        # reading you get, and the switch says whether you are getting it.
        self.units_toggle = W.Toggle(toggles, t("Raw value"), False,
                                     lambda _v: self._toggle_units(), palette,
                                     spacing=tracking)
        self.units_toggle.configure(bg=palette.surface)
        self.units_toggle.pack(anchor="w", pady=(6, 0))
        self.themed.append(self.units_toggle)

    def _build_profile(self, body) -> None:
        palette = self.p
        panel = self._row(body, 4)
        panel.grid_configure(pady=(12, 0))

        caption = tk.Label(panel, text=W.spaced(t("Profile").upper()),
                           font=W.ui(8, "bold"), bg=palette.surface,
                           fg=palette.text_dim)
        caption.pack(anchor="w")
        self._reg(caption, bg="surface", fg="text_dim")

        self.profile_select = W.HudSelect(
            panel, palette, width=140, height=30,
            on_change=lambda i: self._call("profile_choose", self.index, i))
        self.profile_select.configure(bg=palette.surface)
        self.profile_select.pack(fill="x", pady=(4, 6))
        self.themed.append(self.profile_select)

        buttons = self._wrap(panel, per_row=2 if self.vertical else 4)
        self.profile_buttons: dict[str, W.HudButton] = {}
        for key, label, handler in (
                ("save", t("Save"), lambda: self._call("profile_save", self.index)),
                ("save_as", t("Save as"),
                 lambda: self._call("profile_save_as", self.index)),
                ("delete", t("Delete"),
                 lambda: self._call("profile_delete", self.index)),
                ("reset", t("Reset"),
                 lambda: self._call("profile_reset", self.index))):
            button = W.HudButton(next(buttons), label, handler, palette,
                                 height=26, pad=7 if self.vertical else 9)
            button.configure(bg=palette.surface)
            button.pack(side="left", padx=(0, 6), pady=2)
            self.themed.append(button)
            self.profile_buttons[key] = button

    def _build_advanced(self, body) -> None:
        panel = tk.Frame(body, bg=self.p.surface)
        self._reg(panel, bg="surface")
        self.advanced_panel = panel
        self.advanced_row = 6

        sliders = tk.Frame(panel, bg=self.p.surface)
        sliders.pack(fill="x", pady=(10, 0))
        self._reg(sliders, bg="surface")

        width = 132 if self.vertical else 150
        _g, self.curve_slider, self.curve_label = self._slider_group(
            sliders, t("Linearity"), -P.CURVE_MAX, P.CURVE_MAX,
            self._curve_dragged, self._curve_committed, width=width,
            stacked=self.vertical)
        _g, self.dz_slider, self.dz_label = self._slider_group(
            sliders, t("Deadzone"), 0, P.DEADZONE_MAX,
            self._deadzone_dragged, self._deadzone_committed, suffix="%",
            padx=(0, 0) if self.vertical else (18, 0), width=width,
            stacked=self.vertical)

        reset = W.HudButton(panel, t("Linear"), self._reset_curve, self.p,
                            height=26, pad=10)
        reset.configure(bg=self.p.surface)
        reset.pack(anchor="e", pady=(8, 0))
        self.themed.append(reset)

        self.graph = W.CurveGraph(panel, self.p,
                                  height=112 if self.vertical else 132)
        self.graph.pack(fill="x", pady=(6, 0))
        self.themed.append(self.graph)

        hint = tk.Label(
            panel, justify="left", anchor="w", font=W.ui(8),
            wraplength=200 if self.vertical else 420,
            bg=self.p.surface, fg=self.p.text_dim,
            text=t("Left of centre is more sensitive; right is gentler.")
                 + "\n" + t("Deadzone ignores the first part of the travel."))
        hint.pack(anchor="w", pady=(8, 0))
        self._reg(hint, bg="surface", fg="text_dim")
        self._refresh_curve()

    # -- construction helpers --------------------------------------------

    def _reg(self, widget: tk.Widget, **roles: str) -> None:
        self.plain.append((widget, roles))

    def _row(self, body, row: int) -> tk.Frame:
        frame = tk.Frame(body, bg=self.p.surface)
        frame.grid(row=row, column=0, sticky="ew")
        self._reg(frame, bg="surface")
        return frame

    def _wrap(self, parent, per_row: int):
        """Hand out rows of buttons, `per_row` to a row.

        Side by side, a card is about a third of the window wide and four
        buttons in a line simply do not fit; rather than shrinking the text
        until it can't be read, they wrap.
        """
        def rows():
            count = 0
            row = None
            while True:
                if row is None or count % per_row == 0:
                    row = tk.Frame(parent, bg=self.p.surface)
                    row.pack(anchor="w", fill="x")
                    self._reg(row, bg="surface")
                count += 1
                yield row
        return rows()

    def _slider_group(self, parent, label: str, minimum: int, maximum: int,
                      on_drag, on_commit, suffix: str = "", padx=(0, 0),
                      width: int = 150, stacked: bool = False):
        """Caption above, slider and value below - so two fit side by side."""
        group = tk.Frame(parent, bg=self.p.surface)
        if stacked:
            group.pack(anchor="w", fill="x", pady=(0, 6))
        else:
            group.pack(side="left", padx=padx)
        self._reg(group, bg="surface")

        caption = tk.Label(group, text=W.spaced(label.upper()),
                           font=W.ui(8, "bold"), anchor="w",
                           bg=self.p.surface, fg=self.p.text_dim)
        caption.pack(anchor="w")
        self._reg(caption, bg="surface", fg="text_dim")

        row = tk.Frame(group, bg=self.p.surface)
        row.pack(anchor="w", pady=(4, 0))
        self._reg(row, bg="surface")

        slider = W.Slider(row, self.p, minimum, maximum, 0, command=on_drag,
                          width=width)
        slider.on_release = on_commit
        slider.configure(bg=self.p.surface)
        slider.pack(side="left")
        self.themed.append(slider)

        value = tk.Label(row, text="0" + suffix, font=W.mono(11), width=5,
                         anchor="e", bg=self.p.surface, fg=self.p.text)
        value.pack(side="left", padx=(6, 0))
        self._reg(value, bg="surface", fg="text")
        return group, slider, value

    # -- advanced section -------------------------------------------------

    def _toggle_advanced(self, open_: bool) -> None:
        if open_:
            self.advanced_panel.grid(row=self.advanced_row, column=0,
                                     sticky="ew")
        else:
            self.advanced_panel.grid_forget()
        self.fit()
        self._call("resized")

    def _curve_dragged(self, value: int) -> None:
        """Live while dragging: redraw locally, don't flood the serial link."""
        self.linearity = int(value)
        self._refresh_curve()
        self._call("curve_preview", self.index, self.linearity)

    def _curve_committed(self, value: int) -> None:
        self._call("curve_commit", self.index, int(value))

    def _reset_curve(self) -> None:
        self.set_linearity(0)
        self._curve_committed(0)

    def _deadzone_dragged(self, value: int) -> None:
        self.deadzone = int(value)
        self.dz_label.config(text=f"{self.deadzone}%")
        self._refresh_curve()

    def _deadzone_committed(self, value: int) -> None:
        self._call("deadzone_commit", self.index, int(value))

    def _toggle_units(self) -> None:
        self.set_show_raw(not self.show_raw)
        self._call("show_raw", self.index, self.show_raw)

    def _smoothing_changed(self, value: bool) -> None:
        self._call("smoothing", self.index, value)

    def _call(self, hook: str, *args) -> None:
        handler = self.hooks.get(hook)
        if handler is not None:
            handler(*args)

    def _refresh_readout(self) -> None:
        if self.show_raw:
            self.pct_label.config(text=f"{self.raw:04d}")
        else:
            output = P.pedal_output(self.raw, self.lo, self.hi, self.linearity,
                                    self.deadzone)
            # No decimal. A tenth of a percent is well inside the noise of any
            # potentiometer, so the digit only ever flickered.
            self.pct_label.config(text=f"{round(output * 100)}%")

    def _refresh_curve(self) -> None:
        self.curve_label.config(
            text=f"{self.linearity:+d}" if self.linearity else "0")
        self.dz_label.config(text=f"{self.deadzone}%")
        steps = self.CURVE_SAMPLES
        # The smooth function, not the sampled output: plotting the discrete
        # values put a visible kink at every step.
        threshold = self.deadzone / 100
        points = []
        for i in range(steps + 1):
            x = i / steps
            if x <= threshold:
                points.append((x, 0.0))
                continue
            stretched = (x - threshold) / (1 - threshold) if threshold < 1 else 0
            points.append((x, P.curve_ideal(stretched, self.linearity)))
        self.graph.set_curve(points)

    # -- setters used by the app -----------------------------------------

    def set_linearity(self, value: int) -> None:
        self.linearity = max(-P.CURVE_MAX, min(P.CURVE_MAX, int(value)))
        self.curve_slider.set(self.linearity)
        self._refresh_curve()

    def set_deadzone(self, value: int) -> None:
        self.deadzone = max(0, min(P.DEADZONE_MAX, int(value)))
        self.dz_slider.set(self.deadzone)
        self._refresh_curve()

    def set_smoothing(self, value: bool) -> None:
        self.smooth_toggle.set(bool(value))

    def smoothing(self) -> bool:
        return bool(self.smooth_toggle.value)

    def set_show_raw(self, value: bool) -> None:
        self.show_raw = bool(value)
        self.units_toggle.set(self.show_raw)
        self._refresh_readout()

    def set_profiles(self, names: list[str], chosen: str) -> None:
        values = [t("None")] + names
        index = names.index(chosen) + 1 if chosen in names else 0
        self.profile_select.set_values(values, index)
        self.profile_buttons["delete"].set_enabled(index > 0)

    def profile_name_at(self, index: int) -> str:
        """Dropdown index to profile name; index 0 is the 'none' row."""
        values = self.profile_select.values
        return values[index] if 1 <= index < len(values) else ""

    # -- calibration ------------------------------------------------------

    def limits(self) -> tuple[int, int]:
        return self.lo, self.hi

    def limits_pct(self) -> tuple[int, int]:
        return P.raw_to_pct(self.lo), P.raw_to_pct(self.hi)

    def set_limits(self, lo: int, hi: int) -> None:
        self.lo = max(0, min(P.ADC_MAX, int(lo)))
        self.hi = max(0, min(P.ADC_MAX, int(hi)))
        self.update_raw(self.raw)

    def _set_min(self) -> None:
        if self.raw >= self.hi:
            self._call("warn", f"{t(self.name)}: "
                               + t("Rest has to be below full - set Max at the "
                                   "floor first"))
            return
        self.lo = self.raw
        self.update_raw(self.raw)
        self._call("limits", self.index)

    def _set_max(self) -> None:
        if self.raw <= self.lo:
            self._call("warn", f"{t(self.name)}: "
                               + t("Full has to be above rest - set Min with "
                                   "your foot off first"))
            return
        self.hi = self.raw
        self.update_raw(self.raw)
        self._call("limits", self.index)

    def _learn(self) -> None:
        self._call("learn", self.index)

    def set_learning(self, learning: bool) -> None:
        self.learn_btn.set_text(t("Stop") if learning else t("Learn"))
        self.learn_btn.variant = "primary" if learning else "ghost"
        self.learn_btn.redraw()

    # -- live values ------------------------------------------------------

    def update_raw(self, raw: int) -> None:
        self.raw = raw
        output = P.pedal_output(raw, self.lo, self.hi, self.linearity,
                                self.deadzone)
        self.meter.set_output(output)
        self._refresh_readout()
        if self.advanced.open:
            self.graph.set_position(P.scale(raw, self.lo, self.hi))

    def redraw_meter(self) -> None:
        self.update_raw(self.raw)

    # -- theming ---------------------------------------------------------

    def apply_theme(self, palette: T.Palette) -> None:
        super().apply_theme(palette)
        for widget, roles in self.plain:
            widget.configure(**{opt: getattr(palette, attr)
                                for opt, attr in roles.items()})
        for child in self.themed:
            child.configure(bg=palette.surface)
            child.apply_theme(palette)


class CalibratorApp(tk.Frame):
    def __init__(self, master: tk.Tk, initial_port: str | None = None) -> None:
        self.cfg = S.load()
        i18n.set_language(self.cfg.language)
        self.store = PR.ProfileStore()
        self.p = self._palette()
        super().__init__(master, bg=self.p.bg, padx=PAD, pady=PAD)
        W.init_fonts()
        self.master.configure(bg=self.p.bg)
        self.pack(fill="both", expand=True)

        self.device: PedalDevice | None = None
        self.ports: list[PortInfo] = []
        self.learning: set[int] = set()
        self.identified = False
        self.hid = None
        self._connecting = False
        self._handshakes = 0
        self._alive = True
        self._pending: set[str] = set()
        self._observed: list[list[int]] = [[P.ADC_MAX, 0] for _ in P.AXIS_NAMES]
        self._tray: tray_module.Tray | None = None
        # pystray's callbacks arrive on its own thread; Tk must only ever be
        # touched from the main loop, so they queue up and _tick drains them.
        self._tray_requests: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self.set_on_top(self.cfg.on_top)
        if self.cfg.tray and self._start_tray() and self.cfg.start_minimised:
            self.master.withdraw()
        self.refresh_ports(select=initial_port or self.cfg.last_port)
        remembered = (initial_port is None and self.cfg.last_port
                      and self._selected_port() == self.cfg.last_port)
        if initial_port is not None:
            self._schedule(200, self.toggle_connection)
        elif remembered:
            self._schedule(200,
                           lambda: self._begin_connect(self.cfg.last_port,
                                                       quiet=True))
        self._schedule(self._poll_ms(), self._tick)
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)
        if not self.cfg.language_chosen:
            # After the window exists, so the prompt has something to sit on.
            self._schedule(300, self._ask_language_once)

    # -- building and rebuilding -----------------------------------------

    def _build_ui(self) -> None:
        """Construct the whole widget tree. Safe to call again.

        Changing the language or the pedal layout changes text and geometry
        everywhere at once, and a live retranslate would mean every widget
        remembering which string it was built from. Throwing the tree away and
        building it again is less code and cannot drift out of step; the
        device connection, the profile store and the settings all live outside
        the tree, so nothing is lost by doing it.
        """
        self.themed: list[W.Themed] = []
        self.plain: list[tuple[tk.Widget, dict]] = []
        self.master.title(f"{BRAND} {t('Pedal Calibrator')}")
        self._apply_min_size()

        self._build_header()
        self._build_tabs()
        # The console is packed against the bottom edge *before* the page area
        # claims the rest. Pack it afterwards and an expanded page leaves it
        # with zero height, so Tk never maps it and the panel simply
        # doesn't appear.
        self._build_console()
        self.pages.pack(fill="both", expand=True)
        self._build_calibration_page()
        self._build_settings_page()
        self._show_page(self.tabs.active)
        self._place_panels()
        self._refresh_all_profiles()
        self._set_status(t("Not connected"))
        self._set_live(self.identified)
        self._set_hid_label()
        if self.device is not None:
            self._set_connect_button(t("Disconnect"), "ghost")

    def _rebuild_ui(self, keep_tab: int = 0) -> None:
        self._cancel_pending()
        for child in list(self.winfo_children()):
            child.destroy()
        self._build_ui()
        self.tabs.active = keep_tab
        self.tabs.redraw()
        self._show_page(keep_tab)
        self.refresh_ports(select=self.cfg.last_port)
        self._schedule(self._poll_ms(), self._tick)

    def _palette(self) -> T.Palette:
        return T.palette_for(self.cfg.bg_brightness, self.cfg.accent,
                             self.cfg.bg_custom)

    def _apply_min_size(self) -> None:
        """Hold the window to a size the current layout can actually use.

        Growing the window is skipped entirely until it has been mapped. A
        size asked for with `geometry()` is not applied until Tk next goes
        idle, so during startup both `geometry()` and `winfo_width()` still
        report 1x1 - and 1 is smaller than any minimum, so the app would
        resize itself to the minimum and throw away the size it was launched
        with. `minsize` on its own is enough there; the window manager applies
        it when the window appears.
        """
        width, height = MIN_SIZE.get(self.cfg.layout, MIN_SIZE["stacked"])
        try:
            self.master.minsize(width, height)
            have_w = self.master.winfo_width()
            have_h = self.master.winfo_height()
            if have_w <= 1 or have_h <= 1:
                return
            if have_w < width or have_h < height:
                self.master.geometry(
                    f"{max(have_w, width)}x{max(have_h, height)}")
        except (tk.TclError, ValueError):
            pass

    # -- small helpers ---------------------------------------------------

    def _reg(self, widget: tk.Widget, **roles: str) -> None:
        self.plain.append((widget, roles))

    def _card(self, parent, title: str | None = None, padding: int = 14):
        card = W.Card(parent, self.p, padding=padding)
        card.pack(fill="x", pady=(0, 10))
        self.themed.append(card)
        if title:
            label = tk.Label(card.body, text=W.spaced(title.upper()),
                             font=W.ui(8, "bold"), bg=self.p.surface,
                             fg=self.p.text_dim)
            label.pack(anchor="w", pady=(0, 10))
            self._reg(label, bg="surface", fg="text_dim")
        return card

    def _hint(self, parent, text: str, pady=(10, 0)) -> tk.Label:
        label = tk.Label(parent, text=text, justify="left", anchor="w",
                         font=W.ui(8), wraplength=460, bg=self.p.surface,
                         fg=self.p.text_dim)
        label.pack(anchor="w", fill="x", pady=pady)
        self._reg(label, bg="surface", fg="text_dim")
        return label

    def _dialog(self, func, *args, **kwargs):
        """Run a modal dialog with always-on-top suspended.

        A -topmost window sits above its own message boxes on Windows, so the
        app would look frozen behind an invisible prompt.
        """
        was_on_top = bool(self.master.attributes("-topmost"))
        if was_on_top:
            self.master.attributes("-topmost", False)
        try:
            return func(*args, **kwargs)
        finally:
            if was_on_top and self._alive:
                self.master.attributes("-topmost", True)

    def _poll_ms(self) -> int:
        return max(4, round(1000 / max(15, self.cfg.fps)))

    # -- timers ----------------------------------------------------------

    def _schedule(self, delay_ms: int, callback) -> None:
        """after(), but cancellable - see _cancel_pending."""
        if not self._alive:
            return
        holder: dict[str, str] = {}

        def fire() -> None:
            self._pending.discard(holder.get("token", ""))
            if self._alive:
                callback()

        holder["token"] = self.after(delay_ms, fire)
        self._pending.add(holder["token"])

    def _cancel_pending(self) -> None:
        # Destroying the window deletes the underlying Tcl command, so a timer
        # still in flight raises "invalid command name" from inside Tk, before
        # any Python guard could run. It has to be cancelled, not guarded.
        for token in self._pending:
            try:
                self.after_cancel(token)
            except Exception:
                pass
        self._pending.clear()

    # -- header and tabs -------------------------------------------------

    def _build_header(self) -> None:
        row = tk.Frame(self, bg=self.p.bg)
        row.pack(fill="x", pady=(0, 12))
        self._reg(row, bg="bg")

        mark = tk.Label(row, text="◆", font=W.ui(11), bg=self.p.bg,
                        fg=self.p.accent)
        mark.pack(side="left", padx=(0, 8))
        self._reg(mark, bg="bg", fg="accent")

        title = tk.Label(
            row, text=W.spaced(f"{BRAND} {t('Pedal Calibrator')}".upper()),
            font=W.ui(10, "bold"), bg=self.p.bg, fg=self.p.text)
        title.pack(side="left")
        self._reg(title, bg="bg", fg="text")

        self.live_dot = tk.Canvas(row, width=10, height=10, bg=self.p.bg,
                                  highlightthickness=0, bd=0)
        self.live_dot.pack(side="right")
        self._reg(self.live_dot, bg="bg")

        self.live_label = tk.Label(row, text=W.spaced(t("Offline").upper()),
                                   font=W.ui(8, "bold"), bg=self.p.bg,
                                   fg=self.p.offline)
        self.live_label.pack(side="right", padx=(0, 8))
        self._reg(self.live_label, bg="bg")
        self._paint_dot()

    def _status_colour(self) -> str:
        """Green connected, red not. Deliberately outside the accent palette -
        a connection light is one of the few places where the colour means
        something specific and shouldn't change with the theme."""
        return self.p.ok if self.identified else self.p.offline

    def _paint_dot(self) -> None:
        self.live_dot.delete("all")
        self.live_dot.configure(bg=self.p.bg)
        self.live_dot.create_oval(1, 1, 9, 9, fill=self._status_colour(),
                                  width=0)

    def _build_tabs(self) -> None:
        row = tk.Frame(self, bg=self.p.bg)
        row.pack(fill="x", pady=(0, 12))
        self._reg(row, bg="bg")
        self.tabs = W.Tabs(row, [t("Calibration"), t("Settings")], self.p,
                           on_change=self._show_page)
        self.tabs.pack(side="left")
        self.themed.append(self.tabs)

        self.pages = tk.Frame(self, bg=self.p.bg)   # packed once the console is
        self._reg(self.pages, bg="bg")

    def _show_page(self, index: int) -> None:
        for i, page in enumerate(self.page_frames):
            if i == index:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()

    # -- calibration page ------------------------------------------------

    def _build_calibration_page(self) -> None:
        # The clutch card's Advanced section used to open below the bottom of
        # the window with no way to reach it. Everything on this page now
        # lives in the same scrolling area the settings page uses.
        scroller = W.ScrollArea(self.pages, self.p)
        self.themed.append(scroller)
        self.calibration_page = scroller
        page = scroller.body
        self._reg(page, bg="bg")

        hooks = {
            "limits": self._limits_changed,
            "learn": self.toggle_learn,
            "curve_preview": self._curve_preview,
            "curve_commit": self._curve_commit,
            "deadzone_commit": self._deadzone_commit,
            "smoothing": self._smoothing_commit,
            "show_raw": self._show_raw_changed,
            "profile_choose": self._profile_chosen,
            "profile_save": self._profile_save,
            "profile_save_as": self._profile_save_as,
            "profile_delete": self._profile_delete,
            "profile_reset": self._profile_reset,
            "resized": lambda: scroller._on_body(),
            "warn": self._set_status,
        }
        vertical = self.cfg.layout == "side"
        self.panel_holder = tk.Frame(page, bg=self.p.bg)
        self.panel_holder.pack(fill="both", expand=True)
        self._reg(self.panel_holder, bg="bg")

        self.panels = [
            AxisPanel(self.panel_holder, i, name, self.p, hooks,
                      vertical=vertical)
            for i, name in enumerate(P.AXIS_NAMES)]
        for panel in self.panels:
            panel.set_linearity(self.cfg.curves[panel.index])
            panel.set_deadzone(self.cfg.deadzones[panel.index])
            panel.set_smoothing(self.cfg.smoothing[panel.index])
            panel.set_show_raw(self.cfg.show_raw[panel.index])
            self.themed.append(panel)

        row = tk.Frame(page, bg=self.p.bg)
        row.pack(fill="x", pady=(2, 0))
        self._reg(row, bg="bg")
        for i, (label, command) in enumerate((
                (t("Apply"), self.apply_calibration),
                (t("Save"), self.save_calibration),
                (t("Reload"), self.reload_calibration))):
            button = W.HudButton(row, label, command, self.p, height=34)
            button.pack(side="left", padx=(0 if i == 0 else 8, 0))
            self.themed.append(button)
        self.action_row = row

    def _place_panels(self) -> None:
        """Lay the pedal cards out, hiding any the user says aren't wired up."""
        holder = self.panel_holder
        for panel in self.panels:
            panel.pack_forget()
            panel.grid_forget()
        visible = [p for p in self.panels if self.cfg.axes[p.index]]

        if self.cfg.layout == "side":
            for column in range(len(self.panels)):
                # uniform= makes the columns share the width equally instead of
                # each taking what its contents happen to ask for, so the three
                # cards stay the same size as the window is resized.
                holder.columnconfigure(column, weight=0, uniform="")
            for column, panel in enumerate(visible):
                holder.columnconfigure(column, weight=1, uniform="pedal")
                # The same padding on every card, rather than a gap only
                # between them: uniform columns are equal in total, so an
                # unpadded first column ends up with a wider card in it.
                panel.grid(row=0, column=column, sticky="nsew", padx=4,
                           pady=(0, 10))
        else:
            for column in range(len(self.panels)):
                holder.columnconfigure(column, weight=0, uniform="")
            for panel in visible:
                panel.pack(fill="x", pady=(0, 10))
        for panel in visible:
            panel.fit()

    # -- settings page ---------------------------------------------------

    def _build_settings_page(self) -> None:
        scroller = W.ScrollArea(self.pages, self.p)
        self.themed.append(scroller)
        page = scroller.body
        self._reg(page, bg="bg")
        self.settings_page = scroller
        self.page_frames = [self.calibration_page, scroller]

        self._build_device_card(page)
        self._build_pedals_card(page)
        self._build_language_card(page)
        self._build_interface_card(page)
        self._build_background_card(page)

        card = self._card(page, t("Reset"))
        reset = W.HudButton(card.body, t("Reset everything"),
                            self.reset_everything, self.p, variant="danger",
                            height=34)
        reset.configure(bg=self.p.surface)
        reset.pack(anchor="w")
        self.themed.append(reset)
        card.fit()

        self._sync_appearance_buttons()

    def _build_device_card(self, page) -> None:
        card = self._card(page, t("Device"))
        row = tk.Frame(card.body, bg=self.p.surface)
        row.pack(fill="x")
        self._reg(row, bg="surface")

        pedals_caption = tk.Label(row, text=W.spaced(t("Pedals").upper()),
                                  font=W.ui(8, "bold"), width=CAPTION_CHARS,
                                  anchor="w", bg=self.p.surface,
                                  fg=self.p.text_dim)
        pedals_caption.pack(side="left", padx=(0, 8))
        self._reg(pedals_caption, bg="surface", fg="text_dim")

        # Pack the fixed-width buttons first: a dropdown packed with expand=True
        # ahead of them would swallow the row and clip their labels.
        self.connect_btn = W.HudButton(row, t("Connect"), self.toggle_connection,
                                       self.p, variant="primary", height=34,
                                       fits=[t("Disconnect"), t("Cancel")])
        self.connect_btn.configure(bg=self.p.surface)
        self.connect_btn.pack(side="right")
        self.themed.append(self.connect_btn)

        refresh = W.HudButton(row, t("Refresh"), lambda: self.refresh_ports(),
                              self.p, height=34)
        refresh.configure(bg=self.p.surface)
        refresh.pack(side="right", padx=(8, 8))
        self.themed.append(refresh)

        self.port_select = W.HudSelect(row, self.p, width=120)
        self.port_select.configure(bg=self.p.surface)
        self.port_select.pack(side="left", fill="x", expand=True)
        self.themed.append(self.port_select)

        self.hid_label = tk.Label(card.body, justify="left", anchor="w",
                                  font=W.ui(8), wraplength=460,
                                  bg=self.p.surface, fg=self.p.text_dim)
        self.hid_label.pack(anchor="w", fill="x", pady=(10, 0))
        self._reg(self.hid_label, bg="surface")

        # Nothing reads this yet - it's here so the layout doesn't have to be
        # rearranged when handbrake support lands, and so a choice made now
        # survives until then. A shifter needs no help from this app: the
        # Arduino sketch can present its buttons on its own.
        self.extra_selects: dict[str, W.HudSelect] = {}
        for key, label in (("handbrake", t("Handbrake")),):
            extra = tk.Frame(card.body, bg=self.p.surface)
            extra.pack(fill="x", pady=(8, 0))
            self._reg(extra, bg="surface")
            caption = tk.Label(extra, text=W.spaced(label.upper()),
                               width=CAPTION_CHARS, anchor="w",
                               font=W.ui(8, "bold"), bg=self.p.surface,
                               fg=self.p.text_dim)
            caption.pack(side="left", padx=(0, 8))
            self._reg(caption, bg="surface", fg="text_dim")
            select = W.HudSelect(
                extra, self.p, width=120,
                on_change=lambda i, k=key: self._set_extra_port(k, i))
            select.configure(bg=self.p.surface)
            select.pack(side="left", fill="x", expand=True)
            self.themed.append(select)
            self.extra_selects[key] = select

        self._hint(card.body, t("Handbrake support is not implemented yet."))
        card.fit()
        self.device_card = card

    def _build_pedals_card(self, page) -> None:
        card = self._card(page, t("Pedals connected"))
        self._hint(card.body,
                   t("Turn off any pedal you haven't wired up.") + " "
                   + t("An unused input copies its neighbour and looks like a "
                       "stuck pedal."),
                   pady=(0, 10))
        self.axis_toggles = []
        for i, name in enumerate(P.AXIS_NAMES):
            toggle = W.Toggle(card.body, t(name), self.cfg.axes[i],
                              lambda value, i=i: self._set_axis_enabled(i, value),
                              self.p)
            toggle.pack(anchor="w", pady=2)
            self.axis_toggles.append(toggle)
            self.themed.append(toggle)
        card.fit()
        self.pedals_card = card

    def _build_language_card(self, page) -> None:
        card = self._card(page, t("Language"))
        self.language_select = W.HudSelect(
            card.body, self.p, width=220,
            on_change=self._language_chosen)
        self.language_select.configure(bg=self.p.surface)
        self.language_select.set_values(
            [name for _code, name in i18n.LANGUAGES],
            i18n.LANGUAGE_CODES.index(self.cfg.language)
            if self.cfg.language in i18n.LANGUAGE_CODES else 0)
        self.language_select.pack(anchor="w", fill="x")
        self.themed.append(self.language_select)
        self._hint(card.body,
                   t("The console keeps its English wording so faults stay "
                     "searchable."))
        card.fit()

    def _build_interface_card(self, page) -> None:
        card = self._card(page, t("Interface"))

        # --- layout -----------------------------------------------------
        layout_row = tk.Frame(card.body, bg=self.p.surface)
        layout_row.pack(fill="x", pady=(0, 14))
        self._reg(layout_row, bg="surface")
        layout_caption = tk.Label(layout_row, text=W.spaced(t("Layout").upper()),
                                  font=W.ui(8, "bold"), bg=self.p.surface,
                                  fg=self.p.text_dim)
        layout_caption.pack(side="left", padx=(0, 10))
        self._reg(layout_caption, bg="surface", fg="text_dim")

        self.layout_tabs = W.Tabs(
            layout_row, [t("Stacked"), t("Side by side")], self.p,
            on_change=self._layout_chosen, height=28)
        self.layout_tabs.configure(bg=self.p.surface)
        self.layout_tabs.active = S.LAYOUTS.index(self.cfg.layout)
        self.layout_tabs.redraw()
        self.layout_tabs.pack(side="left")
        self.themed.append(self.layout_tabs)

        # --- background brightness --------------------------------------
        bright_caption = tk.Label(card.body,
                                  text=W.spaced(t("Brightness").upper()),
                                  font=W.ui(8, "bold"), bg=self.p.surface,
                                  fg=self.p.text_dim)
        bright_caption.pack(anchor="w")
        self._reg(bright_caption, bg="surface", fg="text_dim")

        bright_row = tk.Frame(card.body, bg=self.p.surface)
        bright_row.pack(fill="x", pady=(4, 0))
        self._reg(bright_row, bg="surface")
        self.bright_slider = W.Slider(bright_row, self.p, 0, 100,
                                      self.cfg.bg_brightness,
                                      command=self._brightness_dragged,
                                      width=240)
        self.bright_slider.on_release = self._brightness_committed
        self.bright_slider.configure(bg=self.p.surface)
        self.bright_slider.pack(side="left")
        self.themed.append(self.bright_slider)
        self.bright_label = tk.Label(bright_row, text="", font=W.mono(11),
                                     width=5, anchor="e", bg=self.p.surface,
                                     fg=self.p.text)
        self.bright_label.pack(side="left", padx=(6, 0))
        self._reg(self.bright_label, bg="surface", fg="text")
        self._set_brightness_label()

        # --- background colour code -------------------------------------
        bg_row = tk.Frame(card.body, bg=self.p.surface)
        bg_row.pack(anchor="w", fill="x", pady=(10, 0))
        self._reg(bg_row, bg="surface")
        bg_caption = tk.Label(bg_row, text=W.spaced(t("Colour").upper()),
                              font=W.ui(8, "bold"), bg=self.p.surface,
                              fg=self.p.text_dim)
        bg_caption.pack(side="left", padx=(0, 8))
        self._reg(bg_caption, bg="surface", fg="text_dim")

        self.bg_var = tk.StringVar(value=self.cfg.bg_custom or self.p.bg)
        bg_entry = W.HudEntry(bg_row, self.bg_var, self.p, width=130)
        bg_entry.entry.configure(font=W.mono(10), width=12)
        bg_entry.configure(bg=self.p.surface)
        bg_entry.pack(side="left")
        self.themed.append(bg_entry)
        bg_entry.entry.bind("<Return>", lambda _e: self._apply_custom_bg())

        use_bg = W.HudButton(bg_row, t("Use"), self._apply_custom_bg, self.p,
                             height=30, pad=10)
        use_bg.configure(bg=self.p.surface)
        use_bg.pack(side="left", padx=(8, 0))
        self.themed.append(use_bg)

        clear_bg = W.HudButton(bg_row, t("Slider"), self._clear_custom_bg,
                               self.p, height=30, pad=10)
        clear_bg.configure(bg=self.p.surface)
        clear_bg.pack(side="left", padx=(6, 0))
        self.themed.append(clear_bg)

        self.bg_hint = self._hint(
            card.body, t("Hex (#101418) or RGB (16, 20, 24)."), pady=(6, 0))

        # --- accent ------------------------------------------------------
        accent_caption = tk.Label(card.body, text=W.spaced(t("Accent").upper()),
                                  font=W.ui(8, "bold"), bg=self.p.surface,
                                  fg=self.p.text_dim)
        accent_caption.pack(anchor="w", pady=(14, 4))
        self._reg(accent_caption, bg="surface", fg="text_dim")

        self.swatches = []
        for start in (0, 6):
            strip = tk.Frame(card.body, bg=self.p.surface)
            strip.pack(anchor="w", pady=2)
            self._reg(strip, bg="surface")
            for _name, colour in T.ACCENTS[start:start + 6]:
                swatch = W.Swatch(strip, colour, self._set_accent, self.p)
                swatch.configure(bg=self.p.surface)
                swatch.pack(side="left", padx=3)
                self.swatches.append(swatch)
                self.themed.append(swatch)

        custom = tk.Frame(card.body, bg=self.p.surface)
        custom.pack(anchor="w", pady=(12, 0))
        self._reg(custom, bg="surface")
        caption = tk.Label(custom, text=W.spaced(t("Custom").upper()),
                           font=W.ui(8, "bold"), bg=self.p.surface,
                           fg=self.p.text_dim)
        caption.pack(side="left", padx=(0, 8))
        self._reg(caption, bg="surface", fg="text_dim")

        self.custom_var = tk.StringVar(value=self.p.accent_seed)
        entry = W.HudEntry(custom, self.custom_var, self.p, width=130)
        entry.entry.configure(font=W.mono(10), width=12)
        entry.configure(bg=self.p.surface)
        entry.pack(side="left")
        self.themed.append(entry)
        entry.entry.bind("<Return>", lambda _e: self._apply_custom_colour())

        use = W.HudButton(custom, t("Use"), self._apply_custom_colour, self.p,
                          height=30, pad=10)
        use.configure(bg=self.p.surface)
        use.pack(side="left", padx=(8, 0))
        self.themed.append(use)

        self.custom_hint = self._hint(
            card.body, t("Hex (#22d3ee) or RGB (34, 211, 238)."), pady=(6, 0))

        # --- refresh rate -------------------------------------------------
        fps_row = tk.Frame(card.body, bg=self.p.surface)
        fps_row.pack(anchor="w", fill="x", pady=(14, 0))
        self._reg(fps_row, bg="surface")
        fps_caption = tk.Label(fps_row, text=W.spaced(t("Refresh rate").upper()),
                               font=W.ui(8, "bold"), bg=self.p.surface,
                               fg=self.p.text_dim)
        fps_caption.pack(side="left", padx=(0, 10))
        self._reg(fps_caption, bg="surface", fg="text_dim")

        self.fps_tabs = W.Tabs(fps_row, [f"{f} fps" for f in FPS_CHOICES],
                               self.p, on_change=self._fps_chosen, height=28)
        self.fps_tabs.configure(bg=self.p.surface)
        self.fps_tabs.active = (FPS_CHOICES.index(self.cfg.fps)
                                if self.cfg.fps in FPS_CHOICES else 1)
        self.fps_tabs.redraw()
        self.fps_tabs.pack(side="left")
        self.themed.append(self.fps_tabs)

        self.on_top_toggle = W.Toggle(card.body, t("Always on top"),
                                      self.cfg.on_top, self.set_on_top, self.p)
        self.on_top_toggle.pack(anchor="w", pady=(14, 0))
        self.themed.append(self.on_top_toggle)
        card.fit()
        self.appearance_card = card

    def _build_background_card(self, page) -> None:
        card = self._card(page, t("Running in the background"))
        self.tray_toggle = W.Toggle(card.body, t("Keep running in the tray"),
                                    self.cfg.tray, self.set_tray, self.p)
        self.tray_toggle.pack(anchor="w")
        self.themed.append(self.tray_toggle)

        self.minimised_toggle = W.Toggle(
            card.body, t("Start minimised"), self.cfg.start_minimised,
            self.set_start_minimised, self.p)
        self.minimised_toggle.pack(anchor="w", pady=(6, 0))
        self.themed.append(self.minimised_toggle)

        self.autostart_toggle = W.Toggle(
            card.body, t("Start with Windows"), self.cfg.start_with_windows,
            self.set_autostart, self.p)
        self.autostart_toggle.pack(anchor="w", pady=(6, 0))
        self.themed.append(self.autostart_toggle)

        note = t("Once calibrated, the board works on its own.")
        if not tray_module.available():
            note += " " + t("A tray icon isn't available on this system.")
        elif not autostart.supported():
            note += " " + t("Start with login is Windows only.")
        self.background_note = self._hint(card.body, note)
        card.fit()

    # -- console ---------------------------------------------------------

    def _build_console(self) -> None:
        bar = tk.Frame(self, bg=self.p.bg)
        bar.pack(side="bottom", fill="x")
        self._reg(bar, bg="bg")

        self.status_label = tk.Label(bar, text=t("Not connected"), anchor="w",
                                     font=W.ui(9), bg=self.p.bg,
                                     fg=self.p.text_dim)
        self.status_label.pack(fill="x", pady=(10, 6))
        self._reg(self.status_label, bg="bg", fg="text_dim")

        self.console_toggle = W.Disclosure(bar, t("Console"),
                                           self.cfg.console_open,
                                           self._set_console_open, self.p)
        self.console_toggle.pack(fill="x")
        self.themed.append(self.console_toggle)

        card = W.Card(bar, self.p, padding=10)
        self.log_box = tk.Text(card.body, height=6, wrap="none", bd=0,
                               highlightthickness=0, state="disabled",
                               font=W.mono(8), bg=self.p.surface,
                               fg=self.p.text_dim)
        self.log_box.pack(fill="both", expand=True)
        self._reg(self.log_box, bg="surface", fg="text_dim")
        self.themed.append(card)
        self.console_card = card
        self._set_console_open(self.cfg.console_open, save=False)

    def _set_console_open(self, open_: bool, save: bool = True) -> None:
        if open_:
            self.console_card.pack(fill="x", pady=(6, 0))
            self.console_card.fit()
        else:
            self.console_card.pack_forget()
        self.cfg.console_open = open_
        if save:
            S.save(self.cfg)

    def log(self, text: str) -> None:
        """The console is deliberately never translated - see i18n.py."""
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _set_hid_label(self) -> None:
        """Say plainly whether games will actually see the pedals."""
        if not hasattr(self, "hid_label"):
            return
        head = t("Game controller output")
        if self.hid is None:
            text, colour = (f"{head}: " + t("Unknown until connected"),
                            self.p.text_dim)
        elif self.hid:
            text, colour = f"{head}: " + t("Active"), self.p.ok
        else:
            text, colour = (f"{head}: " + t("Not active") + " - "
                            + t("this board can't act as one, or the Joystick "
                                "library wasn't installed when you flashed it. "
                                "Calibration still works."), self.p.offline)
        self.hid_label.config(text=text, fg=colour)
        if hasattr(self, "device_card"):
            self.device_card.fit()

    # -- settings actions ------------------------------------------------

    def _set_axis_enabled(self, index: int, value: bool) -> None:
        axes = list(self.cfg.axes)
        axes[index] = value
        if not any(axes):
            # Hiding every pedal would leave an empty calibration tab.
            self.axis_toggles[index].set(True)
            self._set_status(t("At least one pedal has to stay switched on."))
            return
        self.cfg.axes = axes
        S.save(self.cfg)
        self._place_panels()
        self._push_axis_enables()
        self._set_status(f"{t(P.AXIS_NAMES[index])}: "
                         + (t("On") if value else t("Off")))

    def _language_chosen(self, index: int) -> None:
        code = i18n.LANGUAGE_CODES[index]
        if code == self.cfg.language:
            return
        self.cfg.language = code
        self.cfg.language_chosen = True
        S.save(self.cfg)
        i18n.set_language(code)
        # Deferred by one idle cycle. This runs from inside the dropdown's
        # popup menu, whose parent is one of the widgets about to be
        # destroyed; rebuilding here pulls the ground out from under the call
        # that is still unwinding.
        self._schedule(0, lambda: self._rebuild_ui(keep_tab=1))

    def _ask_language_once(self) -> None:
        """Asked on the very first run, and never again.

        The answer is recorded even if the prompt is dismissed, because a
        question that reappears every launch is worse than a wrong default -
        and the language can be changed in Settings at any time.
        """
        self.cfg.language_chosen = True
        names = [name for _code, name in i18n.LANGUAGES]
        choice = self._dialog(
            W.ask_choice, self, self.p, f"{BRAND} {t('Pedal Calibrator')}",
            t("Choose your language"), names,
            t("You can change this later in Settings."))
        S.save(self.cfg)
        if choice is None:
            return
        code = i18n.LANGUAGE_CODES[choice]
        if code != self.cfg.language:
            self.cfg.language = code
            S.save(self.cfg)
            i18n.set_language(code)
            self._rebuild_ui(keep_tab=self.tabs.active)

    def _layout_chosen(self, index: int) -> None:
        layout = S.LAYOUTS[index]
        if layout == self.cfg.layout:
            return
        self.cfg.layout = layout
        S.save(self.cfg)
        # The cards are built differently in each layout - upright bar, wrapped
        # buttons - so they are rebuilt rather than re-packed, and the rebuild
        # waits for the click that asked for it to finish unwinding first.
        self._schedule(0, lambda: self._rebuild_ui(keep_tab=1))

    def _push_axis_enables(self) -> None:
        if self.device is None:
            return
        for i, on in enumerate(self.cfg.axes):
            try:
                self.device.send(P.cmd_enable(i, on))
            except Exception as exc:  # noqa: BLE001
                self.log(f"write failed: {exc}")
                return

    def set_tray(self, value: bool) -> None:
        self.cfg.tray = value
        S.save(self.cfg)
        if value:
            if not self._start_tray():
                self.tray_toggle.set(False)
                self.cfg.tray = False
                S.save(self.cfg)
                self._set_status(t("A tray icon isn't available on this system."))
                return
            self._set_status(t("Closing the window will now leave it running."))
        else:
            self._stop_tray()
            self._set_status(t("Closing the window will now quit."))

    def set_start_minimised(self, value: bool) -> None:
        self.cfg.start_minimised = value
        S.save(self.cfg)
        if value and not self.cfg.tray:
            self._set_status(t("Turn on \"keep running in the tray\" as well, "
                               "or there is nothing to minimise into."))

    def set_autostart(self, value: bool) -> None:
        if not autostart.supported():
            self.autostart_toggle.set(False)
            self._set_status(t("Start with login is Windows only."))
            return
        if not autostart.set_enabled(value):
            self.autostart_toggle.set(not value)
            self._set_status(t("Windows would not let us change the startup "
                               "entry."))
            return
        self.cfg.start_with_windows = value
        S.save(self.cfg)
        self._set_status(t("Start with Windows") + ": "
                         + (t("On") if value else t("Off")))

    def _start_tray(self) -> bool:
        if self._tray is not None and self._tray.running:
            return True
        if not tray_module.available():
            return False
        self._tray = tray_module.Tray(
            ICON_PNG_B64,
            on_show=lambda: self._tray_requests.put("show"),
            on_quit=lambda: self._tray_requests.put("quit"),
        )
        if not self._tray.start():
            self._tray = None
            return False
        return True

    def _stop_tray(self) -> None:
        if self._tray is not None:
            self._tray.stop()
            self._tray = None

    def _hide_to_tray(self) -> None:
        self.master.withdraw()
        self.log("hidden to the tray - the board keeps working regardless")

    def _show_window(self) -> None:
        self.master.deiconify()
        self.master.lift()
        self.master.focus_force()

    def set_on_top(self, value: bool) -> None:
        self.cfg.on_top = value
        S.save(self.cfg)
        try:
            self.master.attributes("-topmost", bool(value))
        except tk.TclError:
            pass

    # -- appearance --------------------------------------------------------

    def _set_brightness_label(self) -> None:
        if hasattr(self, "bright_label"):
            self.bright_label.config(text=f"{self.cfg.bg_brightness}%")

    def _brightness_dragged(self, value: int) -> None:
        """Recolour live. Every colour in the app derives from this number, so
        the only way to judge it is to watch the app wear it."""
        self.cfg.bg_brightness = int(value)
        self.cfg.bg_custom = ""      # the slider takes over from a typed colour
        self._set_brightness_label()
        self._apply_palette(self._palette(), save=False)

    def _brightness_committed(self, _value: int) -> None:
        self.bg_var.set(self.p.bg)
        S.save(self.cfg)

    def _apply_custom_bg(self) -> None:
        parsed = T.parse_colour(self.bg_var.get())
        if parsed is None:
            self.bg_hint.config(text=t("Not a colour - try #101418 or "
                                       "16, 20, 24."), fg=self.p.danger)
            return
        self.cfg.bg_custom = parsed
        self.cfg.bg_brightness = T.bg_brightness_of(parsed)
        self.bright_slider.set(self.cfg.bg_brightness)
        self._set_brightness_label()
        self.bg_hint.config(text=t("Hex (#101418) or RGB (16, 20, 24)."),
                            fg=self.p.text_dim)
        self._apply_palette(self._palette())

    def _clear_custom_bg(self) -> None:
        self.cfg.bg_custom = ""
        self._apply_palette(self._palette())
        self.bg_var.set(self.p.bg)

    def _set_accent(self, colour: str) -> None:
        self.cfg.accent = colour
        self.custom_var.set(colour)
        self._apply_palette(self._palette())

    def _apply_custom_colour(self) -> None:
        parsed = T.parse_colour(self.custom_var.get())
        if parsed is None:
            self.custom_hint.config(
                text=t("Not a colour - try #22d3ee or 34, 211, 238."),
                fg=self.p.danger)
            return
        self.custom_hint.config(text=t("Hex (#22d3ee) or RGB (34, 211, 238)."),
                                fg=self.p.text_dim)
        self._set_accent(parsed)

    def _apply_palette(self, palette: T.Palette, save: bool = True) -> None:
        self.p = palette
        if save:
            S.save(self.cfg)
        self.master.configure(bg=palette.bg)
        self.configure(bg=palette.bg)
        for widget, roles in self.plain:
            widget.configure(**{opt: getattr(palette, attr)
                                for opt, attr in roles.items()})
        for child in self.themed:
            if isinstance(child, (W.HudEntry, W.HudButton, W.Swatch, W.Toggle,
                                  W.HelpDot)):
                parent_bg = child.master.cget("bg")
                child.configure(bg=parent_bg)
            child.apply_theme(palette)
        self._paint_dot()
        self.live_label.config(fg=self._status_colour())
        self._set_hid_label()
        self._sync_appearance_buttons()

    def _sync_appearance_buttons(self) -> None:
        for swatch, (_name, colour) in zip(self.swatches, T.ACCENTS):
            swatch.set_selected(colour == self.p.accent_seed)

    def reset_everything(self) -> None:
        confirmed = self._dialog(
            messagebox.askyesno,
            t("Reset everything?"),
            t("This restores the defaults: calibration back to 0% - 100% on "
              "every pedal, all three pedals switched back on, the dark "
              "background with the cyan accent, always-on-top back on and the "
              "console hidden. Saved profiles are deleted. If a device is "
              "connected the reset is written to it as well.")
            + "\n\n" + t("Continue?"),
            icon="warning", default="no",
        )
        if not confirmed:
            return

        defaults = S.AppSettings.defaults()
        defaults.language = self.cfg.language          # not a "setting" to undo
        defaults.language_chosen = True
        self.cfg = defaults
        self.store.clear()
        for panel in self.panels:
            panel.set_limits(0, P.ADC_MAX)
            panel.set_linearity(0)
            panel.set_deadzone(0)
            panel.set_smoothing(True)
            panel.set_show_raw(False)
        for toggle, value in zip(self.axis_toggles, defaults.axes):
            toggle.set(value)
        self.on_top_toggle.set(defaults.on_top)
        self.custom_var.set(defaults.accent)
        self.bright_slider.set(defaults.bg_brightness)
        self._set_brightness_label()
        self.console_toggle.open = defaults.console_open
        self.console_toggle.redraw()
        self._set_console_open(defaults.console_open, save=False)
        self.set_on_top(defaults.on_top)
        self._place_panels()
        self._refresh_all_profiles()
        self._apply_palette(self._palette())
        self.bg_var.set(self.p.bg)
        S.save(self.cfg)

        if self.device is not None:
            self._push_axis_enables()
            self.apply_calibration()
            self.device.send(P.cmd_save())
        self._set_status(t("Everything reset to defaults."))
        self.log("reset to defaults")

    # -- profiles ----------------------------------------------------------

    def _refresh_all_profiles(self) -> None:
        for panel in self.panels:
            panel.set_profiles(self.store.names(panel.index),
                               self.store.selected(panel.index))

    def _profile_of(self, index: int) -> PR.PedalProfile:
        panel = self.panels[index]
        lo, hi = panel.limits()
        return PR.PedalProfile(lo=lo, hi=hi, curve=panel.linearity,
                               deadzone=panel.deadzone,
                               smoothing=panel.smoothing())

    def _profile_chosen(self, index: int, row: int) -> None:
        panel = self.panels[index]
        name = panel.profile_name_at(row)
        self.store.select(index, name)
        panel.profile_buttons["delete"].set_enabled(bool(name))
        if not name:
            return
        profile = self.store.get(index, name)
        if profile is None:
            return
        self._load_profile(index, profile)
        self._set_status(f"{t(P.AXIS_NAMES[index])}: {name}")

    def _load_profile(self, index: int, profile: PR.PedalProfile) -> None:
        panel = self.panels[index]
        panel.set_limits(profile.lo, profile.hi)
        panel.set_linearity(profile.curve)
        panel.set_deadzone(profile.deadzone)
        panel.set_smoothing(profile.smoothing)
        self.cfg.curves[index] = profile.curve
        self.cfg.deadzones[index] = profile.deadzone
        self.cfg.smoothing[index] = profile.smoothing
        S.save(self.cfg)
        self._push_axis(index)

    def _push_axis(self, index: int) -> None:
        """Send one pedal's whole configuration to the board."""
        if self.device is None:
            return
        panel = self.panels[index]
        lo, hi = panel.limits()
        self._send(P.cmd_set(index, lo, hi))
        self._send(P.cmd_curve(index, panel.linearity))
        self._send(P.cmd_deadzone(index, panel.deadzone))
        self._send(P.cmd_smoothing(index, panel.smoothing()))

    def _profile_save(self, index: int) -> None:
        name = self.store.selected(index)
        if not name:
            self._profile_save_as(index)
            return
        self.store.put(index, name, self._profile_of(index))
        self._refresh_all_profiles()
        self._set_status(f"{t('Profile saved')}: {name}")

    def _profile_save_as(self, index: int) -> None:
        suggestion = self.store.unique_name(
            index, self.store.selected(index) or t("Profile"))
        name = self._dialog(
            W.ask_text, self, self.p, t("New profile"), t("Profile name"),
            suggestion, t("Save"), t("Cancel"))
        if not name:
            return
        saved = self.store.put(index, name, self._profile_of(index))
        self._refresh_all_profiles()
        self._set_status(f"{t('Profile saved')}: {saved}")

    def _profile_delete(self, index: int) -> None:
        name = self.store.selected(index)
        if not name:
            return
        self.store.delete(index, name)
        self._refresh_all_profiles()
        self._set_status(f"{t('Profile deleted')}: {name}")

    def _profile_reset(self, index: int) -> None:
        """Put one pedal back to how it left the factory, leaving the other
        two - and the saved profiles - alone."""
        self.store.select(index, "")
        self._load_profile(index, PR.PedalProfile())
        self._refresh_all_profiles()
        self._set_status(f"{t(P.AXIS_NAMES[index])}: "
                         + t("Reset to defaults."))

    # -- status ----------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.status_label.config(text=text)

    def _set_live(self, live: bool) -> None:
        self.live_label.config(
            text=W.spaced((t("Live") if live else t("Offline")).upper()),
            fg=self._status_colour())
        self._paint_dot()

    def _set_connect_button(self, text: str, variant: str) -> None:
        self.connect_btn.variant = variant
        self.connect_btn.set_text(text)

    # -- connection ------------------------------------------------------

    def refresh_ports(self, select: str | None = None) -> None:
        self.ports = list_serial_ports()
        target = 0
        if select is not None:
            for i, port in enumerate(self.ports):
                if port.device == select:
                    target = i
                    break
        labels = [str(p) for p in self.ports]
        self.port_select.set_values(labels, target)
        for key, select_widget in getattr(self, "extra_selects", {}).items():
            saved = getattr(self.cfg, f"{key}_port", "")
            chosen = next((i for i, p in enumerate(self.ports)
                           if p.device == saved), 0)
            select_widget.set_values(labels, chosen)

    def _selected_port(self) -> str | None:
        idx = self.port_select.get()
        return self.ports[idx].device if 0 <= idx < len(self.ports) else None

    def toggle_connection(self) -> None:
        if self.device is not None or self._connecting:
            self.disconnect()
            return
        port = self._selected_port()
        if port is None:
            self._dialog(messagebox.showwarning, t("No port"),
                         t("No serial port found. Plug the board in and press "
                           "Refresh."))
            return
        self._begin_connect(port)

    def _begin_connect(self, port: str, quiet: bool = False) -> None:
        """`quiet` reports failures in the status line instead of a dialog -
        used when reconnecting to the remembered port at startup, where a
        modal error box for an unplugged board would be obnoxious."""
        # Opening a port takes a couple of seconds - most Arduino boards reset
        # when you connect and need time to boot. Doing that on the GUI thread
        # freezes the window, which looks exactly like a crash, so it happens
        # on a worker thread instead.
        self._connecting = True
        self._set_connect_button(t("Cancel"), "ghost")
        self._set_status(f"{t('Opening')} {port}...")
        self.log(f"opening {port}")
        write_log(f"connect attempt: {port}")

        outcome: dict[str, object] = {}

        def worker() -> None:
            try:
                dev = PedalDevice(port)
                dev.open()
                outcome["device"] = dev
            except Exception as exc:  # noqa: BLE001 - reported to the user
                outcome["error"] = exc

        threading.Thread(target=worker, daemon=True).start()
        self._schedule(100, lambda: self._finish_connect(outcome, port, quiet))

    def _finish_connect(self, outcome: dict, port: str,
                        quiet: bool = False) -> None:
        if not self._alive or not self._connecting:
            dev = outcome.get("device")
            if dev is not None:
                dev.close()
            return
        if not outcome:
            self._schedule(100,
                           lambda: self._finish_connect(outcome, port, quiet))
            return

        self._connecting = False
        error = outcome.get("error")
        if error is not None:
            self._set_connect_button(t("Connect"), "primary")
            self.log(f"failed to open {port}: {error}")
            write_log(f"connect failed: {port}: {error!r}")
            if quiet:
                self._set_status(f"{port}: " + t("Did not open - pick a port "
                                                 "in Settings."))
            else:
                self._set_status(t("Not connected"))
                self._dialog(
                    messagebox.showerror, f"{t('Could not open')} {port}",
                    f"{explain_port_error(error)}\n\nTechnical detail:\n{error}",
                )
            return

        self.device = outcome["device"]
        self.identified = False
        self._handshakes = 0
        if self.cfg.last_port != port:
            self.cfg.last_port = port      # reselected on the next launch
            S.save(self.cfg)
        self._set_connect_button(t("Disconnect"), "ghost")
        self._set_status(f"{t('Connected')} - {port}")
        self.log(f"opened {port}")
        self._handshake()

    def _handshake(self) -> None:
        """Ask 'who are you?' a few times - a board may still be booting."""
        if self.device is None or self.identified or not self._alive:
            return
        self._handshakes += 1
        if self._handshakes > 8:
            self._set_status(t("Connected, but no reply - is the firmware "
                               "flashed?"))
            self.log("no PEDALCAL reply; check the sketch is uploaded "
                     "and the baud rate is 115200")
            return
        try:
            self.device.send(P.cmd_ident())
            self.device.send(P.cmd_get())
        except Exception as exc:  # noqa: BLE001
            self.log(f"write failed: {exc}")
            write_log(f"write failed: {exc!r}")
            return
        self._schedule(500, self._handshake)

    def disconnect(self) -> None:
        self._connecting = False
        if self.device is not None:
            self.device.close()
            self.device = None
        self.identified = False
        self.hid = None
        self._set_connect_button(t("Connect"), "primary")
        self._set_status(t("Not connected"))
        self._set_live(False)
        self._set_hid_label()
        self.log("disconnected")

    # -- commands --------------------------------------------------------

    def apply_calibration(self) -> None:
        if self.device is None:
            return
        for panel in self.panels:
            lo, hi = panel.limits()
            if lo >= hi:
                self._dialog(
                    messagebox.showerror, t(panel.name),
                    f"{t('Rest')} ({P.raw_to_pct(lo)}%) - {t('Full')} "
                    f"({P.raw_to_pct(hi)}%)\n\n"
                    + t("Rest has to be below full - set Max at the floor "
                        "first"))
                return
            self.device.send(P.cmd_set(panel.index, lo, hi))
            self.device.send(P.cmd_curve(panel.index, panel.linearity))
            self.device.send(P.cmd_deadzone(panel.index, panel.deadzone))
            self.device.send(P.cmd_smoothing(
                panel.index, self.cfg.smoothing[panel.index]))
        self._set_status(t("Calibration applied (not yet saved)."))

    def save_calibration(self) -> None:
        if self.device is None:
            return
        self.apply_calibration()
        self.device.send(P.cmd_save())
        self._set_status(t("Saved to the device."))

    def reload_calibration(self) -> None:
        if self.device is not None:
            self.device.send(P.cmd_load())

    def toggle_learn(self, index: int) -> None:
        """Learn one pedal's travel without disturbing the others."""
        panel = self.panels[index]
        name = t(P.AXIS_NAMES[index])
        if index in self.learning:
            self.learning.discard(index)
            panel.set_learning(False)
            lo, hi = self._observed[index]
            if hi > lo:
                panel.set_limits(lo, hi)
                self.apply_calibration()
                self._set_status(f"{name}: {P.raw_to_pct(lo)}% - "
                                 f"{P.raw_to_pct(hi)}%")
            else:
                self._set_status(f"{name}: "
                                 + t("Nothing moved, range unchanged."))
            return

        self.learning.add(index)
        self._observed[index] = [P.ADC_MAX, 0]
        panel.set_learning(True)
        self._set_status(f"{name}: "
                         + t("Press it fully, then press Stop."))

    # -- response curve ---------------------------------------------------

    def _limits_changed(self, index: int) -> None:
        self.apply_calibration()
        lo, hi = self.panels[index].limits_pct()
        self._set_status(f"{t(P.AXIS_NAMES[index])}: {lo}% - {hi}%")

    def _curve_preview(self, index: int, linearity: int) -> None:
        """Dragging the slider: remember it, but don't spam the serial link."""
        self.cfg.curves[index] = linearity

    def _curve_commit(self, index: int, linearity: int) -> None:
        self.cfg.curves[index] = linearity
        S.save(self.cfg)
        if self.device is not None:
            try:
                self.device.send(P.cmd_curve(index, linearity))
            except Exception as exc:  # noqa: BLE001
                self.log(f"curve write failed: {exc}")
                return
        self._set_status(
            f"{t(P.AXIS_NAMES[index])} {t('Linearity')} "
            + (f"{linearity:+d}" if linearity else t("Linear")))

    def _deadzone_commit(self, index: int, percent: int) -> None:
        self.cfg.deadzones[index] = percent
        S.save(self.cfg)
        self._send(P.cmd_deadzone(index, percent))
        self._set_status(f"{t(P.AXIS_NAMES[index])} {t('Deadzone')} {percent}%")

    def _smoothing_commit(self, index: int, on: bool) -> None:
        self.cfg.smoothing[index] = on
        S.save(self.cfg)
        self._send(P.cmd_smoothing(index, on))
        self._set_status(f"{t(P.AXIS_NAMES[index])} {t('Smoothing')}: "
                         + (t("On") if on else t("Off")))

    def _show_raw_changed(self, index: int, on: bool) -> None:
        self.cfg.show_raw[index] = on
        S.save(self.cfg)

    def _send(self, command: str) -> None:
        """Fire and forget - a write failing is logged, never fatal."""
        if self.device is None:
            return
        try:
            self.device.send(command)
        except Exception as exc:  # noqa: BLE001
            self.log(f"write failed: {exc}")

    def _fps_chosen(self, index: int) -> None:
        self.set_fps(FPS_CHOICES[index])

    def _set_extra_port(self, key: str, index: int) -> None:
        if 0 <= index < len(self.ports):
            setattr(self.cfg, f"{key}_port", self.ports[index].device)
            S.save(self.cfg)

    def set_fps(self, fps: int) -> None:
        self.cfg.fps = fps
        S.save(self.cfg)
        # Ask the board to match, so a faster display shows genuinely fresher
        # data rather than redrawing the same reading more often.
        self._send(P.cmd_rate(min(fps, 200)))
        self._set_status(f"{t('Refresh rate')}: {fps} fps")

    # -- event loop ------------------------------------------------------

    def _tick(self) -> None:
        if not self._alive:
            return
        while True:
            try:
                request = self._tray_requests.get_nowait()
            except queue.Empty:
                break
            if request == "show":
                self._show_window()
            elif request == "quit":
                self.quit_app()
                return
        try:
            if self.device is not None:
                for msg in self.device.poll():
                    self._handle(msg)
        except Exception:  # noqa: BLE001 - a bad frame must not kill the app
            write_log("error handling serial data:\n" + traceback.format_exc())
        self._schedule(self._poll_ms(), self._tick)

    def _handle(self, msg: P.Message) -> None:
        if isinstance(msg, P.Data):
            for panel, raw in zip(self.panels, msg.raw):
                if not self.cfg.axes[panel.index]:
                    continue
                panel.update_raw(raw)
                if panel.index in self.learning:
                    seen = self._observed[panel.index]
                    seen[0] = min(seen[0], raw)
                    seen[1] = max(seen[1], raw)
                    panel.set_limits(seen[0], seen[1])
        elif isinstance(msg, P.Ident):
            self.identified = True
            self.hid = msg.hid
            self._set_live(True)
            self._set_hid_label()
            self._set_status(f"{t('Connected')} - {P.FIRMWARE_ID} "
                             f"v{msg.version}")
            self.log(f"identified: {P.FIRMWARE_ID} v{msg.version} "
                     f"({'hid' if msg.hid else 'nohid'})")
            self._push_axis_enables()
            self._send(P.cmd_rate(min(self.cfg.fps, 200)))
        elif isinstance(msg, P.Calibration):
            for panel, (lo, hi) in zip(self.panels, msg.points):
                panel.set_limits(lo, hi)
            self.log(f"calibration from device: {msg.points}")
        elif isinstance(msg, P.Enabled):
            self.log(f"device axis state: {msg.axes}")
        elif isinstance(msg, P.Deadzone):
            for panel, value in zip(self.panels, msg.axes):
                panel.set_deadzone(value)
                self.cfg.deadzones[panel.index] = value
        elif isinstance(msg, P.Smoothing):
            for panel, value in zip(self.panels, msg.axes):
                panel.set_smoothing(value)
                self.cfg.smoothing[panel.index] = value
        elif isinstance(msg, P.Linearity):
            for panel, linearity in zip(self.panels, msg.axes):
                panel.set_linearity(linearity)
                self.cfg.curves[panel.index] = linearity
            self.log(f"curves from device: {msg.axes}")
        elif isinstance(msg, P.Ack):
            if not msg.ok:
                self.log(f"device error: {msg.detail}")
        elif isinstance(msg, P.Unknown) and msg.text:
            self.log(msg.text)

    def _on_close(self) -> None:
        """The window's X. With the tray on, this hides rather than quits."""
        if self.cfg.tray and self._tray is not None and self._tray.running:
            self._hide_to_tray()
            return
        self.quit_app()

    def quit_app(self) -> None:
        self._alive = False
        self._cancel_pending()
        self.disconnect()
        self._stop_tray()
        self.master.destroy()


def _install_crash_handler(root: tk.Tk) -> None:
    """A packaged .exe has no console, so an unhandled error would otherwise
    make the window vanish with no explanation. Show it and write it down."""

    def report(exc_type, exc, tb) -> None:
        write_log("UNHANDLED ERROR\n"
                  + "".join(traceback.format_exception(exc_type, exc, tb)))
        try:
            root.attributes("-topmost", False)
            messagebox.showerror(
                f"{BRAND} Pedal Calibrator",
                f"Something went wrong:\n\n{exc_type.__name__}: {exc}\n\n"
                f"The details were written to:\n{LOG_FILE}",
            )
        except Exception:
            pass

    root.report_callback_exception = report
    sys.excepthook = report


def run(initial_port: str | None = None) -> None:
    root = tk.Tk()
    _install_crash_handler(root)
    root.geometry("640x820")
    try:
        root._icon = tk.PhotoImage(data=ICON_PNG_B64)  # keep a reference
        root.iconphoto(True, root._icon)
    except Exception:
        pass  # cosmetic only, never worth failing over
    CalibratorApp(root, initial_port=initial_port)
    root.mainloop()
