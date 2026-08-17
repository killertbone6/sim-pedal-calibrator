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
            "axes": settings.axes,
        }, indent=2), encoding="utf-8")
    except Exception:
        pass  # a read-only home directory must not break the app
