"""Colours.

There is no longer a dark theme and a light theme. There is one background
colour - picked with a slider that runs from black to white, or typed in as a
colour code - and every other colour in the app is derived from it.

That turned out to be simpler *and* better: a two-way switch can only offer
two of the shades people actually want, and any custom background needs this
machinery anyway. Deriving everything also means the awkward middle of the
range works. A mid-grey background is where a hand-picked palette falls apart,
because whichever text colour was chosen for it is now wrong; here the text,
the accent and the status colours are each fitted to a contrast target against
the background they will actually be drawn on.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The bottom of the brightness slider. Not pure black: a trace of blue reads
#: as "screen off" rather than "hole in the monitor", and it gives the cards
#: something to sit against.
BG_DARKEST = "#04060a"
BG_LIGHTEST = "#ffffff"

#: Where the slider starts on a fresh install - the near-black the app has
#: always used.
DEFAULT_BRIGHTNESS = 18
DEFAULT_ACCENT = "#22d3ee"

#: Minimum contrast ratio the accent and status colours are held to against
#: the surface they sit on. 3:1 is the WCAG floor for large text and UI
#: components, and it is what stops lime disappearing into a white background.
MIN_CONTRAST = 3.0
TEXT_CONTRAST = 11.0

#: The background luminance at which black and white type read equally well:
#: (L + 0.05)/0.05 == 1.05/(L + 0.05). Either side of it, one of the two is
#: clearly better; at it, both manage only 4.58:1, and no colour whatsoever
#: does better. That is the ceiling on a mid-grey background, and the reason
#: the brightness slider defaults near the dark end.
EQUAL_CONTRAST = 0.1791

#: Offered as swatches in the settings row.
ACCENTS = [
    ("Cyan", "#22d3ee"),
    ("Teal", "#2dd4bf"),
    ("Green", "#4ade80"),
    ("Lime", "#a3e635"),
    ("Amber", "#fbbf24"),
    ("Orange", "#fb7c3c"),
    ("Red", "#f87171"),
    ("Pink", "#f472b6"),
    ("Magenta", "#e879f9"),
    ("Violet", "#a78bfa"),
    ("Blue", "#60a5fa"),
    ("Ice", "#cbd5e1"),
]

INK_LIGHT = "#f3f7fb"     # type on a dark background
INK_DARK = "#0b0f14"      # type on a light background

SEED_OK = "#22c55e"
SEED_OFFLINE = "#ef4444"
SEED_DANGER = "#f87171"


@dataclass(frozen=True)
class Palette:
    name: str
    dark: bool
    bg: str           # window background
    surface: str      # card background
    surface_alt: str  # inset areas: meter tracks, entry fields
    border: str       # hairlines
    text: str         # primary type
    text_dim: str     # labels, secondary type
    accent: str       # the one bright colour, fitted to this background
    accent_seed: str  # the swatch the user actually picked
    on_accent: str    # type drawn on top of the accent
    danger: str
    ok: str           # connected. Deliberately not the accent: red/green is
    offline: str      # a convention worth more than palette consistency.


# --------------------------------------------------------------------------
# Colour maths
# --------------------------------------------------------------------------


def _parse(colour: str) -> tuple[int, int, int]:
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def mix(a: str, b: str, t: float) -> str:
    """Blend two hex colours. t=0 gives a, t=1 gives b.

    Tk has no alpha channel, so translucency is faked by blending against
    whatever is behind - that's what makes the dim range bands and the glow
    around the meter fill possible.
    """
    t = max(0.0, min(1.0, t))
    ar, ag, ab = _parse(a)
    br, bg_, bb = _parse(b)
    return "#%02x%02x%02x" % (
        round(ar + (br - ar) * t),
        round(ag + (bg_ - ag) * t),
        round(ab + (bb - ab) * t),
    )


def luminance(colour: str) -> float:
    """Relative luminance, the way contrast ratios define it.

    The gamma step matters: averaging the raw bytes says #0000ff and #ffff00
    are equally bright, and picking text colours on that basis puts white type
    on yellow.
    """
    channels = []
    for value in _parse(colour):
        c = value / 255
        channels.append(c / 12.92 if c <= 0.04045
                        else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def fit_contrast(seed: str, against: str, target: float = MIN_CONTRAST) -> str:
    """Darken or lighten `seed` until it is legible on `against`.

    Two details matter more than they look.

    The direction is decided at the luminance where black and white contrast
    equally (0.179), not at the halfway point of the scale. Judge it by eye at
    0.35 and a light-grey background sends the colour towards white, which
    makes it *less* readable, not more.

    And the best candidate is kept rather than the last one. No colour can
    reach 4.5:1 against a mid-grey background - that is a property of the
    contrast formula, not of this palette - so a loop that runs out of steps
    has to hand back the closest it got, or it hands back the worst.
    """
    best, best_ratio = seed, contrast(seed, against)
    if best_ratio >= target:
        return seed
    toward = "#000000" if luminance(against) > EQUAL_CONTRAST else "#ffffff"
    for step in range(1, 33):
        candidate = mix(seed, toward, step / 32)
        ratio = contrast(candidate, against)
        if ratio >= target:
            return candidate
        if ratio > best_ratio:
            best, best_ratio = candidate, ratio
    return best


def brightness_bg(percent: float) -> str:
    """Slider position (0 = black, 100 = white) to a background colour.

    The ramp is raised to a power rather than being linear. Perceived
    brightness is not proportional to the byte value, so a linear slider spends
    four fifths of its travel in shades nobody would choose and crams every
    usable dark shade into the first centimetre.
    """
    t = max(0.0, min(1.0, percent / 100.0)) ** 2.2
    return mix(BG_DARKEST, BG_LIGHTEST, t)


def bg_brightness_of(colour: str) -> int:
    """The inverse of `brightness_bg`, for putting the slider where a typed-in
    colour would sit."""
    best, best_error = 0, None
    for percent in range(0, 101):
        error = abs(luminance(brightness_bg(percent)) - luminance(colour))
        if best_error is None or error < best_error:
            best, best_error = percent, error
    return best


# --------------------------------------------------------------------------
# Building a palette
# --------------------------------------------------------------------------


def best_ink(against: str) -> str:
    """Light type or dark type, whichever is easier to read on `against`.

    Deciding this by measurement rather than by a brightness threshold is what
    makes the top half of the slider usable. A fixed cut-off put white type on
    a light-grey background around 78% brightness at under 3:1, where black
    type on the same background reads at 7:1 - a threshold cannot know that,
    and the contrast formula can.
    """
    return (INK_LIGHT if contrast(INK_LIGHT, against) >= contrast(INK_DARK, against)
            else INK_DARK)


def palette_from_bg(bg: str, accent_seed: str) -> Palette:
    """Derive a complete palette from one background colour."""
    dark = best_ink(bg) is INK_LIGHT
    lift = BG_LIGHTEST if dark else "#000000"

    surface = mix(bg, lift, 0.055)
    surface_alt = mix(bg, lift, 0.115)

    # Cards are nudged towards the type colour, which costs a little contrast,
    # so the choice is confirmed against the surface the type actually lands on
    # rather than against the window behind it.
    ink = best_ink(surface)
    text = fit_contrast(ink, surface, TEXT_CONTRAST)
    text_dim = fit_contrast(mix(text, surface, 0.45), surface, 3.6)
    border = mix(surface, text, 0.16)

    accent = fit_contrast(accent_seed, surface)
    on_accent = (INK_DARK if contrast(INK_DARK, accent)
                 >= contrast(INK_LIGHT, accent) else INK_LIGHT)

    return Palette(
        name="custom",
        dark=dark,
        bg=bg,
        surface=surface,
        surface_alt=surface_alt,
        border=border,
        text=text,
        text_dim=text_dim,
        accent=accent,
        accent_seed=accent_seed,
        on_accent=on_accent,
        danger=fit_contrast(SEED_DANGER, surface),
        ok=fit_contrast(SEED_OK, surface),
        offline=fit_contrast(SEED_OFFLINE, surface),
    )


def palette_for(brightness: int, accent_seed: str,
                custom_bg: str = "") -> Palette:
    """Build the palette the app should be wearing, from saved settings."""
    bg = parse_colour(custom_bg) if custom_bg else None
    return palette_from_bg(bg or brightness_bg(brightness), accent_seed)


def parse_colour(text: str) -> str | None:
    """Accept the ways people actually write a colour, or return None.

    Handles "#22d3ee", "22d3ee", "34,211,238", "34 211 238" and
    "rgb(34, 211, 238)" - so a value copied out of a colour picker, CSS or a
    paint program all work without the user having to convert anything.
    """
    raw = text.strip().lower()
    if not raw:
        return None

    if raw.startswith("rgb"):
        raw = raw[3:].strip().lstrip("(").rstrip(")")

    hexish = raw.lstrip("#")
    if len(hexish) == 6 and all(c in "0123456789abcdef" for c in hexish):
        return "#" + hexish
    if len(hexish) == 3 and all(c in "0123456789abcdef" for c in hexish):
        return "#" + "".join(c * 2 for c in hexish)

    parts = [p for p in raw.replace(",", " ").split() if p]
    if len(parts) == 3:
        try:
            values = [int(p) for p in parts]
        except ValueError:
            return None
        if all(0 <= v <= 255 for v in values):
            return "#%02x%02x%02x" % tuple(values)
    return None
