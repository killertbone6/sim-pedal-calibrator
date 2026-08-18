"""What the app remembers between launches.

One small JSON file in the user's home directory. Anything unreadable or
missing falls back to a default rather than stopping the app - a corrupt
preferences file should never be the reason someone can't calibrate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import i18n
from . import protocol as P
from . import theme as T

CONFIG_FILE = Path.home() / ".pedalcal.json"

DEFAULT_ACCENT = T.DEFAULT_ACCENT
DEFAULT_BRIGHTNESS = T.DEFAULT_BRIGHTNESS

#: How the pedal cards are arranged on the calibration page.
LAYOUTS = ("stacked", "side")


@dataclass
class AppSettings:
    #: Background, 0 = black to 100 = white. Everything else is derived.
    bg_brightness: int = DEFAULT_BRIGHTNESS
    #: A typed-in background colour, which wins over the slider. "" = slider.
    bg_custom: str = ""
    accent: str = DEFAULT_ACCENT
    #: Interface language. `language_chosen` records that the first-run
    #: prompt has been answered, so it is only ever asked once.
    language: str = "en"
    language_chosen: bool = False
    #: "stacked" puts the pedals in a column, "side" puts them across the
    #: window with upright bars.
    layout: str = "stacked"
    on_top: bool = True
    console_open: bool = False
    #: Last port that connected successfully, reselected on the next launch.
    last_port: str = ""
    #: Keep running in the notification area when the window is closed.
    tray: bool = False
    #: Start hidden in the tray rather than showing the window.
    start_minimised: bool = False
    #: Add a per-user Run entry so the app launches at login (Windows only).
    start_with_windows: bool = False
    #: Response curve per pedal, -100 (twitchier) to +100 (gentler).
    curves: list[int] = field(default_factory=lambda: [0] * P.NUM_AXES)
    #: Travel ignored just off rest, as a percentage, per pedal.
    deadzones: list[int] = field(default_factory=lambda: [0] * P.NUM_AXES)
    #: Noise filtering per pedal.
    smoothing: list[bool] = field(default_factory=lambda: [True] * P.NUM_AXES)
    #: Show the raw sensor number instead of the percentage, per pedal.
    show_raw: list[bool] = field(default_factory=lambda: [False] * P.NUM_AXES)
    #: How often the display refreshes, and how fast the board streams.
    fps: int = 60
    #: Reserved for hardware that doesn't exist yet.
    handbrake_port: str = ""
    shifter_port: str = ""
    #: Which pedals are physically wired up. Unused ones are hidden.
    axes: list[bool] = field(
        default_factory=lambda: [True] * P.NUM_AXES)

    @staticmethod
    def defaults() -> "AppSettings":
        return AppSettings()


def load() -> AppSettings:
    settings = AppSettings()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return settings

    # Files written before the brightness slider existed carry a theme name
    # instead. Map it onto the nearest slider position so upgrading doesn't
    # throw someone back to the default background.
    if "bg_brightness" in data:
        try:
            settings.bg_brightness = max(0, min(100, int(data["bg_brightness"])))
        except (TypeError, ValueError):
            pass
    elif data.get("theme") == "light":
        settings.bg_brightness = 96

    custom = T.parse_colour(str(data.get("bg_custom", "")))
    settings.bg_custom = custom or ""

    accent = T.parse_colour(str(data.get("accent", "")))
    if accent:
        settings.accent = accent

    language = str(data.get("language", "en"))
    if language in i18n.LANGUAGE_CODES:
        settings.language = language
    settings.language_chosen = bool(
        data.get("language_chosen", settings.language_chosen))

    if data.get("layout") in LAYOUTS:
        settings.layout = data["layout"]

    settings.on_top = bool(data.get("on_top", settings.on_top))
    settings.last_port = str(data.get("last_port", ""))[:120]
    settings.tray = bool(data.get("tray", settings.tray))
    settings.start_minimised = bool(
        data.get("start_minimised", settings.start_minimised))
    settings.start_with_windows = bool(
        data.get("start_with_windows", settings.start_with_windows))

    def per_axis(key, cast, fallback):
        raw = data.get(key)
        if isinstance(raw, list) and len(raw) == P.NUM_AXES:
            try:
                return [cast(v) for v in raw]
            except (TypeError, ValueError):
                pass
        return list(fallback)

    settings.curves = per_axis(
        "curves", lambda v: max(-P.CURVE_MAX, min(P.CURVE_MAX, int(v))),
        settings.curves)
    settings.deadzones = per_axis(
        "deadzones", lambda v: max(0, min(P.DEADZONE_MAX, int(v))),
        settings.deadzones)
    settings.smoothing = per_axis("smoothing", bool, settings.smoothing)
    settings.show_raw = per_axis("show_raw", bool, settings.show_raw)

    try:
        settings.fps = max(15, min(240, int(data.get("fps", settings.fps))))
    except (TypeError, ValueError):
        settings.fps = 60

    settings.handbrake_port = str(data.get("handbrake_port", ""))[:120]
    settings.shifter_port = str(data.get("shifter_port", ""))[:120]
    settings.console_open = bool(data.get("console_open", settings.console_open))

    axes = data.get("axes")
    if isinstance(axes, list) and len(axes) == P.NUM_AXES:
        settings.axes = [bool(a) for a in axes]
        if not any(settings.axes):
            settings.axes = [True] * P.NUM_AXES  # never hide everything

    return settings


def save(settings: AppSettings) -> None:
    try:
        CONFIG_FILE.write_text(json.dumps({
            "bg_brightness": settings.bg_brightness,
            "bg_custom": settings.bg_custom,
            "accent": settings.accent,
            "language": settings.language,
            "language_chosen": settings.language_chosen,
            "layout": settings.layout,
            "on_top": settings.on_top,
            "console_open": settings.console_open,
            "last_port": settings.last_port,
            "tray": settings.tray,
            "start_minimised": settings.start_minimised,
            "start_with_windows": settings.start_with_windows,
            "curves": settings.curves,
            "deadzones": settings.deadzones,
            "smoothing": settings.smoothing,
            "show_raw": settings.show_raw,
            "fps": settings.fps,
            "handbrake_port": settings.handbrake_port,
            "shifter_port": settings.shifter_port,
            "axes": settings.axes,
        }, indent=2), encoding="utf-8")
    except Exception:
        pass  # a read-only home directory must not break the app
