"""Hand-drawn widgets for the HUD look.

Tk's stock widgets carry a lot of 1990s chrome - bevels, grey gradients,
square corners - and ttk themes only sand that down so far. Everything visual
here is therefore drawn on a Canvas, which costs a bit of code but means the
app looks identical on Windows, macOS and Linux and can be re-themed live.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from .theme import Palette, mix

UI_FAMILIES = ["Segoe UI", "Inter", "Roboto", "DejaVu Sans", "Helvetica", "Arial"]
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "JetBrains Mono", "Menlo",
                 "DejaVu Sans Mono", "Courier New"]

_families: set[str] = set()


def init_fonts() -> None:
    """Cache the installed font list. Call once, after Tk exists."""
    global _families
    _families = set(tkfont.families())


def _pick(candidates: list[str]) -> str:
    for name in candidates:
        if name in _families:
            return name
    return tkfont.nametofont("TkDefaultFont").cget("family")


def ui(size: int, weight: str = "normal") -> tuple:
    return (_pick(UI_FAMILIES), size, weight)


def mono(size: int, weight: str = "normal") -> tuple:
    return (_pick(MONO_FAMILIES), size, weight)


def spaced(text: str, gap: str = " ") -> str:
    """'THROTTLE' -> 'T H R O T T L E'. Tk can't do letter-spacing, and the
    wide tracking is most of what makes a label read as instrumentation."""
    return gap.join(text)


def round_rect(canvas: tk.Canvas, x0, y0, x1, y1, r, **kw):
    """A rounded rectangle, drawn as a smoothed polygon.

    The points along each straight edge are deliberately duplicated. Tk fits a
    spline through the vertex list, so a single point per edge lets the curve
    bow slightly and leaves bright nicks where it drifts off the border;
    doubling them pins the spline flat and only the corners stay curved.
    """
    r = max(0, min(r, abs(x1 - x0) / 2, abs(y1 - y0) / 2))
    points = [
        x0 + r, y0, x0 + r, y0,
        x1 - r, y0, x1 - r, y0,
        x1, y0,
        x1, y0 + r, x1, y0 + r,
        x1, y1 - r, x1, y1 - r,
        x1, y1,
        x1 - r, y1, x1 - r, y1,
        x0 + r, y1, x0 + r, y1,
        x0, y1,
        x0, y1 - r, x0, y1 - r,
        x0, y0 + r, x0, y0 + r,
        x0, y0,
    ]
    return canvas.create_polygon(points, smooth=True, **kw)


class Themed:
    """Anything that can be recoloured without being rebuilt."""

    def apply_theme(self, palette: Palette) -> None:  # pragma: no cover
        raise NotImplementedError


class HudButton(tk.Canvas, Themed):
    """A flat, rounded, uppercase button with hover and press states."""

    def __init__(self, master, text: str, command, palette: Palette,
                 variant: str = "ghost", width: int | None = None,
                 height: int = 32, radius: int = 9, pad: int = 18,
                 fits: list[str] | None = None) -> None:
        self.p = palette
        self.variant = variant
        self.text = text.upper()
        self.command = command
        self._hover = False
        self._down = False
        self._enabled = True
        self._font = ui(9, "bold")

        # `fits` reserves room for every label this button will ever show, so
        # swapping CONNECT for DISCONNECT doesn't clip the text or shove the
        # rest of the row sideways.
        font = tkfont.Font(font=self._font)
        labels = [self.text] + [t.upper() for t in (fits or [])]
        measure = max(font.measure(spaced(t)) for t in labels)
        w = width if width is not None else measure + pad * 2
        super().__init__(master, width=w, height=height,
                         highlightthickness=0, bd=0, bg=palette.bg)
        self.radius = radius
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.redraw()

    # -- state ----------------------------------------------------------

    def set_text(self, text: str) -> None:
        self.text = text.upper()
        self.redraw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="" if enabled else "")
        self.redraw()

    def _on_enter(self, _e=None):
        self._hover = True
        self.configure(cursor="hand2" if self._enabled else "")
        self.redraw()

    def _on_leave(self, _e=None):
        self._hover = self._down = False
        self.redraw()

    def _on_press(self, _e=None):
        if self._enabled:
            self._down = True
            self.redraw()

    def _on_release(self, _e=None):
        was_down = self._down
        self._down = False
        self.redraw()
        if was_down and self._enabled and self.command is not None:
            self.command()

    # -- painting -------------------------------------------------------

    def _colours(self) -> tuple[str, str, str]:
        p = self.p
        if not self._enabled:
            return mix(p.surface_alt, p.bg, 0.5), p.text_dim, p.border

        if self.variant == "primary":
            fill = p.accent
            if self._down:
                fill = mix(p.accent, "#000000", 0.22)
            elif self._hover:
                fill = mix(p.accent, "#ffffff", 0.18)
            return fill, p.on_accent, fill

        if self.variant == "danger":
            fill = mix(p.surface_alt, p.danger, 0.30 if self._hover else 0.16)
            return fill, p.danger, mix(p.border, p.danger, 0.4)

        fill = p.surface_alt
        edge = p.border
        fg = p.text
        if self._down:
            fill = mix(p.surface_alt, p.accent, 0.30)
            fg = p.accent
            edge = p.accent
        elif self._hover:
            fill = mix(p.surface_alt, p.accent, 0.16)
            fg = p.accent
            edge = mix(p.border, p.accent, 0.6)
        return fill, fg, edge

    def redraw(self) -> None:
        self.delete("all")
        self.configure(bg=self.p.bg)
        w = int(self["width"])
        h = int(self["height"])
        fill, fg, edge = self._colours()
        round_rect(self, 1, 1, w - 1, h - 1, self.radius, fill=fill,
                   outline=edge, width=1)
        self.create_text(w / 2, h / 2 + 1, text=spaced(self.text), fill=fg,
                         font=self._font)

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw()


class Swatch(tk.Canvas, Themed):
    """A round accent-colour chip; shows a ring when it's the active one."""

    SIZE = 22

    def __init__(self, master, colour: str, command, palette: Palette) -> None:
        super().__init__(master, width=self.SIZE, height=self.SIZE,
                         highlightthickness=0, bd=0, bg=palette.bg)
        self.p = palette
        self.colour = colour
        self.command = command
        self.selected = False
        self.bind("<Button-1>", lambda _e: command(colour))
        self.configure(cursor="hand2")
        self.redraw()

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        self.configure(bg=self.p.bg)
        s = self.SIZE
        if self.selected:
            self.create_oval(1, 1, s - 1, s - 1, outline=self.colour, width=2)
            self.create_oval(6, 6, s - 6, s - 6, fill=self.colour, width=0)
        else:
            self.create_oval(4, 4, s - 4, s - 4, fill=self.colour, width=0)

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw()


class HudEntry(tk.Canvas, Themed):
    """A numeric field on a rounded inset, with an accent focus ring."""

    def __init__(self, master, textvariable: tk.StringVar, palette: Palette,
                 width: int = 74, height: int = 30) -> None:
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, bg=palette.bg)
        self.p = palette
        self._focus = False
        self.entry = tk.Entry(
            self, textvariable=textvariable, bd=0, highlightthickness=0,
            justify="center", font=mono(11), width=5,
            bg=palette.surface_alt, fg=palette.text,
            insertbackground=palette.accent, disabledbackground=palette.surface_alt,
        )
        self._win = self.create_window(width / 2, height / 2, window=self.entry)
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self.redraw()

    def _focus_in(self, _e=None):
        self._focus = True
        self.redraw()

    def _focus_out(self, _e=None):
        self._focus = False
        self.redraw()

    def redraw(self) -> None:
        self.delete("bg")
        self.configure(bg=self.p.bg)
        w, h = int(self["width"]), int(self["height"])
        edge = self.p.accent if self._focus else self.p.border
        round_rect(self, 1, 1, w - 1, h - 1, 8, fill=self.p.surface_alt,
                   outline=edge, width=1, tags="bg")
        self.tag_lower("bg")
        self.entry.configure(bg=self.p.surface_alt, fg=self.p.text,
                             insertbackground=self.p.accent)

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw()


class HudSelect(tk.Canvas, Themed):
    """A dropdown: rounded field plus a native popup menu, themed to match."""

    def __init__(self, master, palette: Palette, width: int = 300,
                 height: int = 34, on_change=None) -> None:
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, bg=palette.bg)
        self.p = palette
        self.values: list[str] = []
        self.index = -1
        self.on_change = on_change
        self._hover = False
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<Button-1>", self._popup)
        self.bind("<Configure>", lambda _e: self.redraw())
        self.configure(cursor="hand2")
        self.redraw()

    def _set_hover(self, hover: bool) -> None:
        self._hover = hover
        self.redraw()

    def set_values(self, values: list[str], index: int = 0) -> None:
        self.values = values
        self.index = index if values else -1
        self.redraw()

    def get(self) -> int:
        return self.index

    def _popup(self, event) -> None:
        if not self.values:
            return
        menu = tk.Menu(
            self, tearoff=0, bd=0, relief="flat",
            bg=self.p.surface, fg=self.p.text,
            activebackground=self.p.accent, activeforeground=self.p.on_accent,
            activeborderwidth=0, font=ui(9),
        )
        for i, value in enumerate(self.values):
            menu.add_command(label=value, command=lambda i=i: self._choose(i))
        try:
            menu.tk_popup(self.winfo_rootx(),
                          self.winfo_rooty() + int(self["height"]))
        finally:
            menu.grab_release()

    def _choose(self, index: int) -> None:
        self.index = index
        self.redraw()
        if self.on_change is not None:
            self.on_change(index)

    @staticmethod
    def _ellipsize(text: str, max_px: int) -> str:
        """Port descriptions are long and windows are narrow."""
        font = tkfont.Font(font=ui(9))
        if max_px <= 0 or font.measure(text) <= max_px:
            return text
        while text and font.measure(text + "...") > max_px:
            text = text[:-1]
        return text + "..."

    def redraw(self) -> None:
        self.delete("all")
        self.configure(bg=self.p.bg)
        w = self.winfo_width() or int(self["width"])
        h = int(self["height"])
        edge = mix(self.p.border, self.p.accent, 0.6) if self._hover else self.p.border
        round_rect(self, 1, 1, w - 1, h - 1, 9, fill=self.p.surface_alt,
                   outline=edge, width=1)
        has_value = 0 <= self.index < len(self.values)
        label = self.values[self.index] if has_value else "no ports found"
        self.create_text(14, h / 2, anchor="w",
                         text=self._ellipsize(label, w - 42),
                         fill=self.p.text if self.values else self.p.text_dim,
                         font=ui(9))
        cx = w - 18
        self.create_polygon(cx - 5, h / 2 - 2, cx + 5, h / 2 - 2, cx, h / 2 + 4,
                            fill=self.p.text_dim, width=0)

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw()


class Card(tk.Canvas, Themed):
    """A rounded panel that hosts ordinary widgets inside `self.body`."""

    def __init__(self, master, palette: Palette, padding: int = 16,
                 radius: int = 14, autosize: bool = True) -> None:
        super().__init__(master, highlightthickness=0, bd=0, bg=palette.bg,
                         height=10)
        self.p = palette
        self.padding = padding
        self.radius = radius
        self.autosize = autosize
        self.body = tk.Frame(self, bg=palette.surface)
        self._win = self.create_window(padding, padding, anchor="nw",
                                       window=self.body)
        self.bind("<Configure>", lambda _e: self.redraw())
        # Measuring once after construction is not enough: fonts resolve and
        # children settle over the first few idle cycles, and anything the card
        # grows by afterwards would spill out past the rounded edge. Tracking
        # the body's own size keeps the two in step whatever happens.
        if autosize:
            self.body.bind("<Configure>", self._body_resized)

    def _body_resized(self, event) -> None:
        wanted = event.height + self.padding * 2
        if abs(wanted - int(self["height"])) > 1:
            self.configure(height=wanted)
            self.redraw()

    def fit(self) -> None:
        """Size the card to whatever its contents need. Call after filling it."""
        self.body.update_idletasks()
        if self.autosize:
            self.configure(height=self.body.winfo_reqheight() + self.padding * 2)
        self.redraw()

    def redraw(self) -> None:
        self.delete("bg")
        self.configure(bg=self.p.bg)
        w = self.winfo_width()
        h = int(self["height"]) if self.autosize else (self.winfo_height() or 10)
        if w <= 1:
            return
        self.itemconfig(self._win, width=w - self.padding * 2)
        if not self.autosize:
            # This card stretches with the window, so its contents follow it
            # rather than the other way round.
            self.itemconfig(self._win, height=max(1, h - self.padding * 2))
        round_rect(self, 0.5, 0.5, w - 0.5, h - 0.5, self.radius,
                   fill=self.p.surface, outline=self.p.border, width=1,
                   tags="bg")
        self.tag_lower("bg")

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.body.configure(bg=palette.surface)
        self.redraw()


class Meter(tk.Canvas, Themed):
    """The telemetry bar: full sensor span, calibrated band, live needle."""

    def __init__(self, master, palette: Palette, height: int = 38,
                 adc_max: int = 1023) -> None:
        super().__init__(master, height=height, highlightthickness=0, bd=0,
                         bg=palette.surface)
        self.p = palette
        self.adc_max = adc_max
        self.raw = 0
        self.lo = 0
        self.hi = adc_max
        self.bind("<Configure>", lambda _e: self.redraw())

    def set_values(self, raw: int, lo: int, hi: int) -> None:
        self.raw, self.lo, self.hi = raw, lo, hi
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        p = self.p
        self.configure(bg=p.surface)
        w = self.winfo_width()
        h = int(self["height"])
        if w <= 1:
            return

        def x_of(value: float) -> float:
            return 2 + (w - 4) * (value / self.adc_max)

        # track
        round_rect(self, 2, 2, w - 2, h - 2, 7, fill=p.surface_alt,
                   outline=mix(p.surface_alt, p.border, 0.8), width=1)

        # 10% graticule, the detail that makes it read as an instrument
        grid = mix(p.surface_alt, p.bg, 0.55 if p.dark else 0.35)
        for i in range(1, 10):
            x = 2 + (w - 4) * i / 10
            self.create_line(x, 5, x, h - 5, fill=grid)

        lo_x, hi_x = x_of(self.lo), x_of(self.hi)
        if hi_x > lo_x:
            round_rect(self, lo_x, 3, hi_x, h - 3, 5,
                       fill=mix(p.surface_alt, p.accent, 0.16), width=0)

        # fill up to the current reading, with a soft halo underneath
        fill_x = min(max(x_of(self.raw), lo_x), hi_x)
        if fill_x > lo_x + 1:
            round_rect(self, lo_x, 1, fill_x + 2, h - 1, 7,
                       fill=mix(p.surface if p.dark else p.surface_alt,
                                p.accent, 0.35), width=0)
            round_rect(self, lo_x, 4, fill_x, h - 4, 5, fill=p.accent, width=0)

        # calibration edges
        for x in (lo_x, hi_x):
            self.create_line(x, 2, x, h - 2, fill=mix(p.text_dim, p.text, 0.3))

        # live needle
        nx = x_of(self.raw)
        self.create_line(nx, 0, nx, h, fill=mix(p.accent, "#ffffff", 0.75),
                         width=2)

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw()
