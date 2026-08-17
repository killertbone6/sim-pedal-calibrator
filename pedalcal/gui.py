"""The calibration window - a flat HUD drawn on canvases, not stock widgets."""

from __future__ import annotations

import datetime
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import messagebox

from . import protocol as P
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
    """One pedal: name, live readout, meter, and its two calibration fields."""

    def __init__(self, master, index: int, name: str, on_change,
                 palette: T.Palette) -> None:
        super().__init__(master, palette)
        self.index = index
        self.name = name
        self._on_change = on_change
        self.raw = 0
        self.min_var = tk.StringVar(value="0")
        self.max_var = tk.StringVar(value=str(P.ADC_MAX))
        self.themed: list[W.Themed] = []
        self.plain: list[tuple[tk.Widget, dict]] = []

        body = self.body
        body.columnconfigure(3, weight=1)

        self.title = tk.Label(body, text=W.spaced(name.upper()),
                              font=W.ui(9, "bold"), bg=palette.surface,
                              fg=palette.text_dim)
        self.title.grid(row=0, column=0, columnspan=2, sticky="w")
        self._reg(self.title, bg="surface", fg="text_dim")

        self.raw_label = tk.Label(body, text="0000", font=W.mono(17),
                                  bg=palette.surface, fg=palette.text)
        self.raw_label.grid(row=0, column=3, sticky="e", padx=(0, 14))
        self._reg(self.raw_label, bg="surface", fg="text")

        self.pct_label = tk.Label(body, text="0%", font=W.mono(17, "bold"),
                                  width=5, anchor="e", bg=palette.surface,
                                  fg=palette.accent)
        self.pct_label.grid(row=0, column=4, sticky="e")
        self._reg(self.pct_label, bg="surface", fg="accent")

        self.meter = W.Meter(body, palette)
        self.meter.grid(row=1, column=0, columnspan=5, sticky="ew",
                        pady=(10, 12))
        self.themed.append(self.meter)

        self._build_field(body, "MIN", self.min_var, column=0)
        self._build_field(body, "MAX", self.max_var, column=2, padx=(22, 0))

        for var in (self.min_var, self.max_var):
            var.trace_add("write", lambda *_: self.redraw_meter())

    def _reg(self, widget: tk.Widget, **roles: str) -> None:
        self.plain.append((widget, roles))

    def _build_field(self, body, label: str, var: tk.StringVar, column: int,
                     padx=(0, 0)) -> None:
        holder = tk.Frame(body, bg=self.p.surface)
        holder.grid(row=2, column=column, columnspan=2, sticky="w", padx=padx)
        self._reg(holder, bg="surface")

        caption = tk.Label(holder, text=W.spaced(label), font=W.ui(8, "bold"),
                           bg=self.p.surface, fg=self.p.text_dim)
        caption.pack(side="left", padx=(0, 8))
        self._reg(caption, bg="surface", fg="text_dim")

        entry = W.HudEntry(holder, var, self.p)
        entry.configure(bg=self.p.surface)
        entry.pack(side="left")
        self.themed.append(entry)

        button = W.HudButton(holder, "set", lambda: self._capture(var), self.p,
                             height=30, pad=12)
        button.configure(bg=self.p.surface)
        button.pack(side="left", padx=(6, 0))
        self.themed.append(button)

    # -- values ----------------------------------------------------------

    def limits(self) -> tuple[int, int]:
        """Whatever is in the entry boxes right now, falling back to defaults."""
        def as_int(var: tk.StringVar, fallback: int) -> int:
            try:
                return max(0, min(P.ADC_MAX, int(var.get())))
            except ValueError:
                return fallback

        return as_int(self.min_var, 0), as_int(self.max_var, P.ADC_MAX)

    def set_limits(self, lo: int, hi: int) -> None:
        self.min_var.set(str(lo))
        self.max_var.set(str(hi))

    def _capture(self, var: tk.StringVar) -> None:
        var.set(str(self.raw))
        self._on_change()

    def update_raw(self, raw: int) -> None:
        self.raw = raw
        lo, hi = self.limits()
        pct = P.scale(raw, lo, hi)
        self.raw_label.config(text=f"{raw:04d}")
        self.pct_label.config(text=f"{pct * 100:.0f}%")
        self.meter.set_values(raw, lo, hi)

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
            if isinstance(child, (W.HudEntry, W.HudButton)):
                child.configure(bg=palette.surface)
            child.apply_theme(palette)


class CalibratorApp(tk.Frame):
    def __init__(self, master: tk.Tk, initial_port: str | None = None) -> None:
        self.p = T.load_palette()
        super().__init__(master, bg=self.p.bg, padx=PAD, pady=PAD)
        W.init_fonts()
        self.master.title("Sim Pedal Calibrator")
        self.master.minsize(560, 720)
        self.master.configure(bg=self.p.bg)
        self.pack(fill="both", expand=True)

        self.device: PedalDevice | None = None
        self.ports: list[PortInfo] = []
        self.learning = False
        self.identified = False
        self._connecting = False
        self._handshakes = 0
        self._alive = True
        self._pending: set[str] = set()
        self._observed: list[list[int]] = [[P.ADC_MAX, 0] for _ in P.AXIS_NAMES]
        self.themed: list[W.Themed] = []
        self.plain: list[tuple[tk.Widget, dict]] = []

        self._build_header()
        self._build_settings()
        self._build_connection()
        self.panels = [
            AxisPanel(self, i, name, self.apply_calibration, self.p)
            for i, name in enumerate(P.AXIS_NAMES)
        ]
        for panel in self.panels:
            panel.pack(fill="x", pady=(0, 10))
            panel.fit()
            self.themed.append(panel)
        self._build_actions()
        self._build_log()

        self.refresh_ports(select=initial_port)
        if initial_port is not None:
            self._schedule(200, self.toggle_connection)
        self._schedule(POLL_MS, self._tick)
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- small helpers ---------------------------------------------------

    def _reg(self, widget: tk.Widget, **roles: str) -> None:
        self.plain.append((widget, roles))

    def _row(self, **pack_kw) -> tk.Frame:
        frame = tk.Frame(self, bg=self.p.bg)
        frame.pack(fill="x", **pack_kw)
        self._reg(frame, bg="bg")
        return frame

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

    # -- layout ----------------------------------------------------------

    def _build_header(self) -> None:
        row = self._row(pady=(0, 12))

        mark = tk.Label(row, text="◆", font=W.ui(11), bg=self.p.bg,
                        fg=self.p.accent)
        mark.pack(side="left", padx=(0, 8))
        self._reg(mark, bg="bg", fg="accent")

        title = tk.Label(row, text=W.spaced("PEDAL CALIBRATOR"),
                         font=W.ui(10, "bold"), bg=self.p.bg, fg=self.p.text)
        title.pack(side="left")
        self._reg(title, bg="bg", fg="text")

        self.theme_btn = W.HudButton(row, "theme", self._toggle_settings,
                                     self.p, height=28, pad=12)
        self.theme_btn.pack(side="right")
        self.themed.append(self.theme_btn)

        self.live_dot = tk.Canvas(row, width=10, height=10, bg=self.p.bg,
                                  highlightthickness=0, bd=0)
        self.live_dot.pack(side="right", padx=(0, 8))
        self._reg(self.live_dot, bg="bg")

        self.live_label = tk.Label(row, text=W.spaced("OFFLINE"),
                                   font=W.ui(8, "bold"), bg=self.p.bg,
                                   fg=self.p.text_dim)
        self.live_label.pack(side="right", padx=(0, 8))
        self._reg(self.live_label, bg="bg", fg="text_dim")
        self._paint_dot()

    def _paint_dot(self) -> None:
        self.live_dot.delete("all")
        self.live_dot.configure(bg=self.p.bg)
        colour = self.p.accent if self.identified else self.p.border
        self.live_dot.create_oval(1, 1, 9, 9, fill=colour, width=0)

    def _build_settings(self) -> None:
        self.settings = W.Card(self, self.p, padding=12)
        self.settings_visible = False
        body = self.settings.body

        caption = tk.Label(body, text=W.spaced("THEME"), font=W.ui(8, "bold"),
                           bg=self.p.surface, fg=self.p.text_dim)
        caption.pack(side="left", padx=(0, 10))
        self.settings.plain = [(caption, {"bg": "surface", "fg": "text_dim"})]

        self.dark_btn = W.HudButton(body, "dark", lambda: self._set_base("dark"),
                                    self.p, height=28, pad=12)
        self.dark_btn.configure(bg=self.p.surface)
        self.dark_btn.pack(side="left")
        self.light_btn = W.HudButton(body, "light",
                                     lambda: self._set_base("light"), self.p,
                                     height=28, pad=12)
        self.light_btn.configure(bg=self.p.surface)
        self.light_btn.pack(side="left", padx=(6, 16))

        self.swatches = []
        for _name, colour in T.ACCENTS:
            swatch = W.Swatch(body, colour, self._set_accent, self.p)
            swatch.configure(bg=self.p.surface)
            swatch.pack(side="left", padx=2)
            self.swatches.append(swatch)

        self.settings.themed = [self.dark_btn, self.light_btn, *self.swatches]
        self.themed.append(self.settings)
        self._sync_settings()

    def _build_connection(self) -> None:
        row = self._row(pady=(0, 14))
        self.port_select = W.HudSelect(row, self.p)
        self.port_select.pack(side="left", fill="x", expand=True)
        self.themed.append(self.port_select)

        self.connect_btn = W.HudButton(row, "connect", self.toggle_connection,
                                       self.p, variant="primary", height=34,
                                       fits=["disconnect", "cancel"])
        self.connect_btn.pack(side="right", padx=(8, 0))
        self.themed.append(self.connect_btn)

        refresh = W.HudButton(row, "refresh", lambda: self.refresh_ports(),
                              self.p, height=34)
        refresh.pack(side="right", padx=(8, 0))
        self.themed.append(refresh)

    def _build_actions(self) -> None:
        row = self._row(pady=(2, 12))
        self.learn_btn = W.HudButton(row, "learn range", self.toggle_learn,
                                     self.p, height=34)
        self.learn_btn.pack(side="left")
        self.themed.append(self.learn_btn)

        for label, command in (("apply", self.apply_calibration),
                               ("save", self.save_calibration),
                               ("reload", self.reload_calibration)):
            button = W.HudButton(row, label, command, self.p, height=34)
            button.pack(side="left", padx=(8, 0))
            self.themed.append(button)

    def _build_log(self) -> None:
        self.status_label = tk.Label(self, text="Not connected", anchor="w",
                                     font=W.ui(9), bg=self.p.bg,
                                     fg=self.p.text_dim)
        self.status_label.pack(fill="x", pady=(0, 8))
        self._reg(self.status_label, bg="bg", fg="text_dim")

        card = W.Card(self, self.p, padding=10, autosize=False)
        card.pack(fill="both", expand=True)
        self.log_box = tk.Text(card.body, height=4, wrap="none", bd=0,
                               highlightthickness=0, state="disabled",
                               font=W.mono(8), bg=self.p.surface,
                               fg=self.p.text_dim)
        self.log_box.pack(fill="both", expand=True)
        card.plain = [(self.log_box, {"bg": "surface", "fg": "text_dim"})]
        card.fit()
        self.themed.append(card)
        self.log_card = card

    # -- theming ---------------------------------------------------------

    def _toggle_settings(self) -> None:
        self.settings_visible = not self.settings_visible
        if self.settings_visible:
            self.settings.pack(fill="x", pady=(0, 12),
                               before=self.children_order())
            self.settings.fit()
        else:
            self.settings.pack_forget()

    def children_order(self):
        """The connection row - settings slots in just above it."""
        return self.port_select.master

    def _set_base(self, name: str) -> None:
        self._apply_palette(T.PALETTES[name].with_accent(self.p.accent_seed))

    def _set_accent(self, colour: str) -> None:
        self._apply_palette(self.p.with_accent(colour))

    def _apply_palette(self, palette: T.Palette) -> None:
        self.p = palette
        T.save_palette(palette)
        self.master.configure(bg=palette.bg)
        self.configure(bg=palette.bg)
        for widget, roles in self.plain:
            widget.configure(**{opt: getattr(palette, attr)
                                for opt, attr in roles.items()})
        for child in self.themed:
            child.apply_theme(palette)
        for card in (self.settings, self.log_card):
            for widget, roles in getattr(card, "plain", []):
                widget.configure(**{opt: getattr(palette, attr)
                                    for opt, attr in roles.items()})
            for child in getattr(card, "themed", []):
                child.configure(bg=palette.surface)
                child.apply_theme(palette)
        self._paint_dot()
        self._sync_settings()

    def _sync_settings(self) -> None:
        self.dark_btn.variant = "primary" if self.p.dark else "ghost"
        self.light_btn.variant = "ghost" if self.p.dark else "primary"
        self.dark_btn.redraw()
        self.light_btn.redraw()
        for swatch, (_name, colour) in zip(self.swatches, T.ACCENTS):
            swatch.set_selected(colour == self.p.accent_seed)

    # -- status ----------------------------------------------------------

    def _set_connect_button(self, text: str, variant: str) -> None:
        self.connect_btn.variant = variant
        self.connect_btn.set_text(text)

    def _set_status(self, text: str) -> None:
        self.status_label.config(text=text)

    def _set_live(self, live: bool) -> None:
        self.live_label.config(text=W.spaced("LIVE" if live else "OFFLINE"))
        self.live_label.config(fg=self.p.accent if live else self.p.text_dim)
        self._paint_dot()

    def log(self, text: str) -> None:
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

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
            messagebox.showwarning("No port", "No serial port selected.")
            return

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
        self._schedule(100, lambda: self._finish_connect(outcome, port))

    def _finish_connect(self, outcome: dict, port: str) -> None:
        if not self._alive or not self._connecting:
            dev = outcome.get("device")
            if dev is not None:
                dev.close()
            return
        if not outcome:
            self._schedule(100, lambda: self._finish_connect(outcome, port))
            return

        self._connecting = False
        error = outcome.get("error")
        if error is not None:
            self._set_connect_button("connect", "primary")
            self._set_status("Not connected")
            self.log(f"failed to open {port}: {error}")
            write_log(f"connect failed: {port}: {error!r}")
            messagebox.showerror(
                f"Could not open {port}",
                f"{explain_port_error(error)}\n\nTechnical detail:\n{error}",
            )
            return

        self.device = outcome["device"]
        self.identified = False
        self._handshakes = 0
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
        self._set_connect_button("connect", "primary")
        self._set_status("Not connected")
        self._set_live(False)
        self.log("disconnected")

    # -- commands --------------------------------------------------------

    def apply_calibration(self) -> None:
        if self.device is None:
            return
        for panel in self.panels:
            lo, hi = panel.limits()
            try:
                self.device.send(P.cmd_set(panel.index, lo, hi))
            except ValueError as exc:
                messagebox.showerror(f"{P.AXIS_NAMES[panel.index]} calibration",
                                     str(exc))
                return
        self._set_status("Calibration applied (not yet saved)")

    def save_calibration(self) -> None:
        if self.device is None:
            return
        self.apply_calibration()
        self.device.send(P.cmd_save())
        self._set_status("Saved to device EEPROM")

    def reload_calibration(self) -> None:
        if self.device is not None:
            self.device.send(P.cmd_load())

    def toggle_learn(self) -> None:
        self.learning = not self.learning
        if self.learning:
            self._observed = [[P.ADC_MAX, 0] for _ in P.AXIS_NAMES]
            self.learn_btn.set_text("stop learning")
            self.learn_btn.variant = "primary"
            self.learn_btn.redraw()
            self._set_status("Learning - press every pedal fully, then stop")
        else:
            self.learn_btn.set_text("learn range")
            self.learn_btn.variant = "ghost"
            self.learn_btn.redraw()
            for panel, (lo, hi) in zip(self.panels, self._observed):
                if hi > lo:
                    panel.set_limits(lo, hi)
            self.apply_calibration()
            self._set_status("Learned range applied")

    # -- event loop ------------------------------------------------------

    def _tick(self) -> None:
        if not self._alive:
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
                panel.update_raw(raw)
                if self.learning:
                    seen = self._observed[panel.index]
                    seen[0] = min(seen[0], raw)
                    seen[1] = max(seen[1], raw)
                    panel.set_limits(seen[0], seen[1])
        elif isinstance(msg, P.Ident):
            self.identified = True
            self._set_live(True)
            self._set_status(f"Connected - pedal firmware v{msg.version}")
            self.log(f"identified: {P.FIRMWARE_ID} v{msg.version}")
        elif isinstance(msg, P.Calibration):
            for panel, (lo, hi) in zip(self.panels, msg.points):
                panel.set_limits(lo, hi)
            self.log(f"calibration from device: {msg.points}")
        elif isinstance(msg, P.Ack):
            if not msg.ok:
                self.log(f"device error: {msg.detail}")
        elif isinstance(msg, P.Unknown) and msg.text:
            self.log(msg.text)

    def _on_close(self) -> None:
        self._alive = False
        self._cancel_pending()
        self.disconnect()
        self.master.destroy()


def _install_crash_handler(root: tk.Tk) -> None:
    """A packaged .exe has no console, so an unhandled error would otherwise
    make the window vanish with no explanation. Show it and write it down."""

    def report(exc_type, exc, tb) -> None:
        write_log("UNHANDLED ERROR\n"
                  + "".join(traceback.format_exception(exc_type, exc, tb)))
        try:
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
    root.geometry("620x860")
    try:
        root._icon = tk.PhotoImage(data=ICON_PNG_B64)  # keep a reference
        root.iconphoto(True, root._icon)
    except Exception:
        pass  # cosmetic only, never worth failing over
    CalibratorApp(root, initial_port=initial_port)
    root.mainloop()
