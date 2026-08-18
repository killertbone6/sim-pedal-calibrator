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

try:  # Pillow gives us antialiasing, which a Tk canvas simply doesn't have.
    from PIL import Image, ImageDraw, ImageTk

    _PIL = True
except Exception:  # noqa: BLE001 - drawing falls back to plain canvas lines
    _PIL = False

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


class Tabs(tk.Canvas, Themed):
    """A segmented control: one rounded track, the active tab filled."""

    def __init__(self, master, labels: list[str], palette: Palette,
                 on_change=None, height: int = 36) -> None:
        self.p = palette
        self.labels = [t.upper() for t in labels]
        self.on_change = on_change
        self.active = 0
        self._hover = -1
        self._font = ui(9, "bold")
        font = tkfont.Font(font=self._font)
        seg = max(font.measure(spaced(t)) for t in self.labels) + 44
        super().__init__(master, width=seg * len(self.labels), height=height,
                         highlightthickness=0, bd=0, bg=palette.bg)
        self.seg = seg
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e: self._set_hover(-1))
        self.configure(cursor="hand2")
        self.redraw()

    def _index_at(self, x: float) -> int:
        return max(0, min(len(self.labels) - 1, int(x // self.seg)))

    def _motion(self, event) -> None:
        self._set_hover(self._index_at(event.x))

    def _set_hover(self, index: int) -> None:
        if index != self._hover:
            self._hover = index
            self.redraw()

    def _click(self, event) -> None:
        self.select(self._index_at(event.x))

    def select(self, index: int) -> None:
        if index == self.active:
            return
        self.active = index
        self.redraw()
        if self.on_change is not None:
            self.on_change(index)

    def redraw(self) -> None:
        self.delete("all")
        p = self.p
        self.configure(bg=p.bg)
        h = int(self["height"])
        w = self.seg * len(self.labels)
        round_rect(self, 1, 1, w - 1, h - 1, 10, fill=p.surface_alt,
                   outline=p.border, width=1)
        for i, label in enumerate(self.labels):
            x0 = i * self.seg
            if i == self.active:
                round_rect(self, x0 + 3, 3, x0 + self.seg - 3, h - 3, 8,
                           fill=p.accent, width=0)
                colour = p.on_accent
            elif i == self._hover:
                colour = p.accent
            else:
                colour = p.text_dim
            self.create_text(x0 + self.seg / 2, h / 2 + 1, text=spaced(label),
                             fill=colour, font=self._font)

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw()


class Toggle(tk.Canvas, Themed):
    """An on/off switch with a label."""

    TRACK_W = 38

    def __init__(self, master, text: str, value: bool, command, palette: Palette,
                 width: int | None = None, height: int = 26) -> None:
        label = spaced(text.upper())
        if width is None:
            width = self.TRACK_W + 18 + tkfont.Font(font=ui(8, "bold")).measure(label)
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, bg=palette.surface)
        self.p = palette
        self.text = text.upper()
        self.value = value
        self.command = command
        self._hover = False
        self.bind("<Button-1>", lambda _e: self.toggle())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.configure(cursor="hand2")
        self.redraw()

    def _set_hover(self, hover: bool) -> None:
        self._hover = hover
        self.redraw()

    def toggle(self) -> None:
        self.set(not self.value)
        if self.command is not None:
            self.command(self.value)

    def set(self, value: bool) -> None:
        self.value = value
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        p = self.p
        h = int(self["height"])
        track_w, track_h = self.TRACK_W, 20
        y0 = (h - track_h) / 2
        fill = p.accent if self.value else p.surface_alt
        edge = p.accent if self.value else (
            mix(p.border, p.accent, 0.6) if self._hover else p.border)
        round_rect(self, 1, y0, 1 + track_w, y0 + track_h, track_h / 2,
                   fill=fill, outline=edge, width=1)
        knob_r = track_h - 8
        knob_x = 1 + track_w - knob_r - 4 if self.value else 5
        self.create_oval(knob_x, y0 + 4, knob_x + knob_r, y0 + 4 + knob_r,
                         fill=p.on_accent if self.value else p.text_dim, width=0)
        self.create_text(track_w + 14, h / 2 + 1, anchor="w",
                         text=spaced(self.text), font=ui(8, "bold"),
                         fill=p.text if self.value else p.text_dim)

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw()


class Disclosure(tk.Canvas, Themed):
    """A clickable "> CONSOLE" header that shows and hides a panel."""

    def __init__(self, master, text: str, open_: bool, command,
                 palette: Palette, height: int = 24) -> None:
        super().__init__(master, height=height, highlightthickness=0, bd=0,
                         bg=palette.bg)
        self.p = palette
        self.text = text.upper()
        self.open = open_
        self.command = command
        self._hover = False
        self.bind("<Button-1>", lambda _e: self.toggle())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<Configure>", lambda _e: self.redraw())
        self.configure(cursor="hand2")
        self.redraw()

    def _set_hover(self, hover: bool) -> None:
        self._hover = hover
        self.redraw()

    def toggle(self) -> None:
        self.open = not self.open
        self.redraw()
        if self.command is not None:
            self.command(self.open)

    def redraw(self) -> None:
        self.delete("all")
        p = self.p
        self.configure(bg=p.bg)
        h = int(self["height"])
        colour = p.accent if self._hover else p.text_dim
        cy = h / 2
        if self.open:
            self.create_polygon(4, cy - 2, 14, cy - 2, 9, cy + 4,
                                fill=colour, width=0)
        else:
            self.create_polygon(6, cy - 5, 12, cy, 6, cy + 5,
                                fill=colour, width=0)
        self.create_text(22, cy + 1, anchor="w", text=spaced(self.text),
                         font=ui(8, "bold"), fill=colour)

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw()


class ScrollArea(tk.Canvas, Themed):
    """A vertically scrolling container with a slim drawn scrollbar.

    The settings page is taller than a small laptop screen, and Tk will simply
    refuse to map whatever doesn't fit rather than clipping it - so the bottom
    cards would silently vanish. Put content in `self.body`.
    """

    BAR_W = 4

    def __init__(self, master, palette: Palette) -> None:
        super().__init__(master, highlightthickness=0, bd=0, bg=palette.bg)
        self.p = palette
        self.body = tk.Frame(self, bg=palette.bg)
        self._win = self.create_window(0, 0, anchor="nw", window=self.body)
        self._thumb = None
        self.bind("<Configure>", self._on_resize)
        self.body.bind("<Configure>", self._on_body)
        # Wheel events go to the widget under the pointer, and X11 sends them
        # as buttons 4/5 where Windows and macOS send <MouseWheel>. Binding
        # globally and then checking where the pointer actually is beats
        # tracking Enter/Leave: moving onto a child widget fires Leave on its
        # parent, so an Enter/Leave scheme stops scrolling the moment the
        # pointer crosses onto one of the cards - which is most of the area.
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(sequence, self._wheel, add="+")

    # -- geometry --------------------------------------------------------

    def _on_resize(self, event) -> None:
        self.itemconfig(self._win, width=event.width - self.BAR_W - 4)
        self._sync()

    def _on_body(self, _event=None) -> None:
        self.configure(scrollregion=(0, 0, 0, self.body.winfo_reqheight()))
        self._sync()

    def _content_h(self) -> int:
        return self.body.winfo_reqheight()

    def _sync(self) -> None:
        """Redraw the thumb, and snap back if content shrank below the view."""
        view_h, content_h = self.winfo_height(), self._content_h()
        if content_h <= view_h:
            self.yview_moveto(0)
        if self._thumb is not None:
            self.delete(self._thumb)
            self._thumb = None
        if content_h <= view_h or view_h <= 1:
            return
        top, bottom = self.yview()
        x = self.winfo_width() - self.BAR_W - 1
        y0 = self.canvasy(0) + top * view_h
        y1 = self.canvasy(0) + bottom * view_h
        self._thumb = round_rect(self, x, y0 + 2, x + self.BAR_W, y1 - 2,
                                 self.BAR_W / 2,
                                 fill=mix(self.p.border, self.p.text_dim, 0.5),
                                 width=0)

    # -- wheel -----------------------------------------------------------

    def _pointer_inside(self, event) -> bool:
        """True when the event happened on this area or anything inside it."""
        node = event.widget
        if isinstance(node, str):
            try:
                node = self.nametowidget(node)
            except Exception:
                return False
        while node is not None:
            if node is self:
                return True
            node = getattr(node, "master", None)
        return False

    def _wheel(self, event) -> None:
        if not self.winfo_ismapped() or not self._pointer_inside(event):
            return
        if self._content_h() <= self.winfo_height():
            return
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        self.yview_scroll(step * 2, "units")
        self._sync()

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.configure(bg=palette.bg)
        self.body.configure(bg=palette.bg)
        self._sync()


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
    """The pedal bar: calibrated output from 0 to 100%.

    It deliberately shows output rather than where the sensor sits in its raw
    range. Setting the rest point therefore drops the bar to empty and setting
    full sends it to the end, which is how every other pedal tool behaves and
    what makes the calibration feel like it did something.
    """

    def __init__(self, master, palette: Palette, height: int = 38) -> None:
        super().__init__(master, height=height, highlightthickness=0, bd=0,
                         bg=palette.surface)
        self.p = palette
        self.output = 0.0
        self.bind("<Configure>", lambda _e: self.redraw())

    def set_output(self, fraction: float) -> None:
        self.output = max(0.0, min(1.0, fraction))
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        p = self.p
        self.configure(bg=p.surface)
        w = self.winfo_width()
        h = int(self["height"])
        if w <= 1:
            return

        round_rect(self, 2, 2, w - 2, h - 2, 7, fill=p.surface_alt,
                   outline=mix(p.surface_alt, p.border, 0.8), width=1)

        span = w - 8
        end = 4 + span * self.output

        # Graticule first, so the fill covers it. Drawn over the top it reads
        # as heavy dividers chopping the bar into segments.
        grid = mix(p.surface_alt, p.bg, 0.55 if p.dark else 0.35)
        for i in range(1, 10):
            x = 4 + span * i / 10
            self.create_line(x, 6, x, h - 6, fill=grid)

        if self.output > 0.001:
            round_rect(self, 2, 1, end + 2, h - 1, 7,
                       fill=mix(p.surface if p.dark else p.surface_alt,
                                p.accent, 0.35), width=0)
            round_rect(self, 4, 4, end, h - 4, 5, fill=p.accent, width=0)
            self.create_line(end, 3, end, h - 3,
                             fill=mix(p.accent, "#ffffff", 0.7), width=2)

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw()


class Slider(tk.Canvas, Themed):
    """A draggable value slider. Bipolar ranges get a centre notch."""

    def __init__(self, master, palette: Palette, minimum: int = -100,
                 maximum: int = 100, value: int = 0, command=None,
                 width: int = 210, height: int = 26) -> None:
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, bg=palette.surface)
        self.p = palette
        self.minimum = minimum
        self.maximum = maximum
        self.value = value
        self.command = command          # fired continuously while dragging
        self.on_release = None          # fired once, when the drag finishes
        self._hover = False
        self._drag = False
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<Configure>", lambda _e: self.redraw())
        self.configure(cursor="hand2")
        self.redraw()

    # -- geometry --------------------------------------------------------

    def _track(self) -> tuple[float, float]:
        return 10.0, max(11.0, (self.winfo_width() or int(self["width"])) - 10.0)

    def _x_of(self, value: float) -> float:
        x0, x1 = self._track()
        span = self.maximum - self.minimum or 1
        return x0 + (x1 - x0) * (value - self.minimum) / span

    def _value_at(self, x: float) -> int:
        x0, x1 = self._track()
        span = self.maximum - self.minimum
        ratio = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
        return int(round(self.minimum + max(0.0, min(1.0, ratio)) * span))

    # -- interaction -----------------------------------------------------

    def _set_hover(self, hover: bool) -> None:
        self._hover = hover
        self.redraw()

    def _press(self, event) -> None:
        self._drag = True
        self._apply(self._value_at(event.x))

    def _move(self, event) -> None:
        if self._drag:
            self._apply(self._value_at(event.x))

    def _release(self, _event=None) -> None:
        was = self._drag
        self._drag = False
        self.redraw()
        if was and self.on_release is not None:
            self.on_release(self.value)

    def _apply(self, value: int) -> None:
        value = max(self.minimum, min(self.maximum, value))
        if value != self.value:
            self.value = value
            if self.command is not None:
                self.command(value)
        self.redraw()

    def set(self, value: int, notify: bool = False) -> None:
        self.value = max(self.minimum, min(self.maximum, int(value)))
        self.redraw()
        if notify and self.command is not None:
            self.command(self.value)

    def get(self) -> int:
        return self.value

    # -- painting --------------------------------------------------------

    def redraw(self) -> None:
        self.delete("all")
        p = self.p
        self.configure(bg=self.master.cget("bg"))
        h = int(self["height"])
        x0, x1 = self._track()
        cy = h / 2

        round_rect(self, x0, cy - 3, x1, cy + 3, 3,
                   fill=p.surface_alt, outline=p.border, width=1)

        # A bipolar slider needs a visible home position.
        if self.minimum < 0 < self.maximum:
            zero = self._x_of(0)
            self.create_line(zero, cy - 8, zero, cy + 8,
                             fill=mix(p.border, p.text_dim, 0.6))
            start, end = sorted((zero, self._x_of(self.value)))
            if end - start > 1:
                round_rect(self, start, cy - 3, end, cy + 3, 3,
                           fill=p.accent, width=0)
        else:
            round_rect(self, x0, cy - 3, self._x_of(self.value), cy + 3, 3,
                       fill=p.accent, width=0)

        kx = self._x_of(self.value)
        radius = 9 if (self._hover or self._drag) else 8
        self.create_oval(kx - radius, cy - radius, kx + radius, cy + radius,
                         fill=p.accent if self._drag else p.text,
                         outline=p.bg, width=2)

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw()


class CurveGraph(tk.Canvas, Themed):
    """Input against output, with the live pedal position marked on it.

    Tk draws lines with no antialiasing whatsoever, so a diagonal comes out as
    a visible staircase - the look of a graphing calculator. Where Pillow is
    available the curve is instead rendered into an image at several times the
    final size and scaled down, which is a cheap and very effective way to get
    smooth edges. It's only redrawn when the curve or the widget size changes;
    the live position marker stays as canvas items on top, so the per-frame
    cost is unchanged.
    """

    SUPERSAMPLE = 4

    def __init__(self, master, palette: Palette, height: int = 132) -> None:
        super().__init__(master, height=height, highlightthickness=0, bd=0,
                         bg=palette.surface)
        self.p = palette
        self.points: list[tuple[float, float]] = [(0.0, 0.0), (1.0, 1.0)]
        self.position: float | None = None
        self._photo = None          # a reference has to outlive the call
        self._image_id = None
        self._signature = None      # what the current image was drawn for
        self.bind("<Configure>", lambda _e: self.redraw(force=True))

    def set_curve(self, points: list[tuple[float, float]]) -> None:
        """Points are (input, output) pairs, both 0.0-1.0."""
        self.points = points
        self.redraw(force=True)

    def set_position(self, position: float | None) -> None:
        self.position = position
        self.redraw()

    # -- geometry --------------------------------------------------------

    def _plot_area(self, w: int, h: int) -> tuple[float, float, float, float]:
        pad = 8
        return pad, pad, w - pad, h - pad

    def redraw(self, force: bool = False) -> None:
        w = self.winfo_width()
        h = int(self["height"])
        if w <= 1:
            return
        self.configure(bg=self.p.surface)

        signature = (w, h, self.p.accent, self.p.surface_alt, tuple(self.points))
        if force or signature != self._signature:
            self._signature = signature
            self._render_background(w, h)

        self.delete("overlay")
        if self.position is None:
            return

        x0, y0, x1, y1 = self._plot_area(w, h)
        value_in = max(0.0, min(1.0, self.position))
        value_out = self._output_at(value_in)
        px = x0 + (x1 - x0) * value_in
        py = y1 - (y1 - y0) * value_out
        guide = mix(self.p.accent, self.p.surface_alt, 0.5)
        self.create_line(px, y1 - 2, px, py, fill=guide, tags="overlay")
        self.create_line(x0 + 2, py, px, py, fill=guide, tags="overlay")
        self.create_oval(px - 4, py - 4, px + 4, py + 4, width=0,
                         fill=mix(self.p.accent, "#ffffff", 0.5), tags="overlay")

    # -- the curve itself -------------------------------------------------

    def _render_background(self, w: int, h: int) -> None:
        if _PIL:
            try:
                self._render_with_pillow(w, h)
                return
            except Exception:  # noqa: BLE001 - fall back rather than fail
                pass
        self._render_with_canvas(w, h)

    def _render_with_pillow(self, w: int, h: int) -> None:
        p = self.p
        scale = self.SUPERSAMPLE
        image = Image.new("RGB", (w * scale, h * scale), p.surface)
        draw = ImageDraw.Draw(image)
        x0, y0, x1, y1 = (v * scale for v in self._plot_area(w, h))

        radius = 8 * scale
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                               fill=p.surface_alt,
                               outline=mix(p.surface_alt, p.border, 0.8),
                               width=scale)

        grid = mix(p.surface_alt, p.bg, 0.55 if p.dark else 0.35)
        for i in range(1, 4):
            gx = x0 + (x1 - x0) * i / 4
            gy = y1 - (y1 - y0) * i / 4
            draw.line([gx, y0 + 2 * scale, gx, y1 - 2 * scale], fill=grid,
                      width=scale)
            draw.line([x0 + 2 * scale, gy, x1 - 2 * scale, gy], fill=grid,
                      width=scale)

        # the straight line, so any curve reads as a departure from it
        for i in range(0, 40, 2):
            a, b = i / 40, min(1.0, (i + 1) / 40)
            draw.line([x0 + (x1 - x0) * a, y1 - (y1 - y0) * a,
                       x0 + (x1 - x0) * b, y1 - (y1 - y0) * b],
                      fill=grid, width=scale)

        flat = [(x0 + (x1 - x0) * vx, y1 - (y1 - y0) * vy)
                for vx, vy in self.points]
        if len(flat) >= 2:
            draw.line(flat, fill=p.accent, width=2 * scale, joint="curve")

        image = image.resize((w, h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(image)
        if self._image_id is None:
            self._image_id = self.create_image(0, 0, anchor="nw",
                                               image=self._photo)
        else:
            self.itemconfig(self._image_id, image=self._photo)
        self.tag_lower(self._image_id)

    def _render_with_canvas(self, w: int, h: int) -> None:
        self.delete("bg")
        p = self.p
        x0, y0, x1, y1 = self._plot_area(w, h)
        round_rect(self, x0, y0, x1, y1, 8, fill=p.surface_alt,
                   outline=mix(p.surface_alt, p.border, 0.8), width=1,
                   tags="bg")
        grid = mix(p.surface_alt, p.bg, 0.55 if p.dark else 0.35)
        for i in range(1, 4):
            self.create_line(x0 + (x1 - x0) * i / 4, y0 + 2,
                             x0 + (x1 - x0) * i / 4, y1 - 2, fill=grid,
                             tags="bg")
            self.create_line(x0 + 2, y1 - (y1 - y0) * i / 4, x1 - 2,
                             y1 - (y1 - y0) * i / 4, fill=grid, tags="bg")
        self.create_line(x0, y1, x1, y0, fill=grid, dash=(3, 3), tags="bg")
        flat = []
        for vx, vy in self.points:
            flat.extend((x0 + (x1 - x0) * vx, y1 - (y1 - y0) * vy))
        if len(flat) >= 4:
            self.create_line(*flat, fill=p.accent, width=2, capstyle="round",
                             tags="bg")
        self.tag_lower("bg")

    def _output_at(self, value_in: float) -> float:
        """Linear search is fine - the curve is a couple of dozen points."""
        previous = self.points[0]
        for point in self.points[1:]:
            if point[0] >= value_in:
                span = point[0] - previous[0]
                if span <= 0:
                    return point[1]
                t = (value_in - previous[0]) / span
                return previous[1] + (point[1] - previous[1]) * t
            previous = point
        return previous[1]

    def apply_theme(self, palette: Palette) -> None:
        self.p = palette
        self.redraw(force=True)
