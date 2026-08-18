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
from . import protocol as P
from . import settings as S
from . import tray as tray_module
from . import theme as T
from . import widgets as W
from .device import PedalDevice, PortInfo, explain_port_error, list_serial_ports
from .icon_data import ICON_PNG_B64

#: Errors and connection attempts are appended here, so a crash in the packaged
#: .exe (which has no console to print to) still leaves something to read.
LOG_FILE = Path.home() / "pedalcal.log"

POLL_MS = 25   # how often the UI drains the serial queue
PAD = 14       # outer window padding


def write_log(text: str) -> None:
    try:
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}  {text}\n")
    except Exception:
        pass  # logging must never be the thing that breaks the app


class AxisPanel(W.Card):
    """One pedal: live output, meter, calibration points and response curve.

    Everything the user sees and types is a percentage of the pedal's travel.
    Raw ADC counts still go over the wire because that's what the firmware
    speaks, but they never reach the screen.
    """

    CURVE_SAMPLES = 32

    def __init__(self, master, index: int, name: str, palette: T.Palette,
                 on_change, on_curve, on_curve_commit, on_learn) -> None:
        super().__init__(master, palette)
        self.index = index
        self.name = name
        self._on_change = on_change
        self._on_curve = on_curve
        self._on_curve_commit = on_curve_commit
        self._on_learn = on_learn
        self.raw = 0
        self.linearity = 0
        self.min_var = tk.StringVar(value="0")
        self.max_var = tk.StringVar(value="100")
        self.themed: list[W.Themed] = []
        self.plain: list[tuple[tk.Widget, dict]] = []

        body = self.body
        body.columnconfigure(0, weight=1)

        header = self._row(body, 0)
        self.title = tk.Label(header, text=W.spaced(name.upper()),
                              font=W.ui(9, "bold"), bg=palette.surface,
                              fg=palette.text_dim)
        self.title.pack(side="left")
        self._reg(self.title, bg="surface", fg="text_dim")

        self.pct_label = tk.Label(header, text="0%", font=W.mono(19, "bold"),
                                  width=5, anchor="e", bg=palette.surface,
                                  fg=palette.accent)
        self.pct_label.pack(side="right")
        self._reg(self.pct_label, bg="surface", fg="accent")

        self.meter = W.Meter(body, palette)
        self.meter.grid(row=1, column=0, sticky="ew", pady=(10, 12))
        self.themed.append(self.meter)

        fields = self._row(body, 2)
        self._build_field(fields, "REST", self.min_var)
        self._build_field(fields, "FULL", self.max_var, padx=(24, 0))
        self.learn_btn = W.HudButton(fields, "learn", self._learn, palette,
                                     height=30, pad=12,
                                     fits=["stop", "learn"])
        self.learn_btn.configure(bg=palette.surface)
        self.learn_btn.pack(side="right")
        self.themed.append(self.learn_btn)

        self.advanced = W.Disclosure(body, "advanced", False,
                                     self._toggle_advanced, palette)
        self.advanced.configure(bg=palette.surface)
        self.advanced.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.themed.append(self.advanced)

        self._build_advanced(body)

        for var in (self.min_var, self.max_var):
            var.trace_add("write", lambda *_: self.redraw_meter())

    # -- construction helpers --------------------------------------------

    def _reg(self, widget: tk.Widget, **roles: str) -> None:
        self.plain.append((widget, roles))

    def _row(self, body, row: int) -> tk.Frame:
        frame = tk.Frame(body, bg=self.p.surface)
        frame.grid(row=row, column=0, sticky="ew")
        self._reg(frame, bg="surface")
        return frame

    def _build_field(self, parent, label: str, var: tk.StringVar,
                     padx=(0, 0)) -> None:
        holder = tk.Frame(parent, bg=self.p.surface)
        holder.pack(side="left", padx=padx)
        self._reg(holder, bg="surface")

        caption = tk.Label(holder, text=W.spaced(label), font=W.ui(8, "bold"),
                           bg=self.p.surface, fg=self.p.text_dim)
        caption.pack(side="left", padx=(0, 8))
        self._reg(caption, bg="surface", fg="text_dim")

        entry = W.HudEntry(holder, var, self.p, width=58)
        entry.configure(bg=self.p.surface)
        entry.pack(side="left")
        self.themed.append(entry)

        unit = tk.Label(holder, text="%", font=W.mono(10), bg=self.p.surface,
                        fg=self.p.text_dim)
        unit.pack(side="left", padx=(3, 0))
        self._reg(unit, bg="surface", fg="text_dim")

        button = W.HudButton(holder, "set", lambda: self._capture(var), self.p,
                             height=30, pad=12)
        button.configure(bg=self.p.surface)
        button.pack(side="left", padx=(8, 0))
        self.themed.append(button)

    def _build_advanced(self, body) -> None:
        panel = tk.Frame(body, bg=self.p.surface)
        self._reg(panel, bg="surface")
        self.advanced_panel = panel
        self.advanced_row = 4

        row = tk.Frame(panel, bg=self.p.surface)
        row.pack(fill="x", pady=(10, 6))
        self._reg(row, bg="surface")

        caption = tk.Label(row, text=W.spaced("LINEARITY"),
                           font=W.ui(8, "bold"), bg=self.p.surface,
                           fg=self.p.text_dim)
        caption.pack(side="left", padx=(0, 10))
        self._reg(caption, bg="surface", fg="text_dim")

        self.curve_slider = W.Slider(
            panel, self.p, -P.CURVE_MAX, P.CURVE_MAX, 0,
            command=self._curve_dragged)
        self.curve_slider.on_release = self._curve_committed
        self.curve_slider.configure(bg=self.p.surface)
        self.curve_slider.pack(in_=row, side="left")
        self.themed.append(self.curve_slider)

        self.curve_label = tk.Label(row, text="0", font=W.mono(11), width=5,
                                    anchor="e", bg=self.p.surface,
                                    fg=self.p.text)
        self.curve_label.pack(side="left", padx=(8, 0))
        self._reg(self.curve_label, bg="surface", fg="text")

        reset = W.HudButton(row, "linear", self._reset_curve, self.p,
                            height=28, pad=10)
        reset.configure(bg=self.p.surface)
        reset.pack(side="right")
        self.themed.append(reset)

        self.graph = W.CurveGraph(panel, self.p)
        self.graph.pack(fill="x")
        self.themed.append(self.graph)

        hint = tk.Label(
            panel, justify="left", anchor="w", font=W.ui(8),
            bg=self.p.surface, fg=self.p.text_dim,
            text="left of centre reacts sooner and is more sensitive; "
                 "right of centre\nis gentler off the top and easier to "
                 "hold part-way")
        hint.pack(anchor="w", pady=(6, 0))
        self._reg(hint, bg="surface", fg="text_dim")
        self._refresh_curve()

    # -- advanced section -------------------------------------------------

    def _toggle_advanced(self, open_: bool) -> None:
        if open_:
            self.advanced_panel.grid(row=self.advanced_row, column=0,
                                     sticky="ew")
        else:
            self.advanced_panel.grid_forget()
        self.fit()

    def _curve_dragged(self, value: int) -> None:
        """Live while dragging: redraw locally, don't flood the serial link."""
        self.linearity = int(value)
        self._refresh_curve()
        if self._on_curve is not None:
            self._on_curve(self.index, self.linearity)

    def _curve_committed(self, value: int) -> None:
        if self._on_curve_commit is not None:
            self._on_curve_commit(self.index, int(value))

    def _reset_curve(self) -> None:
        self.set_linearity(0)
        self._curve_committed(0)

    def _refresh_curve(self) -> None:
        self.curve_label.config(text=f"{self.linearity:+d}"
                                     if self.linearity else "0")
        steps = self.CURVE_SAMPLES
        self.graph.set_curve([
            (i / steps,
             P.apply_curve(round(i / steps * P.ADC_MAX), self.linearity)
             / P.ADC_MAX)
            for i in range(steps + 1)
        ])

    def set_linearity(self, value: int) -> None:
        self.linearity = max(-P.CURVE_MAX, min(P.CURVE_MAX, int(value)))
        self.curve_slider.set(self.linearity)
        self._refresh_curve()

    # -- learning ---------------------------------------------------------

    def _learn(self) -> None:
        if self._on_learn is not None:
            self._on_learn(self.index)

    def set_learning(self, learning: bool) -> None:
        self.learn_btn.set_text("stop" if learning else "learn")
        self.learn_btn.variant = "primary" if learning else "ghost"
        self.learn_btn.redraw()

    # -- values ----------------------------------------------------------

    def limits_pct(self) -> tuple[int, int]:
        def as_pct(var: tk.StringVar, fallback: int) -> int:
            try:
                return max(0, min(100, int(float(var.get().strip().rstrip("%")))))
            except ValueError:
                return fallback

        return as_pct(self.min_var, 0), as_pct(self.max_var, 100)

    def limits(self) -> tuple[int, int]:
        """The calibration in raw counts, which is what the firmware wants."""
        lo_pct, hi_pct = self.limits_pct()
        return P.pct_to_raw(lo_pct), P.pct_to_raw(hi_pct)

    def set_limits(self, lo: int, hi: int) -> None:
        """Takes raw counts (from the device) and shows them as percentages."""
        self.min_var.set(str(P.raw_to_pct(lo)))
        self.max_var.set(str(P.raw_to_pct(hi)))

    def _capture(self, var: tk.StringVar) -> None:
        var.set(str(P.raw_to_pct(self.raw)))
        self._on_change()

    def update_raw(self, raw: int) -> None:
        self.raw = raw
        lo, hi = self.limits()
        output = P.pedal_output(raw, lo, hi, self.linearity)
        self.pct_label.config(text=f"{output * 100:.0f}%")
        self.meter.set_values(raw, lo, hi)
        if self.advanced.open:
            self.graph.set_position(P.scale(raw, lo, hi))

    def redraw_meter(self) -> None:
        lo, hi = self.limits()
        self.meter.set_values(self.raw, lo, hi)

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
        self.p = T.palette_for(self.cfg.theme, self.cfg.accent)
        super().__init__(master, bg=self.p.bg, padx=PAD, pady=PAD)
        W.init_fonts()
        self.master.title("Sim Pedal Calibrator")
        self.master.minsize(600, 640)
        self.master.configure(bg=self.p.bg)
        self.pack(fill="both", expand=True)

        self.device: PedalDevice | None = None
        self.ports: list[PortInfo] = []
        self.learning: set[int] = set()
        self.identified = False
        self._connecting = False
        self._handshakes = 0
        self._alive = True
        self._pending: set[str] = set()
        self._observed: list[list[int]] = [[P.ADC_MAX, 0] for _ in P.AXIS_NAMES]
        self.themed: list[W.Themed] = []
        self.plain: list[tuple[tk.Widget, dict]] = []
        self._tray: tray_module.Tray | None = None
        # pystray's callbacks arrive on its own thread; Tk must only ever be
        # touched from the main loop, so they queue up and _tick drains them.
        self._tray_requests: queue.Queue[str] = queue.Queue()

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

        self._apply_axis_visibility()
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
        self._schedule(POLL_MS, self._tick)
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- small helpers ---------------------------------------------------

    def _reg(self, widget: tk.Widget, **roles: str) -> None:
        self.plain.append((widget, roles))

    def _card(self, parent, title: str | None = None, padding: int = 14):
        card = W.Card(parent, self.p, padding=padding)
        card.pack(fill="x", pady=(0, 10))
        self.themed.append(card)
        if title:
            label = tk.Label(card.body, text=W.spaced(title),
                             font=W.ui(8, "bold"), bg=self.p.surface,
                             fg=self.p.text_dim)
            label.pack(anchor="w", pady=(0, 10))
            self._reg(label, bg="surface", fg="text_dim")
        return card

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

        title = tk.Label(row, text=W.spaced("PEDAL CALIBRATOR"),
                         font=W.ui(10, "bold"), bg=self.p.bg, fg=self.p.text)
        title.pack(side="left")
        self._reg(title, bg="bg", fg="text")

        self.live_dot = tk.Canvas(row, width=10, height=10, bg=self.p.bg,
                                  highlightthickness=0, bd=0)
        self.live_dot.pack(side="right")
        self._reg(self.live_dot, bg="bg")

        self.live_label = tk.Label(row, text=W.spaced("OFFLINE"),
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
        self.tabs = W.Tabs(row, ["calibration", "settings"], self.p,
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
        page = tk.Frame(self.pages, bg=self.p.bg)
        self._reg(page, bg="bg")
        self.calibration_page = page

        self.panels = [
            AxisPanel(page, i, name, self.p, self.apply_calibration,
                      self._curve_preview, self._curve_commit, self.toggle_learn)
            for i, name in enumerate(P.AXIS_NAMES)
        ]
        for panel, linearity in zip(self.panels, self.cfg.curves):
            panel.set_linearity(linearity)
            panel.fit()
            self.themed.append(panel)

        row = tk.Frame(page, bg=self.p.bg)
        row.pack(fill="x", pady=(2, 0))
        self._reg(row, bg="bg")
        for i, (label, command) in enumerate((
                ("apply", self.apply_calibration),
                ("save", self.save_calibration),
                ("reload", self.reload_calibration))):
            button = W.HudButton(row, label, command, self.p, height=34)
            button.pack(side="left", padx=(0 if i == 0 else 8, 0))
            self.themed.append(button)
        self.action_row = row

    def _apply_axis_visibility(self) -> None:
        """Hide pedals the user says aren't wired up."""
        for panel in self.panels:
            panel.pack_forget()
        for panel in self.panels:
            if self.cfg.axes[panel.index]:
                panel.pack(fill="x", pady=(0, 10), before=self.action_row)
                panel.fit()

    # -- settings page ---------------------------------------------------

    def _build_settings_page(self) -> None:
        scroller = W.ScrollArea(self.pages, self.p)
        self.themed.append(scroller)
        page = scroller.body
        self._reg(page, bg="bg")
        self.settings_page = scroller
        self.page_frames = [self.calibration_page, scroller]

        # --- device -----------------------------------------------------
        card = self._card(page, "device")
        row = tk.Frame(card.body, bg=self.p.surface)
        row.pack(fill="x")
        self._reg(row, bg="surface")

        # Pack the fixed-width buttons first: a dropdown packed with expand=True
        # ahead of them would swallow the row and clip their labels.
        self.connect_btn = W.HudButton(row, "connect", self.toggle_connection,
                                       self.p, variant="primary", height=34,
                                       fits=["disconnect", "cancel"])
        self.connect_btn.configure(bg=self.p.surface)
        self.connect_btn.pack(side="right")
        self.themed.append(self.connect_btn)

        refresh = W.HudButton(row, "refresh", lambda: self.refresh_ports(),
                              self.p, height=34)
        refresh.configure(bg=self.p.surface)
        refresh.pack(side="right", padx=(8, 8))
        self.themed.append(refresh)

        self.port_select = W.HudSelect(row, self.p, width=120)
        self.port_select.configure(bg=self.p.surface)
        self.port_select.pack(side="left", fill="x", expand=True)
        self.themed.append(self.port_select)

        self.hid_label = tk.Label(card.body, justify="left", anchor="w",
                                  font=W.ui(8), bg=self.p.surface,
                                  fg=self.p.text_dim)
        self.hid_label.pack(anchor="w", fill="x", pady=(10, 0))
        self._reg(self.hid_label, bg="surface")
        self.hid = None
        self._set_hid_label()
        card.fit()
        self.device_card = card

        # --- which pedals exist ----------------------------------------
        card = self._card(page, "pedals connected")
        hint = tk.Label(
            card.body,
            text="Turn off any pedal you haven't wired up. An unused input "
                 "picks up\nthe signal from its neighbour, which looks like a "
                 "stuck pedal.",
            justify="left", font=W.ui(8), bg=self.p.surface,
            fg=self.p.text_dim)
        hint.pack(anchor="w", pady=(0, 10))
        self._reg(hint, bg="surface", fg="text_dim")

        self.axis_toggles = []
        for i, name in enumerate(P.AXIS_NAMES):
            toggle = W.Toggle(card.body, name, self.cfg.axes[i],
                              lambda value, i=i: self._set_axis_enabled(i, value),
                              self.p)
            toggle.pack(anchor="w", pady=2)
            self.axis_toggles.append(toggle)
            self.themed.append(toggle)
        card.fit()
        self.pedals_card = card

        # --- appearance -------------------------------------------------
        card = self._card(page, "interface")
        row = tk.Frame(card.body, bg=self.p.surface)
        row.pack(fill="x", pady=(0, 12))
        self._reg(row, bg="surface")
        self.dark_btn = W.HudButton(row, "dark", lambda: self._set_base("dark"),
                                    self.p, height=28, pad=12)
        self.dark_btn.configure(bg=self.p.surface)
        self.dark_btn.pack(side="left")
        self.themed.append(self.dark_btn)
        self.light_btn = W.HudButton(row, "light",
                                     lambda: self._set_base("light"), self.p,
                                     height=28, pad=12)
        self.light_btn.configure(bg=self.p.surface)
        self.light_btn.pack(side="left", padx=(6, 0))
        self.themed.append(self.light_btn)

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
        caption = tk.Label(custom, text=W.spaced("CUSTOM"), font=W.ui(8, "bold"),
                           bg=self.p.surface, fg=self.p.text_dim)
        caption.pack(side="left", padx=(0, 8))
        self._reg(caption, bg="surface", fg="text_dim")

        self.custom_var = tk.StringVar(value=self.p.accent_seed)
        entry = W.HudEntry(custom, self.custom_var, self.p, width=150)
        entry.entry.configure(font=W.mono(10), width=14)
        entry.configure(bg=self.p.surface)
        entry.pack(side="left")
        self.themed.append(entry)
        entry.entry.bind("<Return>", lambda _e: self._apply_custom_colour())

        use = W.HudButton(custom, "use", self._apply_custom_colour, self.p,
                          height=30, pad=12)
        use.configure(bg=self.p.surface)
        use.pack(side="left", padx=(8, 0))
        self.themed.append(use)

        self.custom_hint = tk.Label(
            card.body, text="hex (#22d3ee) or RGB (34, 211, 238)",
            font=W.ui(8), bg=self.p.surface, fg=self.p.text_dim)
        self.custom_hint.pack(anchor="w", pady=(6, 0))
        self._reg(self.custom_hint, bg="surface", fg="text_dim")

        self.on_top_toggle = W.Toggle(card.body, "always on top",
                                      self.cfg.on_top, self.set_on_top, self.p)
        self.on_top_toggle.pack(anchor="w", pady=(14, 0))
        self.themed.append(self.on_top_toggle)
        card.fit()
        self.appearance_card = card

        # --- background ---------------------------------------------------
        card = self._card(page, "background")
        self.tray_toggle = W.Toggle(card.body, "keep running in the tray",
                                    self.cfg.tray, self.set_tray, self.p)
        self.tray_toggle.pack(anchor="w")
        self.themed.append(self.tray_toggle)

        self.minimised_toggle = W.Toggle(
            card.body, "start minimised", self.cfg.start_minimised,
            self.set_start_minimised, self.p)
        self.minimised_toggle.pack(anchor="w", pady=(6, 0))
        self.themed.append(self.minimised_toggle)

        self.autostart_toggle = W.Toggle(
            card.body, "start with windows", self.cfg.start_with_windows,
            self.set_autostart, self.p)
        self.autostart_toggle.pack(anchor="w", pady=(6, 0))
        self.themed.append(self.autostart_toggle)

        note = "Once calibrated the board works on its own - none of this is\n"
        if not tray_module.available():
            note += ("needed to play. A tray icon isn't available here: "
                     f"{tray_module.unavailable_reason()[:44]}")
        elif not autostart.supported():
            note += "needed to play. Start-with-login is Windows only."
        else:
            note += "needed to play; it's here for convenience while tuning."
        self.background_note = tk.Label(card.body, text=note, justify="left",
                                        anchor="w", font=W.ui(8),
                                        bg=self.p.surface, fg=self.p.text_dim)
        self.background_note.pack(anchor="w", pady=(10, 0))
        self._reg(self.background_note, bg="surface", fg="text_dim")
        card.fit()

        # --- reset -------------------------------------------------------
        card = self._card(page, "reset")
        reset = W.HudButton(card.body, "reset everything", self.reset_everything,
                            self.p, variant="danger", height=34)
        reset.configure(bg=self.p.surface)
        reset.pack(anchor="w")
        self.themed.append(reset)
        card.fit()

        self._sync_appearance_buttons()

    # -- console ---------------------------------------------------------

    def _build_console(self) -> None:
        bar = tk.Frame(self, bg=self.p.bg)
        bar.pack(side="bottom", fill="x")
        self._reg(bar, bg="bg")

        self.status_label = tk.Label(bar, text="Not connected", anchor="w",
                                     font=W.ui(9), bg=self.p.bg,
                                     fg=self.p.text_dim)
        self.status_label.pack(fill="x", pady=(10, 6))
        self._reg(self.status_label, bg="bg", fg="text_dim")

        self.console_toggle = W.Disclosure(bar, "console",
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
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _set_hid_label(self) -> None:
        """Say plainly whether games will actually see the pedals."""
        if not hasattr(self, "hid_label"):
            return
        if self.hid is None:
            text, colour = "Game controller output: unknown until connected", \
                self.p.text_dim
        elif self.hid:
            text, colour = "Game controller output: ACTIVE", self.p.ok
        else:
            text, colour = (
                "Game controller output: NOT ACTIVE - this board can't act as\n"
                "one, or the Joystick library wasn't installed when you flashed\n"
                "it. Calibration still works. See the README.", self.p.offline)
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
            self._set_status("At least one pedal has to stay switched on")
            return
        self.cfg.axes = axes
        S.save(self.cfg)
        self._apply_axis_visibility()
        self._push_axis_enables()
        self._set_status(
            f"{P.AXIS_NAMES[index]} {'enabled' if value else 'disabled'}")

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
                self._set_status("A tray icon isn't available on this system")
                return
            self._set_status("Closing the window will now leave it running")
        else:
            self._stop_tray()
            self._set_status("Closing the window will now quit")

    def set_start_minimised(self, value: bool) -> None:
        self.cfg.start_minimised = value
        S.save(self.cfg)
        if value and not self.cfg.tray:
            self._set_status("Turn on \"keep running in the tray\" as well, "
                             "or there is nothing to minimise into")

    def set_autostart(self, value: bool) -> None:
        if not autostart.supported():
            self.autostart_toggle.set(False)
            self._set_status("Start-with-login is only wired up for Windows")
            return
        if not autostart.set_enabled(value):
            self.autostart_toggle.set(not value)
            self._set_status("Windows would not let us change the startup entry")
            return
        self.cfg.start_with_windows = value
        S.save(self.cfg)
        self._set_status("Will start with Windows" if value
                         else "No longer starts with Windows")

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

    def _set_base(self, name: str) -> None:
        self.cfg.theme = name
        self._apply_palette(T.palette_for(name, self.cfg.accent))

    def _set_accent(self, colour: str) -> None:
        self.cfg.accent = colour
        self.custom_var.set(colour)
        self._apply_palette(T.palette_for(self.cfg.theme, colour))

    def _apply_custom_colour(self) -> None:
        parsed = T.parse_colour(self.custom_var.get())
        if parsed is None:
            self.custom_hint.config(
                text="not a colour - try #22d3ee or 34, 211, 238",
                fg=self.p.danger)
            return
        self.custom_hint.config(text="hex (#22d3ee) or RGB (34, 211, 238)",
                                fg=self.p.text_dim)
        self._set_accent(parsed)

    def _apply_palette(self, palette: T.Palette) -> None:
        self.p = palette
        S.save(self.cfg)
        self.master.configure(bg=palette.bg)
        self.configure(bg=palette.bg)
        for widget, roles in self.plain:
            widget.configure(**{opt: getattr(palette, attr)
                                for opt, attr in roles.items()})
        for child in self.themed:
            if isinstance(child, (W.HudEntry, W.HudButton, W.Swatch, W.Toggle)):
                parent_bg = child.master.cget("bg")
                child.configure(bg=parent_bg)
            child.apply_theme(palette)
        self._paint_dot()
        self.live_label.config(fg=self._status_colour())
        self._set_hid_label()
        self._sync_appearance_buttons()

    def _sync_appearance_buttons(self) -> None:
        self.dark_btn.variant = "primary" if self.p.dark else "ghost"
        self.light_btn.variant = "ghost" if self.p.dark else "primary"
        self.dark_btn.redraw()
        self.light_btn.redraw()
        for swatch, (_name, colour) in zip(self.swatches, T.ACCENTS):
            swatch.set_selected(colour == self.p.accent_seed)

    def reset_everything(self) -> None:
        confirmed = self._dialog(
            messagebox.askyesno,
            "Reset everything?",
            "This will restore the defaults:\n\n"
            "  -  calibration back to 0% - 100% on every pedal\n"
            "  -  all three pedals switched back on\n"
            "  -  dark theme with the cyan accent\n"
            "  -  always-on-top back on, console hidden\n\n"
            "If a device is connected the reset is written to it as well.\n\n"
            "Continue?",
            icon="warning", default="no",
        )
        if not confirmed:
            return

        defaults = S.AppSettings.defaults()
        self.cfg = defaults
        for panel in self.panels:
            panel.set_limits(0, P.ADC_MAX)
            panel.set_linearity(0)
        for toggle, value in zip(self.axis_toggles, defaults.axes):
            toggle.set(value)
        self.on_top_toggle.set(defaults.on_top)
        self.custom_var.set(defaults.accent)
        self.console_toggle.open = defaults.console_open
        self.console_toggle.redraw()
        self._set_console_open(defaults.console_open, save=False)
        self.set_on_top(defaults.on_top)
        self._apply_axis_visibility()
        self._apply_palette(T.palette_for(defaults.theme, defaults.accent))
        S.save(self.cfg)

        if self.device is not None:
            self._push_axis_enables()
            self.apply_calibration()
            self.device.send(P.cmd_save())
        self._set_status("Everything reset to defaults")
        self.log("reset to defaults")

    # -- status ----------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.status_label.config(text=text)

    def _set_live(self, live: bool) -> None:
        self.live_label.config(text=W.spaced("LIVE" if live else "OFFLINE"),
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
        self.port_select.set_values([str(p) for p in self.ports], target)

    def _selected_port(self) -> str | None:
        idx = self.port_select.get()
        return self.ports[idx].device if 0 <= idx < len(self.ports) else None

    def toggle_connection(self) -> None:
        if self.device is not None or self._connecting:
            self.disconnect()
            return
        port = self._selected_port()
        if port is None:
            self._dialog(messagebox.showwarning, "No port",
                         "No serial port found. Plug the board in and press "
                         "Refresh.")
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
        self._set_connect_button("cancel", "ghost")
        self._set_status(f"Opening {port}...")
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
            self._set_connect_button("connect", "primary")
            self.log(f"failed to open {port}: {error}")
            write_log(f"connect failed: {port}: {error!r}")
            if quiet:
                self._set_status(f"{port} did not open - pick a port in Settings")
            else:
                self._set_status("Not connected")
                self._dialog(
                    messagebox.showerror, f"Could not open {port}",
                    f"{explain_port_error(error)}\n\nTechnical detail:\n{error}",
                )
            return

        self.device = outcome["device"]
        self.identified = False
        self._handshakes = 0
        if self.cfg.last_port != port:
            self.cfg.last_port = port      # reselected on the next launch
            S.save(self.cfg)
        self._set_connect_button("disconnect", "ghost")
        self._set_status(f"Connected to {port} - waiting for firmware...")
        self.log(f"opened {port}")
        self._handshake()

    def _handshake(self) -> None:
        """Ask 'who are you?' a few times - a board may still be booting."""
        if self.device is None or self.identified or not self._alive:
            return
        self._handshakes += 1
        if self._handshakes > 8:
            self._set_status("Connected, but no reply - is the firmware flashed?")
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
        self._set_connect_button("connect", "primary")
        self._set_status("Not connected")
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
                    messagebox.showerror, f"{panel.name} calibration",
                    f"Rest ({P.raw_to_pct(lo)}%) has to be below full "
                    f"({P.raw_to_pct(hi)}%).")
                return
            self.device.send(P.cmd_set(panel.index, lo, hi))
            self.device.send(P.cmd_curve(panel.index, panel.linearity))
        self._set_status("Calibration applied (not yet saved)")

    def save_calibration(self) -> None:
        if self.device is None:
            return
        self.apply_calibration()
        self.device.send(P.cmd_save())
        self._set_status("Saved to device")

    def reload_calibration(self) -> None:
        if self.device is not None:
            self.device.send(P.cmd_load())

    def toggle_learn(self, index: int) -> None:
        """Learn one pedal's travel without disturbing the others."""
        panel = self.panels[index]
        name = P.AXIS_NAMES[index]
        if index in self.learning:
            self.learning.discard(index)
            panel.set_learning(False)
            lo, hi = self._observed[index]
            if hi > lo:
                panel.set_limits(lo, hi)
                self.apply_calibration()
                self._set_status(f"{name}: learned {P.raw_to_pct(lo)}% - "
                                 f"{P.raw_to_pct(hi)}%")
            else:
                self._set_status(f"{name}: nothing moved, range unchanged")
            return

        self.learning.add(index)
        self._observed[index] = [P.ADC_MAX, 0]
        panel.set_learning(True)
        self._set_status(f"Learning {name} - press it fully, then press Stop")

    # -- response curve ---------------------------------------------------

    def _curve_preview(self, index: int, linearity: int) -> None:
        """Dragging the slider: remember it, but don't spam the serial link."""
        self.cfg.curves[index] = linearity

    def _curve_commit(self, index: int, linearity: int) -> None:
        self.cfg.curves[index] = linearity
        S.save(self.cfg)
        if self.device is not None:
            try:
                self.device.send(P.cmd_curve(index, linearity))
            except (ValueError, Exception) as exc:  # noqa: BLE001
                self.log(f"curve write failed: {exc}")
                return
        self._set_status(
            f"{P.AXIS_NAMES[index]} curve set to {linearity:+d}"
            if linearity else f"{P.AXIS_NAMES[index]} curve set to linear")

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
        self._schedule(POLL_MS, self._tick)

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
            controller = {True: "game controller active",
                          False: "no game controller output",
                          None: "controller state unknown"}[msg.hid]
            self._set_status(f"Connected - firmware v{msg.version}, {controller}")
            self.log(f"identified: {P.FIRMWARE_ID} v{msg.version} "
                     f"({'hid' if msg.hid else 'nohid'})")
            self._push_axis_enables()
        elif isinstance(msg, P.Calibration):
            for panel, (lo, hi) in zip(self.panels, msg.points):
                panel.set_limits(lo, hi)
            self.log(f"calibration from device: {msg.points}")
        elif isinstance(msg, P.Enabled):
            self.log(f"device axis state: {msg.axes}")
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
                "Sim Pedal Calibrator",
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
    root.geometry("620x800")
    try:
        root._icon = tk.PhotoImage(data=ICON_PNG_B64)  # keep a reference
        root.iconphoto(True, root._icon)
    except Exception:
        pass  # cosmetic only, never worth failing over
    CalibratorApp(root, initial_port=initial_port)
    root.mainloop()
