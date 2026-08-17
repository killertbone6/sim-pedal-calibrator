"""The Tkinter calibration window."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import protocol as P
from .device import PedalDevice, PortInfo, list_serial_ports

POLL_MS = 25  # how often the UI drains the serial queue

BAR_HEIGHT = 26
COL_TRACK = "#2b2f36"
COL_RANGE = "#3b6ea5"
COL_NEEDLE = "#f5f5f5"


class AxisPanel(ttk.LabelFrame):
    """One pedal: live bar, calibration entries, capture buttons."""

    def __init__(self, master, index: int, name: str, on_change) -> None:
        super().__init__(master, text=name, padding=(10, 6, 10, 10))
        self.index = index
        self._on_change = on_change
        self.raw = 0
        self.min_var = tk.StringVar(value="0")
        self.max_var = tk.StringVar(value=str(P.ADC_MAX))

        self.raw_label = ttk.Label(self, text="raw 0")
        self.raw_label.grid(row=0, column=0, columnspan=3, sticky="w")
        self.range_label = ttk.Label(self, text="", anchor="e")
        self.range_label.grid(row=0, column=3, columnspan=3, sticky="e")

        self.canvas = tk.Canvas(
            self, height=BAR_HEIGHT, bg=COL_TRACK,
            highlightthickness=0, bd=0,
        )
        self.canvas.grid(row=1, column=0, columnspan=6, sticky="ew", pady=(2, 6))
        self._range_id = self.canvas.create_rectangle(
            0, 0, 0, BAR_HEIGHT, fill=COL_RANGE, width=0
        )
        self._needle_id = self.canvas.create_rectangle(
            0, 0, 0, BAR_HEIGHT, fill=COL_NEEDLE, width=0
        )
        self.canvas.bind("<Configure>", lambda _e: self.redraw())

        self.output = ttk.Progressbar(self, maximum=1000)
        self.output.grid(row=2, column=0, columnspan=5, sticky="ew")
        self.pct_label = ttk.Label(self, text="0%", width=6, anchor="e")
        self.pct_label.grid(row=2, column=5, sticky="e", padx=(6, 0))

        ttk.Label(self, text="Min").grid(row=3, column=0, sticky="w", pady=(8, 0))
        min_entry = ttk.Entry(self, textvariable=self.min_var, width=7)
        min_entry.grid(row=3, column=1, sticky="w", pady=(8, 0))
        ttk.Button(
            self, text="Use current", width=12,
            command=lambda: self._capture(self.min_var),
        ).grid(row=3, column=2, sticky="w", padx=(4, 16), pady=(8, 0))

        ttk.Label(self, text="Max").grid(row=3, column=3, sticky="w", pady=(8, 0))
        max_entry = ttk.Entry(self, textvariable=self.max_var, width=7)
        max_entry.grid(row=3, column=4, sticky="w", pady=(8, 0))
        ttk.Button(
            self, text="Use current", width=12,
            command=lambda: self._capture(self.max_var),
        ).grid(row=3, column=5, sticky="w", padx=(4, 0), pady=(8, 0))

        self.columnconfigure(4, weight=1)
        for var in (self.min_var, self.max_var):
            var.trace_add("write", lambda *_: self.redraw())

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
        self.output["value"] = pct * 1000
        self.pct_label.config(text=f"{pct * 100:.0f}%")
        self.redraw()

    # -- drawing ---------------------------------------------------------

    def redraw(self) -> None:
        width = self.canvas.winfo_width()
        if width <= 1:
            return
        lo, hi = self.limits()

        def x_of(raw: int) -> float:
            return width * (raw / P.ADC_MAX)

        self.canvas.coords(self._range_id, x_of(lo), 0, x_of(hi), BAR_HEIGHT)
        nx = x_of(self.raw)
        self.canvas.coords(self._needle_id, nx - 1.5, 0, nx + 1.5, BAR_HEIGHT)
        self.raw_label.config(text=f"raw {self.raw}")
        self.range_label.config(text=f"calibrated range  {lo} - {hi}")


class CalibratorApp(ttk.Frame):
    def __init__(self, master: tk.Tk, initial_port: str | None = None) -> None:
        super().__init__(master, padding=12)
        self.master.title("Sim Pedal Calibrator")
        self.master.minsize(560, 620)
        self.pack(fill="both", expand=True)

        self.device: PedalDevice | None = None
        self.ports: list[PortInfo] = []
        self.learning = False
        self._observed: list[list[int]] = [[P.ADC_MAX, 0] for _ in P.AXIS_NAMES]

        self._build_connection_row()
        self.panels = [
            AxisPanel(self, i, name, self.apply_calibration)
            for i, name in enumerate(P.AXIS_NAMES)
        ]
        for panel in self.panels:
            panel.pack(fill="x", pady=(0, 10))
        self._build_actions()
        self._build_log()

        self.refresh_ports(select=initial_port)
        if initial_port is not None:
            # --port / --simulate means "just start", so don't make the user
            # click Connect as well.
            self.after(200, self.toggle_connection)
        self.after(POLL_MS, self._tick)
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- layout ----------------------------------------------------------

    def _build_connection_row(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(0, 12))
        ttk.Label(row, text="Port").pack(side="left")
        self.port_box = ttk.Combobox(row, state="readonly", width=34)
        self.port_box.pack(side="left", padx=6)
        ttk.Button(row, text="Refresh", width=9,
                   command=lambda: self.refresh_ports()).pack(side="left")
        self.connect_btn = ttk.Button(row, text="Connect", width=11,
                                      command=self.toggle_connection)
        self.connect_btn.pack(side="left", padx=6)

    def _build_actions(self) -> None:
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(2, 10))
        self.learn_btn = ttk.Button(row, text="Learn range",
                                    command=self.toggle_learn)
        self.learn_btn.pack(side="left")
        ttk.Button(row, text="Apply", command=self.apply_calibration).pack(
            side="left", padx=6)
        ttk.Button(row, text="Save to device", command=self.save_calibration).pack(
            side="left")
        ttk.Button(row, text="Reload", command=self.reload_calibration).pack(
            side="left", padx=6)

    def _build_log(self) -> None:
        self.status = ttk.Label(self, text="Not connected", anchor="w")
        self.status.pack(fill="x")
        self.log_box = tk.Text(self, height=5, wrap="none", state="disabled",
                               font=("TkFixedFont", 8))
        self.log_box.pack(fill="both", expand=True, pady=(6, 0))

    def log(self, text: str) -> None:
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    # -- connection ------------------------------------------------------

    def refresh_ports(self, select: str | None = None) -> None:
        self.ports = list_serial_ports()
        self.port_box["values"] = [str(p) for p in self.ports]
        target = 0
        if select is not None:
            for i, p in enumerate(self.ports):
                if p.device == select:
                    target = i
                    break
        if self.ports:
            self.port_box.current(target)

    def _selected_port(self) -> str | None:
        idx = self.port_box.current()
        return self.ports[idx].device if 0 <= idx < len(self.ports) else None

    def toggle_connection(self) -> None:
        if self.device is not None:
            self.disconnect()
            return
        port = self._selected_port()
        if port is None:
            messagebox.showwarning("No port", "No serial port selected.")
            return
        try:
            self.device = PedalDevice(port)
            self.device.open()
        except Exception as exc:
            self.device = None
            messagebox.showerror("Could not open port", str(exc))
            return
        self.connect_btn.config(text="Disconnect")
        self.status.config(text=f"Connected to {port} - identifying...")
        self.log(f"opened {port}")
        self.device.send(P.cmd_ident())
        self.device.send(P.cmd_get())

    def disconnect(self) -> None:
        if self.device is not None:
            self.device.close()
            self.device = None
        self.connect_btn.config(text="Connect")
        self.status.config(text="Not connected")
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
        self.status.config(text="Calibration applied (not yet saved)")

    def save_calibration(self) -> None:
        if self.device is None:
            return
        self.apply_calibration()
        self.device.send(P.cmd_save())
        self.status.config(text="Saved to device EEPROM")

    def reload_calibration(self) -> None:
        if self.device is not None:
            self.device.send(P.cmd_load())

    def toggle_learn(self) -> None:
        self.learning = not self.learning
        if self.learning:
            self._observed = [[P.ADC_MAX, 0] for _ in P.AXIS_NAMES]
            self.learn_btn.config(text="Stop learning")
            self.status.config(
                text="Learning - press every pedal fully, then stop")
        else:
            self.learn_btn.config(text="Learn range")
            for panel, (lo, hi) in zip(self.panels, self._observed):
                if hi > lo:
                    panel.set_limits(lo, hi)
            self.apply_calibration()
            self.status.config(text="Learned range applied")

    # -- event loop ------------------------------------------------------

    def _tick(self) -> None:
        if self.device is not None:
            for msg in self.device.poll():
                self._handle(msg)
        self.after(POLL_MS, self._tick)

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
            self.status.config(
                text=f"Connected - pedal firmware v{msg.version}")
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
        self.disconnect()
        self.master.destroy()


def _icon_path() -> Path:
    """Where icon.png lives, both when run from source and inside a
    PyInstaller one-file build (which unpacks to sys._MEIPASS)."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "pedalcal" / "icon.png"
    return Path(__file__).resolve().parent / "icon.png"


def run(initial_port: str | None = None) -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    try:
        root._icon = tk.PhotoImage(file=str(_icon_path()))  # keep a reference
        root.iconphoto(True, root._icon)
    except Exception:
        pass  # cosmetic only, never worth failing over
    CalibratorApp(root, initial_port=initial_port)
    root.mainloop()
