"""What the app remembers between launches.

One small JSON file in the user's home directory. Anything unreadable or
missing falls back to a default rather than stopping the app - a corrupt
preferences file should never be the reason someone can't calibrate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import protocol as P

CONFIG_FILE = Path.home() / ".pedalcal.json"

DEFAULT_THEME = "dark"
DEFAULT_ACCENT = "#22d3ee"


@dataclass
class AppSettings:
    theme: str = DEFAULT_THEME
    accent: str = DEFAULT_ACCENT
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
    #: Show the raw sensor number next to the percentage, per pedal.
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

    if data.get("theme") in ("dark", "light"):
        settings.theme = data["theme"]

    accent = str(data.get("accent", ""))
    if accent.startswith("#") and len(accent) == 7:
        settings.accent = accent

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
            "theme": settings.theme,
            "accent": settings.accent,
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
