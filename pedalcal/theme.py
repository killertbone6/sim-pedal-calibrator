"""Colour palettes, accent choice, and where the preference is stored."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

CONFIG_FILE = Path.home() / ".pedalcal.json"


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
    accent: str       # the one bright colour, adjusted for this background
    accent_seed: str  # the swatch the user actually picked
    on_accent: str    # type drawn on top of the accent
    danger: str

    def with_accent(self, seed: str) -> "Palette":
        """Adopt a swatch, adapting it to this background.

        The swatches are tuned for a near-black window. Dropped straight onto
        the light theme the brighter ones (lime, amber) turn into unreadable
        pastel, so they get darkened - the hue the user picked survives, the
        contrast does too. `accent_seed` remembers the original so the swatch
        row still knows which chip is selected.
        """
        if self.dark:
            return replace(self, accent=seed, accent_seed=seed,
                           on_accent="#07090c")
        return replace(self, accent=mix(seed, "#000000", 0.30),
                       accent_seed=seed, on_accent="#ffffff")


DARK = Palette(
    name="dark",
    dark=True,
    bg="#0a0c0f",
    surface="#12161b",
    surface_alt="#1a1f26",
    border="#242a32",
    text="#e8eef5",
    text_dim="#79838f",
    accent="#22d3ee",
    accent_seed="#22d3ee",
    on_accent="#07090c",
    danger="#f87171",
)

LIGHT = Palette(
    name="light",
    dark=False,
    bg="#eef1f5",
    surface="#ffffff",
    surface_alt="#e6eaf0",
    border="#d3dae2",
    text="#0d1219",
    text_dim="#606b78",
    accent="#0891b2",
    accent_seed="#22d3ee",
    on_accent="#ffffff",
    danger="#dc2626",
)

PALETTES = {"dark": DARK, "light": LIGHT}

#: Offered as swatches in the settings row.
ACCENTS = [
    ("Cyan", "#22d3ee"),
    ("Lime", "#a3e635"),
    ("Amber", "#fbbf24"),
    ("Orange", "#fb7c3c"),
    ("Magenta", "#e879f9"),
    ("Blue", "#60a5fa"),
]


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


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def load_palette() -> Palette:
    """The user's saved theme, or the dark default."""
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        base = PALETTES.get(str(data.get("theme", "dark")), DARK)
        accent = str(data.get("accent", base.accent_seed))
        if not (accent.startswith("#") and len(accent) == 7):
            return base
        return base.with_accent(accent)
    except Exception:
        return DARK


def save_palette(palette: Palette) -> None:
    try:
        CONFIG_FILE.write_text(
            json.dumps({"theme": palette.name, "accent": palette.accent_seed}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass  # a read-only home directory must not break the app
